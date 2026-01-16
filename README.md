# OBS  YouTube Uploader (Python)

Watches a folder for new OBS recording files, matches the recording time to a Dota 2 match using OpenDota, writes a `.txt` description with match details (including items), uploads the video to YouTube, then sends a completion webhook notification.

This project is designed to run on **Windows via Docker**.

## What It Does

When a new video appears in the watch folder:

1. Parses the datetime from the filename (expects OBS naming like `YYYY-MM-DD_HH-MM-SS.mp4`).
2. Interprets that time in `RECORDING_TZ` (default: `America/New_York`, DST-aware) and converts to UTC.
3. Calls OpenDota to find the match closest to the recording time:
   - `GET https://api.opendota.com/api/players/<player_id>/recentMatches`
   - If not found, falls back to `GET https://api.opendota.com/api/players/<player_id>/matches?date=<days>`
4. Fetches full match details:
   - `GET https://api.opendota.com/api/matches/<match_id>`
   - Also loads constants:
     - `GET https://api.opendota.com/api/constants/heroes`
     - `GET https://api.opendota.com/api/constants/items`
5. Generates a `.txt` next to the video with:
   - match id, start time, duration, winner, score
   - your hero + K/D/A
   - your items (main/backpack/neutral)
   - OpenDota match link
6. Uploads the video to YouTube.
7. Sends a webhook notification:
   - `POST https://n8n.jhowl.com/webhook/2a55d28f-0635-46b5-878b-0b64f388d363`

## Project Layout

- `obs_youtube_uploader/main.py`  app entrypoint
- `obs_youtube_uploader/watcher.py`  folder watcher + stable-file detection
- `obs_youtube_uploader/process_video.py`  orchestrates OpenDota lookup, `.txt` generation, YouTube upload, webhook
- `obs_youtube_uploader/opendota.py`  OpenDota API client
- `obs_youtube_uploader/description.py`  description builder
- `obs_youtube_uploader/youtube_uploader.py`  YouTube upload using OAuth refresh token
- `tools/youtube_refresh_token.py`  one-time refresh token generator

## Requirements

- Docker Desktop on Windows (recommended runtime)
- A Google OAuth Desktop app client with YouTube Data API v3 enabled

## Setup

### 1) Configure `.env`

Create `obs-youtube-uploader/.env` based on `.env.example`.

Key variables:

- `WATCH_FOLDER` (optional): folder to watch. If not set, defaults to `/app/watch` inside container.
- `VIDEO_EXTENSIONS`: default `.mp4,.mkv`
- `PROCESS_EXISTING`: if `true`, processes existing files already in the folder on startup
- `DRY_RUN`: if `true`, skips YouTube upload + webhook (still generates `.txt`)

Time + match matching:

- `RECORDING_TZ`: timezone for the OBS filename time (default `America/New_York`)
- `MATCH_TIME_BEFORE_SEC`: how far *before match start* the recording time may be (default 10800 = 3h)
- `MATCH_TIME_AFTER_SEC`: how far *after match end* the recording time may be (default 10800 = 3h)

OpenDota:

- `OPENDOTA_PLAYER_ID`: default `115732760`

Webhook:

- `N8N_WEBHOOK_URL`: your workflow URL

YouTube:

- `YOUTUBE_CLIENT_ID`
- `YOUTUBE_CLIENT_SECRET`
- `YOUTUBE_REFRESH_TOKEN`
- `YOUTUBE_PRIVACY_STATUS` (`private` | `unlisted` | `public`)
- `YOUTUBE_CATEGORY_ID` (optional)
- `YOUTUBE_TAGS` (comma separated)

### 2) One-time: generate `YOUTUBE_REFRESH_TOKEN`

Run locally (not in Docker) on any machine with Python 3:

```bash
cd obs-youtube-uploader
python3 -m pip install -r requirements.txt
python3 tools/youtube_refresh_token.py
```

It opens a browser auth flow and prints a refresh token. Paste it into `.env` as `YOUTUBE_REFRESH_TOKEN=...`.

Recommended: set `YOUTUBE_CLIENT_SECRETS_FILE` in `.env` pointing to the downloaded Google client secrets JSON.

If you get `No refresh_token returned`, revoke the app access in your Google Account (Third-party access) and run again.

## Running on Windows with Docker

### Build

From `obs-youtube-uploader/`:

```powershell
docker build -t obs-youtube-uploader:py .
```

### Run (watch project-local `./watch` folder)

```powershell
docker run --rm -it `
  --env-file .env `
  -v "${PWD}\watch:/app/watch" `
  obs-youtube-uploader:py
```

### Run (watch your real OBS output folder)

Replace the `-v` with your OBS recordings path:

```powershell
docker run --rm -it `
  --env-file .env `
  -v "C:\Users\YOUR_USER\Videos\OBS:/app/watch" `
  obs-youtube-uploader:py
```

## Filename Format (Important)

The watcher expects OBS recordings named with datetime:

- `YYYY-MM-DD_HH-MM-SS.mp4`
- `YYYY-MM-DD HH-MM-SS.mp4`
- `YYYY-MM-DD-HH-MM-SS.mp4`

Example:

- `2025-12-12_20-24-33.mp4`

The datetime is interpreted in `RECORDING_TZ` and converted to UTC to match OpenDota times.

## Output

For a video file:

- `watch/2025-12-12_20-24-33.mp4`

The app creates:

- `watch/2025-12-12_20-24-33.txt`

And then uploads to YouTube (unless `DRY_RUN=true`).

## Webhook Payload

The n8n webhook receives JSON like:

```json
{
  "status": "success",
  "startedAt": "2026-01-16T12:34:56.000000Z",
  "finishedAt": "2026-01-16T12:40:12.000000Z",
  "videoPath": "...",
  "descriptionPath": "...",
  "matchId": 1234567890,
  "youtubeVideoId": "abcdEFGHijk",
  "error": null
}
```

If something fails, `status` is `error` and `error` contains the message.

## Troubleshooting

- No match found:
  - Increase `MATCH_TIME_BEFORE_SEC` / `MATCH_TIME_AFTER_SEC`
  - Confirm `RECORDING_TZ` matches the OBS filename timezone
  - Ensure the match is within OpenDota history for that player

- Video picked up too early:
  - The watcher waits until the file size is stable for ~20 seconds before processing

- Docker cant access the OBS folder:
  - On Windows, check Docker Desktop File Sharing settings and permissions

## Notes

- Do not commit secrets. Keep `.env` local.
- YouTube upload uses a refresh token (OAuth). Make sure you keep it private.
