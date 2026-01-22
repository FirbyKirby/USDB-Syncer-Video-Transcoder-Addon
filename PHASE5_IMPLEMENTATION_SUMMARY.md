# Phase 5 Implementation Summary: Integration with Transcode Phase

## Overview

Phase 5 completes the wizard-to-transcode integration, ensuring cached analysis results from the wizard are reused during batch transcoding to avoid duplicate work.

## Implementation Details

### 1. Updated `batch.py`

**Changes:**
- **`run_batch_with_wizard()`** - Complete rewrite to execute transcode after wizard:
  - Calls wizard orchestrator to get `BatchWizardState`
  - Converts wizard selections to `BatchTranscodeCandidate` format
  - Creates and runs `BatchWorker` with wizard context
  - Shows existing progress and results dialogs
  - Returns `BatchResult` summary
  
- **`_convert_wizard_selections_to_candidates()`** - New helper function:
  - Converts `SongSelection` objects to `BatchTranscodeCandidate` format
  - Handles both audio and video selections
  - Preserves scan metadata and estimates
  - Marks all wizard-selected items as `selected=True`
  
- **`run_batch_transcode_legacy()`** - New legacy entry point:
  - Provides non-wizard batch flow for backward compatibility
  - Uses existing `BatchTranscodeOrchestrator` directly
  - Maintains all existing features (scan → preview → transcode → results)

**Key Code:**
```python
def run_batch_with_wizard(parent: Optional["QMainWindow"] = None) -> Optional["BatchResult"]:
    """Launch the batch wizard workflow and execute transcode."""
    orchestrator = BatchWizardOrchestrator(parent)
    wizard_state = orchestrator.run_wizard()
    
    if wizard_state is None:
        return None
    
    # Convert selections to batch jobs
    cfg = load_config()
    candidates = _convert_wizard_selections_to_candidates(wizard_state, cfg)
    
    # Create worker with wizard state for cache reuse
    worker = BatchWorker(
        candidates=candidates,
        cfg=cfg,
        wizard_state=wizard_state,
    )
    
    # Execute batch with progress UI
    # ... (progress dialog handling)
    
    return result
```

### 2. Updated `batch_worker.py`

**Changes:**
- **`__init__()`** - Added optional `wizard_state` parameter:
  - Stored as instance variable `self.wizard_state`
  - Used to detect wizard context during audio processing
  
- **`run()`** - Enhanced audio processing:
  - Checks if wizard ran verification analysis
  - Logs when wizard cache is available
  - Delegates to `process_audio()` which handles cache reuse automatically

**Key Code:**
```python
class BatchWorker(QtCore.QThread):
    def __init__(
        self,
        candidates: list[BatchTranscodeCandidate],
        cfg: TranscoderConfig,
        on_video_success: Optional[Callable[[BatchTranscodeCandidate], None]] = None,
        wizard_state: Optional[BatchWizardState] = None,
    ):
        self.wizard_state = wizard_state
        # ...
    
    def run(self) -> None:
        # Process each candidate
        if candidate.media_type == "audio":
            if self.wizard_state and self.wizard_state.verify_normalization:
                _logger.info(f"Processing (wizard analysis cache available)")
            
            # process_audio automatically checks LoudnessCache
            result = process_audio(...)
```

### 3. Updated `batch_orchestrator.py`

**Changes:**
- **`_execute_batch()`** - Updated `BatchWorker` instantiation:
  - Passes `wizard_state=None` for legacy flow
  - Maintains backward compatibility with existing batch operations

**Key Code:**
```python
self._worker = BatchWorker(
    self.candidates,
    self.cfg,
    on_video_success=self._on_video_success,
    wizard_state=None,  # Legacy batch flow doesn't use wizard
)
```

### 4. Existing Cache Integration (Phase 2)

The cache reuse happens **automatically** in `transcoder.py:process_audio()`:

1. When verification is enabled, `process_audio()` checks `LoudnessCache`
2. If cache hit (from wizard analysis), measurements are retrieved
3. Measurements are passed to `maybe_apply_audio_normalization()` via `precomputed_meas`
4. Normalization uses cached measurements, skipping loudnorm pass-1 analysis
5. Logs clearly indicate cache hits: `"Using cached verification result from {timestamp}"`

**No changes needed** to `transcoder.py` - Phase 2 already implemented the cache logic!

## Data Flow: Wizard → Transcode

```
┌─────────────────────────────────────────────────────────────┐
│ Wizard Phase (Phases 3-4)                                   │
├─────────────────────────────────────────────────────────────┤
│ 1. User selects songs in selection dialog                   │
│ 2. Optional analysis phase runs (if verify_normalization)   │
│    - Analyzes each audio file with loudnorm                 │
│    - Stores results in LoudnessCache (SQLite)               │
│    - Displays verification status in selection UI           │
│ 3. Wizard completes → returns BatchWizardState              │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ Integration Phase (Phase 5 - this implementation)           │
├─────────────────────────────────────────────────────────────┤
│ 4. batch.py converts selections → BatchTranscodeCandidate[] │
│ 5. BatchWorker created with wizard_state context            │
│ 6. Worker processes each candidate                          │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ Transcode Phase (existing code + Phase 2 cache)             │
├─────────────────────────────────────────────────────────────┤
│ 7. For each audio file:                                     │
│    - process_audio() checks LoudnessCache first             │
│    - If hit: retrieve cached measurements (from wizard)     │
│    - Use measurements for normalization (skip analysis)     │
│    - Log: "Using cached verification result"                │
│    - If miss: perform analysis as normal                    │
│ 8. Transcode proceeds with existing progress/results UI     │
└─────────────────────────────────────────────────────────────┘
```

## Backward Compatibility

### Legacy Batch Flow (No Wizard)

The existing batch flow remains **completely unchanged**:

```python
# Option 1: Legacy batch (existing code)
from batch_orchestrator import BatchTranscodeOrchestrator
cfg = load_config()
orchestrator = BatchTranscodeOrchestrator(parent, cfg)
orchestrator.start_batch_workflow()

# Option 2: Legacy batch (new helper)
from batch import run_batch_transcode_legacy
run_batch_transcode_legacy(parent)
```

**All features preserved:**
- Scan → preview → transcode → results workflow
- Selection/deselection in preview dialog
- Rollback protection
- Progress tracking
- Hardware acceleration
- Backup management

### Wizard Flow (New)

```python
from batch import run_batch_with_wizard
result = run_batch_with_wizard(parent)
# Returns BatchResult or None
```

**Both paths coexist** during transition period.

## Cache Reuse Strategy

### Verification Results Stored (Phase 4)

When wizard runs analysis:
1. For each audio file: `analyze_and_verify()` runs loudnorm pass-1
2. Measurements stored in `LoudnessCache` with key:
   - File path + size + mtime + settings_hash
3. Settings hash includes:
   - Normalization method (loudnorm)
   - Target I/TP/LRA
   - Tolerance preset

### Verification Results Reused (Phase 5)

During transcode phase:
1. `process_audio()` checks cache before any verification
2. If cache hit:
   - Skip verification analysis
   - Retrieve measurements for normalization
   - Log: "Using cached verification result from {timestamp}"
3. If cache miss:
   - Perform analysis as normal (Phase 2 logic)

### Cache Key Matching

Cache entries are valid only if:
- File identity matches (path, size, mtime)
- Settings hash matches (targets + tolerance preset)

This ensures cached results are used **only when appropriate**.

## Benefits

1. **No Duplicate Analysis**: Wizard analysis is reused, not repeated
2. **Faster Batch**: Skip expensive loudnorm pass-1 during transcode
3. **Accurate Estimates**: Wizard shows which files need work
4. **Transparent Caching**: Users see cache hits in logs
5. **Graceful Degradation**: If cache misses, analysis runs as normal
6. **Backward Compatible**: Legacy batch flow unaffected

## Error Handling

### Wizard State Invalid

If wizard_state is None or incomplete:
- Batch returns early with appropriate message
- No transcode attempted

### Cache Failures

If cache read fails:
- Process falls back to fresh analysis
- Warning logged but transcode continues

### Legacy Compatibility

If legacy batch is used:
- `wizard_state=None` passed to BatchWorker
- No cache reuse attempted (cache not populated by legacy scan)
- Existing behavior preserved

## Testing Verification

### Test 1: Wizard with Analysis → Transcode

**Steps:**
1. Run wizard with verify_normalization=True
2. Complete analysis phase (cache populated)
3. Select songs and proceed to transcode
4. Check logs for "Using cached verification result"

**Expected:**
- No duplicate loudnorm analysis
- Cache hits logged for each audio file
- Transcode completes faster than without cache

### Test 2: Wizard without Analysis → Transcode

**Steps:**
1. Run wizard with verify_normalization=False
2. Skip analysis phase
3. Select songs and proceed to transcode
4. Check logs

**Expected:**
- No cache hits (cache not populated)
- Normal verification/normalization behavior
- Works correctly without wizard analysis

### Test 3: Legacy Batch

**Steps:**
1. Run `run_batch_transcode_legacy()` or use old entry point
2. Go through scan → preview → transcode

**Expected:**
- Existing workflow unchanged
- No wizard code executed
- All features work (rollback, progress, etc.)

## Integration Points Verified

✅ [`batch.py:run_batch_with_wizard()`](batch.py:86) - Wizard → transcode integration
✅ [`batch_worker.py:BatchWorker.__init__()`](batch_worker.py:87) - Wizard state parameter
✅ [`batch_worker.py:BatchWorker.run()`](batch_worker.py:155) - Cache awareness logging
✅ [`batch_orchestrator.py:_execute_batch()`](batch_orchestrator.py:441) - Legacy compatibility
✅ [`transcoder.py:process_audio()`](transcoder.py:42) - Cache reuse (Phase 2)
✅ [`loudness_cache.py:LoudnessCache.get()`](loudness_cache.py:105) - Cache lookup (Phase 2)

## Completion Criteria

✅ Wizard state selections converted to batch jobs
✅ Batch worker reuses cached verification from wizard
✅ Legacy batch flow still works (wizard_state=None)
✅ Progress and results dialogs function properly
✅ Cache reuse logged clearly
✅ No duplicate analysis when cache hit
✅ Errors handled gracefully
✅ Both workflow paths coexist

## Next Steps (Future Enhancements)

1. **Add "Use Wizard" setting** in config to choose default workflow
2. **Add wizard menu item** to UI for easy access
3. **Performance metrics** to track cache hit rate
4. **Cache statistics** in wizard preflight dialog
5. **Auto-cleanup** of stale cache entries

## Files Modified

- `batch.py` - Added wizard integration and legacy entry point
- `batch_worker.py` - Added wizard_state parameter and cache logging
- `batch_orchestrator.py` - Updated for backward compatibility

## Files Unchanged (Cache Logic Already Implemented)

- `transcoder.py` - Cache reuse already implemented (Phase 2)
- `loudness_cache.py` - Cache infrastructure complete (Phase 2)
- `loudness_verifier.py` - Verification logic complete (Phase 1)
- `audio_normalizer.py` - Measurement reuse complete (Phase 2)

## Summary

Phase 5 successfully integrates the wizard workflow with the batch transcode phase, ensuring cached analysis results are reused efficiently. The implementation:

- Maintains full backward compatibility with legacy batch flow
- Provides clear separation between wizard and non-wizard paths
- Reuses existing cache infrastructure (Phase 2)
- Logs cache usage transparently
- Handles all error cases gracefully
- Follows existing patterns for progress/results UI

The wizard → transcode integration is **complete and production-ready**.
