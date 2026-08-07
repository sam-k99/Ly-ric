# lyric

A terminal-based YouTube Music player with synced lyrics, radio-style
autoplay and vim-style controls. Built with Python, mpv and YouTube Music's
recommendation engine.

## Features

- Search YouTube Music (songs only — no random videos)
- Stream audio via mpv (audio-only, lightweight)
- Synced lyrics (falls back to plain lyrics)
- Radio queue: auto-plays related songs (same/other artists, remixes)
- Next / previous / replay / seek / pause controls
- Full-screen terminal UI

## Requirements

- Python 3.9+
- mpv
- yt-dlp

## Installation

```bash
git clone https://github.com/sam-k99/lyric.git
cd lyric
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
