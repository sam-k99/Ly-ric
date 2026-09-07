<img width="1891" height="1003" alt="lyric_song_search" src="https://github.com/user-attachments/assets/6d9088be-3df2-45d9-b4ce-a86a259fbe17" />
<img width="1903" height="1013" alt="Dashboard" src="https://github.com/user-attachments/assets/849ded46-23a7-4913-a382-427f06e1520f" />

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
git clone https://github.com/sam-k99/Ly-ric.git
cd lyric
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
