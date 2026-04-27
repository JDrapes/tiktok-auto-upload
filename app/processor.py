import json
import logging
from dataclasses import dataclass
from pathlib import Path

from app.config import (
    FAILED_DIR,
    MAX_UPLOAD_ATTEMPTS,
    PENDING_DIR,
    UPLOADED_DIR,
    UPLOADING_DIR,
    VIDEO_EXTENSIONS,
)
from app.file_utils import atomic_move, atomic_move_pair
from app.tiktok_client import TikTokClient, TikTokUploadError


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PendingUpload:
    video_path: Path
    metadata_path: Path


@dataclass(frozen=True)
class UploadingUpload:
    video_path: Path
    metadata_path: Path


class VideoProcessor:
    def __init__(self, client: TikTokClient) -> None:
        self.client = client

    def process_once(self, max_uploads: int | None = None) -> int:
        self._recover_interrupted_uploads()

        processed_count = 0
        for pending_upload in self._pending_uploads():
            if max_uploads is not None and processed_count >= max_uploads:
                break

            self._process_upload(pending_upload)
            processed_count += 1

        return processed_count

    def _pending_uploads(self) -> list[PendingUpload]:
        uploads = []
        for video_path in sorted(
            path
            for path in PENDING_DIR.iterdir()
            if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS
        ):
            metadata_path = video_path.with_suffix(".json")
            if not metadata_path.exists():
                logger.error(
                    "Skipping %s because matching metadata file %s is missing",
                    video_path.name,
                    metadata_path.name,
                )
                continue

            uploads.append(PendingUpload(video_path=video_path, metadata_path=metadata_path))

        return uploads

    def _recover_interrupted_uploads(self) -> None:
        for uploading_file in sorted(path for path in UPLOADING_DIR.iterdir() if path.is_file()):
            logger.warning(
                "Found interrupted upload state for %s; moving to failed to avoid duplicate upload",
                uploading_file.name,
            )
            failed_file = atomic_move(uploading_file, FAILED_DIR)
            logger.info("Recovered interrupted file %s to failed", failed_file.name)

    def _process_upload(self, pending_upload: PendingUpload) -> None:
        logger.info(
            "Preparing upload for %s with metadata %s",
            pending_upload.video_path.name,
            pending_upload.metadata_path.name,
        )

        uploading_video_path, uploading_metadata_path = atomic_move_pair(
            pending_upload.video_path,
            pending_upload.metadata_path,
            UPLOADING_DIR,
        )
        uploading_upload = UploadingUpload(
            video_path=uploading_video_path,
            metadata_path=uploading_metadata_path,
        )
        logger.info(
            "Moved %s and %s to uploading",
            uploading_upload.video_path.name,
            uploading_upload.metadata_path.name,
        )

        try:
            metadata = _load_metadata(uploading_upload.metadata_path)
        except Exception:
            logger.exception("Invalid metadata for %s", uploading_upload.video_path.name)
            self._move_upload(uploading_upload, FAILED_DIR)
            return

        for attempt in range(1, MAX_UPLOAD_ATTEMPTS + 1):
            logger.info(
                "Upload attempt %s/%s for %s",
                attempt,
                MAX_UPLOAD_ATTEMPTS,
                uploading_upload.video_path.name,
            )

            try:
                upload_id = self.client.upload_video(uploading_upload.video_path, metadata)
            except TikTokUploadError as exc:
                logger.exception(
                    "Upload attempt %s/%s failed for %s",
                    attempt,
                    MAX_UPLOAD_ATTEMPTS,
                    uploading_upload.video_path.name,
                )
                if not exc.is_retryable:
                    logger.error(
                        "TikTok rejected %s with non-retryable error code %s",
                        uploading_upload.video_path.name,
                        exc.error_code,
                    )
                    break
            except Exception:
                logger.exception(
                    "Upload attempt %s/%s failed for %s",
                    attempt,
                    MAX_UPLOAD_ATTEMPTS,
                    uploading_upload.video_path.name,
                )
                continue

            uploaded_upload = self._move_upload(uploading_upload, UPLOADED_DIR)
            logger.info(
                "Upload succeeded for %s; upload_id=%s; moved to uploaded as %s and %s",
                pending_upload.video_path.name,
                upload_id,
                uploaded_upload.video_path.name,
                uploaded_upload.metadata_path.name,
            )
            return

        failed_upload = self._move_upload(uploading_upload, FAILED_DIR)
        logger.error(
            "Upload failed after %s attempts for %s; moved to failed as %s and %s",
            MAX_UPLOAD_ATTEMPTS,
            pending_upload.video_path.name,
            failed_upload.video_path.name,
            failed_upload.metadata_path.name,
        )

    def _move_upload(self, upload: UploadingUpload, destination_dir: Path) -> UploadingUpload:
        video_path, metadata_path = atomic_move_pair(
            upload.video_path,
            upload.metadata_path,
            destination_dir,
        )
        return UploadingUpload(
            video_path=video_path,
            metadata_path=metadata_path,
        )


def _load_metadata(metadata_path: Path) -> dict:
    with metadata_path.open("r", encoding="utf-8") as metadata_file:
        metadata = json.load(metadata_file)

    if not isinstance(metadata, dict):
        raise ValueError(f"Metadata must be a JSON object: {metadata_path}")

    return metadata
