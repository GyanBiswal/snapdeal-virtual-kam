# Snapdeal Virtual KAM

An AI voice assistant that acts as a Virtual Key Account Manager (KAM) for Snapdeal sellers whose sales have declined. It greets the seller, investigates the problem through a two-way voice conversation, analyzes seller metrics, recommends 2-3 practical actions, and ends with a call summary.

**Live demo:** <PASTE-STREAMLIT-URL-HERE> (use Google Chrome and allow microphone access)

> All seller data in this project is **sample/simulated data** from the assignment brief.

## Features
- Two-way voice: browser speech recognition in, spoken replies out, with a text fallback
- Metrics analysis in Python (sales, orders, cancellations, price, stockouts); the LLM never does the math
- Investigates one topic at a time (stockouts, cancellations, visibility) before recommending
- Records only the commitments the seller actually makes; never claims anything was done
- End-of-call summary: problem, evidence, possible factors, recommendations, agreed actions, next steps

## Tech stack (all free)
Python, Streamlit, Groq API free tier (`openai/gpt-oss-120b`, fallback `openai/gpt-oss-20b`), JSON mock data, browser Web Speech API (speech-to-text), browser SpeechSynthesis (text-to-speech), Streamlit Community Cloud.

## How it works
1. `backend/analysis/seller_analysis.py` loads `seller.json` and computes changes and warning signals.
2. `backend/agent/seller_agent.py` gives the LLM the report plus conversation state; it replies in JSON, and Python validates the JSON and tracks topics, seller facts, recommendations and commitments.
3. `frontend/voice_component/index.html` is a custom Streamlit component (plain HTML/JS) that handles listening and speaking in the browser.
4. `backend/agent/call_summary.py` builds the final summary from the report and state.

## Run locally
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then put your free Groq key in .env
streamlit run frontend/app.py
```
Tests: `pip install -r requirements-dev.txt && python -m pytest -q`

## Limitations
- Voice needs Google Chrome and an internet connection (Chrome sends audio to Google for recognition). Accuracy varies with accent and noise.
- The KAM cannot take actions in Snapdeal systems; it only suggests and records commitments.
- Free-tier limits: Groq rate limits apply, and the hosted app sleeps after inactivity.
- No traffic or product-level data exists, so visibility questions are asked, not computed.