"""AI seller agent powered by Groq.

Workflow per turn:
  1. Python tools load the seller report and pick the next topic to investigate.
  2. The LLM gets the report + investigation state and returns a JSON reply.
  3. Python validates the JSON and updates the conversation state.
"""

import json
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv
from groq import (
    APIConnectionError,
    APIStatusError,
    AuthenticationError,
    Groq,
    NotFoundError,
    RateLimitError,
)

from backend.analysis.seller_analysis import format_inr, generate_report

load_dotenv()

PRIMARY_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
FALLBACK_MODEL = os.getenv("GROQ_FALLBACK_MODEL", "openai/gpt-oss-20b")

INVESTIGATION_TOPICS = ["stockouts", "cancellations", "visibility"]
TOPIC_GUIDE = {
    "stockouts": "Are any out-of-stock products best-sellers? How long have they been out of stock, and why?",
    "cancellations": "What are the main reasons for cancellations (stock or packing delays on the seller side, customer-initiated, courier or return issues)?",
    "visibility": "Have product views, ads, promotions, pricing or listing quality changed? (We have no traffic data, so ask the seller.)",
}
MAX_HISTORY_MESSAGES = 16
MAX_INVALID_JSON_RETRIES = 1

SYSTEM_RULES = """You are the Snapdeal Virtual Key Account Manager (KAM): an AI assistant that proactively helps Snapdeal sellers whose sales have declined. You are speaking with the seller by VOICE, so write the way people talk.

STYLE
- Professional, warm and empathetic. Plain spoken English.
- Keep each reply to 2-3 short sentences (about 60 words max), except when giving recommendations (about 110 words max).
- No markdown, bullets, emojis or numbered lists. Say "first, second, third" inside sentences instead.
- Say money in spoken form, for example "1.35 lakh rupees", not with symbols.
- Ask only ONE question per reply. Never repeat a question the seller has already answered.

HONESTY RULES
- Use ONLY the numbers in the SELLER DATA below. Never invent metrics, product names, customer feedback or traffic data.
- The data is sample data. If asked, say so.
- Stockouts and cancellations are POSSIBLE contributing factors. Never say they definitely caused the decline. Use phrases like "could be", "may be contributing", "let's check".
- You have no data on traffic, conversion, ratings or specific products. Ask the seller if you need it.
- You cannot change anything in Snapdeal systems yourself. Never say something has been done or fixed. You can only suggest actions and note next steps.

CONVERSATION FLOW
1. The first time the seller mentions a sales problem, state the sales decline (exact percentage) and the stockout increase (from X to Y), then ask whether any out-of-stock products are among their best-sellers. Do not recommend anything yet.
2. Investigate before recommending. Follow the NEXT TOPIC in the investigation state, one question at a time. First respond to what the seller just said (acknowledge it, connect it to the data), then ask your next question.
3. Once the key topics are covered (or the seller clearly asks for advice), give 2-3 practical recommendations based on the data and what the seller told you, then ask which ones they are willing to commit to.
4. Record an agreed action only when the seller clearly agrees to it. After they agree, briefly confirm the next steps and ask if there is anything else. When the seller says they are done, close warmly and set conversation_complete to true.
5. If the seller says something off-topic or unclear, answer briefly and steer back, or ask them to clarify.

OUTPUT FORMAT
Respond with a single JSON object and nothing else:
{"reply": "<what you say aloud>", "topic_covered": "<stockouts, cancellations, visibility, or null>", "seller_facts": ["<new facts the seller stated in their latest message>"], "recommendations_given": <true only if THIS reply contains recommendations>, "agreed_actions": ["<actions the seller agreed to in their latest message>"], "conversation_complete": <true only when the conversation is finished>}
- topic_covered: the topic the seller's latest message answered, otherwise null.
- seller_facts and agreed_actions: only NEW items from the seller's latest message; use [] if none. Never put your own suggestions in seller_facts.
"""


# ---------- Data classes ----------

@dataclass
class AgentReply:
    ok: bool
    text: str
    # empty_message | missing_api_key | invalid_api_key | rate_limit |
    # connection | api_error | invalid_response
    error_type: str | None = None


@dataclass
class ConversationState:
    covered_topics: set = field(default_factory=set)
    seller_facts: list = field(default_factory=list)
    agreed_actions: list = field(default_factory=list)
    recommendations_given: bool = False
    complete: bool = False


# ---------- Tools (plain Python functions) ----------

def tool_get_report() -> dict:
    """Tool: seller performance report. All math is done in Python."""
    return generate_report()


def tool_next_topic(covered: set) -> str | None:
    """Tool: next investigation topic not yet covered."""
    for topic in INVESTIGATION_TOPICS:
        if topic not in covered:
            return topic
    return None


# ---------- Prompt + parsing helpers ----------

def build_system_prompt(report: dict, state: ConversationState) -> str:
    seller, last, this, ch = (
        report["seller"], report["last_month"], report["this_month"], report["changes"],
    )
    signals = "\n".join(f"- {s['finding']}" for s in report["warning_signals"])
    covered = ", ".join(sorted(state.covered_topics)) or "none yet"
    facts = "\n".join(f"- {f}" for f in state.seller_facts) or "- none yet"
    actions = "\n".join(f"- {a}" for a in state.agreed_actions) or "- none yet"

    next_topic = tool_next_topic(state.covered_topics)
    if next_topic:
        next_line = f"{next_topic}: {TOPIC_GUIDE[next_topic]}"
    else:
        next_line = "none left. Enough information gathered; move to recommendations (or wrap up if already given)."

    data_block = f"""
SELLER DATA ({report['data_disclaimer']})
Seller: {seller['name']} | Business: {seller['business_name']} | Category: {seller['category']}
Last month: sales {format_inr(last['sales'])}, orders {last['orders']}, cancellation rate {last['cancellation_rate']}%, average selling price {format_inr(last['avg_selling_price'])}, out-of-stock products {last['out_of_stock_products']}
This month: sales {format_inr(this['sales'])}, orders {this['orders']}, cancellation rate {this['cancellation_rate']}%, average selling price {format_inr(this['avg_selling_price'])}, out-of-stock products {this['out_of_stock_products']}
Calculated changes: sales {ch['sales_change_pct']}%, orders {ch['orders_change_pct']}%, average price change {ch['avg_selling_price_change_pct']}%, cancellation rate {ch['cancellation_change_pp']:+} percentage points, out-of-stock products {ch['out_of_stock_change']:+}
Warning signals (possible factors to investigate, NOT proven causes):
{signals}

INVESTIGATION STATE
Topics already covered: {covered}
NEXT TOPIC to investigate: {next_line}
Facts the seller has told you:
{facts}
Recommendations already given: {'yes' if state.recommendations_given else 'no'}
Actions the seller has agreed to:
{actions}
"""
    return SYSTEM_RULES + data_block


def parse_agent_json(raw: str) -> dict | None:
    """Return the parsed dict if it is valid and has a non-empty reply, else None."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    reply = data.get("reply")
    if not isinstance(reply, str) or not reply.strip():
        return None
    return data


# ---------- The agent ----------

class SellerAgent:
    def __init__(self, client=None):
        self.report = tool_get_report()
        self.state = ConversationState()
        self.history: list[dict] = []
        self._client = client  # injectable for tests

    # --- public API ---

    def greeting(self) -> str:
        first_name = self.report["seller"]["name"].split()[0]
        text = (
            f"Hello {first_name}, this is your Snapdeal Virtual Key Account Manager, "
            "an AI assistant. I'm here to look at how your business is doing this month "
            "and help you decide on next steps. How are things going on your side?"
        )
        if not self.history:
            self.history.append({"role": "assistant", "content": text})
        return text

    def respond(self, user_message: str) -> AgentReply:
        text = (user_message or "").strip()
        if not text:
            return AgentReply(False, "I didn't catch that. Could you please say it again?", "empty_message")

        client = self._get_client()
        if client is None:
            return AgentReply(
                False,
                "The AI service is not configured. Please add GROQ_API_KEY to the .env file.",
                "missing_api_key",
            )

        messages = (
            [{"role": "system", "content": build_system_prompt(self.report, self.state)}]
            + self.history[-MAX_HISTORY_MESSAGES:]
            + [{"role": "user", "content": text}]
        )

        try:
            data = self._get_valid_json(client, messages)
        except AuthenticationError:
            return AgentReply(False, "My AI service key was rejected. Please check GROQ_API_KEY.", "invalid_api_key")
        except RateLimitError:
            return AgentReply(False, "I'm getting a lot of requests right now. Please try again in a moment.", "rate_limit")
        except NotFoundError:
            return AgentReply(False, "The configured AI model isn't available. Please check GROQ_MODEL in the .env file.", "model_not_found")
        except APIConnectionError:
            return AgentReply(False, "I'm having trouble connecting. Please check your internet and try again.", "connection")
        except APIStatusError as e:
            return AgentReply(False, f"Something went wrong on the AI service (error {e.status_code}). Please try again.", "api_error")

        if data is None:
            return AgentReply(False, "I had trouble forming a response. Could you please repeat that?", "invalid_response")

        self._update_state(data)
        reply = data["reply"].strip()
        # Only commit to history after a fully successful turn (no duplicates on retry)
        self.history.append({"role": "user", "content": text})
        self.history.append({"role": "assistant", "content": reply})
        return AgentReply(True, reply)

    # --- internals ---

    def _get_client(self):
        if self._client is None:
            api_key = os.getenv("GROQ_API_KEY", "").strip()
            if not api_key or api_key == "paste_your_key_here":
                return None
            self._client = Groq(api_key=api_key, timeout=20.0, max_retries=0)
        return self._client

    def _chat(self, client, messages: list[dict]) -> str:
        """Call Groq; on a rate limit, try the fallback model."""
        models = [PRIMARY_MODEL]
        if FALLBACK_MODEL and FALLBACK_MODEL != PRIMARY_MODEL:
            models.append(FALLBACK_MODEL)
        last_error = None
        for model in models:
            try:
                completion = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=0.4,
                    max_tokens=1500,
                    response_format={"type": "json_object"},
                    extra_body={"reasoning_effort": "low"},
                )
                return completion.choices[0].message.content or ""
            except (RateLimitError, NotFoundError) as e:
                last_error = e
        raise last_error

    def _get_valid_json(self, client, messages: list[dict]) -> dict | None:
        for _ in range(1 + MAX_INVALID_JSON_RETRIES):
            data = parse_agent_json(self._chat(client, messages))
            if data is not None:
                return data
        return None

    def _update_state(self, data: dict) -> None:
        had_recommendations = self.state.recommendations_given

        topic = data.get("topic_covered")
        if topic in INVESTIGATION_TOPICS:
            self.state.covered_topics.add(topic)

        for fact in data.get("seller_facts") or []:
            if isinstance(fact, str) and fact.strip() and fact not in self.state.seller_facts:
                self.state.seller_facts.append(fact.strip())

        # Seller commitments only count if recommendations were given in an EARLIER turn.
        if had_recommendations:
            for action in data.get("agreed_actions") or []:
                if isinstance(action, str) and action.strip() and action not in self.state.agreed_actions:
                    self.state.agreed_actions.append(action.strip())
            if data.get("conversation_complete") is True:
                self.state.complete = True

        if data.get("recommendations_given") is True:
            self.state.recommendations_given = True