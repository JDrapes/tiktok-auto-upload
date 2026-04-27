import os
from pathlib import Path
from uuid import uuid4


def ensure_directories(paths: list[Path]) -> None:
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


def atomic_move(source: Path, destination_dir: Path) -> Path:
    """Move a file into destination_dir with an atomic rename on one filesystem."""
    source = source.resolve()
    destination_dir.mkdir(parents=True, exist_ok=True)

    destination = _available_destination(destination_dir / source.name)
    os.replace(source, destination)
    return destination


def atomic_move_pair(video_path: Path, metadata_path: Path, destination_dir: Path) -> tuple[Path, Path]:
    """Move a video and metadata file while preserving their shared stem."""
    video_path = video_path.resolve()
    metadata_path = metadata_path.resolve()
    destination_dir.mkdir(parents=True, exist_ok=True)

    destination_stem = _available_pair_stem(
        destination_dir=destination_dir,
        stem=video_path.stem,
        video_suffix=video_path.suffix,
        metadata_suffix=metadata_path.suffix,
    )
    video_destination = destination_dir / f"{destination_stem}{video_path.suffix}"
    metadata_destination = destination_dir / f"{destination_stem}{metadata_path.suffix}"

    os.replace(video_path, video_destination)
    os.replace(metadata_path, metadata_destination)
    return video_destination, metadata_destination


def _available_destination(destination: Path) -> Path:
    if not destination.exists():
        return destination

    stem = destination.stem
    suffix = destination.suffix
    parent = destination.parent

    while True:
        candidate = parent / f"{stem}-{uuid4().hex[:8]}{suffix}"
        if not candidate.exists():
            return candidate


def _available_pair_stem(
    destination_dir: Path,
    stem: str,
    video_suffix: str,
    metadata_suffix: str,
) -> str:
    if not (destination_dir / f"{stem}{video_suffix}").exists() and not (
        destination_dir / f"{stem}{metadata_suffix}"
    ).exists():
        return stem

    while True:
        candidate = f"{stem}-{uuid4().hex[:8]}"
        if not (destination_dir / f"{candidate}{video_suffix}").exists() and not (
            destination_dir / f"{candidate}{metadata_suffix}"
        ).exists():
            return candidate
