import json
import os
import time
from pathlib import Path

from app.config import TOKEN_STORE_FILE


def load_token_store(path: Path = TOKEN_STORE_FILE) -> dict:
    if not path.exists():
        return {}

    return json.loads(path.read_text(encoding="utf-8"))


def save_token_store(token_data: dict, path: Path = TOKEN_STORE_FILE) -> None:
    current = load_token_store(path)
    current.update(token_data)

    now = int(time.time())
    current["updated_at"] = now

    if current.get("expires_in"):
        current["access_token_expires_at"] = now + int(current["expires_in"])

    if current.get("refresh_expires_in"):
        current["refresh_token_expires_at"] = now + int(current["refresh_expires_in"])

    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    temp_path.write_text(
        json.dumps(current, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    os.replace(temp_path, path)
