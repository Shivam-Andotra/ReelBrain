# ReelBrain

Your personal video memory. Save short-form videos from TikTok, Instagram, and YouTube Shorts, then chat with them using AI.

## What it does

- **Save videos** — paste a transcript and title; Claude extracts categories, key points, tags, and action items automatically
- **Video chat** — open any saved video and ask questions; ReelBrain answers only from what's in that transcript
- **Library chat** — ask plain-English questions across your entire library ("what do I know about investing?")
- **Weekly digest** — one AI-generated summary of everything you saved in the past 7 days

All data is stored in your browser's `localStorage`. No database, no account.

## Stack

- **Backend** — Flask (Python), Anthropic Python SDK
- **Frontend** — Single-page HTML/CSS/JS, no framework
- **AI** — Claude Sonnet (`claude-sonnet-4-6`) via the Anthropic API

## Setup

**1. Install dependencies**

```bash
pip install -r requirements.txt
```

**2. Run the server**

```bash
python app.py
```

The app runs on `http://localhost:5001`.

**3. Enter your API key**

On first load you'll be prompted for an Anthropic API key (`sk-ant-...`). Get one at [console.anthropic.com](https://console.anthropic.com). It's stored only in your browser — never sent anywhere except directly to the Anthropic API.

## Usage

1. Click **Add video** and paste a title + transcript (the more detail, the better the chat)
2. Optionally hit **Process with AI** to auto-fill categories and key points
3. Click any video card to open a chat session with that video
4. Use the search bar to ask a question across your whole library
5. Click **This week** for a digest of recently saved videos
