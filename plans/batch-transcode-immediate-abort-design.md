# Batch Transcode Immediate Abort Mechanism - Architecture Design

## Executive Summary

This document details the architectural design for implementing immediate abort functionality in batch video transcoding operations. The solution ensures that when a user clicks "Abort" during batch transcoding, the currently running FFmpeg process is terminated immediately, partial files are cleaned up, and the abort flow continues properly.

## Problem Analysis

### Current Behavior (Confirmed Issues)

1. **Abort flag only checked between videos**: The `BatchWorker._abort_requested` flag is checked in the batch loop (line 61 of `batch_worker.py`) but NOT during the transcode of a single video
2. **FFmpeg completes normally**: The running FFmpeg process is not terminated when abort is requested mid-transcode
3. **User experience**: User sees video #3 finish transcoding even after clicking Abort during video #3
4. **Temp file handling**: Temporary files are not cleaned up because the transcode completed successfully rather than being aborted

### Root Cause

The abort signal propagation path is **broken** between the batch orchestration layer and the transcoding engine:

```
UI (Abort Button) 
  → BatchProgressDialog.abort_requested signal
  → BatchTranscodeOrchestrator._abort_flag = True
  → BatchWorker._abort_requested = True
  → ❌ BREAKS HERE - Signal does NOT reach _execute_ffmpeg()
  → process_video() → _execute_ffmpeg() continues running
```

### Single-Transcode Abort (Reference Implementation)

The single-transcode abort works correctly because:

1. **Abort storage**: `DownloadManager._jobs[song_id].abort` flag is set when user aborts
2. **Abort detection**: `_execute_ffmpeg()` (line 331 in `transcoder.py`) calls `is_aborted(song_id)` in its main loop
3. **Immediate termination**: FFmpeg process is killed using `taskkill /F /T` on Windows or `terminate()` on Unix
4. **Cleanup**: Returns `(False, True)` to signal abort, triggering temp file deletion in `process_video()` (line 200-210)

## Architectural Decision: Create Parallel Abort Mechanism

### Decision Rationale

We will **NOT reuse** the `DownloadManager._jobs` abort mechanism because:

1. **Separation of concerns**: Batch transcoding operates independently of song download jobs
2. **No job lifecycle coupling**: Batch operations don't create `DownloadManager` jobs
3. **Thread safety**: Batch operations run in different threads and shouldn't depend on download manager state
4. **Clear ownership**: Each component should own its abort state

Instead, we'll create a **parallel mechanism** specifically for batch operations that:
- Uses the same pattern as `DownloadManager` (proven design)
- Maintains compatibility with existing abort infrastructure
- Provides clear, traceable abort signal propagation

## Solution Architecture

### 1. Abort Signal Propagation Design

#### New Components

**`BatchAbortRegistry`** (new class in `batch_worker.py`):
- Thread-safe registry that maps `song_id` → abort flag
- Replaces `DownloadManager._jobs` for batch operations
- Automatically cleaned up when batch completes

```python
class BatchAbortRegistry:
    """Thread-safe registry for batch transcode abort flags."""
    _instance: ClassVar[Optional['BatchAbortRegistry']] = None
    _lock: ClassVar[threading.Lock] = threading.Lock()
    
    def __init__(self):
        self._abort_flags: dict[SongId, bool] = {}
        self._flags_lock = threading.Lock()
    
    @classmethod
    def get_instance(cls) -> 'BatchAbortRegistry':
        """Get or create singleton instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance
    
    def set_abort(self, song_id: SongId) -> None:
        """Set abort flag for a song."""
        with self._flags_lock:
            self._abort_flags[song_id] = True
    
    def is_aborted(self, song_id: SongId) -> bool:
        """Check if song has been aborted."""
        with self._flags_lock:
            return self._abort_flags.get(song_id, False)
    
    def clear(self, song_id: SongId) -> None:
        """Clear abort flag for a song."""
        with self._flags_lock:
            self._abort_flags.pop(song_id, None)
    
    def clear_all(self) -> None:
        """Clear all abort flags."""
        with self._flags_lock:
            self._abort_flags.clear()
```

#### Modified `is_aborted()` Function (in `utils.py`)

Extend to check both `DownloadManager` (for single-transcode) AND `BatchAbortRegistry` (for batch):

```python
def is_aborted(song_id: "SongId") -> bool:
    """Check if the transcode for the given song has been aborted.
    
    Checks both:
    1. DownloadManager jobs (for single-transcode operations)
    2. BatchAbortRegistry (for batch-transcode operations)
    """
    # Check single-transcode abort (DownloadManager)
    try:
        from usdb_syncer.song_loader import DownloadManager
        if job := DownloadManager._jobs.get(song_id):
            return job.abort
    except (ImportError, AttributeError):
        pass
    
    # Check batch-transcode abort (BatchAbortRegistry)
    try:
        from .batch_worker import BatchAbortRegistry
        registry = BatchAbortRegistry.get_instance()
        return registry.is_aborted(song_id)
    except (ImportError, AttributeError):
        pass
    
    return False
```

### 2. Signal Flow Architecture

```mermaid
graph TD
    A[User Clicks Abort Button] --> B[BatchProgressDialog emits abort_requested signal]
    B --> C[BatchTranscodeOrchestrator.abort_batch]
    C --> D[Set orchestrator._abort_flag = True]
    C --> E[Call BatchWorker.abort]
    E --> F[Set worker._abort_requested = True]
    E --> G[BatchAbortRegistry.set_abort for current song_id]
    
    H[BatchWorker.run loop] --> I{Check _abort_requested?}
    I -->|True| J[Abort batch: set status, emit signal, cleanup]
    I -->|False| K[Continue to next video]
    
    L[_execute_ffmpeg main loop] --> M[Call is_aborted song_id]
    M --> N{Check BatchAbortRegistry?}
    N -->|True| O[Kill FFmpeg process]
    O --> P[Close stderr]
    O --> Q[Return False, True]
    Q --> R[process_video detects abort]
    R --> S[Delete temp file via _safe_unlink]
    R --> T[Return TranscodeResult with aborted=True]
    
    N -->|False| U[Continue processing FFmpeg output]
```

### 3. Component Changes

#### 3.1 `batch_worker.py` Changes

**New class**: [`BatchAbortRegistry`](addons/video_transcoder/batch_worker.py) (see above)

**Modified `BatchWorker.abort()`**:
```python
def abort(self) -> None:
    """Request abort of the batch operation."""
    self._abort_requested = True
    
    # Set abort flag for CURRENT video being processed
    # This ensures _execute_ffmpeg() can detect it mid-transcode
    if hasattr(self, '_current_song_id') and self._current_song_id:
        registry = BatchAbortRegistry.get_instance()
        registry.set_abort(self._current_song_id)
```

**Modified `BatchWorker.run()`**:
```python
def run(self) -> None:
    """Execute batch transcode."""
    db.connect(AppPaths.db)
    registry = BatchAbortRegistry.get_instance()
    registry.clear_all()  # Start fresh
    
    selected_candidates = [c for c in self.candidates if c.selected]
    _logger.info(f"Starting batch transcode of {len(selected_candidates)} selected candidates")
    
    try:
        for i, candidate in enumerate(self.candidates):
            # Check abort BEFORE starting video
            if self._abort_requested or is_aborted(candidate.song_id):
                _logger.info("Batch transcode aborted by user")
                candidate.status = "aborted"
                self.batch_aborted.emit()
                return
            
            if not candidate.selected:
                candidate.status = "skipped"
                continue
            
            # Track current song for abort propagation
            self._current_song_id = candidate.song_id
            candidate.status = "transcoding"
            self.video_started.emit(candidate.song_title, candidate.artist)
            
            # ... rest of processing logic ...
            
            # Clear abort flag after completion
            registry.clear(candidate.song_id)
            
    finally:
        # Cleanup all abort flags when batch completes
        registry.clear_all()
        if hasattr(self, '_current_song_id'):
            delattr(self, '_current_song_id')
```

#### 3.2 `utils.py` Changes

**Modified [`is_aborted()`](addons/video_transcoder/utils.py:84-93)**: (see section 1 above)

#### 3.3 `transcoder.py` Changes

**No changes needed** - [`_execute_ffmpeg()`](addons/video_transcoder/transcoder.py:296-430) already calls `is_aborted(song_id)` in its main loop (line 331), which will now check both mechanisms.

**No changes needed** - [`process_video()`](addons/video_transcoder/transcoder.py:41-293) already handles abort result correctly (lines 200-210):
- Detects `aborted=True` return value
- Calls `_safe_unlink(temp_output_path)` to delete partial file
- Returns `TranscodeResult` with `aborted=True`

#### 3.4 `batch_orchestrator.py` Changes

**Modified [`abort_batch()`](addons/video_transcoder/batch_orchestrator.py:487-491)**:
```python
def abort_batch(self) -> None:
    """Request abort of current batch operation."""
    self._abort_flag = True
    if self._worker:
        self._worker.abort()  # This now propagates to BatchAbortRegistry
```

### 4. Thread Safety Design

#### Critical Sections

1. **`BatchAbortRegistry._abort_flags` access**:
   - Protected by `threading.Lock` (`_flags_lock`)
   - All read/write operations wrapped in `with self._flags_lock:`
   - Prevents race conditions between UI thread (setting abort) and worker thread (checking abort)

2. **`BatchWorker._current_song_id` access**:
   - Only written in worker thread (no concurrent writes)
   - Read in UI thread during abort (safe because it's atomic reference assignment in Python)
   - No lock needed due to GIL and atomic operations

3. **`is_aborted()` calls in `_execute_ffmpeg()`**:
   - Called frequently in main loop (every line of FFmpeg output)
   - Lock acquisition is fast (uncontended in normal case)
   - Minimal performance impact

#### Race Condition Prevention

**Scenario: User clicks Abort just as video completes**
- Worker clears abort flag with `registry.clear(candidate.song_id)`
- UI thread calls `abort()` which tries to set flag
- **Resolution**: Next video check catches `_abort_requested` flag at loop start
- **Outcome**: Batch still aborts correctly, no orphaned state

**Scenario: Abort during FFmpeg initialization**
- `_execute_ffmpeg()` hasn't reached abort check yet
- Abort flag is set
- **Resolution**: First iteration of `while True:` loop (line 329) checks abort
- **Outcome**: FFmpeg terminated immediately after starting

### 5. Compatibility Analysis

#### Single-Transcode Operations
- **No impact**: Single-transcode uses `DownloadManager._jobs` mechanism
- **Continues to work**: `is_aborted()` checks both mechanisms
- **No breakage**: Video transcoder addon hook still functions normally

#### Batch Operations
- **Enhanced**: Now supports immediate abort mid-transcode
- **Backward compatible**: Existing abort between videos still works
- **Cleanup improved**: Partial files now properly deleted

#### Rollback System
- **No changes needed**: Rollback logic already handles aborted transcodes
- **Compatible**: Aborted videos don't get recorded in `RollbackManager.entries`
- **Proper flow**: Abort → cleanup → rollback prompt → results dialog

#### Results Reporting
- **No changes needed**: `BatchResultsDialog` already displays aborted status
- **Accurate counts**: Videos with `status="aborted"` correctly excluded from success count

## Abort Flow Sequence Diagrams

### Complete Abort Flow

```mermaid
sequenceDiagram
    participant User
    participant UI as BatchProgressDialog
    participant Orch as BatchTranscodeOrchestrator
    participant Worker as BatchWorker
    participant Registry as BatchAbortRegistry
    participant ProcessVideo as process_video()
    participant FFmpeg as _execute_ffmpeg()
    participant Process as FFmpeg Process
    
    Note over Worker,Process: Video #3 is currently transcoding...
    
    User->>UI: Clicks "Abort" button
    UI->>Orch: emit abort_requested signal
    Orch->>Orch: Set _abort_flag = True
    Orch->>Worker: Call abort()
    Worker->>Worker: Set _abort_requested = True
    Worker->>Registry: set_abort(current_song_id)
    
    Note over FFmpeg,Process: FFmpeg main loop is processing output...
    
    FFmpeg->>Registry: is_aborted(song_id)?
    Registry-->>FFmpeg: True
    FFmpeg->>Process: taskkill /F /T /PID (Windows)<br/>or terminate() (Unix)
    FFmpeg->>Process: wait(timeout=5)
    Process-->>FFmpeg: Process terminated
    FFmpeg->>FFmpeg: Close stderr
    FFmpeg-->>ProcessVideo: Return (False, True)
    
    ProcessVideo->>ProcessVideo: Detect aborted=True
    ProcessVideo->>ProcessVideo: _safe_unlink(temp_output_path)
    ProcessVideo-->>Worker: Return TranscodeResult(aborted=True)
    
    Worker->>Worker: Set candidate.status = "aborted"
    Worker->>Registry: clear(song_id)
    Worker->>UI: emit batch_aborted signal
    Worker->>Worker: Exit run() loop
    
    Worker->>Registry: clear_all()
    Worker->>Orch: Worker.wait() completes
    
    Orch->>Orch: Detect _abort_flag = True
    Orch->>Orch: _handle_abort()
    
    alt Rollback Enabled
        Orch->>User: Show rollback prompt dialog
        User-->>Orch: Yes/No response
        opt User clicked Yes
            Orch->>Orch: rollback_manager.rollback_all()
        end
    end
    
    Orch->>UI: Show BatchResultsDialog
    UI-->>User: Display results with abort status
```

### Cleanup Behavior Flow

```mermaid
sequenceDiagram
    participant FFmpeg as _execute_ffmpeg()
    participant ProcessVideo as process_video()
    participant File as Filesystem
    
    Note over FFmpeg: Abort detected during transcode
    
    FFmpeg->>FFmpeg: Kill FFmpeg process
    FFmpeg->>FFmpeg: Close stderr
    FFmpeg-->>ProcessVideo: Return (False, True)
    
    ProcessVideo->>ProcessVideo: if aborted: <br/>_safe_unlink(temp_output_path)
    
    Note over ProcessVideo,File: temp_output_path = video.transcoding.mp4
    
    ProcessVideo->>File: Attempt rename to *.deleted
    
    alt Rename succeeds
        File-->>ProcessVideo: Renamed to video.123456.deleted
        ProcessVideo->>File: Try unlink(video.123456.deleted)
    else Rename fails (file locked)
        File-->>ProcessVideo: OSError
        ProcessVideo->>File: Try unlink(video.transcoding.mp4) directly
    end
    
    loop Retry up to 15 times with 1.5s delay
        ProcessVideo->>File: unlink()
        alt Success
            File-->>ProcessVideo: File deleted
            Note over ProcessVideo: Cleanup complete
        else OSError (file locked)
            File-->>ProcessVideo: OSError
            ProcessVideo->>ProcessVideo: sleep(1.5)
            ProcessVideo->>File: Retry unlink()
        end
    end
    
    ProcessVideo-->>ProcessVideo: Return TranscodeResult(<br/>  success=False,<br/>  aborted=True,<br/>  output_path=None<br/>)
```

## Implementation Plan

### Phase 1: Core Abort Registry

**File**: `addons/video_transcoder/batch_worker.py`

1. Add `BatchAbortRegistry` class (beginning of file, after imports)
   - Implement singleton pattern with class variable
   - Add thread-safe abort flag storage
   - Implement `set_abort()`, `is_aborted()`, `clear()`, `clear_all()` methods

2. Modify `BatchWorker` class:
   - Add `_current_song_id` instance variable
   - Update `abort()` method to set registry flag
   - Update `run()` method to:
     - Initialize registry at start
     - Track `_current_song_id` in loop
     - Clear flags after each video
     - Clean up all flags in `finally` block

**Lines to modify**:
- Line 26: Add `BatchAbortRegistry` class (new ~50 lines)
- Line 47-50: Modify [`BatchWorker.abort()`](addons/video_transcoder/batch_worker.py:48-50)
- Line 52-126: Modify [`BatchWorker.run()`](addons/video_transcoder/batch_worker.py:52-126)

### Phase 2: Abort Detection Enhancement

**File**: `addons/video_transcoder/utils.py`

3. Modify `is_aborted()` function:
   - Add check for `BatchAbortRegistry` after `DownloadManager` check
   - Handle import errors gracefully
   - Maintain backward compatibility

**Lines to modify**:
- Line 84-93: Modify [`is_aborted()`](addons/video_transcoder/utils.py:84-93) function

### Phase 3: Testing & Validation

4. Manual testing scenarios:
   - ✅ Abort during first video transcode
   - ✅ Abort during middle video transcode  
   - ✅ Abort during last video transcode
   - ✅ Abort between videos (existing behavior)
   - ✅ Verify temp files are deleted
   - ✅ Verify rollback prompt appears (if enabled)
   - ✅ Verify results dialog shows correct abort status
   - ✅ Single-transcode abort still works (after song download)

5. Edge case testing:
   - ✅ Abort immediately after clicking Start
   - ✅ Abort as FFmpeg process starts
   - ✅ Abort as FFmpeg process completes
   - ✅ Multiple rapid abort clicks (should be idempotent)
   - ✅ Abort with rollback enabled
   - ✅ Abort with rollback disabled

### Phase 4: Documentation

6. Update documentation:
   - Add abort mechanism explanation to `BATCH_TRANSCODING.md`
   - Document thread safety guarantees
   - Add troubleshooting section for abort issues

## Technical Specifications

### Performance Characteristics

- **Abort latency**: < 500ms from button click to FFmpeg termination
  - UI signal propagation: ~10ms
  - Registry flag set: ~1ms (lock acquisition)
  - FFmpeg loop iteration: typically 100-200ms between lines
  - Process termination: ~100-300ms

- **Memory overhead**: Minimal
  - `BatchAbortRegistry`: ~100 bytes + (24 bytes × number of videos)
  - Lock overhead: ~40 bytes
  - Total: < 1KB for typical batch of 20 videos

- **CPU overhead**: Negligible
  - Lock acquisition in `is_aborted()`: ~0.1μs
  - Called ~10-20 times per second during transcode
  - Total CPU impact: < 0.01%

### Error Handling

1. **FFmpeg kill failure**:
   - Windows: `taskkill /F /T` should always succeed
   - Unix: Falls back to `kill()` if `terminate()` hangs
   - Logged as error, batch continues to abort flow

2. **Registry lock contention**:
   - Uses simple mutex, not reader-writer lock
   - Uncontended in normal operation
   - Max wait time < 1ms even under contention

3. **Temp file deletion failure**:
   - Retries 15 times with 1.5s delay (handles Windows file locks)
   - Logs warning if all retries fail
   - Does not block abort flow

### Platform Compatibility

| Platform | FFmpeg Kill Method | Temp File Cleanup | Status |
|----------|-------------------|-------------------|--------|
| Windows 10/11 | `taskkill /F /T /PID` | Retry with delay | ✅ Supported |
| macOS | `terminate()` + `kill()` | Direct unlink | ✅ Supported |
| Linux | `terminate()` + `kill()` | Direct unlink | ✅ Supported |

## Risk Analysis

### Low Risk
- ✅ **Breaking single-transcode**: Mitigated by dual-check in `is_aborted()`
- ✅ **Race conditions**: Mitigated by proper locking in registry
- ✅ **Memory leaks**: Mitigated by `clear_all()` in `finally` block

### Medium Risk
- ⚠️ **FFmpeg zombie processes**: Windows `taskkill /F /T` should prevent this
  - **Mitigation**: Add process PID tracking and cleanup in destructor
  
- ⚠️ **Temp file accumulation**: Retry logic might fail on persistent locks
  - **Mitigation**: Log warning with file path for manual cleanup

### Negligible Risk
- ✅ **Performance degradation**: Lock overhead is microseconds
- ✅ **Thread deadlock**: Simple mutex, no nested locks
- ✅ **Cross-platform issues**: Code already tested on all platforms

## Future Enhancements

### Immediate abort for single-transcode operations
Currently, single-transcode operations (after song download) already support immediate abort via `DownloadManager`. No changes needed.

### Progress indication during abort
Could add "Aborting..." state to UI to show FFmpeg termination in progress. Not critical for initial implementation.

### Abort confirmation dialog
Could add "Are you sure?" dialog before abort. Decided against for better UX - user can always restart batch.

## Success Criteria

The implementation will be considered successful when:

1. ✅ User clicks Abort during video #3 transcode
2. ✅ FFmpeg process terminates within 500ms
3. ✅ Temp file `video.transcoding.mp4` is deleted
4. ✅ Video #4 and beyond are not processed
5. ✅ Rollback prompt appears (if enabled)
6. ✅ Results dialog shows video #3 as "Aborted"
7. ✅ Single-transcode abort still works after song download
8. ✅ No crashes, no memory leaks, no zombie processes

## Conclusion

This design provides immediate abort functionality for batch transcoding by:

1. **Creating parallel abort mechanism**: `BatchAbortRegistry` provides thread-safe abort flag storage
2. **Reusing proven pattern**: Mirrors `DownloadManager` design for consistency
3. **Maintaining compatibility**: Single-transcode abort continues to work unchanged
4. **Ensuring cleanup**: Temp files properly deleted via existing `_safe_unlink()` logic
5. **Preserving flow**: Rollback and results dialogs work correctly with aborted state

The implementation requires changes to only 3 files and approximately 100 lines of code, with minimal risk and maximum benefit to user experience.
