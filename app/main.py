import logging
import sys
import time

from app.config import (
    APP_NAME,
    FAILED_DIR,
    PENDING_DIR,
    RUN_MODE,
    SCAN_INTERVAL_SECONDS,
    TIKTOK_CLIENT_KEY,
    TIKTOK_CLIENT_SECRET,
    TIKTOK_OAUTH_SCOPES,
    UPLOADED_DIR,
    UPLOADING_DIR,
    USE_MOCK_TIKTOK_CLIENT,
)
from app.file_utils import ensure_directories
from app.processor import VideoProcessor
from app.tiktok_client import MockTikTokClient, TikTokClient
from app.tiktok_oauth import refresh_access_token
from app.token_store import load_token_store, save_token_store


TOKEN_REFRESH_SKEW_SECONDS = 300


def configure_logging() -> None:
    _configure_console_encoding()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


def main() -> None:
    configure_logging()
    logger = logging.getLogger(APP_NAME)

    ensure_directories([PENDING_DIR, UPLOADING_DIR, UPLOADED_DIR, FAILED_DIR])

    if USE_MOCK_TIKTOK_CLIENT:
        client = MockTikTokClient()
        logger.info("Using mock TikTok client")
    else:
        client = TikTokClient(access_token=get_tiktok_access_token(logger))
        logger.info("Using real TikTok Content Posting API client")

    processor = VideoProcessor(client)
    logger.info("%s started", APP_NAME)

    if RUN_MODE == "single":
        logger.info("Starting single-upload run")
        processed_count = processor.process_once(max_uploads=1)
        logger.info("Single-upload run complete; processed %s upload(s)", processed_count)
        return

    if RUN_MODE != "loop":
        raise RuntimeError("RUN_MODE must be either single or loop")

    while True:
        logger.info("Starting folder scan")
        processor.process_once()
        logger.info("Scan complete; sleeping for %s seconds", SCAN_INTERVAL_SECONDS)
        time.sleep(SCAN_INTERVAL_SECONDS)


def get_tiktok_access_token(logger: logging.Logger) -> str:
    token_store = load_token_store()
    validate_token_scopes(token_store)
    access_token = token_store.get("access_token")
    access_token_expires_at = int(token_store.get("access_token_expires_at") or 0)
    refresh_token = token_store.get("refresh_token")

    if access_token and access_token_expires_at > int(time.time()) + TOKEN_REFRESH_SKEW_SECONDS:
        logger.info("Using stored TikTok access token")
        return access_token

    if refresh_token and TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET:
        logger.info("Refreshing TikTok user access token from token store")
        token_data = refresh_access_token(
            client_key=TIKTOK_CLIENT_KEY,
            client_secret=TIKTOK_CLIENT_SECRET,
            refresh_token=refresh_token,
        )
        save_token_store(token_data)
        return token_data["access_token"]

    if access_token:
        logger.warning(
            "Using stored TikTok access token without refresh; run OAuth login again "
            "if uploads fail with access_token_invalid"
        )
        return access_token

    raise RuntimeError(
        "Real TikTok mode requires a user token store. Run: python -m app.auth_server"
    )


def _configure_console_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def validate_token_scopes(token_store: dict) -> None:
    granted_scopes = {
        scope.strip()
        for scope in str(token_store.get("scope", "")).replace(" ", ",").split(",")
        if scope.strip()
    }
    required_scopes = {
        scope.strip()
        for scope in TIKTOK_OAUTH_SCOPES.replace(" ", ",").split(",")
        if scope.strip()
    }

    missing_scopes = sorted(required_scopes - granted_scopes)
    if missing_scopes:
        raise RuntimeError(
            "Stored TikTok token is missing required scope(s): "
            f"{', '.join(missing_scopes)}. Run .\\login.ps1 again."
        )


if __name__ == "__main__":
    main()
