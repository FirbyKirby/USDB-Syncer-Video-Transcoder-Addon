"""Codec handler registry and implementations for H.264, VP8, HEVC, VP9, and AV1."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Type

if TYPE_CHECKING:
    from .config import TranscoderConfig
    from .hwaccel import HardwareAccelerator
    from .video_analyzer import VideoInfo


@dataclass
class CodecCapabilities:
    """Describes a codec handler's capabilities."""
    name: str                          # e.g., "h264", "vp8", "hevc"
    display_name: str                  # e.g., "H.264/AVC"
    container: str                     # Default container extension
    supports_quicksync_encode: bool    # Can use QSV encoder
    supports_quicksync_decode: bool    # Can use QSV decoder for this format
    unity_compatible: bool             # Supported by Unity 6 VideoPlayer


class CodecHandler(ABC):
    """Abstract base class for codec handlers."""

    @classmethod
    @abstractmethod
    def capabilities(cls) -> CodecCapabilities:
        """Return codec capabilities."""
        ...

    @classmethod
    @abstractmethod
    def build_encode_command(
        cls,
        input_path: Path,
        output_path: Path,
        video_info: VideoInfo,
        cfg: TranscoderConfig,
        accel: type["HardwareAccelerator"] | None,
        hw_encode_enabled: bool = False,
        hw_decode_enabled: bool = False,
    ) -> list[str]:
        """Build FFMPEG command for encoding to this codec."""
        ...

    @classmethod
    @abstractmethod
    def is_compatible(cls, video_info: VideoInfo) -> bool:
        """Check if input video is already in this codec's target format."""
        ...

    @classmethod
    def get_qsv_decoder(cls, video_info: VideoInfo) -> str | None:
        """Return QSV decoder name for input codec, or None."""
        codec_to_decoder = {
            "h264": "h264_qsv",
            "hevc": "hevc_qsv",
            "h265": "hevc_qsv",
            "vp9": "vp9_qsv",
            "mpeg2video": "mpeg2_qsv",
            "vc1": "vc1_qsv",
            "av1": "av1_qsv",
            "mjpeg": "mjpeg_qsv",
        }
        return codec_to_decoder.get(video_info.codec_name.lower())

    @classmethod
    def get_hw_decoder(
        cls,
        video_info: VideoInfo,
        accel: type["HardwareAccelerator"] | None,
    ) -> str | None:
        """Return the selected hardware decoder name, or None.

        IMPORTANT: Decoder selection must come from the selected accelerator.
        This is critical for future accelerators (NVDEC/VideoToolbox/VAAPI).
        """
        if accel is None:
            return None
        return accel.get_decoder(video_info)


# Global codec registry
CODEC_REGISTRY: Dict[str, Type[CodecHandler]] = {}


def register_codec(handler: Type[CodecHandler]) -> Type[CodecHandler]:
    """Decorator to register a codec handler."""
    caps = handler.capabilities()
    CODEC_REGISTRY[caps.name] = handler
    return handler


def get_codec_handler(codec_name: str) -> Type[CodecHandler] | None:
    """Get handler for a codec by name."""
    return CODEC_REGISTRY.get(codec_name)


@register_codec
class H264Handler(CodecHandler):
    """Handler for H.264/AVC encoding."""

    @classmethod
    def capabilities(cls) -> CodecCapabilities:
        return CodecCapabilities(
            name="h264",
            display_name="H.264/AVC",
            container="mp4",
            supports_quicksync_encode=True,
            supports_quicksync_decode=True,
            unity_compatible=True,
        )

    @classmethod
    def is_compatible(cls, video_info: VideoInfo) -> bool:
        """Check if already H.264 with Unity-compatible settings."""
        if video_info.codec_name.lower() not in ("h264", "avc"):
            return False
        if video_info.pixel_format != "yuv420p":
            return False
        if video_info.profile and video_info.profile.lower() not in ("baseline", "main", "high"):
            return False
        return True

    @classmethod
    def build_encode_command(
        cls,
        input_path: Path,
        output_path: Path,
        video_info: VideoInfo,
        cfg: TranscoderConfig,
        accel: type["HardwareAccelerator"] | None,
        hw_encode_enabled: bool = False,
        hw_decode_enabled: bool = False,
    ) -> list[str]:
        h264_cfg = cfg.h264
        cmd = ["ffmpeg", "-y", "-hide_banner"]

        # Hardware decoder if available and enabled
        if hw_decode_enabled:
            if decoder := cls.get_hw_decoder(video_info, accel):
                cmd.extend(["-c:v", decoder])

        cmd.extend(["-i", str(input_path)])

        # Encoder selection
        if hw_encode_enabled and accel is not None:
            cmd.extend([
                "-c:v", "h264_qsv",
                "-preset", h264_cfg.preset,
                "-profile:v", h264_cfg.profile,
                "-global_quality", str(h264_cfg.crf),
                "-look_ahead", "1",
                "-pix_fmt", "nv12",
            ])
        else:
            cmd.extend([
                "-c:v", "libx264",
                "-preset", h264_cfg.preset,
                "-profile:v", h264_cfg.profile,
                "-crf", str(h264_cfg.crf),
                "-pix_fmt", h264_cfg.pixel_format,
            ])

        # Common settings
        cmd.extend([
            "-vsync", "cfr",
        ])
        # Optional caps
        if cfg.general.max_bitrate_kbps:
            max_k = int(cfg.general.max_bitrate_kbps)
            cmd.extend(["-maxrate", f"{max_k}k", "-bufsize", f"{max_k * 2}k"])

        vf: list[str] = []
        if cfg.general.max_resolution:
            max_w, max_h = cfg.general.max_resolution
            if cfg.usdb_integration.use_usdb_resolution:
                vf.append(
                    "scale='min(iw,{})':'min(ih,{})':force_original_aspect_ratio=decrease".format(
                        int(max_w), int(max_h)
                    )
                )
            else:
                vf.append(
                    "scale={}:{}:force_original_aspect_ratio=decrease,pad={}:{}:(ow-iw)/2:(oh-ih)/2".format(
                        int(max_w), int(max_h), int(max_w), int(max_h)
                    )
                )
        if cfg.general.max_fps:
            vf.append(f"fps=fps={int(cfg.general.max_fps)}")
        if vf:
            cmd.extend(["-vf", ",".join(vf)])

        # Audio handling - Fix MP4 compatibility
        if video_info.has_audio:
            if video_info.audio_codec in ("aac", "mp3", "alac"):
                cmd.extend(["-c:a", "copy"])
            else:
                cmd.extend(["-c:a", "aac", "-b:a", "192k"])
        else:
            cmd.extend(["-an"])

        if output_path.suffix.lower() in (".mp4", ".mov"):
            cmd.extend(["-movflags", "+faststart"])

        cmd.append(str(output_path))
        return cmd


@register_codec
class VP8Handler(CodecHandler):
    """Handler for VP8 encoding."""

    @classmethod
    def capabilities(cls) -> CodecCapabilities:
        return CodecCapabilities(
            name="vp8",
            display_name="VP8",
            container="webm",
            supports_quicksync_encode=False,
            supports_quicksync_decode=False,
            unity_compatible=True,
        )

    @classmethod
    def is_compatible(cls, video_info: VideoInfo) -> bool:
        return video_info.codec_name.lower() == "vp8"

    @classmethod
    def build_encode_command(
        cls,
        input_path: Path,
        output_path: Path,
        video_info: VideoInfo,
        cfg: TranscoderConfig,
        accel: type["HardwareAccelerator"] | None,
        hw_encode_enabled: bool = False,
        hw_decode_enabled: bool = False,
    ) -> list[str]:
        vp8_cfg = cfg.vp8
        cmd = ["ffmpeg", "-y", "-hide_banner"]

        # Hardware decoder if available
        if hw_decode_enabled:
            if decoder := cls.get_hw_decoder(video_info, accel):
                cmd.extend(["-c:v", decoder])

        cmd.extend(["-i", str(input_path)])

        cmd.extend([
            "-c:v", "libvpx",
            "-crf", str(vp8_cfg.crf),
            "-b:v", "0",
            "-cpu-used", str(vp8_cfg.cpu_used),
            "-deadline", "good",
            "-auto-alt-ref", "1",
            "-lag-in-frames", "16",
            "-pix_fmt", "yuv420p",
            "-vsync", "cfr",
        ])

        # Optional caps
        if cfg.general.max_bitrate_kbps:
            max_k = int(cfg.general.max_bitrate_kbps)
            cmd.extend(["-maxrate", f"{max_k}k", "-bufsize", f"{max_k * 2}k"])

        vf: list[str] = []
        if cfg.general.max_resolution:
            max_w, max_h = cfg.general.max_resolution
            if cfg.usdb_integration.use_usdb_resolution:
                vf.append(
                    "scale='min(iw,{})':'min(ih,{})':force_original_aspect_ratio=decrease".format(
                        int(max_w), int(max_h)
                    )
                )
            else:
                vf.append(
                    "scale={}:{}:force_original_aspect_ratio=decrease,pad={}:{}:(ow-iw)/2:(oh-ih)/2".format(
                        int(max_w), int(max_h), int(max_w), int(max_h)
                    )
                )
        if cfg.general.max_fps:
            vf.append(f"fps=fps={int(cfg.general.max_fps)}")
        if vf:
            cmd.extend(["-vf", ",".join(vf)])

        if video_info.has_audio:
            if video_info.audio_codec in ("opus", "vorbis"):
                cmd.extend(["-c:a", "copy"])
            else:
                cmd.extend(["-c:a", "libopus", "-b:a", "160k"])
        else:
            cmd.extend(["-an"])

        cmd.append(str(output_path))
        return cmd


@register_codec
class HEVCHandler(CodecHandler):
    """Handler for HEVC/H.265 encoding."""

    @classmethod
    def capabilities(cls) -> CodecCapabilities:
        return CodecCapabilities(
            name="hevc",
            display_name="HEVC/H.265",
            container="mp4",
            supports_quicksync_encode=True,
            supports_quicksync_decode=True,
            unity_compatible=True,
        )

    @classmethod
    def is_compatible(cls, video_info: VideoInfo) -> bool:
        if video_info.codec_name.lower() not in ("hevc", "h265"):
            return False
        if video_info.pixel_format != "yuv420p":
            return False
        return True

    @classmethod
    def build_encode_command(
        cls,
        input_path: Path,
        output_path: Path,
        video_info: VideoInfo,
        cfg: TranscoderConfig,
        accel: type["HardwareAccelerator"] | None,
        hw_encode_enabled: bool = False,
        hw_decode_enabled: bool = False,
    ) -> list[str]:
        hevc_cfg = cfg.hevc
        cmd = ["ffmpeg", "-y", "-hide_banner"]

        if hw_decode_enabled:
            if decoder := cls.get_hw_decoder(video_info, accel):
                cmd.extend(["-c:v", decoder])

        cmd.extend(["-i", str(input_path)])

        if hw_encode_enabled and accel is not None:
            cmd.extend([
                "-c:v", "hevc_qsv",
                "-preset", hevc_cfg.preset,
                "-profile:v", hevc_cfg.profile,
                "-global_quality", str(hevc_cfg.crf),
                "-rc_mode", "icq",
                "-pix_fmt", "nv12",
            ])
        else:
            cmd.extend([
                "-c:v", "libx265",
                "-preset", hevc_cfg.preset,
                "-profile:v", hevc_cfg.profile,
                "-crf", str(hevc_cfg.crf),
                "-tag:v", "hvc1",
                "-pix_fmt", hevc_cfg.pixel_format,
            ])

        cmd.extend(["-vsync", "cfr"])

        # Optional caps
        if cfg.general.max_bitrate_kbps:
            max_k = int(cfg.general.max_bitrate_kbps)
            cmd.extend(["-maxrate", f"{max_k}k", "-bufsize", f"{max_k * 2}k"])

        vf: list[str] = []
        if cfg.general.max_resolution:
            max_w, max_h = cfg.general.max_resolution
            if cfg.usdb_integration.use_usdb_resolution:
                vf.append(
                    "scale='min(iw,{})':'min(ih,{})':force_original_aspect_ratio=decrease".format(
                        int(max_w), int(max_h)
                    )
                )
            else:
                vf.append(
                    "scale={}:{}:force_original_aspect_ratio=decrease,pad={}:{}:(ow-iw)/2:(oh-ih)/2".format(
                        int(max_w), int(max_h), int(max_w), int(max_h)
                    )
                )
        if cfg.general.max_fps:
            vf.append(f"fps=fps={int(cfg.general.max_fps)}")
        if vf:
            cmd.extend(["-vf", ",".join(vf)])

        # Audio handling - Fix MP4 compatibility
        if video_info.has_audio:
            if video_info.audio_codec in ("aac", "mp3", "alac"):
                cmd.extend(["-c:a", "copy"])
            else:
                cmd.extend(["-c:a", "aac", "-b:a", "192k"])
        else:
            cmd.extend(["-an"])

        if output_path.suffix.lower() in (".mp4", ".mov"):
            cmd.extend(["-movflags", "+faststart"])

        cmd.append(str(output_path))
        return cmd


@register_codec
class VP9Handler(CodecHandler):
    """Handler for VP9 encoding."""

    @classmethod
    def capabilities(cls) -> CodecCapabilities:
        return CodecCapabilities(
            name="vp9",
            display_name="VP9",
            container="webm",
            supports_quicksync_encode=True,
            supports_quicksync_decode=True,
            unity_compatible=False,
        )

    @classmethod
    def is_compatible(cls, video_info: VideoInfo) -> bool:
        return video_info.codec_name.lower() == "vp9"

    @classmethod
    def build_encode_command(
        cls,
        input_path: Path,
        output_path: Path,
        video_info: VideoInfo,
        cfg: TranscoderConfig,
        accel: type["HardwareAccelerator"] | None,
        hw_encode_enabled: bool = False,
        hw_decode_enabled: bool = False,
    ) -> list[str]:
        vp9_cfg = cfg.vp9
        cmd = ["ffmpeg", "-y", "-hide_banner"]

        # Hardware decoder if available
        if hw_decode_enabled:
            if decoder := cls.get_hw_decoder(video_info, accel):
                cmd.extend(["-c:v", decoder])

        cmd.extend(["-i", str(input_path)])

        # Encoder selection
        if hw_encode_enabled and accel is not None:
            # QSV VP9
            cmd.extend([
                "-c:v", "vp9_qsv",
                "-global_quality", str(vp9_cfg.crf),
                "-pix_fmt", "nv12",
            ])
        else:
            # Software VP9
            cmd.extend([
                "-c:v", "libvpx-vp9",
                "-crf", str(vp9_cfg.crf),
                "-b:v", "0",
                "-deadline", vp9_cfg.deadline,
                "-cpu-used", str(vp9_cfg.cpu_used),
                "-row-mt", "1",
                "-tile-columns", "2",
                "-g", "240",
                "-pix_fmt", "yuv420p",
            ])

        cmd.extend(["-vsync", "cfr"])

        # Optional caps
        if cfg.general.max_bitrate_kbps:
            max_k = int(cfg.general.max_bitrate_kbps)
            cmd.extend(["-maxrate", f"{max_k}k", "-bufsize", f"{max_k * 2}k"])

        # Video filters
        vf: list[str] = []
        if cfg.general.max_resolution:
            max_w, max_h = cfg.general.max_resolution
            vf.append(f"scale='min(iw,{int(max_w)})':'min(ih,{int(max_h)})':force_original_aspect_ratio=decrease")
        if cfg.general.max_fps:
            vf.append(f"fps=fps={int(cfg.general.max_fps)}")
        if vf:
            cmd.extend(["-vf", ",".join(vf)])

        # Audio handling - prefer Opus for WebM
        if video_info.has_audio:
            if video_info.audio_codec in ("opus", "vorbis"):
                cmd.extend(["-c:a", "copy"])
            else:
                cmd.extend(["-c:a", "libopus", "-b:a", "160k"])
        else:
            cmd.extend(["-an"])

        cmd.append(str(output_path))
        return cmd


@register_codec
class AV1Handler(CodecHandler):
    """Handler for AV1 encoding."""

    @classmethod
    def capabilities(cls) -> CodecCapabilities:
        return CodecCapabilities(
            name="av1",
            display_name="AV1",
            container="mkv",
            supports_quicksync_encode=True,
            supports_quicksync_decode=True,
            unity_compatible=False,
        )

    @classmethod
    def is_compatible(cls, video_info: VideoInfo) -> bool:
        return video_info.codec_name.lower() == "av1"

    @classmethod
    def build_encode_command(
        cls,
        input_path: Path,
        output_path: Path,
        video_info: VideoInfo,
        cfg: TranscoderConfig,
        accel: type["HardwareAccelerator"] | None,
        hw_encode_enabled: bool = False,
        hw_decode_enabled: bool = False,
    ) -> list[str]:
        av1_cfg = cfg.av1
        cmd = ["ffmpeg", "-y", "-hide_banner"]

        # Hardware decoder if available
        if hw_decode_enabled:
            if decoder := cls.get_hw_decoder(video_info, accel):
                cmd.extend(["-c:v", decoder])

        cmd.extend(["-i", str(input_path)])

        # Encoder selection
        from .utils import check_encoder_available
        if hw_encode_enabled and accel is not None:
            # QSV AV1
            cmd.extend([
                "-c:v", "av1_qsv",
                "-rc_mode", "icq",
                "-global_quality", str(av1_cfg.crf),
                "-pix_fmt", "nv12",
            ])
        elif check_encoder_available("libsvtav1"):
            # Software SVT-AV1
            cmd.extend([
                "-c:v", "libsvtav1",
                "-crf", str(av1_cfg.crf),
                "-preset", str(av1_cfg.cpu_used),
                "-g", "240",
                "-pix_fmt", "yuv420p10le",
            ])
        elif check_encoder_available("libaom-av1"):
            # Software libaom-av1
            cmd.extend([
                "-c:v", "libaom-av1",
                "-crf", str(av1_cfg.crf),
                "-cpu-used", str(av1_cfg.cpu_used),
                "-g", "240",
                "-pix_fmt", "yuv420p10le",
            ])
        else:
            # Fallback to generic av1 encoder
            cmd.extend(["-c:v", "av1"])

        cmd.extend(["-vsync", "cfr"])

        # Optional caps
        if cfg.general.max_bitrate_kbps:
            max_k = int(cfg.general.max_bitrate_kbps)
            cmd.extend(["-maxrate", f"{max_k}k", "-bufsize", f"{max_k * 2}k"])

        # Video filters
        vf: list[str] = []
        if cfg.general.max_resolution:
            max_w, max_h = cfg.general.max_resolution
            vf.append(f"scale='min(iw,{int(max_w)})':'min(ih,{int(max_h)})':force_original_aspect_ratio=decrease")
        if cfg.general.max_fps:
            vf.append(f"fps=fps={int(cfg.general.max_fps)}")
        if vf:
            cmd.extend(["-vf", ",".join(vf)])

        # Audio handling - Opus for MKV/WebM, AAC for MP4
        if video_info.has_audio:
            if output_path.suffix.lower() in (".mp4", ".mov"):
                if video_info.audio_codec in ("aac", "mp3", "alac"):
                    cmd.extend(["-c:a", "copy"])
                else:
                    cmd.extend(["-c:a", "aac", "-b:a", "192k"])
            else:
                if video_info.audio_codec in ("opus", "vorbis"):
                    cmd.extend(["-c:a", "copy"])
                else:
                    cmd.extend(["-c:a", "libopus", "-b:a", "160k"])
        else:
            cmd.extend(["-an"])

        if output_path.suffix.lower() in (".mp4", ".mov"):
            cmd.extend(["-movflags", "+faststart"])

        cmd.append(str(output_path))
        return cmd
