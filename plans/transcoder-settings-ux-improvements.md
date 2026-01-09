# Transcoder Settings UX Improvements - Design Document

**Date:** 2026-01-03  
**Status:** Design Phase  
**Scope:** [`addons/melody_mania_transcoder/`](../addons/melody_mania_transcoder/)

## Executive Summary

This design addresses three critical UX issues in the Melody Mania Transcoder addon:
1. **USDB limits as maximums, not exact values** - Currently applied after transcoding decisions
2. **Limited settings exposure** - GUI only shows CRF values, hiding many codec-specific settings
3. **No user guidance** - Missing tooltips and help text for all settings

The solution involves architectural changes to enforce limits before transcoding decisions, a dynamic codec-specific settings UI, and comprehensive tooltips for all exposed settings.

---

## Issue 1: USDB Integration as Limits (Not Exact Values)

### Current Behavior Analysis

**File:** [`transcoder.py`](../addons/melody_mania_transcoder/transcoder.py)

Current execution order:
1. Line 52: [`analyze_video()`](../addons/melody_mania_transcoder/transcoder.py:52) - Probe source video
2. Line 70: [`needs_transcoding()`](../addons/melody_mania_transcoder/transcoder.py:70) - Make transcoding decision
3. Line 105: [`_apply_usdb_integration()`](../addons/melody_mania_transcoder/transcoder.py:105) - **AFTER decision** was made!

**Problem:** USDB limits are copied into `cfg.general.max_resolution`/`max_fps` AFTER [`needs_transcoding()`](../addons/melody_mania_transcoder/video_analyzer.py:169) has already decided whether to transcode.

In [`video_analyzer.py:needs_transcoding()`](../addons/melody_mania_transcoder/video_analyzer.py:169), lines 177-195 check limits:
- Resolution check (lines 177-181): Returns True if video exceeds limits
- FPS check (lines 183-185): Returns True if FPS exceeds limits  
- Bitrate check (lines 187-195): Returns True if bitrate exceeds limits

But these checks run with **un-integrated** limits because integration happens later!

### Required Behavior

USDB limits should work as **maximums**:

**Scenario 1:** Source video is **below** limit
- Source: 720p @ 30fps
- USDB limit: 1080p @ 60fps
- **Result:** Use source values (720p, 30fps) - no downscaling needed

**Scenario 2:** Source video **exceeds** limit
- Source: 2160p @ 120fps
- USDB limit: 1080p @ 60fps
- **Result:** Downscale to 1080p @ 60fps

### Architecture Changes

#### 1.1 Move USDB Integration Earlier

**File:** [`transcoder.py`](../addons/melody_mania_transcoder/transcoder.py)

Change execution order in [`process_video()`](../addons/melody_mania_transcoder/transcoder.py:36):

```python
# Current order (WRONG):
video_info = analyze_video(video_path)           # Line 52
if not needs_transcoding(video_info, cfg):       # Line 70
cfg = _apply_usdb_integration(cfg)               # Line 105 - TOO LATE!

# NEW order (CORRECT):
video_info = analyze_video(video_path)           # Line 52
cfg = _apply_usdb_integration(cfg)               # MOVE HERE - before needs_transcoding()
if not needs_transcoding(video_info, cfg):       # Line 70 - now uses integrated limits
```

**Rationale:**
- [`needs_transcoding()`](../addons/melody_mania_transcoder/video_analyzer.py:169) checks `cfg.general.max_resolution` and `cfg.general.max_fps`
- These must be populated with USDB values **before** the check
- Moving line 105 to between lines 52-70 ensures limits are applied during the transcoding decision

#### 1.2 Enforce "Lesser Of" Logic

**Current behavior in [`_apply_usdb_integration()`](../addons/melody_mania_transcoder/transcoder.py:277):**

Lines 291-297 simply copy USDB values:
```python
if cfg.usdb_integration.use_usdb_resolution:
    res = settings.get_video_resolution()
    max_res = (res.width(), res.height())  # Blindly uses USDB value

if cfg.usdb_integration.use_usdb_fps:
    fps = settings.get_video_fps()
    max_fps = int(fps.value)  # Blindly uses USDB value
```

**Problem:** Doesn't consider source video's actual resolution/FPS!

**Solution:** New function signature for intelligent limit enforcement:

```python
def _apply_limits(
    cfg: TranscoderConfig,
    video_info: VideoInfo
) -> TranscoderConfig:
    """Apply intelligent limits from USDB (if enabled) and addon config.
    
    Uses the LESSER of (source value, max limit) to avoid unnecessary upscaling/interpolation.
    
    Args:
        cfg: Configuration with USDB integration settings
        video_info: Analyzed source video information
        
    Returns:
        Updated config with effective limits set in cfg.general.max_resolution and max_fps
    """
```

**Algorithm:**

```python
# Resolution logic
effective_max_width = None
effective_max_height = None

# Determine the limit source
if cfg.usdb_integration.use_usdb_resolution:
    # Use USDB Syncer's max resolution
    res = settings.get_video_resolution()
    limit_width = res.width()
    limit_height = res.height()
elif cfg.general.max_resolution:
    # Use addon's own max resolution setting
    limit_width, limit_height = cfg.general.max_resolution
else:
    # No limits configured
    limit_width = None
    limit_height = None

if limit_width and limit_height:
    # Use LESSER of (source, limit) - avoid upscaling
    effective_max_width = min(video_info.width, limit_width)
    effective_max_height = min(video_info.height, limit_height)
    
    # Maintain aspect ratio (use limiting dimension)
    source_ratio = video_info.width / video_info.height
    limit_ratio = limit_width / limit_height
    
    if source_ratio > limit_ratio:
        # Width is limiting dimension
        effective_max_width = min(video_info.width, limit_width)
        effective_max_height = int(effective_max_width / source_ratio)
    else:
        # Height is limiting dimension  
        effective_max_height = min(video_info.height, limit_height)
        effective_max_width = int(effective_max_height * source_ratio)

# FPS logic - simpler, just use minimum
effective_max_fps = None

if cfg.usdb_integration.use_usdb_fps:
    fps_limit = int(settings.get_video_fps().value)
    effective_max_fps = min(video_info.frame_rate, fps_limit)
elif cfg.general.max_fps:
    effective_max_fps = min(video_info.frame_rate, cfg.general.max_fps)

# Return updated config with effective limits
return replace(
    cfg,
    general=replace(
        cfg.general,
        max_resolution=(effective_max_width, effective_max_height) if effective_max_width else None,
        max_fps=effective_max_fps
    )
)
```

**Rationale:**
- Only downscale/reduce FPS when source exceeds limit
- Never upscale (waste of space, no quality gain)
- Preserves aspect ratio when limiting resolution

#### 1.3 Update Function Call Sites

**Changes required:**

1. **Replace `_apply_usdb_integration()` with `_apply_limits()`:**
   - Old: `cfg = _apply_usdb_integration(cfg)`  
   - New: `cfg = _apply_limits(cfg, video_info)`
   - Requires passing `video_info` parameter

2. **Move call site from line 105 to line ~67** (after video analysis, before needs_transcoding check)

3. **Update imports in codec handlers** - None needed, they already read from `cfg.general.max_resolution`/`max_fps`

#### 1.4 Backward Compatibility

**Consideration:** What if USDB Syncer settings module is unavailable?

Current code (lines 282-286) handles this:
```python
try:
    from usdb_syncer import settings
except Exception:
    # If settings can't be imported, keep addon config as-is
    return cfg
```

**Design decision:** Keep this safety check. If USDB Syncer unavailable:
- Fall back to addon's own `cfg.general.max_resolution`/`max_fps` settings
- These should be exposed in GUI when USDB integration is disabled (see Issue 2)

---

## Issue 2: Dynamic Codec Settings UI

### Current Implementation Analysis

**File:** [`settings_gui.py`](../addons/melody_mania_transcoder/settings_gui.py)

Current GUI only exposes:
- Lines 78-87: CRF for each codec (3 spinboxes always visible)
- Missing: profile, level, pixel_format, preset, use_quicksync, container, cpu_used, etc.

**Problems:**
1. Shows all 3 codec CRF fields simultaneously (cluttered)
2. No way to configure advanced codec settings (profile, preset, container, etc.)
3. General limits (max_resolution, max_fps) always hidden - should show when USDB integration is OFF

### Required Behavior

**Dynamic UI pattern:**
1. User selects target codec (H.264, HEVC, or VP8)
2. GUI shows **only** settings relevant to selected codec
3. General settings (max_resolution, max_fps) appear **only** when corresponding USDB toggle is OFF

### UI Design Options

#### Option A: Stacked Widget Approach (RECOMMENDED)

Use `QStackedWidget` to swap entire settings panels based on selected codec.

**Advantages:**
- Clean, native Qt pattern
- Easy to maintain (each codec gets own widget)
- Natural user flow (select codec → see its settings)
- Future extensibility (easy to add new codecs/settings)

**Disadvantages:**
- Slightly more code than inline show/hide

**Implementation pseudocode:**

```python
class TranscoderSettingsDialog(QDialog):
    def _setup_ui(self):
        # ... existing general settings ...
        
        # Target Codec
        codec_group = QGroupBox("Target Format")
        codec_layout = QVBoxLayout(codec_group)
        
        self.target_codec = QComboBox()
        self.target_codec.addItems(["h264", "hevc", "vp8"])
        self.target_codec.currentTextChanged.connect(self._on_codec_changed)
        codec_layout.addWidget(QLabel("Target Codec:"))
        codec_layout.addWidget(self.target_codec)
        layout.addWidget(codec_group)
        
        # Stacked widget for codec-specific settings
        self.codec_settings_stack = QStackedWidget()
        
        # Create separate widget for each codec
        self.h264_widget = self._create_h264_settings()
        self.hevc_widget = self._create_hevc_settings()
        self.vp8_widget = self._create_vp8_settings()
        
        self.codec_settings_stack.addWidget(self.h264_widget)
        self.codec_settings_stack.addWidget(self.hevc_widget)
        self.codec_settings_stack.addWidget(self.vp8_widget)
        
        layout.addWidget(self.codec_settings_stack)
        
    def _on_codec_changed(self, codec: str):
        """Switch visible settings panel when codec changes."""
        codec_to_index = {"h264": 0, "hevc": 1, "vp8": 2}
        self.codec_settings_stack.setCurrentIndex(codec_to_index[codec])
        
    def _create_h264_settings(self) -> QWidget:
        """Create H.264-specific settings panel."""
        widget = QWidget()
        layout = QFormLayout(widget)
        
        # Quality Settings Group
        quality_group = QGroupBox("Quality Settings")
        quality_layout = QFormLayout(quality_group)
        
        self.h264_crf = QSpinBox()
        self.h264_crf.setRange(0, 51)
        self.h264_crf.setValue(18)
        quality_layout.addRow("CRF:", self.h264_crf)
        
        self.h264_profile = QComboBox()
        self.h264_profile.addItems(["baseline", "main", "high"])
        quality_layout.addRow("Profile:", self.h264_profile)
        
        self.h264_level = QComboBox()
        self.h264_level.addItems(["3.0", "3.1", "3.2", "4.0", "4.1", "4.2", "5.0", "5.1"])
        quality_layout.addRow("Level:", self.h264_level)
        
        self.h264_pixel_format = QComboBox()
        self.h264_pixel_format.addItems(["yuv420p", "yuv422p", "yuv444p"])
        quality_layout.addRow("Pixel Format:", self.h264_pixel_format)
        
        layout.addRow(quality_group)
        
        # Performance Settings Group
        perf_group = QGroupBox("Performance Settings")
        perf_layout = QFormLayout(perf_group)
        
        self.h264_preset = QComboBox()
        self.h264_preset.addItems(["ultrafast", "superfast", "veryfast", "faster",
                                   "fast", "medium", "slow", "slower", "veryslow"])
        perf_layout.addRow("Preset:", self.h264_preset)
        
        layout.addRow(perf_group)
        
        # Output Settings Group
        output_group = QGroupBox("Output Settings")
        output_layout = QFormLayout(output_group)
        
        self.h264_container = QComboBox()
        self.h264_container.addItems(["mp4", "mkv", "mov"])
        output_layout.addRow("Container:", self.h264_container)
        
        layout.addRow(output_group)
        
        return widget
    
    def _create_hevc_settings(self) -> QWidget:
        """Create HEVC-specific settings panel."""
        widget = QWidget()
        layout = QFormLayout(widget)
        
        # Quality Settings Group
        quality_group = QGroupBox("Quality Settings")
        quality_layout = QFormLayout(quality_group)
        
        self.hevc_crf = QSpinBox()
        self.hevc_crf.setRange(0, 51)
        self.hevc_crf.setValue(20)
        quality_layout.addRow("CRF:", self.hevc_crf)
        
        self.hevc_profile = QComboBox()
        self.hevc_profile.addItems(["main", "main10"])
        quality_layout.addRow("Profile:", self.hevc_profile)
        
        self.hevc_level = QComboBox()
        self.hevc_level.addItems(["3.0", "3.1", "4.0", "4.1", "5.0", "5.1", "5.2", "6.0", "6.1"])
        quality_layout.addRow("Level:", self.hevc_level)
        
        self.hevc_pixel_format = QComboBox()
        self.hevc_pixel_format.addItems(["yuv420p", "yuv422p", "yuv444p", "yuv420p10le"])
        quality_layout.addRow("Pixel Format:", self.hevc_pixel_format)
        
        layout.addRow(quality_group)
        
        # Performance Settings Group
        perf_group = QGroupBox("Performance Settings")
        perf_layout = QFormLayout(perf_group)
        
        self.hevc_preset = QComboBox()
        self.hevc_preset.addItems(["ultrafast", "superfast", "veryfast", "faster",
                                   "fast", "medium", "slow", "slower", "veryslow"])
        perf_layout.addRow("Preset:", self.hevc_preset)
        
        layout.addRow(perf_group)
        
        # Output Settings Group
        output_group = QGroupBox("Output Settings")
        output_layout = QFormLayout(output_group)
        
        self.hevc_container = QComboBox()
        self.hevc_container.addItems(["mp4", "mkv", "mov"])
        output_layout.addRow("Container:", self.hevc_container)
        
        layout.addRow(output_group)
        
        return widget
    
    def _create_vp8_settings(self) -> QWidget:
        """Create VP8-specific settings panel."""
        widget = QWidget()
        layout = QFormLayout(widget)
        
        # Quality Settings Group
        quality_group = QGroupBox("Quality Settings")
        quality_layout = QFormLayout(quality_group)
        
        self.vp8_crf = QSpinBox()
        self.vp8_crf.setRange(0, 63)
        self.vp8_crf.setValue(10)
        quality_layout.addRow("CRF:", self.vp8_crf)
        
        layout.addRow(quality_group)
        
        # Performance Settings Group
        perf_group = QGroupBox("Performance Settings")
        perf_layout = QFormLayout(perf_group)
        
        self.vp8_cpu_used = QSpinBox()
        self.vp8_cpu_used.setRange(0, 5)
        self.vp8_cpu_used.setValue(1)
        perf_layout.addRow("CPU Used:", self.vp8_cpu_used)
        
        layout.addRow(perf_group)
        
        # Output Settings Group
        output_group = QGroupBox("Output Settings")
        output_layout = QFormLayout(output_group)
        
        self.vp8_container = QComboBox()
        self.vp8_container.addItems(["webm", "mkv"])
        output_layout.addRow("Container:", self.vp8_container)
        
        layout.addRow(output_group)
        
        return widget
```

#### Option B: Show/Hide with setVisible() (NOT RECOMMENDED)

Create all widgets upfront, use `setVisible()` to show/hide.

**Advantages:**
- Simpler code structure (all widgets in one layout)

**Disadvantages:**
- More complex state management (track which widgets belong to which codec)
- Layout jumps/resizes as widgets appear/disappear
- Harder to maintain (widget visibility spread across multiple functions)

**Verdict:** Option A (QStackedWidget) is superior for maintainability and UX.

### Conditional General Settings

**Requirement:** Show/hide `max_resolution` and `max_fps` based on USDB integration toggles.

**Implementation:**

```python
class TranscoderSettingsDialog(QDialog):
    def _setup_ui(self):
        # ... existing code ...
        
        # USDB Integration
        usdb_group = QGroupBox("USDB Syncer Integration")
        usdb_layout = QFormLayout(usdb_group)
        
        self.use_usdb_res = QCheckBox("Use USDB Max Resolution")
        self.use_usdb_res.stateChanged.connect(self._toggle_manual_resolution)
        usdb_layout.addRow(self.use_usdb_res)
        
        # Manual resolution input (hidden when USDB integration is ON)
        self.manual_res_label = QLabel("Manual Max Resolution:")
        self.manual_res_width = QSpinBox()
        self.manual_res_width.setRange(480, 7680)
        self.manual_res_width.setSuffix(" px width")
        self.manual_res_height = QSpinBox()
        self.manual_res_height.setRange(360, 4320)
        self.manual_res_height.setSuffix(" px height")
        
        res_widget = QWidget()
        res_layout = QHBoxLayout(res_widget)
        res_layout.addWidget(self.manual_res_width)
        res_layout.addWidget(QLabel("×"))
        res_layout.addWidget(self.manual_res_height)
        res_layout.setContentsMargins(0, 0, 0, 0)
        
        usdb_layout.addRow(self.manual_res_label, res_widget)
        
        self.use_usdb_fps = QCheckBox("Use USDB Max FPS")
        self.use_usdb_fps.stateChanged.connect(self._toggle_manual_fps)
        usdb_layout.addRow(self.use_usdb_fps)
        
        # Manual FPS input (hidden when USDB integration is ON)
        self.manual_fps_label = QLabel("Manual Max FPS:")
        self.manual_fps = QSpinBox()
        self.manual_fps.setRange(24, 240)
        self.manual_fps.setSuffix(" fps")
        usdb_layout.addRow(self.manual_fps_label, self.manual_fps)
        
        layout.addWidget(usdb_group)
        
    def _toggle_manual_resolution(self, state: Qt.CheckState):
        """Show/hide manual resolution inputs based on USDB integration."""
        is_usdb_enabled = (state == Qt.CheckState.Checked)
        self.manual_res_label.setVisible(not is_usdb_enabled)
        self.manual_res_width.setVisible(not is_usdb_enabled)
        self.manual_res_height.setVisible(not is_usdb_enabled)
        
    def _toggle_manual_fps(self, state: Qt.CheckState):
        """Show/hide manual FPS input based on USDB integration."""
        is_usdb_enabled = (state == Qt.CheckState.Checked)
        self.manual_fps_label.setVisible(not is_usdb_enabled)
        self.manual_fps.setVisible(not is_usdb_enabled)
```

**Behavior:**
- When "Use USDB Max Resolution" is **checked** → Hide manual resolution inputs
- When "Use USDB Max Resolution" is **unchecked** → Show manual resolution inputs (let user set addon's own limit)
- Same logic for FPS

**Rationale:**
- Prevents conflicting settings (can't set both USDB and manual limits)
- Makes it clear which source of limits is active
- Allows addon to work standalone without USDB Syncer

### Additional General Settings to Expose

Currently hidden general settings that should be exposed:

```python
# In general settings group
self.max_bitrate_kbps = QSpinBox()
self.max_bitrate_kbps.setRange(0, 100000)  # 0 = disabled
self.max_bitrate_kbps.setSuffix(" kbps")
self.max_bitrate_kbps.setSpecialValueText("Disabled")
gen_layout.addRow("Max Bitrate:", self.max_bitrate_kbps)

self.timeout_seconds = QSpinBox()
self.timeout_seconds.setRange(60, 3600)
self.timeout_seconds.setSuffix(" seconds")
gen_layout.addRow("Transcode Timeout:", self.timeout_seconds)

self.backup_suffix = QLineEdit()
self.backup_suffix.setPlaceholderText(".source")
gen_layout.addRow("Backup Suffix:", self.backup_suffix)

self.min_free_space_mb = QSpinBox()
self.min_free_space_mb.setRange(0, 10000)
self.min_free_space_mb.setSuffix(" MB")
gen_layout.addRow("Min Free Space:", self.min_free_space_mb)
```

---

## Conditional Settings Dependencies

### Problem Analysis

Several settings have dependencies on other settings, similar to the USDB integration issue. Based on code analysis of [`transcoder.py`](../addons/melody_mania_transcoder/transcoder.py), these dependencies exist:

#### Dependency Chain 1: Hardware Acceleration (Simplified)

**Location:** Lines 107-118 in [`transcoder.py`](../addons/melody_mania_transcoder/transcoder.py:107)

```python
codec_cfg = getattr(cfg, cfg.target_codec)
codec_allows_hw = bool(getattr(codec_cfg, "use_quicksync", False))
if cfg.general.hardware_acceleration and codec_allows_hw:
    accel = get_best_accelerator(cfg.target_codec)
```

**Current behavior:**
- Per-codec `use_quicksync` settings (H.264, HEVC) control hardware acceleration per encoder
- VP8 doesn't have `use_quicksync` (software-only codec)

**Simplified design:**
- Remove per-codec `use_quicksync` settings from GUI
- Rely solely on global `Hardware Acceleration` setting
- When global setting is ON, use best available hardware acceleration for the selected codec
- Simplifies UX: one toggle controls hardware acceleration for all supported codecs

**Rationale:**
- Users who enable hardware acceleration want it for all codecs
- Selecting hardware accel method (QuickSync, NVENC, etc.) should be automatic based on available hardware
- Reduces cognitive load and settings complexity
- Per-codec settings still exist in config for advanced users (manual JSON editing)

**UI Implementation:**
- Remove QuickSync checkboxes from H.264 and HEVC settings panels
- Keep only global "Hardware Acceleration" checkbox in general settings
- Update tooltip to explain it applies to all supported codecs

#### Dependency Chain 2: Hardware Decode → Disabled by Filters

**Location:** Lines 122-127 in [`transcoder.py`](../addons/melody_mania_transcoder/transcoder.py:122)

```python
if accel is not None and cfg.general.hardware_decode:
    if cfg.general.max_resolution or cfg.general.max_fps:
        slog.debug(
            "Disabling hardware decode for this run (filters requested); using hardware encode only."
        )
        cfg = replace(cfg, general=replace(cfg.general, hardware_decode=False))
```

**Dependency:**
- `hardware_decode` is automatically disabled when resolution/FPS filters are needed
- User can still set it, but it will be overridden at runtime if filters are required

**UI Behavior:**
- Always show `hardware_decode` checkbox (user can set preference)
- Add informational tooltip explaining automatic override behavior
- Don't gray out (it's still a valid preference, just conditionally overridden)

#### Dependency Chain 3: Container Selection → Codec Type

**Location:** Lines 131-133 in [`transcoder.py`](../addons/melody_mania_transcoder/transcoder.py:131)

```python
caps = handler.capabilities()
container = getattr(codec_cfg, "container", None) or caps.container
```

**Dependency:**
- Different codecs support different containers
- H.264/HEVC: mp4, mkv, mov (default: mp4)
- VP8: webm, mkv (default: webm) - mp4 not valid!

**UI Behavior:**
- Each codec panel shows only valid containers for that codec
- Different ComboBox items per codec

#### Dependency Chain 4: USDB Integration → Manual Limits

**Location:** Lines 291-297 in [`transcoder.py`](../addons/melody_mania_transcoder/transcoder.py:291)

Already designed in Issue 2 - manual resolution/FPS fields hidden when USDB toggles are ON.

### Conditional Settings Design

#### Implementation Strategy

Use Qt's signal/slot mechanism to enable/disable widgets dynamically:

```python
class TranscoderSettingsDialog(QDialog):
    def _setup_ui(self):
        # ... existing code ...
        
        # Connect USDB toggles to manual limit visibility
        self.use_usdb_res.stateChanged.connect(self._toggle_manual_resolution)
        self.use_usdb_fps.stateChanged.connect(self._toggle_manual_fps)
        
    def _toggle_manual_resolution(self, state: Qt.CheckState):
        """Show/hide manual resolution inputs based on USDB integration."""
        is_usdb_enabled = (state == Qt.CheckState.Checked)
        
        self.manual_res_label.setVisible(not is_usdb_enabled)
        self.manual_res_width.setVisible(not is_usdb_enabled)
        self.manual_res_height.setVisible(not is_usdb_enabled)
        
    def _toggle_manual_fps(self, state: Qt.CheckState):
        """Show/hide manual FPS input based on USDB integration."""
        is_usdb_enabled = (state == Qt.CheckState.Checked)
        
        self.manual_fps_label.setVisible(not is_usdb_enabled)
        self.manual_fps.setVisible(not is_usdb_enabled)
    
    def _load_settings(self):
        """Load settings and update dependent widget states."""
        # Load all settings first
        self.enabled.setChecked(self.cfg.enabled)
        self.hw_accel.setChecked(self.cfg.general.hardware_acceleration)
        # ... load all other settings ...
        
        # IMPORTANT: Trigger dependency updates after loading
        self._toggle_manual_resolution(
            Qt.CheckState.Checked if self.cfg.usdb_integration.use_usdb_resolution else Qt.CheckState.Unchecked
        )
        self._toggle_manual_fps(
            Qt.CheckState.Checked if self.cfg.usdb_integration.use_usdb_fps else Qt.CheckState.Unchecked
        )
```

#### Widget State Matrix

| Master Setting | Dependent Setting | When Disabled | When Enabled |
|----------------|-------------------|---------------|--------------|
| Use USDB Max Resolution | Manual Max Resolution | Hidden | Visible |
| Use USDB Max FPS | Manual Max FPS | Hidden | Visible |
| Target Codec = h264 | Container options | mp4, mkv, mov | N/A |
| Target Codec = hevc | Container options | mp4, mkv, mov | N/A |
| Target Codec = vp8 | Container options | webm, mkv | N/A |

#### Visual Feedback Patterns

**For conditional visibility (Manual limits):**
- Use `QWidget.setVisible(False)` to hide
- Layout adjusts (acceptable here because exclusive choice)
- Clear mutual exclusion (either USDB or manual, not both)

**For container selection:**
- Each codec panel has its own ComboBox with appropriate items
- No dynamic enable/disable needed (always valid options shown)

#### Hardware Decode Special Case

Hardware decode is a **preference**, not a strict setting. It's auto-disabled at runtime if filters are needed (lines 122-127), but we should still let users set their preference.

**UI approach:**
```python
self.hw_decode = QCheckBox("Hardware Decoding")
self.hw_decode.setToolTip(
    "<b>Hardware Decoding</b><br/>"
    "Use hardware-accelerated decoding for input videos.<br/>"
    "<br/>"
    "<b>⚠️ Auto-Disabled When:</b><br/>"
    "• Resolution or FPS limits are active<br/>"
    "• Automatically switches to hardware encode + software decode<br/>"
    "• This prevents hardware surface compatibility issues<br/>"
    "<br/>"
    "<b>Impact:</b> Slightly faster when no filters needed<br/>"
    "<b>Recommended:</b> Enable (auto-managed by addon)"
)
```

**Rationale:** Don't gray out or hide - just inform user of automatic behavior. Their preference is recorded and used when possible.

#### Save/Load Considerations

**When saving hidden settings:**
```python
def save_settings(self):
    # For hidden manual limits, save None if USDB integration is ON
    if self.use_usdb_res.isChecked():
        self.cfg.general.max_resolution = None
    else:
        self.cfg.general.max_resolution = (
            self.manual_res_width.value(),
            self.manual_res_height.value()
        )
    
    if self.use_usdb_fps.isChecked():
        self.cfg.general.max_fps = None
    else:
        self.cfg.general.max_fps = self.manual_fps.value()
```

**Rationale:** Hidden settings are mutually exclusive with USDB integration, so clear them when USDB is enabled.

---

## Issue 3: User Guidance for Settings

### Tooltip Implementation Strategy

Use `QWidget.setToolTip()` to provide context-sensitive help.

**Format pattern:**
```
<b>Setting Name</b><br/>
Brief description of what this setting does.<br/>
<br/>
<b>Values:</b> Valid range or options<br/>
<b>Impact:</b> How it affects quality/size/compatibility<br/>
<b>Recommended:</b> Suggested value for karaoke/music videos
```

### Complete Tooltip Specifications

#### General Settings

**Enable Addon:**
```
<b>Enable Addon</b><br/>
Enable or disable the Melody Mania Transcoder addon.<br/>
When disabled, videos are downloaded without transcoding.
```

**Hardware Acceleration:**
```
<b>Hardware Acceleration</b><br/>
Use Intel QuickSync Video (QSV) for faster encoding when available.<br/>
<br/>
<b>Impact:</b> 3-5x faster encoding on supported Intel CPUs<br/>
<b>Compatibility:</b> Requires Intel processor with QuickSync support (6th gen or newer)<br/>
<b>Recommended:</b> Enable if you have a compatible Intel CPU
```

**Hardware Decoding:**
```
<b>Hardware Decoding</b><br/>
Use hardware-accelerated decoding for input videos.<br/>
<br/>
<b>⚠️ Automatically Disabled When:</b><br/>
• Resolution or FPS limits are configured<br/>
• Addon uses hardware encode + software decode instead<br/>
• Prevents hardware/software surface conversion issues<br/>
<br/>
<b>Impact:</b> Slightly faster decode when filters not needed<br/>
<b>Recommended:</b> Enable (addon auto-manages based on filters)<br/>
<br/>
Your preference is saved and used when no filters are active.
```

**Backup Original Files:**
```
<b>Backup Original Files</b><br/>
Keep a copy of the original video before transcoding.<br/>
<br/>
<b>Impact:</b> Doubles disk space usage temporarily<br/>
<b>Recommended:</b> Enable for safety (you can delete backups later)
```

**Verify Output Files:**
```
<b>Verify Output Files</b><br/>
Check transcoded videos can be read by ffprobe after encoding.<br/>
<br/>
<b>Impact:</b> Adds 1-2 seconds per video, prevents corrupted outputs<br/>
<b>Recommended:</b> Enable (catches rare encoding errors)
```

**Backup Suffix:**
```
<b>Backup Suffix</b><br/>
File extension added to original videos when backing up.<br/>
<br/>
<b>Example:</b> video.mp4 → video.source.mp4<br/>
<b>Default:</b> .source
```

**Min Free Space:**
```
<b>Minimum Free Space</b><br/>
Required free disk space before starting transcode.<br/>
<br/>
<b>Impact:</b> Prevents disk full errors during encoding<br/>
<b>Recommended:</b> 500-1000 MB (default: 500 MB)
```

**Transcode Timeout:**
```
<b>Transcode Timeout</b><br/>
Maximum time allowed for encoding a single video.<br/>
<br/>
<b>Impact:</b> Prevents infinite hangs on problematic videos<br/>
<b>Recommended:</b> 600 seconds (10 min) for most videos,<br/>
increase to 1800 (30 min) for 4K content
```

**Max Bitrate:**
```
<b>Maximum Bitrate</b><br/>
Cap video bitrate to control file size.<br/>
<br/>
<b>Values:</b> 0 (disabled) to 100000 kbps<br/>
<b>Impact:</b> Lower = smaller files but quality loss if too aggressive<br/>
<b>Recommended:</b> Disabled (let CRF control quality),<br/>
or 8000 kbps for 1080p / 16000 kbps for 4K
```

#### USDB Integration

**Use USDB Max Resolution:**
```
<b>Use USDB Max Resolution</b><br/>
Apply resolution limit from USDB Syncer settings.<br/>
<br/>
<b>Behavior:</b> Videos exceeding USDB's max resolution<br/>
will be downscaled. Videos already below the limit are unchanged.<br/>
<br/>
<b>When disabled:</b> Use addon's own manual resolution limit instead
```

**Manual Max Resolution:**
```
<b>Manual Max Resolution</b><br/>
Set maximum video dimensions (only when USDB integration is disabled).<br/>
<br/>
<b>Behavior:</b> Videos exceeding this resolution will be downscaled<br/>
while maintaining aspect ratio. Smaller videos are unchanged.<br/>
<br/>
<b>Common values:</b><br/>
• 1920×1080 (1080p) - Best balance for most use cases<br/>
• 1280×720 (720p) - Save space on older hardware<br/>
• 3840×2160 (4K) - Maximum quality for modern systems
```

**Use USDB Max FPS:**
```
<b>Use USDB Max FPS</b><br/>
Apply FPS (frames per second) limit from USDB Syncer settings.<br/>
<br/>
<b>Behavior:</b> Videos exceeding USDB's max FPS<br/>
will be reduced. Videos already below the limit are unchanged.<br/>
<br/>
<b>When disabled:</b> Use addon's own manual FPS limit instead
```

**Manual Max FPS:**
```
<b>Manual Max FPS</b><br/>
Set maximum frame rate (only when USDB integration is disabled).<br/>
<br/>
<b>Behavior:</b> Videos exceeding this FPS will be reduced<br/>
(frame dropping, not interpolation). Lower FPS videos are unchanged.<br/>
<br/>
<b>Common values:</b><br/>
• 30 fps - Standard for most karaoke content<br/>
• 60 fps - Smooth motion for modern displays<br/>
• 24 fps - Cinematic look, smallest file size
```

#### H.264 Settings

**CRF (Constant Rate Factor):**
```
<b>CRF - Constant Rate Factor</b><br/>
Controls video quality. Lower = better quality, larger file size.<br/>
<br/>
<b>Values:</b> 0-51 (0 = lossless, 51 = worst quality)<br/>
<b>Impact:</b> ±6 CRF points ≈ doubles or halves file size<br/>
<b>Recommended for karaoke:</b><br/>
• 18 - High quality (default, good for preservation)<br/>
• 23 - Medium quality (good balance)<br/>
• 28 - Lower quality (small files, acceptable for practice)
```

**Profile:**
```
<b>H.264 Profile</b><br/>
Encoding profile that controls feature set and compatibility.<br/>
<br/>
<b>Values:</b><br/>
• baseline - Maximum compatibility (old devices, web)<br/>
• main - Balanced (most devices, recommended)<br/>
• high - Best compression (modern devices only)<br/>
<br/>
<b>Impact:</b> Lower profiles = wider compatibility but larger files<br/>
<b>Recommended:</b> baseline (Unity requires it for best compatibility)
```

**Level:**
```
<b>H.264 Level</b><br/>
Defines processing requirements and maximum resolution/bitrate.<br/>
<br/>
<b>Common values:</b><br/>
• 3.1 - Up to 720p @ 30fps (default, wide compatibility)<br/>
• 4.0 - Up to 1080p @ 30fps<br/>
• 4.1 - Up to 1080p @ 60fps<br/>
• 5.1 - Up to 4K @ 30fps<br/>
<br/>
<b>Recommended:</b> 3.1 (unless you need higher resolution/fps)
```

**Pixel Format:**
```
<b>Pixel Format</b><br/>
Color sampling and bit depth.<br/>
<br/>
<b>Values:</b><br/>
• yuv420p - 4:2:0 subsampling (standard, best compatibility)<br/>
• yuv422p - 4:2:2 subsampling (better color, larger files)<br/>
• yuv444p - 4:4:4 no subsampling (highest quality, largest)<br/>
<br/>
<b>Recommended:</b> yuv420p (Unity compatibility, sufficient quality)
```

**Preset:**
```
<b>Encoding Preset</b><br/>
Speed vs. compression efficiency trade-off.<br/>
<br/>
<b>Values:</b> ultrafast, superfast, veryfast, faster, fast,<br/>
medium, slow, slower, veryslow<br/>
<br/>
<b>Impact:</b> Slower presets = smaller files at same quality<br/>
(20-30% size reduction from ultrafast → veryslow)<br/>
<b>Encoding time:</b> each step ~40% slower<br/>
<br/>
<b>Recommended:</b><br/>
• slow - Good balance (default, worth the wait)<br/>
• medium - Faster encoding, slightly larger files<br/>
• fast - Quick encodes for testing
```

**Use QuickSync:**
```
<b>Use Intel QuickSync</b><br/>
Enable hardware-accelerated H.264 encoding.<br/>
<br/>
<b>Impact:</b> 3-5x faster encoding, slightly larger files<br/>
(~10-15% vs. software libx264 at same quality)<br/>
<b>Compatibility:</b> Requires Intel 6th gen (Skylake) or newer<br/>
<br/>
<b>Recommended:</b> Enable if available (speed worth minor size increase)
```

**Container:**
```
<b>Output Container</b><br/>
File format for the transcoded video.<br/>
<br/>
<b>Values:</b><br/>
• mp4 - Best compatibility (default, recommended)<br/>
• mkv - Matroska, supports more features<br/>
• mov - QuickTime format (macOS/iOS preferred)<br/>
<br/>
<b>Recommended:</b> mp4 (Unity and most players)
```

#### HEVC (H.265) Settings

**CRF:**
```
<b>CRF - Constant Rate Factor</b><br/>
Controls video quality. Lower = better quality, larger file size.<br/>
<br/>
<b>Values:</b> 0-51 (0 = lossless, 51 = worst quality)<br/>
<b>Impact:</b> HEVC is ~40% more efficient than H.264,<br/>
so CRF 20 in HEVC ≈ CRF 18 in H.264<br/>
<br/>
<b>Recommended for karaoke:</b><br/>
• 20 - High quality (default)<br/>
• 24 - Medium quality (good balance)<br/>
• 28 - Lower quality (small files)
```

**Profile:**
```
<b>HEVC Profile</b><br/>
Encoding profile for HEVC/H.265.<br/>
<br/>
<b>Values:</b><br/>
• main - 8-bit color (standard, best compatibility)<br/>
• main10 - 10-bit color (better gradients, HDR support)<br/>
<br/>
<b>Impact:</b> main10 = slightly larger files, requires modern players<br/>
<b>Recommended:</b> main (unless you have 10-bit source content)
```

**Level:**
```
<b>HEVC Level</b><br/>
Defines processing requirements and maximum resolution/bitrate.<br/>
<br/>
<b>Common values:</b><br/>
• 4.0 - Up to 1080p @ 30fps (default)<br/>
• 4.1 - Up to 1080p @ 60fps<br/>
• 5.0 - Up to 4K @ 30fps<br/>
• 5.1 - Up to 4K @ 60fps<br/>
<br/>
<b>Recommended:</b> 4.0 (unless you need higher resolution/fps)
```

**Pixel Format:**
```
<b>Pixel Format</b><br/>
Color sampling and bit depth.<br/>
<br/>
<b>Values:</b><br/>
• yuv420p - 8-bit 4:2:0 (standard, best compatibility)<br/>
• yuv420p10le - 10-bit 4:2:0 (HDR, main10 profile)<br/>
• yuv422p - 8-bit 4:2:2 (professional)<br/>
• yuv444p - 8-bit 4:4:4 (highest quality)<br/>
<br/>
<b>Recommended:</b> yuv420p (standard content)
```

**Preset, Use QuickSync, Container:**
Same tooltips as H.264 equivalents (substitute "HEVC" for "H.264" where applicable).

#### VP8 Settings

**CRF:**
```
<b>CRF - Constant Rate Factor</b><br/>
Controls video quality. Lower = better quality, larger file size.<br/>
<br/>
<b>Values:</b> 0-63 (note: VP8 uses wider range than H.264)<br/>
<b>Impact:</b> VP8 CRF 10 ≈ H.264 CRF 18 in quality<br/>
<br/>
<b>Recommended for karaoke:</b><br/>
• 10 - High quality (default)<br/>
• 20 - Medium quality<br/>
• 30 - Lower quality (small files)
```

**CPU Used:**
```
<b>CPU Used</b><br/>
Speed vs. quality trade-off for VP8 encoding.<br/>
<br/>
<b>Values:</b> 0-5<br/>
• 0 - Best quality, slowest (like H.264 "veryslow")<br/>
• 1 - Good quality (default, like H.264 "slow")<br/>
• 2-3 - Balanced (like H.264 "medium")<br/>
• 4-5 - Fast encoding, lower efficiency<br/>
<br/>
<b>Impact:</b> Each step faster = ~10-20% larger files<br/>
<b>Recommended:</b> 1 (good balance)
```

**Container:**
```
<b>Output Container</b><br/>
File format for the transcoded video.<br/>
<br/>
<b>Values:</b><br/>
• webm - Native VP8 container (recommended)<br/>
• mkv - Matroska, also supports VP8<br/>
<br/>
<b>Recommended:</b> webm (best compatibility with VP8)
```

---

## Config Schema Changes

### Required Additions to [`config.py`](../addons/melody_mania_transcoder/config.py)

No breaking changes - only expose existing fields in GUI. However, for completeness, ensure all config fields have sensible defaults:

```python
@dataclass
class H264Config:
    """Configuration for H.264 encoding."""
    profile: H264Profile = "baseline"  # ✓ Already defined
    level: str = "3.1"                 # ✓ Already defined
    pixel_format: str = "yuv420p"      # ✓ Already defined
    crf: int = 18                      # ✓ Already defined
    preset: str = "slow"               # ✓ Already defined
    use_quicksync: bool = True         # ✓ Already defined
    container: str = "mp4"             # ✓ Already defined

@dataclass
class VP8Config:
    """Configuration for VP8 encoding."""
    crf: int = 10                      # ✓ Already defined
    cpu_used: int = 1                  # ✓ Already defined
    container: str = "webm"            # ✓ Already defined

@dataclass
class HEVCConfig:
    """Configuration for HEVC encoding."""
    profile: HEVCProfile = "main"      # ✓ Already defined
    level: str = "4.0"                 # ✓ Already defined
    pixel_format: str = "yuv420p"      # ✓ Already defined
    crf: int = 20                      # ✓ Already defined
    preset: str = "slow"               # ✓ Already defined
    use_quicksync: bool = True         # ✓ Already defined
    container: str = "mp4"             # ✓ Already defined

@dataclass
class GeneralConfig:
    """General transcoding settings."""
    hardware_acceleration: bool = True
    hardware_decode: bool = True
    backup_original: bool = True
    backup_suffix: str = ".source"
    max_resolution: Optional[tuple[int, int]] = None  # Expose when use_usdb_resolution=False
    max_fps: Optional[int] = None                     # Expose when use_usdb_fps=False
    max_bitrate_kbps: Optional[int] = None            # Expose in GUI
    timeout_seconds: int = 600                        # Expose in GUI
    verify_output: bool = True
    min_free_space_mb: int = 500                      # Expose in GUI
```

**Verdict:** All fields already exist with good defaults. No schema changes needed.

---

## Issue 4: Menu Icons for Addon Actions

### Current Behavior

The addon currently adds two menu items to the Tools menu in [`__init__.py`](../addons/melody_mania_transcoder/__init__.py):
- "Transcoder Settings..."
- "Transcode All Videos..."

These menu items **do not have icons** and use the "..." suffix, which is inconsistent with other USDB Syncer menu items.

### Required Changes

1. **Remove "..." suffix** from menu text to match USDB Syncer style
2. **Add icons** to both menu items for better visual recognition
3. **Support theme switching** (dark/light) for icons

### Recommended Icons

Based on USDB Syncer's existing icon set (from [`src/usdb_syncer/Gui/icons.py`](../src/usdb_syncer/gui/icons.py)):

**"Transcoder Settings" menu item:**
- **Icon:** [`Icon.VIDEO`](../src/usdb_syncer/gui/icons.py:102)
- **Files:** `video.png` / `filmstrip-white.svg`
- **Rationale:** Clearly indicates video-related settings

**"Transcode All Videos" menu item:**
- **Icon:** [`Icon.FFMPEG`](../src/usdb_syncer/gui/icons.py:48)
- **File:** `ffmpeg.svg`
- **Rationale:** Explicitly conveys transcoding/encoding action

### Implementation Design

#### A. Store Action References

Currently the addon doesn't store references to the created actions. Update to:

```python
class TranscoderAddon:
    def __init__(self):
        self.settings_action: Optional[QAction] = None
        self.batch_action: Optional[QAction] = None
        self.main_window: Optional[QMainWindow] = None
```

#### B. Update Menu Creation

Modify the [`MainWindowDidLoad`](../src/usdb_syncer/gui/hooks.py:13) callback:

```python
def _on_main_window_loaded(main_window: QMainWindow):
    """Called when the main window is ready."""
    from usdb_syncer.gui import icons
    
    # Store reference for theme updates
    addon.main_window = main_window
    
    # Create actions WITH icons
    addon.settings_action = main_window.menu_tools.addAction(
        "Transcoder Settings",  # No "..." suffix
        lambda: _open_settings(main_window)
    )
    addon.settings_action.setIcon(icons.Icon.VIDEO.icon())
    
    addon.batch_action = main_window.menu_tools.addAction(
        "Transcode All Videos",  # No "..." suffix
        lambda: _start_batch_transcode(main_window)
    )
    addon.batch_action.setIcon(icons.Icon.FFMPEG.icon())
    
    # Subscribe to theme changes to update icons
    from usdb_syncer.gui import events
    events.ThemeChanged.subscribe(_on_theme_changed)
```

#### C. Handle Theme Changes

Add theme change handler to update icons:

```python
def _on_theme_changed(theme_key: str):
    """Update menu icons when theme changes."""
    if addon.settings_action and addon.batch_action:
        from usdb_syncer.gui import icons
        addon.settings_action.setIcon(icons.Icon.VIDEO.icon())
        addon.batch_action.setIcon(icons.Icon.FFMPEG.icon())
```

**Note:** The [`Icon.icon()`](../src/usdb_syncer/gui/icons.py:120) method automatically returns the correct themed version based on current theme state.

#### D. File Modifications

**File:** [`__init__.py`](../addons/melody_mania_transcoder/__init__.py)

Changes needed:
1. Add addon class attributes for action storage
2. Import icons module: `from usdb_syncer.gui import icons, events`
3. Update menu item text (remove "...")
4. Call `.setIcon()` on actions after creation
5. Subscribe to `ThemeChanged` event
6. Add `_on_theme_changed()` callback function

### Alternative Implementations

#### Option A: Inline Icons (RECOMMENDED)

Set icons immediately when creating actions, subscribe to theme events.

**Pros:**
- Follows USDB Syncer pattern ([`mw.py`](../src/usdb_syncer/gui/mw.py:510))
- Icons update with theme changes
- Clean separation of concerns

**Cons:**
- Slightly more code (theme handler)

#### Option B: No Theme Support

Set icons once, don't subscribe to theme changes.

**Pros:**
- Simpler implementation

**Cons:**
- Icons don't update when user changes theme
- Inconsistent with rest of USDB Syncer
- **NOT RECOMMENDED**

### Menu Text Examples

**Before:**
- "Transcoder Settings..."
- "Transcode All Videos..."

**After:**
- "Transcoder Settings" (with VIDEO icon)
- "Transcode All Videos" (with FFMPEG icon)

### Testing

1. **Visual verification:** Icons appear next to menu items
2. **Theme switching:** Icons update when switching between dark/light themes
3. **macOS compatibility** Icons visible on macOS (requires `AA_DontShowIconsInMenus=False`, already set by USDB Syncer)

---

## Implementation Strategy

### Phase 1: Fix USDB Limit Enforcement (Issue 1)

**Priority:** HIGH - This is a functional bug affecting transcoding decisions

**Steps:**
1. Rename `_apply_usdb_integration()` → `_apply_limits()` in [`transcoder.py`](../addons/melody_mania_transcoder/transcoder.py)
2. Update function signature to accept `video_info` parameter
3. Implement "lesser of" logic for resolution and FPS limits
4. Move call site from line 105 to between lines 52-70 (after video analysis, before needs_transcoding)
5. Add unit tests for limit calculation logic

**Estimated complexity:** MEDIUM (core logic change, careful testing needed)

**Testing requirements:**
- Test with source < limit (should not upscale)
- Test with source > limit (should downscale)
- Test with USDB integration enabled/disabled
- Test with no limits configured
- Test aspect ratio preservation

### Phase 2: Implement Dynamic Codec Settings UI (Issue 2 + Conditional Settings)

**Priority:** MEDIUM - UX improvement, unlocks advanced settings

**Steps:**
1. Create new widget builder functions in [`settings_gui.py`](../addons/melody_mania_transcoder/settings_gui.py):
   - `_create_h264_settings()` → returns QWidget with all H.264 controls
   - `_create_hevc_settings()` → returns QWidget with all HEVC controls
   - `_create_vp8_settings()` → returns QWidget with all VP8 controls
2. Add `QStackedWidget` to dialog layout
3. Connect target codec ComboBox to stack widget index
4. Implement conditional resolution/FPS fields (shown when USDB integration is OFF)
5. **Implement conditional settings dependencies** (see "Conditional Settings Dependencies" section):
   - Add `_toggle_quicksync_availability()` signal handler
   - Connect hardware acceleration checkbox to QuickSync enable/disable
   - Update QuickSync tooltips dynamically based on state
   - Implement proper container options per codec (H.264/HEVC: mp4/mkv/mov, VP8: webm/mkv)
6. Update `_load_settings()` to:
   - Load all settings from config
   - **Trigger all conditional update functions after loading** (hardware accel, USDB toggles)
7. Update `save_settings()` to:
   - Save all widget values (**even if currently disabled** - preserves user choices)
   - Handle manual resolution/FPS correctly (None when USDB integration ON)
8. Test UI responsiveness (switching between codecs should be instant, no flicker)

**Estimated complexity:** MEDIUM-HIGH (lots of widgets, state management, dynamic dependencies)

**UI/UX considerations:**
- Group settings logically (Quality / Performance / Output)
- Use consistent widget types (ComboBox for enums, SpinBox for numbers)
- Set appropriate min/max ranges on all numeric inputs
- Dialog should resize smoothly when switching codecs
- QuickSync controls should gray out smoothly (not hide) when hardware acceleration is OFF
- Manual limits should hide/show smoothly when toggling USDB integration

### Phase 3: Add Tooltips (Issue 3)

**Priority:** LOW - Quality of life improvement

**Steps:**
1. Add `.setToolTip()` calls for every widget created in Phase 2
2. Use HTML formatting for readability (`<b>`, `<br/>`, etc.)
3. Test tooltips appear correctly on hover
4. Consider adding "?" tooltip buttons for complex settings (optional)

**Estimated complexity:** LOW (just adding strings, but write them carefully)

**Writing guidelines:**
- Keep tooltips concise but informative
- Include practical examples
- Explain impact on quality/size/speed
- Provide recommended values
- Use consistent formatting across all tooltips

### Phase 4: Integration Testing

**Priority:** HIGH - Ensure all changes work together

**Test scenarios:**
1. **USDB Integration ON:**
   - Manual resolution/FPS fields hidden
   - USDB limits correctly applied before transcoding decision
   - Video below limit → not transcoded (unless codec differs)
   - Video above limit → transcoded with downscale

2. **USDB Integration OFF:**
   - Manual resolution/FPS fields visible
   - Addon's own limits correctly applied
   - Same limit enforcement behavior as USDB case

3. **Codec Switching:**
   - UI shows correct settings for selected codec
   - Settings persist when switching between codecs
   - Save/load correctly handles all codec configs
   - Container options are codec-specific (H.264/HEVC: mp4/mkv/mov, VP8: webm/mkv)

4. **Hardware Acceleration Dependencies:**
   - When hardware acceleration is OFF → QuickSync checkboxes disabled (grayed)
   - When hardware acceleration is ON → QuickSync checkboxes enabled
   - QuickSync settings are saved even when disabled
   - Tooltips update dynamically to explain disabled state

5. **USDB Toggle Dependencies:**
   - Toggling "Use USDB Max Resolution" hides/shows manual resolution fields
   - Toggling "Use USDB Max FPS" hides/shows manual FPS field
   - Manual limits are cleared (set to None) when USDB integration is enabled
   - Manual limits are preserved when USDB integration is re-disabled

6. **Settings Persistence:**
   - Disabled QuickSync preferences are saved and restored
   - Hidden manual limits are saved as None when USDB integration is ON
   - All settings load correctly on dialog open
   - Conditional update functions fire correctly after load

7. **Edge Cases:**
   - USDB Syncer module unavailable → graceful fallback
   - Invalid user input → validation/clamping
   - Very small/large resolution values → handled correctly
   - Rapidly toggling hardware acceleration → no UI glitches
   - Switching codecs with hardware acceleration OFF → QuickSync still grayed

**Acceptance criteria:**
- All unit tests pass
- Manual testing confirms expected behavior
- No regressions in existing functionality
- UI is responsive and intuitive
- Dependencies update correctly and immediately
- No layout jumping or flashing during state changes

---

## File Change Summary

### Files to Modify

1. **[`transcoder.py`](../addons/melody_mania_transcoder/transcoder.py)**
   - Rename `_apply_usdb_integration()` → `_apply_limits()`
   - Add `video_info` parameter to new function
   - Implement "lesser of" logic for limits
   - Move function call earlier (line ~67 instead of 105)
   - Update imports (none needed)

2. **[`settings_gui.py`](../addons/melody_mania_transcoder/settings_gui.py)**
   - Add `QStackedWidget` for codec-specific settings
   - Create `_create_h264_settings()` method (NO QuickSync checkbox)
   - Create `_create_hevc_settings()` method (NO QuickSync checkbox)
   - Create `_create_vp8_settings()` method
   - Add `_on_codec_changed()` signal handler
   - Add conditional resolution/FPS fields with show/hide logic
   - Update `_load_settings()` to populate all new widgets
   - Update `save_settings()` to persist all new settings
   - Add `.setToolTip()` calls for all widgets (100+ tooltips)
   - Update Hardware Acceleration tooltip to explain global behavior

3. **[`__init__.py`](../addons/melody_mania_transcoder/__init__.py)**
   - Add class attributes to store action references
   - Import icons and events modules from USDB Syncer
   - Update menu text (remove "..." suffix)
   - Set icons on menu actions (VIDEO for settings, FFMPEG for batch)
   - Subscribe to `ThemeChanged` event
   - Add `_on_theme_changed()` callback to update icons

4. **[`config.py`](../addons/melody_mania_transcoder/config.py)**
   - NO CHANGES NEEDED (schema already supports all settings)

5. **[`video_analyzer.py`](../addons/melody_mania_transcoder/video_analyzer.py)**
   - NO CHANGES NEEDED (already checks cfg.general limits)

6. **[`codecs.py`](../addons/melody_mania_transcoder/codecs.py)**
   - NO CHANGES NEEDED (already reads from config)

### Files NOT Changed

- [`batch.py`](../addons/melody_mania_transcoder/batch.py) - Uses public API, no changes needed
- [`hwaccel.py`](../addons/melody_mania_transcoder/hwaccel.py) - Hardware detection, unaffected
- [`sync_meta_updater.py`](../addons/melody_mania_transcoder/sync_meta_updater.py) - Only updates metadata, unaffected
- [`utils.py`](../addons/melody_mania_transcoder/utils.py) - Generic utilities, unaffected

---

## Risk Assessment

### High Risk Areas

1. **Limit Enforcement Logic:**
   - **Risk:** Incorrect "lesser of" calculation could cause upscaling or skip needed transcodes
   - **Mitigation:** Comprehensive unit tests, manual testing with various source/limit combinations
   - **Rollback strategy:** Easy to revert (keep old `_apply_usdb_integration()` in comments during development)

2. **Aspect Ratio Preservation:**
   - **Risk:** Incorrect resolution limiting could distort videos
   - **Mitigation:** Use ffmpeg's `scale` filter with `force_original_aspect_ratio=decrease` (already implemented)
   - **Testing:** Verify output aspect ratio matches input in all test cases

### Medium Risk Areas

1. **UI State Management:**
   - **Risk:** Settings might not save/load correctly for all codecs
   - **Mitigation:** Test save/load cycle for each codec, write validation for all inputs
   - **Impact:** User annoyance (settings reset), but no data corruption

2. **USDB Integration Fallback:**
   - **Risk:** Crash if USDB Syncer unavailable
   - **Mitigation:** Existing try/except block in `_apply_usdb_integration()`, keep it in `_apply_limits()`
   - **Testing:** Test with USDB module mocked as unavailable

### Low Risk Areas

1. **Tooltips:**
   - **Risk:** Typos or incorrect information in tooltips
   - **Mitigation:** Peer review, spell check
   - **Impact:** Minor user confusion, easy to fix in iterative updates

2. **UI Layout:**
   - **Risk:** Dialog might be too large on small screens
   - **Mitigation:** Test on 1366×768 laptop display, add scrollbars if needed
   - **Impact:** Cosmetic only

---

## Future Enhancements

### Post-MVP Improvements

1. **Preset System:**
   - Add "Quality Presets" dropdown: "High Quality", "Balanced", "Small Files"
   - Each preset configures CRF, preset, resolution, FPS with one click
   - Simplifies UX for users who don't want to tweak individual settings

2. **Live Preview:**
   - Show estimated file size based on current settings
   - Calculate based on source bitrate/duration and target CRF
   - Helps users make informed trade-offs

3. **Per-Song Overrides:**
   - Allow settings override for specific songs/folders
   - Useful for mixed libraries (4K concert footage + SD karaoke)
   - Requires integration with USDB Syncer's song metadata system

4. **Batch Simulation:**
   - "Preview" mode that shows what would be transcoded without doing it
   - Reports: X videos need transcode, estimated total time/space
   - Helps users validate settings before processing entire library

5. **Hardware Accelerator Detection:**
   - Show detected hardware capabilities in UI
   - Gray out QuickSync option if not available
   - Add support for NVENC (NVIDIA) and VideoToolbox (macOS)

6. **Adaptive Quality:**
   - Analyze source quality (bitrate, sharpness) and adjust CRF automatically
   - Avoid wasting bits on low-quality sources
   - More complex, but could save significant space

---

## Appendix: Diagram

### Current Architecture (BROKEN)

```
┌──────────────────┐
│  process_video() │
└────────┬─────────┘
         │
         ▼
   ┌───────────────┐
   │ analyze_video │ ─► VideoInfo (source resolution, FPS)
   └───────┬───────┘
           │
           ▼
   ┌─────────────────────┐
   │ needs_transcoding?  │ ◄── Uses cfg.general.max_resolution/max_fps
   └─────────┬───────────┘     (NOT YET POPULATED FROM USDB!)
             │
             ▼
      ┌──────────┐
      │ Skip? No │
      └────┬─────┘
           │
           ▼
   ┌────────────────────────┐
   │ _apply_usdb_integration│ ◄── TOO LATE! Decision already made
   └────────────────────────┘
           │
           ▼
   ┌───────────────┐
   │ build_command │
   └───────────────┘
```

### Fixed Architecture (CORRECT)

```
┌──────────────────┐
│  process_video() │
└────────┬─────────┘
         │
         ▼
   ┌───────────────┐
   │ analyze_video │ ─► VideoInfo (source resolution, FPS)
   └───────┬───────┘
           │
           ▼
   ┌──────────────────────┐
   │   _apply_limits()     │ ◄── NEW: Happens BEFORE decision
   │  (with video_info)   │     Computes min(source, limit)
   └──────────┬───────────┘
              │
              ▼ cfg.general.* now populated
   ┌─────────────────────┐
   │ needs_transcoding?  │ ◄── Now sees correct limits!
   └─────────┬───────────┘
             │
             ▼
      ┌──────────┐
      │ Skip? No │
      └────┬─────┘
           │
           ▼
   ┌───────────────┐
   │ build_command │ ◄── Uses effective limits from _apply_limits()
   └───────────────┘
```

### UI State Machine

```
User selects codec
        │
        ▼
┌───────────────────┐
│ onCodecChanged()  │
└────────┬──────────┘
         │
         ▼
  ┌────────────┐
  │ Switch to: │
  └──┬──┬──┬───┘
     │  │  │
 ┌───┘  │  └───┐
 │      │      │
 ▼      ▼      ▼
H.264  HEVC   VP8
Panel  Panel  Panel
 │      │      │
 └──┬───┴──┬───┘
    │      │
    ▼      ▼
  Visible Hidden
  Settings Settings
```

---

## Conclusion

This design addresses all four identified issues:

1. **Issue 1 - USDB Integration** - Fixed by moving limit application before transcoding decision and implementing intelligent "lesser of" logic
2. **Issue 2 - Dynamic Codec Settings** - Solved with QStackedWidget-based dynamic codec settings and conditional general settings
3. **Issue 3 - User Guidance** - Addressed with comprehensive HTML-formatted tooltips for every setting
4. **Issue 4 - Menu Icons** - Added icons to menu items with automatic theme switching support

**Key benefits:**
- Functionally correct USDB limit enforcement
- Exposes ~30 hidden settings in intuitive UI
- Provides guidance for technical and casual users
- Simplified hardware acceleration (global setting only)
- Professional menu appearance with icons
- Maintains backward compatibility
- Clean, maintainable implementation

**Simplified design changes per user feedback:**
- Removed per-codec QuickSync checkboxes
- Hardware acceleration now controlled by single global setting
- Automatic hardware detection (QuickSync, NVENC, etc.)
- Menu items now have icons and no "..." suffix

**Next steps:**
1. Review this design document with stakeholders
2. Implement Phase 1 (limit enforcement fix) first - it's a functional bug
3. Implement Phase 2 (UI expansion) and Phase 3 (tooltips) together
4. Implement Phase 4 (menu icons) - low-hanging fruit
5. Comprehensive testing per Phase 5 strategy
6. Document new settings in user-facing documentation

This design is ready for implementation.
