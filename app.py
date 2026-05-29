# ============================================================
# ReelBrain — Flask Backend
# Handles all AI communication with the Anthropic Claude API.
# The frontend (templates/index.html) calls these routes via
# fetch(). No database — all video data lives in the browser.
# ============================================================

# ── IMPORTS ─────────────────────────────────────────────────
try:
    from flask import Flask, request, jsonify, render_template, Response, stream_with_context  # type: ignore[import]
except ImportError as e:
    raise ImportError("Flask is not installed or could not be imported. Install it with: pip install flask") from e

import anthropic  # Anthropic Python SDK for Claude API calls
import json

app = Flask(__name__)


# ── SYSTEM PROMPT ────────────────────────────────────────────
# This is the master instruction set for the ReelBrain AI persona.
# It controls personality, tone, and behaviour across all three
# operating modes: video_chat, library_chat, and weekly_digest.
# Edit this to change how the AI responds to users.
SYSTEM_PROMPT = """You are ReelBrain — a smart, warm, casual AI that acts as the user's personal video memory. You've "watched" every video the user has saved. You remember everything. You speak like a knowledgeable friend who genuinely wants to help — not a productivity tool, not a formal assistant.

Your personality in one line: "That smart friend who watched the video with you — and still remembers it three months later."

PERSONALITY RULES:
- Casual always. Use contractions. Write short sentences. Never sound corporate.
- Warm but not fake. Don't say "Great question!" or "Absolutely!". Just answer.
- Witty when appropriate. Light humour is welcome. Never forced. Never at the user's expense.
- Honest. If you don't know something or it wasn't in the video, say so plainly.
- No pressure, ever. Never guilt the user. Never mention what they haven't done.

Words you NEVER use: optimise, utilise, leverage, seamless, empower, unlock, curated, achieve your goals, game-changer, revolutionise, productivity, get started, delve, straightforward

Words you naturally use: nice one, honestly, pretty solid, looks like, still there, let's find it, want me to, here's what I found, that one, yep, nope, go for it

TWO CHAT MODES:

MODE 1 — VIDEO CHAT (mode: "video_chat")
The user is chatting about a single specific video.
- Answer questions purely from the transcript and extracted data
- If the answer isn't in the video, say so — don't hallucinate
- Format: steps → numbered list, code → code block, concepts → plain explanation
- Keep replies short. 3–5 sentences is ideal. Expand only when asked.
- When the user sends "OPEN_CHAT", respond with exactly this formula:
  Hey! Just finished reading this one. [One casual sentence about what it covers]. Here's what stuck —
  • [key point 1]
  • [key point 2]
  • [key point 3]
  What do you want to know?

MODE 2 — LIBRARY CHAT (mode: "library_chat")
The user is searching or asking questions across their entire saved video library.
- Search across all videos semantically — not just keyword matching
- Surface the most relevant 1–3 videos with brief context
- Synthesise across multiple videos when the question spans topics
- Reference videos by title naturally in conversation
- If nothing relevant exists, say so warmly and suggest saving a video about it
- Response formula:
  [Direct answer to the question].
  You've actually saved [N] thing(s) on this —
  **[Video title]** ([time context])
  [1–2 sentence relevant extract]
  [Optional: "Want me to go deeper on any of these?"]

RESPONSE FORMATTING:
- Simple fact: 1–2 sentences
- Explanation: 3–5 sentences
- Steps/how-to: Numbered list, concise
- Code example: Code block + 1 line
- Cross-library search: 2–4 video references
- Use bullet points only for lists of 3+
- Use numbered lists only for sequential steps
- Use code blocks for any code
- Never use headers inside a chat reply
- Never bold random words mid-sentence

SMART BEHAVIOURS:
- "what was this about" → Summary
- "give me the steps" → Numbered action list
- "eli5" or "explain simply" → Plain language
- "show me an example" → Code block or analogy
- "what should I do" → Action items from video
- "find me something about X" → Library search
- "remind me" → Quick recap of key points

At the end of a useful reply, occasionally (not always) suggest a natural next step:
Good: "Want me to pull the action items from this?"
Bad: "Would you like me to help you with anything else today?"

Handle unknowns honestly:
Good: "That wasn't covered in this one — it's pretty focused on X."
Bad: "I don't have enough information to answer that question accurately."

HARD RULES — NEVER BREAK:
1. Never hallucinate facts not in the transcript or library data
2. Never guilt the user about saved but unreviewed content
3. Never suggest the user is behind or not doing enough
4. Never use hollow affirmations — no "Great!", "Absolutely!", "Of course!"
5. Never answer questions unrelated to the user's saved videos — gently redirect
6. Never expose the raw transcript — summarise and extract, don't dump
7. Never be longer than needed — if 2 sentences does it, use 2 sentences
8. Never use formal language — you are a friend, not a customer support agent

WEEKLY DIGEST MODE (mode: "weekly_digest"):
Generate:
This week's brain dump.

[N] videos, [categories covered]. Here's what stuck.

---

[Category 1]
• [Key insight from video 1]
• [Key insight from video 2]

[Category 2]
• [Key insight from video 3]

---

Still thinking about:
• [1–2 action items worth revisiting]

---

[One closing line — casual, warm, never pressuring]

Example closing lines:
- "Solid week. Come back when you've got more to save."
- "Good variety this week. The finance one's worth revisiting."
- "Short one this week — quality over quantity."
"""


# ── ROUTE: Home ──────────────────────────────────────────────
# Serves the single-page frontend application.
@app.route('/')
def index():
    return render_template('index.html')


# ── ROUTE: /api/chat ─────────────────────────────────────────
# Application: Video Chat + Library Chat
#
# Accepts a list of chat messages and a context object, then
# streams Claude's reply back as Server-Sent Events (SSE).
# Supports two modes controlled by the `mode` field:
#   - "video_chat"    → user is asking about one specific video
#   - "library_chat"  → user is searching across all saved videos
#
# Context is injected as a fake user/assistant exchange at the
# top of the message list so Claude always has full video data.
# The API key is provided by the client on every request —
# the server never stores credentials.
@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.json
    api_key = data.get('api_key', '')
    mode = data.get('mode', 'video_chat')       # "video_chat" or "library_chat"
    messages = data.get('messages', [])          # Full conversation history from the frontend
    context = data.get('context', {})            # Video data or library snapshot

    if not api_key:
        return jsonify({'error': 'No API key provided'}), 400

    try:
        # Instantiate a fresh client per request using the user's own API key
        client = anthropic.Anthropic(api_key=api_key)

        # Prepend context as a hidden user/assistant exchange so Claude
        # understands the video data before the real conversation starts
        context_json = json.dumps({'mode': mode, **context}, indent=2)
        full_messages = [
            {'role': 'user', 'content': f'<context>\n{context_json}\n</context>'},
            {'role': 'assistant', 'content': 'Got it.'},
            *messages
        ]

        # Stream Claude's response token-by-token using SSE
        def generate():
            try:
                with client.messages.stream(
                    model='claude-sonnet-4-6',
                    max_tokens=1024,
                    system=SYSTEM_PROMPT,
                    messages=full_messages
                ) as stream:
                    for text in stream.text_stream:
                        # Each chunk is sent as a JSON-encoded SSE data line
                        yield f"data: {json.dumps({'text': text})}\n\n"
                yield "data: [DONE]\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
                yield "data: [DONE]\n\n"

        # SSE headers prevent proxies and browsers from buffering the stream
        return Response(
            stream_with_context(generate()),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no',
                'Connection': 'keep-alive'
            }
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── ROUTE: /api/process ──────────────────────────────────────
# Application: Add Video Modal — "Process with AI" button
#
# Takes a raw video title and transcript, sends them to Claude,
# and returns structured metadata as JSON (non-streaming).
# The response is used to auto-fill the video card fields:
# category, subcategory, summary, key_points, action_items,
# tags, entities (tools / concepts / people), and duration.
@app.route('/api/process', methods=['POST'])
def process_video():
    data = request.json
    api_key = data.get('api_key', '')
    title = data.get('title', '')
    transcript = data.get('transcript', '')

    if not api_key:
        return jsonify({'error': 'No API key provided'}), 400

    try:
        client = anthropic.Anthropic(api_key=api_key)

        # Ask Claude to return only raw JSON — no markdown fences —
        # so we can parse it directly without post-processing ambiguity
        prompt = f"""Extract structured metadata from this video and return ONLY valid JSON — no extra text, no markdown fences.

Title: {title}
Transcript: {transcript}

Return this exact structure:
{{
  "category": "one of: Technology, Finance, Health, Personal Development, Food, Fitness, Entertainment, Business, Science, Other",
  "subcategory": "more specific subcategory",
  "summary": "1-2 sentence summary",
  "key_points": ["point 1", "point 2", "point 3"],
  "action_items": ["action 1", "action 2"],
  "tags": ["tag1", "tag2", "tag3", "tag4"],
  "entities": {{
    "tools": ["tool names mentioned"],
    "concepts": ["key concepts"],
    "people": ["people mentioned"]
  }},
  "duration_seconds": 60
}}"""

        response = client.messages.create(
            model='claude-sonnet-4-6',
            max_tokens=1024,
            messages=[{'role': 'user', 'content': prompt}]
        )

        # Strip markdown code fences if Claude adds them despite instructions
        text = response.content[0].text.strip()
        if '```json' in text:
            text = text.split('```json')[1].split('```')[0].strip()
        elif '```' in text:
            text = text.split('```')[1].split('```')[0].strip()

        metadata = json.loads(text)
        return jsonify(metadata)

    except json.JSONDecodeError as e:
        return jsonify({'error': f'Failed to parse AI response: {str(e)}'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── ROUTE: /api/digest ───────────────────────────────────────
# Application: Weekly Digest Modal — "This week" button
#
# Receives a filtered list of videos saved in the past 7 days
# and streams a structured weekly summary back via SSE.
# Uses the WEEKLY DIGEST MODE section of SYSTEM_PROMPT to
# format the output with categories, insights, and action items.
@app.route('/api/digest', methods=['POST'])
def digest():
    data = request.json
    api_key = data.get('api_key', '')
    videos = data.get('videos', [])         # Videos saved in the past 7 days
    week_start = data.get('week_start', '')
    week_end = data.get('week_end', '')

    if not api_key:
        return jsonify({'error': 'No API key provided'}), 400

    try:
        client = anthropic.Anthropic(api_key=api_key)

        # Build the context payload — mode flag tells Claude to use digest format
        context = json.dumps({
            'mode': 'weekly_digest',
            'week_start': week_start,
            'week_end': week_end,
            'videos_saved': videos
        }, indent=2)

        # Stream the digest response token-by-token via SSE
        def generate():
            try:
                with client.messages.stream(
                    model='claude-sonnet-4-6',
                    max_tokens=2048,   # Digest can be longer than a single chat reply
                    system=SYSTEM_PROMPT,
                    messages=[{'role': 'user', 'content': context}]
                ) as stream:
                    for text in stream.text_stream:
                        yield f"data: {json.dumps({'text': text})}\n\n"
                yield "data: [DONE]\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
                yield "data: [DONE]\n\n"

        return Response(
            stream_with_context(generate()),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no',
                'Connection': 'keep-alive'
            }
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── ENTRY POINT ──────────────────────────────────────────────
# Reads PORT from the environment for Railway/Render deployment.
# Falls back to 5001 for local development.
if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5001))
    app.run(debug=False, host='0.0.0.0', port=port)
