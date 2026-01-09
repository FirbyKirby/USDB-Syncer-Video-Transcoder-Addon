"""Batch transcoding for existing video library.

This module follows the architecture plan's batch processing goal:
- Find existing videos managed by SyncMeta
- Reuse the same core transcoding engine
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Iterator

from usdb_syncer import SongId, settings
from usdb_syncer.logger import song_logger
from usdb_syncer.sync_meta import SyncMeta
from usdb_syncer.usdb_song import UsdbSong

from .transcoder import process_video
from .utils import is_aborted
from .video_analyzer import VideoInfo, analyze_video, needs_transcoding

if TYPE_CHECKING:
    from .config import TranscoderConfig

_logger = logging.getLogger(__name__)


@dataclass
class BatchResult:
    """Result of a batch transcoding operation."""

    total: int
    successful: int
    skipped: int
    failed: int
    errors: list[tuple[int, str]]  # song_id, error_message


def find_videos_needing_transcode(
    cfg: "TranscoderConfig",
    song_dir: Path | None = None,
) -> Iterator[tuple[SongId, Path, VideoInfo]]:
    """Yield (song_id, video_path, video_info) for videos that need transcoding."""

    if song_dir is None:
        song_dir = settings.get_song_dir()

    for sync_meta in SyncMeta.get_in_folder(song_dir):
        video_path = sync_meta.path.parent / sync_meta.video.file.fname if sync_meta.video and sync_meta.video.file and sync_meta.video.file.fname else None
        if not video_path or not video_path.exists():
            continue

        info = analyze_video(video_path)
        if not info:
            _logger.warning(f"Could not analyze video: {video_path}")
            continue

        if needs_transcoding(info, cfg):
            yield sync_meta.song_id, video_path, info


