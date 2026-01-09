"""GUI settings dialog for the Video Transcoder addon."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from usdb_syncer.gui import icons

from . import config

if TYPE_CHECKING:
    from PySide6.QtWidgets import QMainWindow


class TranscoderSettingsDialog(QDialog):
    """Dialog for adjusting transcoder settings."""

    def __init__(self, parent: QMainWindow) -> None:
        super().__init__(parent)
        self.cfg = config.load_config()
        self._setup_ui()
        self._load_settings()

    def _setup_ui(self) -> None:
        self.setWindowTitle("Video Transcoder Settings")
        self.setWindowIcon(icons.Icon.VIDEO.icon())
        self.setMinimumWidth(800)
        self.setMinimumHeight(650)
        
        main_layout = QVBoxLayout(self)
        
        # Two-column layout
        columns_layout = QHBoxLayout()
        main_layout.addLayout(columns_layout)
        
        left_column = QVBoxLayout()
        right_column = QVBoxLayout()
        columns_layout.addLayout(left_column)
        columns_layout.addLayout(right_column)

        # 1. General Settings
        gen_group = QGroupBox("General Settings")
        gen_layout = QFormLayout(gen_group)
        
        self.auto_transcode_enabled = QCheckBox("Automatic Video Transcode")
        self.auto_transcode_enabled.setToolTip(
            "<b>Automatic Video Transcode</b><br/>"
            "Enable automatic video transcoding after song downloads. "
            "When disabled, videos are not automatically transcoded after download. "
            "Batch transcoding remains available via Tools menu."
        )
        
        self.hw_enc = QCheckBox("Hardware Encoding")
        self.hw_enc.setToolTip(
            "<b>Hardware Encoding</b><br/>"
            "Use hardware-accelerated video encoding when available.<br/>"
            "Automatically detects and uses best method for your system:<br/>"
            "• Intel QuickSync (Intel CPUs 6th gen+)<br/>"
            "<br/>"
            "<b>Impact:</b> 3-5x faster encoding on supported hardware<br/>"
            "<b>Recommended:</b> Enable if you have compatible hardware"
        )
        
        self.hw_decode = QCheckBox("Hardware Decoding")
        self.hw_decode.setToolTip(
            "<b>Hardware Decoding</b><br/>"
            "Use hardware acceleration to decode the source video file.<br/>"
            "<br/>"
            "<b>Note:</b> Automatically disabled when resolution or FPS settings "
            "are applied to ensure filter compatibility."
        )
        
        self.verify = QCheckBox("Verify Output Files")
        self.verify.setToolTip(
            "<b>Verify Output Files</b><br/>"
            "Analyze the transcoded file to ensure it was created correctly.<br/>"
            "Adds a small delay after each transcode."
        )

        self.force_transcode = QCheckBox("Force Transcode")
        self.force_transcode.setToolTip(
            "<b>Force Transcode</b><br/>"
            "Force transcoding even if the video already matches the target format.<br/>"
            "Useful for applying new quality settings or fixing corrupted files."
        )

        self.backup = QCheckBox("Backup Original Files")
        self.backup.setToolTip(
            "<b>Backup Original Files</b><br/>"
            "Defines if new backups should be created and kept for videos that don't already have one.<br/>"
            "<br/>"
            "<b>Note:</b> If a backup already exists for a video, it will always be "
            "preserved and updated, regardless of this setting."
        )

        self.backup_suffix = QLineEdit()
        self.backup_suffix.setPlaceholderText("-source")
        self.backup_suffix.setToolTip(
            "<b>Backup Suffix</b><br/>"
            "File extension added to original videos when backing up.<br/>"
            "<br/>"
            "<b>Example:</b> video.mp4 → video-source.mp4<br/>"
            "<b>Default:</b> -source"
        )
        self.backup_suffix_label = QLabel("Backup Suffix:")
        
        # Prevent layout jumps when hiding
        self.backup_suffix.hide()
        self.backup_suffix_label.hide()
        
        gen_layout.addRow(self.auto_transcode_enabled)
        gen_layout.addRow(self.hw_enc)
        gen_layout.addRow(self.hw_decode)
        gen_layout.addRow(self.verify)
        gen_layout.addRow(self.force_transcode)
        gen_layout.addRow(self.backup)
        gen_layout.addRow(self.backup_suffix_label, self.backup_suffix)
        left_column.addWidget(gen_group)

        # 2. USDB Integration & Limits
        limits_group = QGroupBox("Resolution and FPS Limits")
        limits_layout = QFormLayout(limits_group)
        
        self.use_usdb_res = QCheckBox("Use USDB Max Resolution")
        self.use_usdb_res.setToolTip(
            "<b>Use USDB Max Resolution</b><br/>"
            "Use the 'Max Video Resolution' setting from USDB Syncer's main settings.<br/>"
            "Source videos exceeding this resolution will be downscaled."
        )
        limits_layout.addRow(self.use_usdb_res)
        
        self.manual_res = QComboBox()
        self.manual_res.addItems(["Original", "2160p (4K)", "1440p (2K)", "1080p (Full HD)", "720p (HD)",  "480p (SD)", "270p"])
        self.manual_res.setToolTip(
            "<b>Manual Resolution</b><br/>"
            "Set the exact output resolution (only when USDB integration is disabled).<br/>"
            "<br/>"
            "<b>Behavior:</b> Videos will be transcoded to this exact resolution "
            "while maintaining aspect ratio."
        )
        self.res_row_label = QLabel("Manual Resolution:")
        
        limits_layout.addRow(self.res_row_label, self.manual_res)
        
        self.use_usdb_fps = QCheckBox("Use USDB Max FPS")
        self.use_usdb_fps.setToolTip(
            "<b>Use USDB Max FPS</b><br/>"
            "Use the 'Max Video FPS' setting from USDB Syncer's main settings.<br/>"
            "Source videos exceeding this FPS will be reduced."
        )
        limits_layout.addRow(self.use_usdb_fps)
        
        self.manual_fps = QComboBox()
        self.manual_fps.addItems(["Original", "240", "120", "60", "30", "25", "24"])
        self.manual_fps.setToolTip(
            "<b>Manual FPS</b><br/>"
            "Set the exact output frame rate (only when USDB integration is disabled).<br/>"
            "<br/>"
            "<b>Behavior:</b> Videos will be transcoded to this exact frame rate."
        )
        self.fps_row_label = QLabel("Manual FPS:")
        
        limits_layout.addRow(self.fps_row_label, self.manual_fps)
        
        left_column.addWidget(limits_group)

        # 3. Operational Settings
        ops_group = QGroupBox("Operational Settings")
        ops_layout = QFormLayout(ops_group)
        
        self.max_bitrate = QSpinBox()
        self.max_bitrate.setRange(0, 100000)
        self.max_bitrate.setSuffix(" kbps")
        self.max_bitrate.setSpecialValueText("No Limit")
        self.max_bitrate.setToolTip(
            "<b>Max Bitrate</b><br/>"
            "Upper limit for video bitrate. If source exceeds this, it will be transcoded.<br/>"
            "Useful for reducing file size of extremely high-bitrate videos."
        )
        
        self.timeout = QSpinBox()
        self.timeout.setRange(30, 3600)
        self.timeout.setSuffix(" s")
        self.timeout.setToolTip(
            "<b>Transcode Timeout</b><br/>"
            "Maximum time allowed for a single transcode operation.<br/>"
            "Increase this if you have a slow CPU or very long videos."
        )
        
        self.min_space = QSpinBox()
        # Allow very large values (e.g. 400000 MB) for users with large disks.
        # QSpinBox supports up to ~2.1 billion.
        self.min_space.setRange(0, 2_000_000)
        self.min_space.setSingleStep(1000)
        self.min_space.setSuffix(" MB")
        self.min_space.setToolTip(
            "<b>Min Free Space</b><br/>"
            "Minimum free disk space required to start a transcode.<br/>"
            "Prevents filling up your disk during batch operations."
        )
        
        ops_layout.addRow("Max Bitrate:", self.max_bitrate)
        ops_layout.addRow("Transcode Timeout:", self.timeout)
        ops_layout.addRow("Min Free Space:", self.min_space)
        left_column.addWidget(ops_group)

        # 4. Target Format & Codec Settings (Right Column)
        codec_group = QGroupBox("Target Format")
        codec_layout = QVBoxLayout(codec_group)
        
        target_selector_layout = QFormLayout()
        self.target_codec = QComboBox()
        self.target_codec.addItems(["h264", "hevc", "vp8", "vp9", "av1"])
        self.target_codec.setToolTip(
            "<b>Target Codec</b><br/>"
            "The video codec to use for the transcoded file.<br/>"
            "• <b>H.264:</b> Best compatibility, fast encoding.<br/>"
            "• <b>HEVC:</b> Best quality/size ratio, slower encoding.<br/>"
            "• <b>VP8:</b> Open format, good for WebM."
        )
        target_selector_layout.addRow("Target Codec:", self.target_codec)
        codec_layout.addLayout(target_selector_layout)
        
        # Stacked widget for codec-specific settings
        self.codec_stack = QStackedWidget()
        self.codec_stack.addWidget(self._create_h264_settings())
        self.codec_stack.addWidget(self._create_hevc_settings())
        self.codec_stack.addWidget(self._create_vp8_settings())
        self.codec_stack.addWidget(self._create_vp9_settings())
        self.codec_stack.addWidget(self._create_av1_settings())
        
        # Ensure stack doesn't shrink when switching to VP8 (which has fewer settings)
        self.codec_stack.setMinimumHeight(300)
        
        codec_layout.addWidget(self.codec_stack)
        
        right_column.addWidget(codec_group)
        right_column.addStretch()

        # Buttons
        btn_layout = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        main_layout.addLayout(btn_layout)
        
        # Connections
        self.target_codec.currentIndexChanged.connect(self.codec_stack.setCurrentIndex)
        self.use_usdb_res.stateChanged.connect(self._toggle_manual_resolution)
        self.use_usdb_fps.stateChanged.connect(self._toggle_manual_fps)
        self.backup.stateChanged.connect(self._toggle_backup_suffix)

    def _create_h264_settings(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Quality Group
        q_group = QGroupBox("Quality Settings")
        q_layout = QFormLayout(q_group)
        
        self.h264_crf = QSpinBox()
        self.h264_crf.setRange(0, 51)
        self.h264_crf.setToolTip(
            "<b>H.264 CRF (Constant Rate Factor)</b><br/>"
            "Controls the quality vs. file size trade-off.<br/>"
            "<br/>"
            "<b>Values:</b> 0-51<br/>"
            "• 0 - Lossless (huge files)<br/>"
            "• 18 - Visually transparent (high quality)<br/>"
            "• 23 - Default (good balance)<br/>"
            "• 28 - Lower quality (small files)<br/>"
            "<br/>"
            "<b>Recommended:</b> 18-23"
        )
        
        self.h264_profile = QComboBox()
        self.h264_profile.addItems(["baseline", "main", "high"])
        self.h264_profile.setToolTip(
            "<b>H.264 Profile</b><br/>"
            "Defines the set of features used for encoding.<br/>"
            "• <b>baseline:</b> Best compatibility (older devices).<br/>"
            "• <b>main:</b> Standard for most modern devices.<br/>"
            "• <b>high:</b> Best quality/compression (modern PCs/TVs).<br/>"
            "<br/>"
            "<b>Recommended:</b> high"
        )
        
        self.h264_pix_fmt = QComboBox()
        self.h264_pix_fmt.addItems(["yuv420p", "yuv422p", "yuv444p"])
        self.h264_pix_fmt.setToolTip(
            "<b>Pixel Format</b><br/>"
            "How color information is stored.<br/>"
            "• <b>yuv420p:</b> Most compatible (standard).<br/>"
            "<br/>"
            "<b>Recommended:</b> yuv420p"
        )
        
        q_layout.addRow("CRF:", self.h264_crf)
        q_layout.addRow("Profile:", self.h264_profile)
        q_layout.addRow("Pixel Format:", self.h264_pix_fmt)
        layout.addWidget(q_group)
        
        # Performance Group
        p_group = QGroupBox("Performance Settings")
        p_layout = QFormLayout(p_group)
        
        self.h264_preset = QComboBox()
        self.h264_preset.addItems(["ultrafast", "superfast", "veryfast", "faster",
                                   "fast", "medium", "slow", "slower", "veryslow"])
        self.h264_preset.setToolTip(
            "<b>Encoding Preset</b><br/>"
            "Trade-off between encoding speed and compression efficiency.<br/>"
            "• <b>ultrafast:</b> Fastest, largest files.<br/>"
            "• <b>medium:</b> Balanced.<br/>"
            "• <b>veryslow:</b> Best compression, very slow.<br/>"
            "<br/>"
            "<b>Recommended:</b> slow"
        )
        p_layout.addRow("Preset:", self.h264_preset)
        layout.addWidget(p_group)
        
        # Output Group
        o_group = QGroupBox("Output Settings")
        o_layout = QFormLayout(o_group)
        
        self.h264_container = QComboBox()
        self.h264_container.addItems(["mp4", "mkv", "mov"])
        self.h264_container.setToolTip(
            "<b>Output Container</b><br/>"
            "The file format for the transcoded video.<br/>"
            "• <b>mp4:</b> Best compatibility.<br/>"
            "• <b>mkv:</b> Flexible, supports many features."
        )
        o_layout.addRow("Container:", self.h264_container)
        layout.addWidget(o_group)
        
        return widget

    def _create_hevc_settings(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Quality Group
        q_group = QGroupBox("Quality Settings")
        q_layout = QFormLayout(q_group)
        
        self.hevc_crf = QSpinBox()
        self.hevc_crf.setRange(0, 51)
        self.hevc_crf.setToolTip("<b>HEVC CRF</b><br/>Similar to H.264 but more efficient.<br/><b>Recommended:</b> 20-25")
        
        self.hevc_profile = QComboBox()
        self.hevc_profile.addItems(["main", "main10"])
        self.hevc_profile.setToolTip("<b>HEVC Profile</b><br/>• <b>main:</b> Standard 8-bit.<br/>• <b>main10:</b> 10-bit color.")
        
        self.hevc_pix_fmt = QComboBox()
        self.hevc_pix_fmt.addItems(["yuv420p", "yuv420p10le"])
        self.hevc_pix_fmt.setToolTip(
            "<b>Pixel Format</b><br/>"
            "Color sampling and bit depth.<br/>"
            "<br/>"
            "<b>Values:</b><br/>"
            "• yuv420p - 8-bit 4:2:0 (standard, best compatibility)<br/>"
            "• yuv420p10le - 10-bit 4:2:0 (HDR, main10 profile)<br/>"
            "<br/>"
            "<b>Recommended:</b> yuv420p (standard content)"
        )
        
        q_layout.addRow("CRF:", self.hevc_crf)
        q_layout.addRow("Profile:", self.hevc_profile)
        q_layout.addRow("Pixel Format:", self.hevc_pix_fmt)
        layout.addWidget(q_group)
        
        # Performance Group
        p_group = QGroupBox("Performance Settings")
        p_layout = QFormLayout(p_group)
        
        self.hevc_preset = QComboBox()
        self.hevc_preset.addItems(["ultrafast", "superfast", "veryfast", "faster",
                                   "fast", "medium", "slow", "slower", "veryslow"])
        p_layout.addRow("Preset:", self.hevc_preset)
        layout.addWidget(p_group)
        
        # Output Group
        o_group = QGroupBox("Output Settings")
        o_layout = QFormLayout(o_group)
        
        self.hevc_container = QComboBox()
        self.hevc_container.addItems(["mp4", "mkv", "mov"])
        o_layout.addRow("Container:", self.hevc_container)
        layout.addWidget(o_group)
        
        return widget

    def _create_vp8_settings(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Quality Group
        q_group = QGroupBox("Quality Settings")
        q_layout = QFormLayout(q_group)
        
        self.vp8_crf = QSpinBox()
        self.vp8_crf.setRange(0, 63)
        self.vp8_crf.setToolTip("<b>VP8 CRF</b><br/>Values 0-63.<br/><b>Recommended:</b> 10")
        
        q_layout.addRow("CRF:", self.vp8_crf)
        layout.addWidget(q_group)
        
        # Performance Group
        p_group = QGroupBox("Performance Settings")
        p_layout = QFormLayout(p_group)
        
        self.vp8_cpu_used = QSpinBox()
        self.vp8_cpu_used.setRange(0, 5)
        self.vp8_cpu_used.setToolTip(
            "<b>CPU Used</b><br/>"
            "Speed vs. quality trade-off for VP8.<br/>"
            "• 0: Best quality (slowest).<br/>"
            "• 5: Fastest (lowest quality).<br/>"
            "<br/>"
            "<b>Recommended:</b> 1"
        )
        p_layout.addRow("CPU Used:", self.vp8_cpu_used)
        layout.addWidget(p_group)
        
        # Output Group
        o_group = QGroupBox("Output Settings")
        o_layout = QFormLayout(o_group)
        
        self.vp8_container = QComboBox()
        self.vp8_container.addItems(["webm", "mkv"])
        o_layout.addRow("Container:", self.vp8_container)
        layout.addWidget(o_group)
        
        return widget

    def _create_vp9_settings(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        
        q_group = QGroupBox("Quality Settings")
        q_layout = QFormLayout(q_group)
        
        self.vp9_crf = QSpinBox()
        self.vp9_crf.setRange(0, 63)
        self.vp9_crf.setToolTip("<b>VP9 CRF</b><br/>Values 0-63.<br/><b>Recommended:</b> 20")
        
        self.vp9_deadline = QComboBox()
        self.vp9_deadline.addItems(["good", "best", "realtime"])
        self.vp9_deadline.setToolTip("<b>Deadline</b><br/>Encoding speed/quality tradeoff.")
        
        q_layout.addRow("CRF:", self.vp9_crf)
        q_layout.addRow("Deadline:", self.vp9_deadline)
        layout.addWidget(q_group)
        
        p_group = QGroupBox("Performance Settings")
        p_layout = QFormLayout(p_group)
        
        self.vp9_cpu_used = QSpinBox()
        self.vp9_cpu_used.setRange(0, 8)
        self.vp9_cpu_used.setToolTip("<b>CPU Used</b><br/>0-8, lower is better quality.")
        
        p_layout.addRow("CPU Used:", self.vp9_cpu_used)
        layout.addWidget(p_group)
        
        o_group = QGroupBox("Output Settings")
        o_layout = QFormLayout(o_group)
        
        self.vp9_container = QComboBox()
        self.vp9_container.addItems(["webm", "mkv"])
        o_layout.addRow("Container:", self.vp9_container)
        layout.addWidget(o_group)
        
        return widget

    def _create_av1_settings(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        
        q_group = QGroupBox("Quality Settings")
        q_layout = QFormLayout(q_group)
        
        self.av1_crf = QSpinBox()
        self.av1_crf.setRange(0, 63)
        self.av1_crf.setToolTip("<b>AV1 CRF</b><br/>Values 0-63.<br/><b>Recommended:</b> 20")
        
        q_layout.addRow("CRF:", self.av1_crf)
        layout.addWidget(q_group)
        
        p_group = QGroupBox("Performance Settings")
        p_layout = QFormLayout(p_group)
        
        self.av1_cpu_used = QSpinBox()
        self.av1_cpu_used.setRange(0, 13)
        self.av1_cpu_used.setToolTip("<b>Preset/CPU Used</b><br/>Lower is slower/better.")
        
        p_layout.addRow("Preset/CPU Used:", self.av1_cpu_used)
        layout.addWidget(p_group)
        
        o_group = QGroupBox("Output Settings")
        o_layout = QFormLayout(o_group)
        
        self.av1_container = QComboBox()
        self.av1_container.addItems(["mkv", "mp4", "webm"])
        o_layout.addRow("Container:", self.av1_container)
        layout.addWidget(o_group)
        
        return widget

    def _toggle_manual_resolution(self, state: int) -> None:
        visible = state == Qt.CheckState.Unchecked.value
        self.manual_res.setVisible(visible)
        self.res_row_label.setVisible(visible)

    def _toggle_manual_fps(self, state: int) -> None:
        visible = state == Qt.CheckState.Unchecked.value
        self.manual_fps.setVisible(visible)
        self.fps_row_label.setVisible(visible)

    def _toggle_backup_suffix(self, state: int) -> None:
        visible = state == Qt.CheckState.Checked.value
        self.backup_suffix.setVisible(visible)
        self.backup_suffix_label.setVisible(visible)

    def _load_settings(self) -> None:
        self.auto_transcode_enabled.setChecked(self.cfg.auto_transcode_enabled)
        
        # General
        self.hw_enc.setChecked(self.cfg.general.hardware_encoding)
        self.hw_decode.setChecked(self.cfg.general.hardware_decode)
        self.backup.setChecked(self.cfg.general.backup_original)
        self.backup_suffix.setText(self.cfg.general.backup_suffix)
        self.verify.setChecked(self.cfg.general.verify_output)
        self.force_transcode.setChecked(self.cfg.general.force_transcode)
        self.max_bitrate.setValue(self.cfg.general.max_bitrate_kbps or 0)
        self.timeout.setValue(self.cfg.general.timeout_seconds)
        self.min_space.setValue(self.cfg.general.min_free_space_mb)
        
        # Limits
        self.use_usdb_res.setChecked(self.cfg.usdb_integration.use_usdb_resolution)
        if self.cfg.general.max_resolution:
            w, h = self.cfg.general.max_resolution
            res_str = "Original"
            if h == 2160: res_str = "2160p (4K)"
            elif h == 1440: res_str = "1440p (2K)"
            elif h == 1080: res_str = "1080p (Full HD)"
            elif h == 720: res_str = "720p (HD)"
            elif h == 480: res_str = "480p (SD)"
            elif h == 270: res_str = "270p"
            self.manual_res.setCurrentText(res_str)
        else:
            self.manual_res.setCurrentText("Original")
            
        self.use_usdb_fps.setChecked(self.cfg.usdb_integration.use_usdb_fps)
        if self.cfg.general.max_fps:
            self.manual_fps.setCurrentText(str(self.cfg.general.max_fps))
        else:
            self.manual_fps.setCurrentText("Original")
        
        # Trigger visibility updates
        self._toggle_manual_resolution(
            Qt.CheckState.Checked.value if self.use_usdb_res.isChecked() else Qt.CheckState.Unchecked.value
        )
        self._toggle_manual_fps(
            Qt.CheckState.Checked.value if self.use_usdb_fps.isChecked() else Qt.CheckState.Unchecked.value
        )
        self._toggle_backup_suffix(
            Qt.CheckState.Checked.value if self.backup.isChecked() else Qt.CheckState.Unchecked.value
        )
        
        # Target Codec
        self.target_codec.setCurrentText(self.cfg.target_codec)
        self.codec_stack.setCurrentIndex(self.target_codec.currentIndex())
        
        # H.264
        self.h264_crf.setValue(self.cfg.h264.crf)
        self.h264_profile.setCurrentText(self.cfg.h264.profile)
        self.h264_pix_fmt.setCurrentText(self.cfg.h264.pixel_format)
        self.h264_preset.setCurrentText(self.cfg.h264.preset)
        self.h264_container.setCurrentText(self.cfg.h264.container)
        
        # HEVC
        self.hevc_crf.setValue(self.cfg.hevc.crf)
        self.hevc_profile.setCurrentText(self.cfg.hevc.profile)
        self.hevc_pix_fmt.setCurrentText(self.cfg.hevc.pixel_format)
        self.hevc_preset.setCurrentText(self.cfg.hevc.preset)
        self.hevc_container.setCurrentText(self.cfg.hevc.container)
        
        # VP8
        self.vp8_crf.setValue(self.cfg.vp8.crf)
        self.vp8_cpu_used.setValue(self.cfg.vp8.cpu_used)
        self.vp8_container.setCurrentText(self.cfg.vp8.container)
        
        # VP9
        self.vp9_crf.setValue(self.cfg.vp9.crf)
        self.vp9_cpu_used.setValue(self.cfg.vp9.cpu_used)
        self.vp9_deadline.setCurrentText(self.cfg.vp9.deadline)
        self.vp9_container.setCurrentText(self.cfg.vp9.container)
        
        # AV1
        self.av1_crf.setValue(self.cfg.av1.crf)
        self.av1_cpu_used.setValue(self.cfg.av1.cpu_used)
        self.av1_container.setCurrentText(self.cfg.av1.container)

    def save_settings(self) -> None:
        self.cfg.auto_transcode_enabled = self.auto_transcode_enabled.isChecked()
        
        # General
        self.cfg.general.hardware_encoding = self.hw_enc.isChecked()
        self.cfg.general.hardware_decode = self.hw_decode.isChecked()
        self.cfg.general.backup_original = self.backup.isChecked()
        self.cfg.general.backup_suffix = self.backup_suffix.text()
        self.cfg.general.verify_output = self.verify.isChecked()
        self.cfg.general.force_transcode = self.force_transcode.isChecked()
        self.cfg.general.max_bitrate_kbps = self.max_bitrate.value() or None
        self.cfg.general.timeout_seconds = self.timeout.value()
        self.cfg.general.min_free_space_mb = self.min_space.value()
        
        # Limits
        self.cfg.usdb_integration.use_usdb_resolution = self.use_usdb_res.isChecked()
        if self.cfg.usdb_integration.use_usdb_resolution:
            self.cfg.general.max_resolution = None
        else:
            res_text = self.manual_res.currentText()
            if res_text == "Original":
                self.cfg.general.max_resolution = None
            else:
                h = int(res_text.split("p")[0])
                w = int(h * 16 / 9) # Assume 16:9 for the tuple  
                if h == 2160: w = 3840
                elif h == 1440: w = 2560
                elif h == 1080: w = 1920
                elif h == 720: w = 1280
                elif h == 480: w = 854
                elif h == 270: w = 480
                self.cfg.general.max_resolution = (w, h)
            
        self.cfg.usdb_integration.use_usdb_fps = self.use_usdb_fps.isChecked()
        if self.cfg.usdb_integration.use_usdb_fps:
            self.cfg.general.max_fps = None
        else:
            fps_text = self.manual_fps.currentText()
            if fps_text == "Original":
                self.cfg.general.max_fps = None
            else:
                self.cfg.general.max_fps = int(fps_text)
            
        # Target Codec
        self.cfg.target_codec = self.target_codec.currentText()  # type: ignore
        
        # H.264
        self.cfg.h264.crf = self.h264_crf.value()
        self.cfg.h264.profile = self.h264_profile.currentText()  # type: ignore
        self.cfg.h264.pixel_format = self.h264_pix_fmt.currentText()
        self.cfg.h264.preset = self.h264_preset.currentText()
        self.cfg.h264.container = self.h264_container.currentText()
        
        # HEVC
        self.cfg.hevc.crf = self.hevc_crf.value()
        self.cfg.hevc.profile = self.hevc_profile.currentText()  # type: ignore
        self.cfg.hevc.pixel_format = self.hevc_pix_fmt.currentText()
        self.cfg.hevc.preset = self.hevc_preset.currentText()
        self.cfg.hevc.container = self.hevc_container.currentText()
        
        # VP8
        self.cfg.vp8.crf = self.vp8_crf.value()
        self.cfg.vp8.cpu_used = self.vp8_cpu_used.value()
        self.cfg.vp8.container = self.vp8_container.currentText()
        
        # VP9
        self.cfg.vp9.crf = self.vp9_crf.value()
        self.cfg.vp9.cpu_used = self.vp9_cpu_used.value()
        self.cfg.vp9.deadline = self.vp9_deadline.currentText()
        self.cfg.vp9.container = self.vp9_container.currentText()
        
        # AV1
        self.cfg.av1.crf = self.av1_crf.value()
        self.cfg.av1.cpu_used = self.av1_cpu_used.value()
        self.cfg.av1.container = self.av1_container.currentText()
        
        config.save_config(self.cfg)


def show_settings(parent: QMainWindow) -> None:
    dialog = TranscoderSettingsDialog(parent)
    if dialog.exec() == QDialog.Accepted:
        dialog.save_settings()
