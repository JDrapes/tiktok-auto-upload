import hashlib
import logging
import mimetypes
from pathlib import Path

import requests

from app.config import (
    TIKTOK_BRAND_CONTENT,
    TIKTOK_BRAND_ORGANIC,
    TIKTOK_DISABLE_COMMENT,
    TIKTOK_DISABLE_DUET,
    TIKTOK_DISABLE_STITCH,
    TIKTOK_POST_MODE,
    TIKTOK_POST_TITLE,
    TIKTOK_PRIVACY_LEVEL,
    TIKTOK_UPLOAD_CHUNK_SIZE_BYTES,
)


logger = logging.getLogger(__name__)


class TikTokUploadError(RuntimeError):
    def __init__(self, message: str, error_code: str | None = None) -> None:
        super().__init__(message)
        self.error_code = error_code

    @property
    def is_retryable(self) -> bool:
        return self.error_code not in {
            "privacy_level_option_mismatch",
            "scope_not_authorized",
            "unaudited_client_can_only_post_to_private_accounts",
        }


class MockTikTokClient:
    """Mock TikTok API client.

    The mock keeps behavior stable per file name so retry handling is easy to
    exercise during local development.
    """

    def upload_video(self, video_path: Path, metadata: dict | None = None) -> str:
        if not video_path.exists():
            raise TikTokUploadError(f"Video file does not exist: {video_path}")

        if video_path.stat().st_size == 0:
            raise TikTokUploadError("Video file is empty")

        digest = hashlib.sha256(video_path.name.encode("utf-8")).hexdigest()
        simulated_failure = int(digest[:2], 16) < 38

        logger.info("Mock uploading %s", video_path.name)

        if simulated_failure:
            raise TikTokUploadError("Mock upload failed")

        return f"mock-upload-{digest[:12]}"


class TikTokClient:
    INBOX_UPLOAD_URL = "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/"
    DIRECT_POST_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"
    CREATOR_INFO_URL = "https://open.tiktokapis.com/v2/post/publish/creator_info/query/"

    def __init__(
        self,
        access_token: str,
        chunk_size_bytes: int = TIKTOK_UPLOAD_CHUNK_SIZE_BYTES,
    ) -> None:
        if not access_token:
            raise ValueError("TikTok access token is required")
        if chunk_size_bytes <= 0:
            raise ValueError("TikTok upload chunk size must be greater than zero")

        self.access_token = access_token
        self.chunk_size_bytes = chunk_size_bytes
        self.post_mode = TIKTOK_POST_MODE

    def upload_video(self, video_path: Path, metadata: dict | None = None) -> str:
        if not video_path.exists():
            raise TikTokUploadError(f"Video file does not exist: {video_path}")

        video_size = video_path.stat().st_size
        if video_size == 0:
            raise TikTokUploadError("Video file is empty")

        chunk_size = min(self.chunk_size_bytes, video_size)
        total_chunk_count = (video_size + chunk_size - 1) // chunk_size

        logger.info(
            "Initializing TikTok %s upload for %s; size=%s bytes; chunks=%s",
            self.post_mode,
            video_path.name,
            video_size,
            total_chunk_count,
        )
        publish_id, upload_url = self._initialize_upload(
            video_path=video_path,
            metadata=metadata or {},
            video_size=video_size,
            chunk_size=chunk_size,
            total_chunk_count=total_chunk_count,
        )

        logger.info("Sending video bytes to TikTok for %s", video_path.name)
        self._upload_chunks(
            upload_url=upload_url,
            video_path=video_path,
            video_size=video_size,
            chunk_size=chunk_size,
        )

        logger.info("TikTok upload completed for %s; publish_id=%s", video_path.name, publish_id)
        return publish_id

    def _initialize_upload(
        self,
        video_path: Path,
        metadata: dict,
        video_size: int,
        chunk_size: int,
        total_chunk_count: int,
    ) -> tuple[str, str]:
        if self.post_mode == "direct":
            return self._initialize_direct_post(
                video_path=video_path,
                metadata=metadata,
                video_size=video_size,
                chunk_size=chunk_size,
                total_chunk_count=total_chunk_count,
            )

        if self.post_mode == "inbox":
            return self._initialize_inbox_upload(
                video_size=video_size,
                chunk_size=chunk_size,
                total_chunk_count=total_chunk_count,
            )

        raise TikTokUploadError(
            f"Unsupported TIKTOK_POST_MODE={self.post_mode!r}; expected direct or inbox"
        )

    def _initialize_inbox_upload(
        self,
        video_size: int,
        chunk_size: int,
        total_chunk_count: int,
    ) -> tuple[str, str]:
        response = requests.post(
            self.INBOX_UPLOAD_URL,
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json; charset=UTF-8",
            },
            json={
                "source_info": {
                    "source": "FILE_UPLOAD",
                    "video_size": video_size,
                    "chunk_size": chunk_size,
                    "total_chunk_count": total_chunk_count,
                }
            },
            timeout=30,
        )

        data = _json_response(response)
        error = data.get("error", {})
        if response.status_code >= 400 or error.get("code") != "ok":
            raise TikTokUploadError(f"TikTok upload init failed: {data}")

        upload_data = data.get("data", {})
        publish_id = upload_data.get("publish_id")
        upload_url = upload_data.get("upload_url")

        if not publish_id or not upload_url:
            raise TikTokUploadError(f"TikTok upload init response missing data: {data}")

        return publish_id, upload_url

    def _initialize_direct_post(
        self,
        video_path: Path,
        metadata: dict,
        video_size: int,
        chunk_size: int,
        total_chunk_count: int,
    ) -> tuple[str, str]:
        creator_info = self.query_creator_info()
        privacy_level = _select_privacy_level(
            requested_privacy_level=_metadata_privacy_level(metadata),
            privacy_level_options=creator_info.get("privacy_level_options", []),
        )

        post_info = {
            "title": _metadata_title(metadata, video_path),
            "privacy_level": privacy_level,
            "disable_duet": _metadata_bool(metadata, "allow_duet", not TIKTOK_DISABLE_DUET)
            is False,
            "disable_comment": _metadata_bool(
                metadata,
                "allow_comments",
                not TIKTOK_DISABLE_COMMENT,
            )
            is False,
            "disable_stitch": _metadata_bool(
                metadata,
                "allow_stitch",
                not TIKTOK_DISABLE_STITCH,
            )
            is False,
            "brand_content_toggle": _metadata_bool(
                metadata,
                "brand_content",
                TIKTOK_BRAND_CONTENT,
            ),
            "brand_organic_toggle": _metadata_bool(
                metadata,
                "brand_organic",
                TIKTOK_BRAND_ORGANIC,
            ),
        }
        logger.info(
            "Direct post settings for %s: privacy_level=%s, comments_disabled=%s, "
            "duet_disabled=%s, stitch_disabled=%s",
            video_path.name,
            post_info["privacy_level"],
            post_info["disable_comment"],
            post_info["disable_duet"],
            post_info["disable_stitch"],
        )

        response = requests.post(
            self.DIRECT_POST_URL,
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json; charset=UTF-8",
            },
            json={
                "post_info": post_info,
                "source_info": {
                    "source": "FILE_UPLOAD",
                    "video_size": video_size,
                    "chunk_size": chunk_size,
                    "total_chunk_count": total_chunk_count,
                },
            },
            timeout=30,
        )

        data = _json_response(response)
        error = data.get("error", {})
        if response.status_code >= 400 or error.get("code") != "ok":
            raise TikTokUploadError(
                f"TikTok direct post init failed: {data}",
                error_code=error.get("code"),
            )

        upload_data = data.get("data", {})
        publish_id = upload_data.get("publish_id")
        upload_url = upload_data.get("upload_url")

        if not publish_id or not upload_url:
            raise TikTokUploadError(f"TikTok direct post init response missing data: {data}")

        return publish_id, upload_url

    def query_creator_info(self) -> dict:
        response = requests.post(
            self.CREATOR_INFO_URL,
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json; charset=UTF-8",
            },
            timeout=30,
        )

        data = _json_response(response)
        error = data.get("error", {})
        if response.status_code >= 400 or error.get("code") != "ok":
            raise TikTokUploadError(f"TikTok creator info query failed: {data}")

        return data.get("data", {})

    def _upload_chunks(
        self,
        upload_url: str,
        video_path: Path,
        video_size: int,
        chunk_size: int,
    ) -> None:
        content_type = mimetypes.guess_type(video_path.name)[0] or "video/mp4"

        with video_path.open("rb") as video_file:
            start = 0
            while start < video_size:
                chunk = video_file.read(chunk_size)
                if not chunk:
                    break

                end = start + len(chunk) - 1
                response = requests.put(
                    upload_url,
                    headers={
                        "Content-Type": content_type,
                        "Content-Length": str(len(chunk)),
                        "Content-Range": f"bytes {start}-{end}/{video_size}",
                    },
                    data=chunk,
                    timeout=300,
                )

                if response.status_code >= 400:
                    raise TikTokUploadError(
                        "TikTok video byte upload failed: "
                        f"status={response.status_code}; body={response.text}"
                    )

                logger.info("Uploaded TikTok chunk bytes %s-%s/%s", start, end, video_size)
                start = end + 1


def _json_response(response: requests.Response) -> dict:
    try:
        return response.json()
    except ValueError as exc:
        raise TikTokUploadError(
            f"TikTok returned non-JSON response: status={response.status_code}; "
            f"body={response.text}"
        ) from exc


def _select_privacy_level(
    requested_privacy_level: str,
    privacy_level_options: list[str],
) -> str:
    if requested_privacy_level in privacy_level_options:
        return requested_privacy_level

    if "SELF_ONLY" in privacy_level_options:
        logger.warning(
            "Requested TikTok privacy level %s is unavailable; using SELF_ONLY",
            requested_privacy_level,
        )
        return "SELF_ONLY"

    if privacy_level_options:
        fallback = privacy_level_options[0]
        logger.warning(
            "Requested TikTok privacy level %s is unavailable; using %s",
            requested_privacy_level,
            fallback,
        )
        return fallback

    raise TikTokUploadError("TikTok creator info returned no privacy level options")


def _metadata_title(metadata: dict, video_path: Path) -> str:
    configured_title = TIKTOK_POST_TITLE.strip()
    if configured_title:
        return configured_title

    caption = str(metadata.get("caption") or "").strip()
    hashtags = metadata.get("hashtags") or []
    if not isinstance(hashtags, list):
        hashtags = []

    hashtag_text = " ".join(
        f"#{str(tag).lstrip('#').strip()}"
        for tag in hashtags
        if str(tag).strip()
    )
    title = " ".join(part for part in (caption, hashtag_text) if part)
    return title or video_path.stem


def _metadata_privacy_level(metadata: dict) -> str:
    configured_privacy_level = TIKTOK_PRIVACY_LEVEL.strip()
    if configured_privacy_level:
        return configured_privacy_level

    visibility = str(metadata.get("visibility") or "").strip().lower()
    visibility_map = {
        "public": "PUBLIC_TO_EVERYONE",
        "friends": "MUTUAL_FOLLOW_FRIENDS",
        "followers": "FOLLOWER_OF_CREATOR",
        "private": "SELF_ONLY",
        "self": "SELF_ONLY",
        "self_only": "SELF_ONLY",
    }

    if visibility in visibility_map:
        return visibility_map[visibility]

    return str(metadata.get("privacy_level") or TIKTOK_PRIVACY_LEVEL).strip()


def _metadata_bool(metadata: dict, key: str, default: bool) -> bool:
    value = metadata.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes"}
    return bool(value)
