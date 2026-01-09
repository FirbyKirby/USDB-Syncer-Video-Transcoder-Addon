# Batch Transcoding — Comprehensive Guide

This guide explains the end-to-end workflow for batch transcoding synchronized videos with the Video Transcoder addon. It covers user experience, advanced options, troubleshooting, and technical details.

## 1) Overview

Batch transcoding converts an existing library of synchronized videos to your configured target codec and limits in one operation. Use it when:
- You changed codec or quality settings and want your library standardized
- You enabled strict matching and want non-conforming videos updated
- You migrated devices and need a uniform, compatible format

Entry point: Tools → Batch Video Transcode. Internally this launches [BatchTranscodeOrchestrator.start_batch_workflow()](addons/video_transcoder/batch_orchestrator.py:164).

## 2) Prerequisites

- FFMPEG/FFPROBE available and working. Verification steps are in [addons/video_transcoder/TROUBLESHOOTING.md](addons/video_transcoder/TROUBLESHOOTING.md)
- Sufficient free disk space for outputs, temporary files, and optional backups. The preview dialog validates this before you can start
- Optional hardware acceleration supported and enabled via [config.GeneralConfig](addons/video_transcoder/config.py:64)

Warnings
- Ensure plenty of free space. The dialog will compute required space, but real outputs can vary
- Clicking Abort immediately terminates the active transcode (within ~500ms) and ends the batch. If rollback is enabled, you are prompted to restore processed videos

## 3) Step-by-Step Walkthrough

1. Launching the batch transcode
- Open Tools → Batch Video Transcode
- Orchestrator: [BatchTranscodeOrchestrator.start_batch_workflow()](addons/video_transcoder/batch_orchestrator.py:164)

2. Understanding the preview dialog
- The orchestrator scans synchronized songs, identifies videos that need transcoding, analyzes them, and computes estimates
  - Preview generation: [BatchTranscodeOrchestrator._generate_preview()](addons/video_transcoder/batch_orchestrator.py:180)
  - Analysis: [video_analyzer.analyze_video()](addons/video_transcoder/video_analyzer.py:60)
  - Decision logic: [video_analyzer.needs_transcoding()](addons/video_transcoder/video_analyzer.py:198)
  - Size/time estimation: [BatchEstimator.estimate_output_size()](addons/video_transcoder/batch_estimator.py:19), [BatchEstimator.estimate_transcode_time()](addons/video_transcoder/batch_estimator.py:89)

3. Filtering and selecting videos
- Use the filter box to search by title, artist, codec, etc.
- Select All / Deselect All apply to currently visible rows
- Live statistics update as you select or filter
- Dialog: [addons/video_transcoder/batch_preview_dialog.py](addons/video_transcoder/batch_preview_dialog.py)
- Stats and validation: [BatchPreviewDialog._update_statistics()](addons/video_transcoder/batch_preview_dialog.py:170) using [BatchEstimator.calculate_disk_space_required()](addons/video_transcoder/batch_estimator.py:200) and [BatchEstimator.get_free_disk_space()](addons/video_transcoder/batch_estimator.py:181)

4. Understanding statistics
- Selected count and total videos
- Estimated total time for the selected set
- Required disk space vs current free space, with red/green indicator; Start is disabled when space is insufficient

5. Rollback protection option
- Enable rollback to allow restoration of processed videos if the batch is aborted
- Temporary vs permanent backups are supported (see Advanced Features)
- Rollback manager: [RollbackManager](addons/video_transcoder/rollback.py) invoked from [BatchTranscodeOrchestrator._execute_batch()](addons/video_transcoder/batch_orchestrator.py:301) and finalized in [BatchTranscodeOrchestrator._handle_abort()](addons/video_transcoder/batch_orchestrator.py:363)

6. Starting the transcode
- Click Start Transcoding; the orchestrator launches the background worker
- Worker thread: [BatchWorker](addons/video_transcoder/batch_worker.py) processes videos and emits per-video signals

7. Monitoring progress
- A modal progress dialog displays the current video along with percent, fps, speed, elapsed, and ETA per video, plus overall progress
- Progress UI: [addons/video_transcoder/batch_progress_dialog.py](addons/video_transcoder/batch_progress_dialog.py)
- Signals: [BatchWorker.video_progress](addons/video_transcoder/batch_worker.py:29), [BatchProgressDialog.abort_requested](addons/video_transcoder/batch_progress_dialog.py:27)

8. Handling abort
- Click the Abort button at any time
- The current video stops within ~500ms and the batch ends. If rollback is enabled, you are prompted to restore processed videos
- Temporary .transcoding* files are cleaned automatically; only completed outputs remain
- Orchestrator: [BatchTranscodeOrchestrator.abort_batch()](addons/video_transcoder/batch_orchestrator.py:393) and [BatchTranscodeOrchestrator._handle_abort()](addons/video_transcoder/batch_orchestrator.py:363)

9. Understanding results
- Summary shows counts of success, failed, skipped, aborted, and rolled back, total elapsed time, and net space saved
- Detailed table lists each video’s status, change summary, and any error
- Results dialog: [addons/video_transcoder/batch_results_dialog.py](addons/video_transcoder/batch_results_dialog.py)

10. Exporting reports
- Export the detailed results to CSV or copy a text summary to the clipboard
- CSV: [BatchResultsDialog._export_to_csv()](addons/video_transcoder/batch_results_dialog.py:180)

## 4) Advanced Features

Rollback system details
- When enabled, the orchestrator activates rollback tracking and records each successful transcode
- Manager: [RollbackManager](addons/video_transcoder/rollback.py), enabling via [RollbackManager.enable_rollback()](addons/video_transcoder/rollback.py:66), restoration via [RollbackManager.rollback_all()](addons/video_transcoder/rollback.py:90)

Interaction with backup settings
- If [config.GeneralConfig.backup_original](addons/video_transcoder/config.py:64) is true, originals are preserved automatically using the configured suffix
- With rollback enabled, backups may be temporary if you choose; temporary backups are cleaned after a fully successful batch by [RollbackManager.cleanup_temporary_backups()](addons/video_transcoder/rollback.py:132)

Temporary vs permanent backups
- Permanent: controlled by your configuration’s backup_original setting
- Temporary: used only for this batch to enable rollback on abort, then removed on success

USDB integration for resolution/FPS
- The preview shows whether resolution/FPS limits are sourced from USDB Syncer settings or exact values
- Display formatting: [BatchTranscodeOrchestrator._format_resolution_display()](addons/video_transcoder/batch_orchestrator.py:399), [BatchTranscodeOrchestrator._format_fps_display()](addons/video_transcoder/batch_orchestrator.py:409)

## 5) Troubleshooting

Common issues and solutions
- Preview generation is slow
  - Large libraries or network/NAS storage increase scan time; allow the first pass to complete and consider filtering
- Disk space estimate seems off
  - Estimates are heuristic; leave headroom. Estimation logic: [BatchEstimator.estimate_output_size()](addons/video_transcoder/batch_estimator.py:19)
- Abort did not stop immediately
  - Abort should stop the active transcode within ~500ms. If it takes longer, wait a couple of seconds; if still running, check the log for Transcode aborted by user and any FFMPEG shutdown messages. The worker coordinates immediate shutdown via [BatchWorker](addons/video_transcoder/batch_worker.py)
  - Very rarely, OS scheduling or encoder stalls can delay termination briefly; the general timeout still applies per [transcoder._execute_ffmpeg()](addons/video_transcoder/transcoder.py:396)
- CSV export failed
  - Pick a writable directory and ensure the file is not open elsewhere. Export path: [BatchResultsDialog._export_to_csv()](addons/video_transcoder/batch_results_dialog.py:180)

Understanding error messages
- Per-video errors are shown in the results dialog and recorded in the log
- Failures typically originate from the single-file pipeline [transcoder.process_video()](addons/video_transcoder/transcoder.py:41)

## 6) Technical Details

How estimation works
- Size: codec efficiency, CRF, resolution scaling, and optional bitrate caps → [BatchEstimator.estimate_output_size()](addons/video_transcoder/batch_estimator.py:19)
- Time: codec complexity, hardware acceleration, preset, and resolution → [BatchEstimator.estimate_transcode_time()](addons/video_transcoder/batch_estimator.py:89)
- Disk: outputs + temp files + backups/rollback → [BatchEstimator.calculate_disk_space_required()](addons/video_transcoder/batch_estimator.py:200)

Resolution/FPS handling
- When USDB integration is enabled, limits are treated as maxima; otherwise exact values are targeted
- Displayed via [BatchTranscodeOrchestrator._format_resolution_display()](addons/video_transcoder/batch_orchestrator.py:399) and [BatchTranscodeOrchestrator._format_fps_display()](addons/video_transcoder/batch_orchestrator.py:409)

Thread safety and background processing
- The batch runs in a dedicated worker thread [BatchWorker](addons/video_transcoder/batch_worker.py:26) to keep the UI responsive
- Progress updates are emitted via Qt signals [BatchWorker.video_progress](addons/video_transcoder/batch_worker.py:31) and consumed by [BatchProgressDialog](addons/video_transcoder/batch_progress_dialog.py)
- Each single-file transcode uses the same verified pipeline [transcoder.process_video()](addons/video_transcoder/transcoder.py:41), including cleanup of partial files on failure [transcoder.process_video()](addons/video_transcoder/transcoder.py:189)

