# Video Transcoder Addon — Final Validation Test Plan

Scope: [`addons/video_transcoder/`](addons/video_transcoder/TEST_PLAN.md)

This plan is designed to maximize confidence in primary use cases while remaining time-efficient for a large existing library:

- Library size: 1238 songs total, 1001 videos.
- Source formats: predominantly AV1 with some H264.
- Platform assumption: Windows with Intel iGPU QuickSync available.
- Primary target codec: H.264 in MP4.
- Secondary validation: small VP8 pass.
- Fully destructive testing is permitted (library can be re-downloaded).
- Automatic download + auto-transcode is deprioritized (already substantially tested).

Key implementation behaviors referenced by this plan:

- Single-video pipeline entry: [`transcoder.process_video()`](addons/video_transcoder/transcoder.py:41)
- Strict transcode decision: [`video_analyzer.needs_transcoding()`](addons/video_transcoder/video_analyzer.py:232)
- Sync metadata and #VIDEO tag update: [`sync_meta_updater.update_sync_meta_video()`](addons/video_transcoder/sync_meta_updater.py:25)
- Batch workflow entry: [`BatchTranscodeOrchestrator.start_batch_workflow()`](addons/video_transcoder/batch_orchestrator.py:170)
- Rollback manager: [`RollbackManager`](addons/video_transcoder/rollback.py:54)
- Backup discovery/deletion: [`backup_manager.discover_backups()`](addons/video_transcoder/backup_manager.py:44)
- Hardware acceleration selection: [`hwaccel.get_best_accelerator()`](addons/video_transcoder/hwaccel.py:79)

---

## 1) Goals and coverage map

This test suite provides coverage of:

1. Core functionality
2. Edge cases
3. Error handling
4. User interface interactions
5. Performance characteristics with 1238 songs / 1001 videos
6. Video format handling for AV1 and H264 sources (plus VP8 as secondary target)
7. Data integrity operations (SyncMeta + #VIDEO + filesystem)
8. Destructive operations to validate robustness

Non-goals / deprioritized:

- End-to-end automatic download behavior validation (already tested); only a minimal sanity check is included.

---

## 2) Test environment prerequisites

### 2.1 Required external dependencies

- `ffmpeg` and `ffprobe` installed and discoverable by USDB Syncer.
- For QuickSync validation: FFmpeg build includes QSV support, and the machine has Intel iGPU + drivers.

Evidence to capture:

- Copy/paste of `ffmpeg -version` and `ffprobe -version` output.
- Copy/paste of `ffmpeg -encoders` filtered for QSV (h264_qsv, hevc_qsv, vp9_qsv, av1_qsv).

### 2.2 Test library and safety

- Ensure the library folder is local (not network/NAS) for performance tests, if possible.
- Ensure sufficient free disk space for:
  - outputs
  - temp `.transcoding*` files
  - optional backups and rollback backups

Destructive testing note:

- This plan includes tests that intentionally delete, corrupt, or rename video files and backups.
- Before starting destructive phases, confirm you can re-download the full library.

### 2.3 Instrumentation and artifacts

Collect and retain for each test session:

- USDB Syncer log excerpt covering each operation (start → end).
- Exported CSV from Batch Results (when applicable).
- For any failure: include FFmpeg command line (logged) and the error message.

---

## 3) Test data selection (time-efficient)

Create a “representative set” of videos to avoid repeatedly testing on the full 1001-video corpus.

### 3.1 Recommended representative set (12–20 videos)

Select specific songs/videos that match these attributes:

- AV1 source in `.mkv` (with audio)
- AV1 source in `.mp4` (with audio) if present
- AV1 source without audio (if available)
- H264 source already matching your intended H.264 config (expected to SKIP)
- H264 source with different pixel format than target (expected to TRANSCODE)
- H264 source with profile mismatch vs target (expected to TRANSCODE)
- Container mismatch (e.g., H264 in `.mkv` but target container is `.mp4` → expected TRANSCODE)
- High FPS source (e.g., > 60) to validate FPS capping when enabled
- High resolution source (e.g., 4K) to validate resolution capping when enabled
- Odd aspect ratio (e.g., vertical or ultrawide) to validate scale/pad behavior
- Very short video (< 5s) to validate progress parsing / edge durations
- Longest video in library (to validate timeout behavior and performance expectations)

If any of the above categories do not exist in your library, substitute a nearby proxy and note it.

### 3.2 VP8 target validation subset (3–5 videos)

From the representative set, choose:

- 2 AV1 sources with audio
- 1 H264 source with audio
- Optional: 1 without audio

---

## 4) Test execution order (sequential)

The suite is organized as “P0 then P1/P2”, where:

- P0 = must-pass for release confidence.
- P1 = high-value depth/coverage.
- P2 = optional / exploratory / extended.

Each test includes prerequisites, steps, expected results, and evidence.

---

## 5) P0 — Core functionality and integrity

### P0-01 — Addon loads and Tools menu entries exist

Prerequisites:

- USDB Syncer installed with addon folder present.

Steps:

1. Launch USDB Syncer.
2. Confirm the addon reports itself loaded in the log.
3. Open the Tools menu.

Expected:

- Tools contains:
  - Transcoder Settings
  - Batch Video Transcode
  - Manage Video Backups

Evidence:

- Screenshot of Tools menu.
- Log line confirming addon loaded.

### P0-02 — Transcoder Settings UI: persistence and correctness

Prerequisites:

- Addon config exists at [`addons/video_transcoder/config.json`](addons/video_transcoder/config.json).

Steps:

1. Open Tools → Transcoder Settings.
2. Set target codec to `h264` and container `mp4`.
3. Toggle:
   - Hardware Encoding ON
   - Hardware Decoding ON
   - Verify Output ON
   - Backup Original ON (backup suffix default)
4. Save.
5. Re-open settings dialog.

Expected:

- All selections persist and re-load correctly.
- Backup suffix field visibility matches the Backup checkbox behavior.

Evidence:

- Screenshot before Save and after re-open.

### P0-03 — Strict decision logic (skip vs transcode)

Prerequisites:

- Representative set contains at least:
  - one H264 source already compliant
  - one non-compliant (e.g., AV1 source)

Steps:

1. Configure target codec: `h264`.
2. Ensure force transcode is OFF.
3. Process the compliant H264 video (via a controlled operation; batch preview is fine).
4. Process the non-compliant AV1 video.

Expected:

- Compliant H264 is skipped with an explicit “skipping transcode” decision.
- AV1 is identified as requiring transcode.

Evidence:

- Log excerpt showing decision path and reasons (strict matching).

### P0-04 — Single-video transcode: AV1 → H264/MP4 with QuickSync

Prerequisites:

- Pick an AV1 source with audio.
- Hardware encoding enabled.

Steps:

1. Ensure target codec is `h264`, container `mp4`.
2. Transcode the selected AV1 video.
3. Verify output file exists and is playable in your target player.

Expected:

- FFmpeg command uses `h264_qsv` when QSV is available.
- Output container is `.mp4`.
- Audio handling:
  - If source audio codec is MP4-compatible (AAC/MP3/ALAC), audio is copied.
  - Otherwise, audio is encoded to AAC.
- Output verification succeeds (when enabled).

Evidence:

- Log excerpt including FFmpeg command and completion summary.
- `ffprobe` output of resulting file showing codec is h264.

### P0-05 — Backup creation + atomic replacement behavior

Prerequisites:

- Backup Original ON, suffix default `-source`.

Steps:

1. Choose a video that will transcode (AV1 → H264).
2. Transcode.
3. Inspect the song folder.

Expected:

- A backup of the original exists as `<stem>-source<orig_ext>`.
- The active video filename matches the new container (e.g., `.mp4`).
- No stray `.transcoding*` temp files remain.

Evidence:

- Screenshot or listing of song folder showing:
  - active video
  - backup video
  - absence of `.transcoding*`

### P0-06 — SyncMeta + #VIDEO tag integrity

Prerequisites:

- A song with a `.txt` file and a video.

Steps:

1. Transcode the song’s video to a new filename/extension.
2. Open the song `.txt` file.
3. Confirm the `#VIDEO:` line matches the new filename.
4. Confirm SyncMeta points to the new filename and mtime is updated.

Expected:

- `#VIDEO:` header updated or inserted.
- SyncMeta video resource file updated while preserving the original resource ID.
- No re-download loop occurs on subsequent sync check.

Evidence:

- Before/after excerpt of the `.txt` showing the `#VIDEO:` line.
- Log excerpt confirming SyncMeta update.

---

## 6) P0 — Batch workflow and UI interactions

### P0-07 — Batch preview scan correctness and UI responsiveness

Prerequisites:

- Target codec: `h264`.
- force transcode OFF.

Steps:

1. Launch Tools → Batch Video Transcode.
2. Allow scan to complete.
3. Validate the candidate list includes expected AV1 sources.
4. Use filter box to search by a known title/artist.

Expected:

- Scan completes without crashing.
- Preview table populates with correct columns.
- Filtering hides non-matching rows and de-selects hidden rows.
- Statistics update as selection changes.

Evidence:

- Screenshot of preview dialog with a filter applied.

### P0-08 — Disk space gating in preview dialog

Prerequisites:

- Any candidate list.

Steps:

1. Temporarily set “Min Free Space” to a value higher than your current free space.
2. Re-open Batch Video Transcode preview.

Expected:

- Start button is disabled due to insufficient space.
- UI indicates required vs available space.

Evidence:

- Screenshot showing Start disabled and red indicator.

### P0-09 — Batch transcode subset (10–20): success path

Prerequisites:

- Choose 10–20 candidates from the representative set.
- Rollback OFF.

Steps:

1. Start batch.
2. Observe per-video progress updates (percent/fps/speed).
3. Let it complete.
4. Open results dialog and export CSV.

Expected:

- Progress dialog remains responsive.
- Results show correct success/failure counts.
- CSV export succeeds.

Evidence:

- Screenshot of results summary.
- Exported CSV file.

### P0-10 — Abort behavior: immediate stop of active transcode

Prerequisites:

- Choose a long video for the batch to ensure time to abort mid-transcode.

Steps:

1. Start batch transcode.
2. While a video is actively transcoding, click Abort.

Expected:

- Active FFmpeg process terminates promptly (logs indicate aborted by user).
- Temporary `.transcoding*` output is cleaned.
- Remaining selected items are marked aborted; unselected are skipped.

Evidence:

- Log excerpt showing abort requested and FFmpeg termination.
- Results dialog showing aborted statuses.

---

## 7) P1 — Error handling and edge cases

### P1-01 — ffprobe analysis failure handling

Goal: Validate graceful handling when analysis fails.

Prerequisites:

- Choose any existing video.

Steps:

1. Create a corrupted copy of a video (e.g., truncate file or overwrite the first few KB).
2. Ensure the corrupted file is the active video for a test song (renaming is fine for destructive test).
3. Run batch preview or single transcode attempt.

Expected:

- Candidate is skipped or fails gracefully without crashing.
- Error reported as analysis failure.

Evidence:

- Log excerpt indicating ffprobe failure / failed analysis.

### P1-02 — FFmpeg timeout path

Prerequisites:

- Pick a long video.

Steps:

1. Set timeout to an intentionally low value.
2. Start transcode.

Expected:

- FFmpeg is terminated due to timeout.
- Temp output is cleaned up.
- Result is marked failed with timeout message.

Evidence:

- Log excerpt showing timeout and termination.

### P1-03 — Permissions: backup creation failure

Prerequisites:

- Choose a song directory and make it read-only (or deny write permission).

Steps:

1. Attempt transcode with Backup Original ON.

Expected:

- Backup rename failure is logged as warning.
- Transcode still completes if output can be written; if not, it fails gracefully.
- No partial temp output remains.

Evidence:

- Log excerpt showing backup failure warning and final outcome.

### P1-04 — Container mismatch triggers transcode even when codec matches

Prerequisites:

- Obtain an H264 source in a non-target container (e.g., `.mkv`) while target container is `.mp4`.

Steps:

1. Configure target `h264` + container `mp4`.
2. Run decision + transcode.

Expected:

- Video is transcoded due to container mismatch.

Evidence:

- Log excerpt showing container mismatch reason.

### P1-05 — Audio transcoding decisions

Prerequisites:

- At least two sources:
  - one with AAC/MP3 audio
  - one with Opus/Vorbis audio

Steps:

1. Transcode both to H264/MP4.

Expected:

- AAC/MP3 audio copied.
- Opus/Vorbis re-encoded to AAC.

Evidence:

- `ffprobe` output for both resulting files.

### P1-06 — Force Transcode overrides skip logic

Prerequisites:

- Pick a video that already matches the target H.264 settings and container (the one used in P0-03).

Steps:

1. Enable Force Transcode in settings.
2. Process the already-compliant video.

Expected:

- Transcode proceeds even though the file would normally be skipped.
- Output verification passes and no `.transcoding*` temp files remain.

Evidence:

- Log excerpt showing force transcode decision.

### P1-07 — Filters disable hardware decode but keep hardware encode when possible

Goal: Validate the “hardware decode may be disabled when filters requested” behavior.

Prerequisites:

- Hardware Encoding ON.
- Hardware Decoding ON.

Steps:

1. Configure a resolution cap and/or FPS cap (manual or via USDB integration).
2. Transcode an AV1 source.

Expected:

- Logs indicate hardware decoding is disabled for that run due to filters.
- Hardware encoding remains enabled if QSV is available.

Evidence:

- Log excerpt showing decode disabled due to filters and encode using QuickSync.

---

## 8) P1 — Rollback robustness (batch)

### P1-08 — Rollback: abort then restore

Prerequisites:

- Choose 10 candidates including at least one long video.
- Enable rollback in preview dialog.

Steps:

1. Start batch.
2. After 1–3 successes, abort.
3. When prompted, choose YES to rollback.

Expected:

- Original videos restored from rollback temp backups.
- SyncMeta updated back to original.
- Results show “rolled_back” for successfully restored items.

Evidence:

- Screenshot of rollback prompt and completion message.
- Spot-check restored file matches expected (codec/container per original).

### P1-09 — Rollback directory cleanup

Prerequisites:

- Same as P1-06.

Steps:

1. After rollback completes, confirm the rollback temp directory was removed.

Expected:

- Rollback directory is deleted.
- No manifest/backups remain in temp.

Evidence:

- Filesystem check showing absence of rollback directory.

---

## 9) P1 — Backup management UI and destructive operations

### P1-10 — Backup discovery correctness

Prerequisites:

- Ensure you have multiple `-source` backups present (from earlier tests).

Steps:

1. Open Tools → Manage Video Backups.
2. Run scan.

Expected:

- Backup list includes:
  - backups referenced by SyncMeta custom data
  - backups discovered by suffix pattern
- Active transcoded video is never listed as deletable backup.

Evidence:

- Screenshot of selection dialog list.

### P1-11 — Backup deletion flow: confirm, cancel, and error reporting

Prerequisites:

- At least 5 backups discovered.

Steps:

1. Select 5 backups.
2. Start deletion and then cancel mid-way.
3. Re-run and complete deletion.
4. Introduce a failure (make one backup read-only) and delete again.

Expected:

- Cancel stops further deletions; already-deleted files remain deleted.
- Results dialog reports success/failure counts and lists errors.
- SyncMeta `transcoder_source_fname` is cleared when that exact backup file is deleted.

Evidence:

- Screenshot of results dialog with at least one failure.

---

## 10) P2 — Performance characterization at full library scale

Goal: Validate acceptable responsiveness and stability with 1238 songs / 1001 videos without necessarily transcoding all videos.

### P2-01 — Full-library scan time and stability

Steps:

1. Launch Batch Video Transcode.
2. Allow full scan to complete.
3. Record scan duration and number of candidates found.

Expected:

- Scan completes without crashing.
- UI remains responsive.
- Candidate count is plausible given current config and existing library state.

Evidence:

- Log excerpt with scan duration and candidate count.

### P2-02 — Throughput sampling

Steps:

1. Select 20 candidates representative of typical durations/resolutions.
2. Run batch with rollback OFF.
3. Compute approximate throughput from results (realtime speed, wall time).

Expected:

- H264 QSV achieves materially faster-than-realtime on typical content.
- No runaway memory growth / UI freeze.

Evidence:

- Results CSV and log excerpt showing “x realtime” speed.

---

## 11) P2 — Secondary codec validation (VP8)

### P2-03 — VP8/WebM transcode subset

Prerequisites:

- Select 3–5 videos from the VP8 subset.

Steps:

1. Change target codec to `vp8` (container `webm`).
2. Batch transcode subset.

Expected:

- Output codec is VP8, container is WebM.
- Audio is copied if Opus/Vorbis, otherwise encoded to Opus.
- Playback works in your target environment.

Evidence:

- `ffprobe` output for one resulting file.

---

## 12) Minimal auto-transcode sanity (deprioritized)

### P2-04 — Auto-transcode runs post-download (smoke only)

Prerequisites:

- auto-transcode enabled.

Steps:

1. Download a single song known to have an AV1 video.
2. Observe post-download logs.

Expected:

- Video analysis runs.
- Transcode runs if needed.

Evidence:

- Log excerpt showing post-download hook activity.

---

## 13) Exit criteria

Release confidence is considered high if:

- All P0 tests pass.
- No P1 test reveals data integrity issues (SyncMeta or `#VIDEO:` mismatches), orphaned `.transcoding*` files, or rollback/backup deletion removing active videos.
- Performance characterization (P2) shows stable scanning and responsive UI at full-library scale.
