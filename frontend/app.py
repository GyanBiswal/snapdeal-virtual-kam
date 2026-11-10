import sys
from pathlib import Path

# Make the project root importable (so `backend` can be found)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
import streamlit.components.v1 as components

from backend.agent.seller_agent import SellerAgent
from backend.analysis.seller_analysis import format_inr

st.set_page_config(page_title="Snapdeal Virtual KAM", page_icon="📞", layout="wide")

# Custom component: plain HTML/JS (no npm build) doing speech-to-text + text-to-speech in the browser
voice_component = components.declare_component(
    "kam_voice", path=str(Path(__file__).resolve().parent / "voice_component")
)


# ---------- Session setup ----------

def init_session():
    # These survive "Start new conversation" so voice events are never replayed or skipped
    st.session_state.setdefault("speak_id", 0)
    st.session_state.setdefault("speak_text", "")
    st.session_state.setdefault("epoch", 0)
    st.session_state.setdefault("last_voice_id", None)
    if "agent" not in st.session_state:
        agent = SellerAgent()
        st.session_state.agent = agent
        st.session_state.transcript = [
            {"role": "assistant", "content": agent.greeting()}
        ]
        st.session_state.last_error = None


init_session()
agent: SellerAgent = st.session_state.agent
report = agent.report
seller, last, this, ch = (
    report["seller"], report["last_month"], report["this_month"], report["changes"],
)


def handle_user_message(text: str) -> None:
    """Send a message (typed or spoken) to the agent and queue the reply to be spoken."""
    result = agent.respond(text)
    if result.ok:
        st.session_state.transcript.append({"role": "user", "content": text})
        st.session_state.transcript.append({"role": "assistant", "content": result.text})
        st.session_state.last_error = None
    else:
        st.session_state.last_error = result.text
    # The voice component speaks this if a call is active (each speak_id is used once)
    st.session_state.speak_text = result.text
    st.session_state.speak_id += 1


# ---------- Sidebar ----------

with st.sidebar:
    st.header("Controls")
    if st.button("Start new conversation", use_container_width=True):
        for key in ("agent", "transcript", "last_error"):
            st.session_state.pop(key, None)
        st.session_state.speak_text = ""
        st.session_state.epoch += 1  # tells the voice component to end any active call
        st.rerun()

    with st.expander("Debug: agent state"):
        s = agent.state
        st.write("Topics covered:", ", ".join(sorted(s.covered_topics)) or "none")
        st.write("Last question was about:", s.pending_topic or "none")
        st.write("Seller facts:", s.seller_facts or "none")
        st.write("Recommendations given:", s.recommendations_given)
        st.write("Agreed actions:", s.agreed_actions or "none")

# ---------- Header + seller info ----------

st.title("📞 Snapdeal Virtual KAM")
st.caption("Your AI Key Account Manager for understanding and improving seller performance.")

st.markdown(
    f"**{seller['name']}** · {seller['business_name']} · {seller['category']} · ID {seller['id']}"
)
st.info(report["data_disclaimer"] + " Seller name and figures are illustrative.", icon="ℹ️")

# ---------- Metrics: last month vs this month ----------

st.subheader("Sales performance: last month vs this month")
c1, c2, c3, c4, c5 = st.columns(5)

c1.metric("Sales", format_inr(this["sales"]), f"{ch['sales_change_pct']}%")
c1.caption(f"Last month: {format_inr(last['sales'])}")

c2.metric("Orders", this["orders"], f"{ch['orders_change_pct']}%")
c2.caption(f"Last month: {last['orders']}")

c3.metric(
    "Avg selling price",
    format_inr(this["avg_selling_price"]),
    "0% (unchanged)" if ch["avg_selling_price_change_pct"] == 0 else f"{ch['avg_selling_price_change_pct']}%",
    delta_color="off" if ch["avg_selling_price_change_pct"] == 0 else "normal",
)
c3.caption(f"Last month: {format_inr(last['avg_selling_price'])}")

c4.metric(
    "Cancellation rate",
    f"{this['cancellation_rate']}%",
    f"{ch['cancellation_change_pp']:+g} pp",
    delta_color="inverse",
)
c4.caption(f"Last month: {last['cancellation_rate']}%")

c5.metric(
    "Out-of-stock products",
    this["out_of_stock_products"],
    f"{ch['out_of_stock_change']:+d}",
    delta_color="inverse",
)
c5.caption(f"Last month: {last['out_of_stock_products']}")

with st.expander("Possible factors flagged by the data (to be investigated, not proven causes)"):
    for signal in report["warning_signals"]:
        st.write(f"- {signal['finding']}")

st.divider()

# ---------- Conversation (voice + text) ----------

st.subheader("Conversation with your KAM")
st.caption("Click the button to start a voice call (use Google Chrome). You can always type below instead.")

voice_event = voice_component(
    greeting=agent.greeting(),
    speak_text=st.session_state.speak_text,
    speak_id=st.session_state.speak_id,
    epoch=st.session_state.epoch,
    key="kam_voice",
    default=None,
)

chat_area = st.container()
user_input = st.chat_input("Type your message to the KAM...")

# Decide whether there is a NEW message to process (spoken or typed)
pending_text = None
if (
    isinstance(voice_event, dict)
    and voice_event.get("type") == "utterance"  # "end_call" events are ignored for now
    and voice_event.get("id") != st.session_state.last_voice_id  # never process the same utterance twice
):
    st.session_state.last_voice_id = voice_event["id"]
    pending_text = voice_event.get("text", "")
elif user_input:
    pending_text = user_input

with chat_area:
    for msg in st.session_state.transcript:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
    if pending_text:
        with st.chat_message("user"):
            st.markdown(pending_text)
        with st.spinner("KAM is thinking..."):
            handle_user_message(pending_text)

if pending_text:
    st.rerun()  # re-render so the transcript updates and the component receives the reply to speak

if st.session_state.last_error:
    st.warning(st.session_state.last_error)