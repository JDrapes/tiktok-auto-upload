import os
from pathlib import Path


APP_NAME = "tiktok-uploader"

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"
TOKEN_STORE_FILE = BASE_DIR / "token_store.json"


def load_env_file(path: Path = ENV_FILE) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        if key and key not in os.environ:
            os.environ[key] = value


load_env_file()

PENDING_DIR = BASE_DIR / "pending"
UPLOADING_DIR = BASE_DIR / "uploading"
UPLOADED_DIR = BASE_DIR / "uploaded"
FAILED_DIR = BASE_DIR / "failed"

VIDEO_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".avi",
    ".mkv",
    ".webm",
    ".m4v",
}

MAX_UPLOAD_ATTEMPTS = 3
SCAN_INTERVAL_SECONDS = 30
RUN_MODE = os.getenv("RUN_MODE", "single").lower()

USE_MOCK_TIKTOK_CLIENT = os.getenv("TIKTOK_USE_MOCK", "true").lower() in {
    "1",
    "true",
    "yes",
}
TIKTOK_CLIENT_KEY = os.getenv("TIKTOK_CLIENT_KEY")
TIKTOK_CLIENT_SECRET = os.getenv("TIKTOK_CLIENT_SECRET")
TIKTOK_REDIRECT_URI = os.getenv("TIKTOK_REDIRECT_URI")
TIKTOK_OAUTH_SCOPES = os.getenv("TIKTOK_OAUTH_SCOPES", "video.publish")
TIKTOK_POST_MODE = os.getenv("TIKTOK_POST_MODE", "direct").lower()
TIKTOK_POST_TITLE = os.getenv("TIKTOK_POST_TITLE", "")
TIKTOK_PRIVACY_LEVEL = os.getenv("TIKTOK_PRIVACY_LEVEL", "SELF_ONLY")
TIKTOK_DISABLE_DUET = os.getenv("TIKTOK_DISABLE_DUET", "true").lower() in {
    "1",
    "true",
    "yes",
}
TIKTOK_DISABLE_STITCH = os.getenv("TIKTOK_DISABLE_STITCH", "true").lower() in {
    "1",
    "true",
    "yes",
}
TIKTOK_DISABLE_COMMENT = os.getenv("TIKTOK_DISABLE_COMMENT", "true").lower() in {
    "1",
    "true",
    "yes",
}
TIKTOK_BRAND_CONTENT = os.getenv("TIKTOK_BRAND_CONTENT", "false").lower() in {
    "1",
    "true",
    "yes",
}
TIKTOK_BRAND_ORGANIC = os.getenv("TIKTOK_BRAND_ORGANIC", "false").lower() in {
    "1",
    "true",
    "yes",
}
TIKTOK_UPLOAD_CHUNK_SIZE_BYTES = int(
    os.getenv("TIKTOK_UPLOAD_CHUNK_SIZE_BYTES", str(64 * 1024 * 1024))
)
