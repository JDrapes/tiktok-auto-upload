# tiktok-uploader

Python 3.11 service that scans `pending/` for video files and uploads them sequentially through a TikTok API client wrapper. It can run with a mock uploader for local testing or TikTok's Content Posting API for real uploads.

## Folder flow

```text
pending/    -> files waiting for upload
uploading/  -> files currently being processed
uploaded/   -> successfully uploaded files
failed/     -> files that failed after retries
```

The processor moves each file to `uploading/` before attempting an upload. On success it moves the file to `uploaded/`; after 3 failed attempts it moves the file to `failed/`.

Each video must have a matching JSON metadata file with the same basename:

```text
pending/clip_001.mp4
pending/clip_001.json
```

Example metadata:

```json
{
  "caption": "Insane clutch moment",
  "hashtags": ["twitchclips", "gaming", "fyp"],
  "visibility": "public",
  "allow_comments": true,
  "allow_duet": false,
  "allow_stitch": false
}
```

The video and JSON file move through `uploading/`, `uploaded/`, and `failed/` together.

`TIKTOK_PRIVACY_LEVEL` in `.env` takes priority over per-file `visibility`. Leave it as `SELF_ONLY` while the TikTok app is unaudited; TikTok rejects public Direct Post requests from unaudited clients.

On restart, any file left in `uploading/` is moved to `failed/` before the next scan. This avoids duplicate uploads if the previous process stopped after TikTok accepted the upload but before the local file move completed.

## Install

```bash
pip install -r requirements.txt
```

## Run

Mock mode is enabled by default:

```powershell
.\run.ps1
```

Real TikTok upload mode:

```powershell
# Edit .env first:
# TIKTOK_USE_MOCK=false
# TIKTOK_CLIENT_KEY=your_client_key
# TIKTOK_CLIENT_SECRET=your_client_secret
# TIKTOK_REDIRECT_URI=http://localhost:8000/callback
.\login.ps1
.\run.ps1
```

The service scans once, processes all eligible files sequentially, logs every attempt, then sleeps for 30 seconds before scanning again.
By default `RUN_MODE=single`, so the app processes at most one pending video pair and exits. Use `RUN_MODE=loop` for the original continuous service behavior.

Supported video extensions are configured in `app/config.py`.

## Environment

Local configuration is loaded from `.env`. Use `.env.example` as the template.

```text
TIKTOK_USE_MOCK=true
RUN_MODE=single
TIKTOK_CLIENT_KEY=your_client_key_here
TIKTOK_CLIENT_SECRET=your_client_secret_here
TIKTOK_REDIRECT_URI=http://127.0.0.1:8080/callback
TIKTOK_OAUTH_SCOPES=video.publish
TIKTOK_POST_MODE=direct
TIKTOK_POST_TITLE=
TIKTOK_PRIVACY_LEVEL=SELF_ONLY
TIKTOK_DISABLE_DUET=true
TIKTOK_DISABLE_STITCH=true
TIKTOK_DISABLE_COMMENT=true
TIKTOK_BRAND_CONTENT=false
TIKTOK_BRAND_ORGANIC=false
TIKTOK_UPLOAD_CHUNK_SIZE_BYTES=67108864
```

`.env` is ignored by git so client credentials are not committed. TikTok user tokens are stored in `token_store.json`, which is also ignored by git.

## OAuth

TikTok Content Posting API requires a user-authorized access token. Client key and client secret alone can only create a client access token, which is not valid for uploading to a user's TikTok account.

First, set `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`, and `TIKTOK_REDIRECT_URI` in `.env`. The redirect URI must match one of the redirect URIs registered for Login Kit in the TikTok developer portal.

Then start the local login server:

```powershell
.\login.ps1
```

The script opens TikTok Login Kit, waits for the redirect callback, exchanges the one-time authorization code, and writes the returned user tokens to `token_store.json`. The uploader refreshes the access token from that token store at startup.

TikTok's desktop Login Kit requires PKCE. This app generates a fresh `code_verifier` for each login and sends TikTok the SHA-256 hex digest as `code_challenge` with `code_challenge_method=S256`.

### Sandbox login errors

If TikTok shows `non_sandbox_target`, the TikTok account you are logging in with is not a target user for that sandbox app. In the TikTok developer portal, switch to the same sandbox that owns your client key, open Sandbox settings, and add the TikTok account under Target users. TikTok notes that target user changes can take up to an hour to appear.

Also confirm that Login Kit and Content Posting API are added to that same sandbox configuration and that the requested scope is enabled for the app.

## TikTok API setup

This app currently uses TikTok's Direct Post flow:

- Product: Content Posting API
- Scope: `video.publish`
- Creator info endpoint: `/v2/post/publish/creator_info/query/`
- Direct post endpoint: `/v2/post/publish/video/init/`
- Source mode: `FILE_UPLOAD`

Direct Post requires the TikTok app to have Direct Post enabled and the user token to include `video.publish`. If your existing `token_store.json` was created with `video.upload`, run `.\login.ps1` again after changing `TIKTOK_OAUTH_SCOPES=video.publish`.

Unaudited TikTok API clients are restricted to private Direct Post usage. Keep `TIKTOK_PRIVACY_LEVEL=SELF_ONLY`, and if TikTok returns `unaudited_client_can_only_post_to_private_accounts`, make the sandbox TikTok account private or complete TikTok's app audit.
