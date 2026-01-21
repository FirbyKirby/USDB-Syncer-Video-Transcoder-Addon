"""SQLite-based cache for loudness analysis results.

This module provides persistent caching of loudness measurements to avoid
repeated analysis of the same files with the same settings.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .audio_normalizer import LoudnormMeasurements, LoudnormTargets

_logger = logging.getLogger(__name__)

# Addon version for cache invalidation
ADDON_VERSION = "1.0.0"


@dataclass(frozen=True)
class TargetSettings:
    """Settings that affect analysis results."""

    normalization_method: str  # "loudnorm" or "replaygain"
    target_i: float
    target_tp: float
    target_lra: float
    tolerance_preset: str  # "strict", "balanced", "relaxed"


@dataclass(frozen=True)
class CacheEntry:
    """Cached analysis result."""

    file_path: str
    file_mtime: int
    file_size: int
    normalization_method: str
    target_i: float
    target_tp: float
    target_lra: float
    measurements: LoudnormMeasurements
    analyzed_at: int  # unix timestamp
    addon_version: str


class LoudnessCache:
    """SQLite-based cache for loudness analysis results."""

    def __init__(self, cache_path: Path) -> None:
        """Initialize cache with database path."""
        self.cache_path = cache_path
        self._connection: Optional[sqlite3.Connection] = None
        self._ensure_connection()

    def _ensure_connection(self) -> sqlite3.Connection:
        """Get or create database connection."""
        if self._connection is None:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self._connection = sqlite3.connect(str(self.cache_path))
            self._create_schema()
        return self._connection

    def _create_schema(self) -> None:
        """Create database tables if they don't exist."""
        conn = self._ensure_connection()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS loudnorm_analysis (
                id INTEGER PRIMARY KEY,
                path TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                mtime_ns INTEGER NOT NULL,
                settings_hash TEXT NOT NULL,
                measured_I REAL NOT NULL,
                measured_TP REAL NOT NULL,
                measured_LRA REAL NOT NULL,
                measured_thresh REAL NOT NULL,
                offset REAL NOT NULL,
                raw_json TEXT,
                created_at INTEGER NOT NULL,
                addon_version TEXT NOT NULL,
                UNIQUE(path, size_bytes, mtime_ns, settings_hash)
            )
        """)
        conn.commit()

    def _get_settings_hash(self, target_settings: TargetSettings) -> str:
        """Generate hash for target settings."""
        key_parts = [
            target_settings.normalization_method,
            f"{target_settings.target_i:.3f}",
            f"{target_settings.target_tp:.3f}",
            f"{target_settings.target_lra:.3f}",
            target_settings.tolerance_preset,
        ]
        key_str = "|".join(key_parts)
        return hashlib.sha256(key_str.encode()).hexdigest()

    def get(self, file_path: Path, target_settings: TargetSettings) -> Optional[CacheEntry]:
        """Retrieve cached result if valid."""
        try:
            conn = self._ensure_connection()
            settings_hash = self._get_settings_hash(target_settings)

            # Get file stats
            stat = file_path.stat()
            file_size = stat.st_size
            mtime_ns = stat.st_mtime_ns

            cursor = conn.execute("""
                SELECT path, size_bytes, mtime_ns, measured_I, measured_TP, measured_LRA,
                       measured_thresh, offset, raw_json, created_at, addon_version
                FROM loudnorm_analysis
                WHERE path = ? AND size_bytes = ? AND mtime_ns = ? AND settings_hash = ?
                ORDER BY created_at DESC
                LIMIT 1
            """, (str(file_path), file_size, mtime_ns, settings_hash))

            row = cursor.fetchone()
            if row is None:
                return None

            path, size_bytes, mtime_ns, measured_I, measured_TP, measured_LRA, measured_thresh, offset, raw_json, created_at, addon_version = row

            # Reconstruct measurements
            measurements = LoudnormMeasurements(
                measured_I=measured_I,
                measured_TP=measured_TP,
                measured_LRA=measured_LRA,
                measured_thresh=measured_thresh,
                offset=offset,
                raw=eval(raw_json) if raw_json else {},  # Safe since we control the data
            )

            return CacheEntry(
                file_path=path,
                file_mtime=mtime_ns,
                file_size=size_bytes,
                normalization_method=target_settings.normalization_method,
                target_i=target_settings.target_i,
                target_tp=target_settings.target_tp,
                target_lra=target_settings.target_lra,
                measurements=measurements,
                analyzed_at=created_at,
                addon_version=addon_version,
            )

        except (OSError, sqlite3.Error) as e:
            _logger.warning(f"Cache read error for {file_path}: {e}")
            return None

    def put(self, file_path: Path, target_settings: TargetSettings, measurements: LoudnormMeasurements) -> None:
        """Store analysis result in cache."""
        try:
            conn = self._ensure_connection()
            settings_hash = self._get_settings_hash(target_settings)

            # Get file stats
            stat = file_path.stat()
            file_size = stat.st_size
            mtime_ns = stat.st_mtime_ns
            now = int(time.time())

            # Insert or replace
            conn.execute("""
                INSERT OR REPLACE INTO loudnorm_analysis
                (path, size_bytes, mtime_ns, settings_hash, measured_I, measured_TP, measured_LRA,
                 measured_thresh, offset, raw_json, created_at, addon_version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                str(file_path),
                file_size,
                mtime_ns,
                settings_hash,
                measurements.measured_I,
                measurements.measured_TP,
                measurements.measured_LRA,
                measurements.measured_thresh,
                measurements.offset,
                repr(measurements.raw),  # Store as string representation
                now,
                ADDON_VERSION,
            ))
            conn.commit()

        except (OSError, sqlite3.Error) as e:
            _logger.warning(f"Cache write error for {file_path}: {e}")

    def invalidate(self, file_path: Path) -> None:
        """Remove all entries for a file."""
        try:
            conn = self._ensure_connection()
            conn.execute("DELETE FROM loudnorm_analysis WHERE path = ?", (str(file_path),))
            conn.commit()
        except sqlite3.Error as e:
            _logger.warning(f"Cache invalidation error for {file_path}: {e}")

    def cleanup_old_entries(self, days: int = 90) -> None:
        """Remove entries older than specified days."""
        try:
            conn = self._ensure_connection()
            cutoff = int(time.time()) - (days * 24 * 60 * 60)
            cursor = conn.execute("DELETE FROM loudnorm_analysis WHERE created_at < ?", (cutoff,))
            deleted_count = cursor.rowcount
            conn.commit()
            if deleted_count > 0:
                _logger.info(f"Cleaned up {deleted_count} old cache entries")
        except sqlite3.Error as e:
            _logger.warning(f"Cache cleanup error: {e}")

    def close(self) -> None:
        """Close database connection."""
        if self._connection:
            self._connection.close()
            self._connection = None

    def __enter__(self) -> LoudnessCache:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


def get_cache_path() -> Path:
    """Return path to cache database in USDB Syncer data directory."""
    from usdb_syncer.utils import AppPaths
    return AppPaths.db.parent / "transcoder_loudness_cache.sqlite"