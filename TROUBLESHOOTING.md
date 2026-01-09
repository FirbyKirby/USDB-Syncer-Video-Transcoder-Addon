# Video Transcoder — Troubleshooting

This guide helps diagnose and resolve common problems with the video transcoder addon.

## Is the addon running?

Checklist
- After starting USDB_Syncer, the log should include: Video Transcoder addon loaded
- The addon subscribes to [hooks.SongLoaderDidFinish](src/usdb_syncer/hooks.py:47) in [addons/video_transcoder/__init__.py](addons/video_transcoder/__init__.py)
- After a song download completes, look for log lines like: Analyzing video: ..., FFMPEG command: ..., Transcode completed in ...

Log file location
- Windows: %LocalAppData%/usdb_syncer/usdb_syncer.log
- macOS: ~/Library/Application Support/usdb_syncer/usdb_syncer.log
- Linux: ~/.local/share/usdb_syncer/usdb_syncer.log

Path is defined by [utils.AppPaths.log](src/usdb_syncer/utils.py:113).

## Common errors and fixes

1) FFMPEG not available - skipping video transcode
- Cause: USDB_Syncer cannot find ffmpeg/ffprobe
- Fix: Install FFMPEG and ensure ffmpeg and ffprobe are in your PATH, or set the FFMPEG folder in USDB_Syncer settings
- Verify: Run ffmpeg -version and ffprobe -version in a terminal

2) Failed to analyze video file
- Cause: ffprobe could not parse the source file
- Fix: Ensure the downloaded file is a valid video. Try re-downloading the song. Check that your FFMPEG installation works
- Where it happens: analysis in [video_analyzer.analyze_video()](addons/video_transcoder/video_analyzer.py:60)

3) Insufficient disk space for transcoding
- Cause: Free space below min_free_space_mb
- Fix: Free up disk space or lower general.min_free_space_mb in config
- Check setting: [config.GeneralConfig](addons/video_transcoder/config.py:64)

4) FFMPEG encoding failed or FFMPEG timeout after Ns
- Cause: Encoder error or operation exceeded general.timeout_seconds
- Fix: Try a faster preset or higher CRF. Verify your FFMPEG build supports the selected encoder (e.g., h264_qsv). Increase timeout_seconds if needed
- Where it happens: command execution in [transcoder.process_video()](addons/video_transcoder/transcoder.py:41)

5) Transcoded output verification failed
- Cause: Output was produced but could not be parsed by ffprobe
- Fix: Re-try with verify_output left enabled. Consider a different preset/CRF, or switch to H.264 for maximum compatibility
- Verification step occurs after encode in [transcoder.process_video()](addons/video_transcoder/transcoder.py:41)

6) Could not backup original
- Cause: File permission issues or destination in use
- Fix: Close media players, ensure write permissions on the song folder. Originals are renamed to name-source.ext using the suffix from [config.GeneralConfig.backup_suffix](addons/video_transcoder/config.py:72)

7) Could not update .txt #VIDEO header
- Cause: The song text file couldn’t be modified
- Fix: Ensure the .txt is writable. The update is performed by [sync_meta_updater.update_txt_video_header()](addons/video_transcoder/sync_meta_updater.py:130)

8) Hardware encoding requested but no suitable accelerator found. Falling back to software
- Cause: No supported accelerator detected (only Intel QuickSync is currently supported) while [config.GeneralConfig.hardware_encoding](addons/video_transcoder/config.py:64) is enabled
- Fix: Ensure an Intel iGPU with drivers is present and your FFMPEG build includes QSV encoders (h264_qsv, hevc_qsv, vp9_qsv, av1_qsv). Otherwise, encoding proceeds in software. You can also disable hardware encoding globally via [config.GeneralConfig.hardware_encoding](addons/video_transcoder/config.py:64)
- Detection/selection logic: [hwaccel.get_best_accelerator()](addons/video_transcoder/hwaccel.py:79), QuickSync implementation [hwaccel.QuickSyncAccelerator](addons/video_transcoder/hwaccel.py:121)

## Abort during transcode

Symptoms
- You clicked Abort and saw Transcode aborted by user in the log
- The video stopped quickly but you want to confirm cleanup or rollback
- Abort seems to take longer than expected

Explanation
- Abort is immediate. The addon detects aborts via [utils.is_aborted()](addons/video_transcoder/utils.py:84) and terminates the running FFMPEG process within ~500ms. FFMPEG is asked to exit cleanly first; if it does not, it is force-terminated: see [transcoder._execute_ffmpeg()](addons/video_transcoder/transcoder.py:331) and [transcoder._execute_ffmpeg()](addons/video_transcoder/transcoder.py:347)
- In a batch operation, the video currently being transcoded at the time of abort is correctly marked as "Aborted" in the final report, and any remaining videos are marked as "Aborted" (if they were selected) or "Skipped" (if they were not). If you choose to roll back, successfully transcoded videos are restored and marked as "Rolled Back" in the final report.

What to do
- Expect the active transcode to stop within ~500ms after clicking Abort. Give the UI a moment to refresh
- If it has not stopped after a couple of seconds, check the log for Transcode aborted by user and any FFMPEG shutdown messages. Rare OS scheduling or encoder stalls can delay termination briefly
- If FFMPEG becomes unresponsive, the general timeout still applies as a hard cap: [config.GeneralConfig.timeout_seconds](addons/video_transcoder/config.py:76). On timeout, the process is terminated in [transcoder._execute_ffmpeg()](addons/video_transcoder/transcoder.py:366)

Cleanup behavior
- Temporary .transcoding* files are removed automatically on abort or failure: cleanup paths in [transcoder.process_video()](addons/video_transcoder/transcoder.py:189) and [transcoder.process_video()](addons/video_transcoder/transcoder.py:213). Completed outputs remain. If rollback is enabled, you will be prompted to restore processed videos

## Why was my already-H.264 (or HEVC/VP8) video transcoded?

The addon now uses strict matching against your configuration. It will transcode even if the source codec is already Unity-compatible when:
- The codec does not match your target_codec (e.g., source is HEVC but target is h264)
- General caps are exceeded: resolution, FPS, or bitrate higher than configured maximums
- Codec settings do not match your target (per codec):
  - H.264: pixel_format or profile differ from your config
  - HEVC: pixel_format or profile differ from your config
  - VP8/VP9/AV1: must match the target codec

What you can do
- If you want to keep existing H.264s as-is, set your H.264 profile/pixel_format to match them
- Otherwise, keep your preferred settings and let the addon standardize the library during the next transcode pass

## How to check hardware encoding status

From logs
- When active, you will see a message about hardware encoding being used. Otherwise, a warning about falling back to software appears from [transcoder.process_video()](addons/video_transcoder/transcoder.py:41)

Note: If you set general.max_resolution or general.max_fps, the addon may disable hardware decoding for that run (it will log this decision) to avoid hardware decode + filter pipeline issues, while keeping hardware encoding enabled when possible. Control these via [config.GeneralConfig.hardware_decode](addons/video_transcoder/config.py:64) and [config.GeneralConfig.hardware_encoding](addons/video_transcoder/config.py:64).

AV1 specifics
- With hardware encoding enabled, AV1 uses QSV when available; otherwise it falls back to software encoders in order: libsvtav1 → libaom-av1. If your FFMPEG lacks SVT-AV1, expect libaom-av1 or software-only operation

## Batch transcoding (existing library)

If you already have a library of downloaded songs and want to convert them in bulk:
- Use the GUI menu: Tools → Batch Video Transcode
- A preview and selection dialog appears with filtering and live statistics
  - Orchestrator and preview: [addons/video_transcoder/batch_orchestrator.py](addons/video_transcoder/batch_orchestrator.py), [addons/video_transcoder/batch_preview_dialog.py](addons/video_transcoder/batch_preview_dialog.py)
  - Progress and abort: [addons/video_transcoder/batch_progress_dialog.py](addons/video_transcoder/batch_progress_dialog.py)
  - Results and export: [addons/video_transcoder/batch_results_dialog.py](addons/video_transcoder/batch_results_dialog.py) (summarizes success, failed, skipped, aborted, and rolled back items)
  - Estimation and space checks: [addons/video_transcoder/batch_estimator.py](addons/video_transcoder/batch_estimator.py)
  - Optional rollback protection: [addons/video_transcoder/rollback.py](addons/video_transcoder/rollback.py)

Common issues in the new workflow

1) Preview generation is taking a long time
- Cause: The system scans synchronized songs and runs ffprobe analysis per video; large libraries or slow disks increase time
- Fix:
  - Let the initial scan complete once; subsequent runs are faster with fewer candidates
  - Reduce the number of candidates by tightening your configuration so fewer videos qualify
  - Ensure ffprobe is on a fast local disk and your antivirus is not scanning video files
- Where it happens: preview generation in [BatchTranscodeOrchestrator._generate_preview()](addons/video_transcoder/batch_orchestrator.py:180), analysis in [video_analyzer.analyze_video()](addons/video_transcoder/video_analyzer.py:60)

2) Disk space estimate seems inaccurate
- Explanation: Estimates are heuristic and based on codec, CRF, resolution, and bitrate limits
- Fix:
  - Verify your CRF and preset choices; higher quality settings increase size
  - If you have max_bitrate_kbps set, the estimate will clamp to that value
  - Leave extra headroom beyond the estimate; the dialog disables Start if free space is below the required total
- Implementation: [BatchEstimator.estimate_output_size()](addons/video_transcoder/batch_estimator.py:19), [BatchEstimator.calculate_disk_space_required()](addons/video_transcoder/batch_estimator.py:200)

3) Rollback didn’t restore all videos
- Cause:
  - Backup files were moved or deleted outside the tool
  - Rollback protection was disabled, or permanent backups were not available
- Fix:
  - Re-run the batch and enable rollback protection in the preview dialog
  - Check the log for missing backup warnings during rollback
  - If permanent backups are enabled via configuration, verify originals with the configured suffix still exist
- Implementation: [RollbackManager.rollback_all()](addons/video_transcoder/rollback.py:90), manifest handling in [RollbackManager.enable_rollback()](addons/video_transcoder/rollback.py:66)

4) Export to CSV failed
- Cause: Destination not writable or file locked by another application
- Fix:
  - Choose a writable location (e.g., your Documents folder)
  - Close any application holding the CSV open and retry
  - Retry with a different filename
- Implementation: [BatchResultsDialog._export_to_csv()](addons/video_transcoder/batch_results_dialog.py:180)

5) Progress window does not update or abort seems delayed
- Explanation: UI updates depend on encoder output cadence; however, abort still stops the active transcode within ~500ms even if the UI lags briefly
- Fix:
  - Give the UI a moment to refresh after the abort; the batch will end immediately after the current process is terminated
  - If it does not stop within a couple of seconds, check the log for Transcode aborted by user and any FFMPEG shutdown messages
- Implementation: [BatchWorker.video_progress](addons/video_transcoder/batch_worker.py:31), abort path [BatchTranscodeOrchestrator.abort_batch()](addons/video_transcoder/batch_orchestrator.py:393) and [BatchTranscodeOrchestrator._handle_abort()](addons/video_transcoder/batch_orchestrator.py:363)

From command line
- List hardware encoders: ffmpeg -encoders | findstr qsv (Windows) or ffmpeg -encoders | grep qsv (macOS/Linux)
- Quick test encode: ffmpeg -f lavfi -i nullsrc=s=64x64:d=0.1 -c:v h264_qsv -f null -

## Restoring from Video Backups — troubleshooting

Entry point: Tools → Manage Video Backups...; run scan, select backups, then click Restore Selected in the selection dialog.

Symptoms
- The confirmation step warns about overwriting active videos
- Space to reclaim is not shown in the selection dialog when restoring
- A restore failed on one or more items

What restore does
- Replaces the active transcoded video with the selected backup file
- Before replacement, the current active video is saved alongside it with a .safety-[timestamp] suffix; creation occurs in [backup_manager.restore_backup()](addons/video_transcoder/backup_manager.py:231)

Common issues and fixes
1) Restore failed: Backup file missing
- Cause: The backup file no longer exists at the recorded path
- Fix: Re-scan in Tools → Manage Video Backups.... Verify the backup still exists next to the song’s video, then choose Restore Selected again

2) Restore failed: Permission denied
- Cause: The song folder or target file is read-only or locked by another app
- Fix: Close media players, ensure write permission to the song folder, and retry

3) I restored the wrong version — how do I undo?
- Find the safety copy created during restore in the same folder. Its name is the previous active file with a .safety-[timestamp] suffix
- To revert, rename the safety copy back to the active filename and delete the unwanted version if needed

4) Why is Total Space to Reclaim hidden?
- Space reclaim is only relevant when deleting backups. In restore mode the manager hides this metric by design

Access
- Single entry point: Tools → Manage Video Backups... (choose Delete Selected or Restore Selected in the selection dialog)

## Videos won’t play

 Try these steps
- Set target_codec to h264 in config and use high profile, pixel_format yuv420p in [config.H264Config](addons/video_transcoder/config.py:19). With strict matching, the addon will convert non-conforming inputs to these exact settings
- Ensure the file extension is .mp4 and the song’s #VIDEO header points to the new filename
- Confirm the addon updated metadata: the original was renamed to name-source.ext and the new file exists
- Re-run the download so the addon processes the video again

Compatibility notes
- H.264/AVC in MP4 is the safest choice
- HEVC/H.265 offers better compression
- VP8/VP9/AV1 are excellent open alternatives

## Verify FFMPEG is working

Run these in a terminal
- ffmpeg -version
- ffprobe -version
- ffmpeg -encoders | grep -E "h264_qsv|hevc_qsv|vp9_qsv|av1_qsv"  # Check for QSV support

If not found, install FFMPEG and add it to your PATH, or set an explicit FFMPEG directory in USDB_Syncer settings. USDB_Syncer’s availability check is implemented by [utils.ffmpeg_is_available()](src/usdb_syncer/utils.py:364).

## How to report issues

Include the following in your report
- USDB_Syncer version and OS
- CPU/GPU details (especially whether you have Intel QuickSync)
- The contents of addons/video_transcoder/config.json (especially auto_transcode_enabled)
- A short excerpt of usdb_syncer.log around the time of the failure (redact personal paths if needed)
- The exact error message (copy from the log)

Where to look in code
- Transcode pipeline: [transcoder.process_video()](addons/video_transcoder/transcoder.py:41)
- Analysis: [video_analyzer.analyze_video()](addons/video_transcoder/video_analyzer.py:58)
- Codec command builders: [addons/video_transcoder/codecs.py](addons/video_transcoder/codecs.py)
- Hardware selection: [hwaccel.get_best_accelerator()](addons/video_transcoder/hwaccel.py:79), [hwaccel.QuickSyncAccelerator](addons/video_transcoder/hwaccel.py:121)
- Sync updates: [sync_meta_updater.update_sync_meta_video()](addons/video_transcoder/sync_meta_updater.py:25)
