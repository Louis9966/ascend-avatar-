"""Configuration loading for ascend-avatar."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


def _project_root() -> Path:
    return Path(os.environ.get("PROJECT_ROOT", "/ascend-avatar"))


@dataclass(frozen=True)
class Config:
    # LLM
    llm_api_key: str = ""
    llm_base_url: str = "http://192.168.1.117:1025/v1"
    llm_model: str = "qwen3_32b"

    # NPU
    ascend_npu_device: str = "npu:0"

    # Paths
    project_root: Path = field(default_factory=_project_root)
    avatar_dir: Path = field(default_factory=lambda: _project_root() / "avatars")
    voice_dir: Path = Path("/ascend-avatar/voices")
    output_dir: Path = Path("/ascend-avatar/output")
    thg_dir: Path = Path("/ascend-avatar/thg")

    # MuseTalk
    muse_version: str = "v15"
    muse_model_dir: Path = Path("/ascend-avatar/thg/models")
    muse_unet_config: Path = Path("/ascend-avatar/thg/models/musetalkV15/musetalk.json")
    muse_unet_path: Path = Path("/ascend-avatar/thg/models/musetalkV15/unet.pth")
    muse_vae_type: str = "sd-vae"
    muse_whisper_dir: Path = Path("/ascend-avatar/thg/models/whisper_hf")
    muse_batch_size: int = 8
    muse_fps: int = 25
    muse_bbox_shift: int = 0

    # THG quality tuning
    thg_extra_margin: int = 10
    thg_parsing_mode: str = "jaw"
    thg_left_cheek_width: int = 90
    thg_right_cheek_width: int = 90
    thg_upper_boundary_ratio: float = 0.5
    thg_expand: float = 1.5
    thg_blur_ratio: float = 0.03
    thg_render_interpolation: str = "lanczos4"
    # e.g. "512x512" to center-crop and scale the input avatar before MuseTalk prepare
    thg_prepare_resolution: str = ""
    ffmpeg_crf: int = 18
    ffmpeg_preset: str = "medium"

    # Optional GFPGAN post-processing for video generation
    video_gen_postprocess_gfpgan: bool = False
    gfpgan_model_path: Path = field(
        default_factory=lambda: _project_root() / "thg/models/gfpgan/GFPGANv1.4.pth"
    )
    gfpgan_upscale: int = 1
    gfpgan_arch: str = "clean"
    gfpgan_channel_multiplier: int = 2
    gfpgan_device: str = "cpu"

    avatar_id: str = "default"
    avatar_video: Path = Path("/ascend-avatar/avatars/default_base.mp4")

    # TTS
    tts_voice_zh_female: str = "zh-CN-XiaoxiaoNeural"
    tts_voice_zh_male: str = "zh-CN-YunxiNeural"
    tts_voice_en: str = "en-US-AriaNeural"
    tts_rate: str = "+0%"
    tts_pitch: str = "+0Hz"

    # Upload / video generation
    upload_dir: Path = Path("/ascend-avatar/uploads")
    generated_dir: Path = Path("/ascend-avatar/output/generated")
    video_gen_tts_engine: str = "paddlespeech"
    video_gen_fallback_tts: bool = True
    max_upload_duration_s: int = 30
    max_upload_size_mb: int = 200
    avatar_cache_size: int = 3

    # PaddleSpeech TTS
    paddlespeech_am: str = "fastspeech2_aishell3"
    paddlespeech_voc: str = "hifigan_aishell3"
    paddlespeech_lang: str = "zh"
    paddlespeech_spk_id: int = 0
    paddlespeech_device: str = "cpu"

    # Media server
    mediamtx_path: Path = Path("/ascend-avatar/bin/mediamtx")
    mediamtx_config: Path = Path("/ascend-avatar/config/mediamtx.yml")
    mediamtx_host: str = "127.0.0.1"
    mediamtx_rtmp_port: int = 1935
    mediamtx_webrtc_port: int = 8889

    @property
    def rtmp_url(self) -> str:
        return f"rtmp://{self.mediamtx_host}:{self.mediamtx_rtmp_port}/live"

    @property
    def webrtc_play_url(self) -> str:
        return f"http://{self.mediamtx_host}:{self.mediamtx_webrtc_port}/live"

    # Web UI
    webui_host: str = "0.0.0.0"
    webui_port: int = 8188

    # Logging
    log_level: str = "INFO"

    def avatar_base_path(self) -> Path:
        return self.output_dir / "avatars" / self.avatar_id

    def ensure_dirs(self) -> None:
        for p in (
            self.avatar_dir,
            self.voice_dir,
            self.output_dir,
            self.upload_dir,
            self.generated_dir,
            self.avatar_base_path(),
        ):
            p.mkdir(parents=True, exist_ok=True)


def load_config(env_path: str | None = None) -> Config:
    """Load config from .env file and environment variables."""
    if env_path is None:
        candidates = [
            "/ascend-avatar/.env",
            "/ascend-avatar/config/.env",
            str(Path.cwd() / ".env"),
        ]
        for c in candidates:
            if Path(c).exists():
                load_dotenv(c, override=True)
                break
    else:
        load_dotenv(env_path, override=True)

    def _path(key: str, default: Path) -> Path:
        v = os.environ.get(key)
        return Path(v) if v else default

    def _int(key: str, default: int) -> int:
        v = os.environ.get(key)
        return int(v) if v else default

    def _bool(key: str, default: bool) -> bool:
        v = os.environ.get(key)
        if v is None:
            return default
        return v.lower() in ("1", "true", "yes", "on")

    return Config(
        llm_api_key=os.environ.get("LLM_API_KEY", ""),
        llm_base_url=os.environ.get("LLM_BASE_URL", "http://192.168.1.117:1025/v1"),
        llm_model=os.environ.get("LLM_MODEL", "qwen3_32b"),
        ascend_npu_device=os.environ.get("ASCEND_NPU_DEVICE", "npu:0"),
        project_root=_path("PROJECT_ROOT", _project_root()),
        avatar_dir=_path("AVATAR_DIR", _project_root() / "avatars"),
        voice_dir=_path("VOICE_DIR", _project_root() / "voices"),
        output_dir=_path("OUTPUT_DIR", _project_root() / "output"),
        thg_dir=_path("THG_DIR", _project_root() / "thg"),
        muse_version=os.environ.get("MUSE_TALK_VERSION", "v15"),
        muse_model_dir=_path("MUSE_TALK_MODEL_DIR", _project_root() / "thg/models"),
        muse_unet_config=_path(
            "MUSE_TALK_UNET_CONFIG",
            _project_root() / "thg/models/musetalkV15/musetalk.json",
        ),
        muse_unet_path=_path(
            "MUSE_TALK_UNET_PATH",
            _project_root() / "thg/models/musetalkV15/unet.pth",
        ),
        muse_vae_type=os.environ.get("MUSE_TALK_VAE_TYPE", "sd-vae"),
        muse_whisper_dir=_path(
            "MUSE_TALK_WHISPER_DIR", _project_root() / "thg/models/whisper_hf"
        ),
        muse_batch_size=int(os.environ.get("MUSE_TALK_BATCH_SIZE", "8")),
        muse_fps=int(os.environ.get("MUSE_TALK_FPS", "25")),
        muse_bbox_shift=int(os.environ.get("MUSE_TALK_BBOX_SHIFT", "0")),
        thg_extra_margin=_int("THG_EXTRA_MARGIN", 10),
        thg_parsing_mode=os.environ.get("THG_PARSING_MODE", "jaw"),
        thg_left_cheek_width=_int("THG_LEFT_CHEEK_WIDTH", 90),
        thg_right_cheek_width=_int("THG_RIGHT_CHEEK_WIDTH", 90),
        thg_upper_boundary_ratio=float(os.environ.get("THG_UPPER_BOUNDARY_RATIO", "0.5")),
        thg_expand=float(os.environ.get("THG_EXPAND", "1.5")),
        thg_blur_ratio=float(os.environ.get("THG_BLUR_RATIO", "0.03")),
        thg_render_interpolation=os.environ.get("THG_RENDER_INTERPOLATION", "lanczos4"),
        thg_prepare_resolution=os.environ.get("THG_PREPARE_RESOLUTION", ""),
        ffmpeg_crf=_int("FFMPEG_CRF", 18),
        ffmpeg_preset=os.environ.get("FFMPEG_PRESET", "medium"),
        video_gen_postprocess_gfpgan=_bool("VIDEO_GEN_POSTPROCESS_GFPGAN", False),
        gfpgan_model_path=_path(
            "GFPGAN_MODEL_PATH", _project_root() / "thg/models/gfpgan/GFPGANv1.4.pth"
        ),
        gfpgan_upscale=_int("GFPGAN_UPSCALE", 2),
        gfpgan_arch=os.environ.get("GFPGAN_ARCH", "clean"),
        gfpgan_channel_multiplier=_int("GFPGAN_CHANNEL_MULTIPLIER", 2),
        gfpgan_device=os.environ.get("GFPGAN_DEVICE", "cpu"),
        avatar_id=os.environ.get("AVATAR_ID", "default"),
        avatar_video=_path("AVATAR_VIDEO", _project_root() / "avatars/default_base.mp4"),
        tts_voice_zh_female=os.environ.get("TTS_VOICE_ZH_FEMALE", "zh-CN-XiaoxiaoNeural"),
        tts_voice_zh_male=os.environ.get("TTS_VOICE_ZH_MALE", "zh-CN-YunxiNeural"),
        tts_voice_en=os.environ.get("TTS_VOICE_EN", "en-US-AriaNeural"),
        tts_rate=os.environ.get("TTS_RATE", "+0%"),
        tts_pitch=os.environ.get("TTS_PITCH", "+0Hz"),
        upload_dir=_path("UPLOAD_DIR", _project_root() / "uploads"),
        generated_dir=_path("GENERATED_DIR", _project_root() / "output/generated"),
        video_gen_tts_engine=os.environ.get("VIDEO_GEN_TTS_ENGINE", "paddlespeech"),
        video_gen_fallback_tts=_bool("VIDEO_GEN_FALLBACK_TTS", True),
        max_upload_duration_s=_int("MAX_UPLOAD_DURATION_S", 30),
        max_upload_size_mb=_int("MAX_UPLOAD_SIZE_MB", 200),
        avatar_cache_size=_int("AVATAR_CACHE_SIZE", 3),
        paddlespeech_am=os.environ.get("PADDLESPEECH_AM", "fastspeech2_aishell3"),
        paddlespeech_voc=os.environ.get("PADDLESPEECH_VOC", "hifigan_aishell3"),
        paddlespeech_lang=os.environ.get("PADDLESPEECH_LANG", "zh"),
        paddlespeech_spk_id=_int("PADDLESPEECH_SPK_ID", 0),
        paddlespeech_device=os.environ.get("PADDLESPEECH_DEVICE", "cpu"),
        mediamtx_path=_path("MEDIAMTX_PATH", _project_root() / "bin/mediamtx"),
        mediamtx_config=_path("MEDIAMTX_CONFIG", _project_root() / "config/mediamtx.yml"),
        mediamtx_host=os.environ.get("MEDIAMTX_HOST", "127.0.0.1"),
        mediamtx_rtmp_port=int(os.environ.get("MEDIAMTX_RTMP_PORT", "1935")),
        mediamtx_webrtc_port=int(os.environ.get("MEDIAMTX_WEBRTC_PORT", "8889")),
        webui_host=os.environ.get("WEBUI_HOST", "0.0.0.0"),
        webui_port=int(os.environ.get("WEBUI_PORT", "8188")),
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
    )


if __name__ == "__main__":
    cfg = load_config()
    print(cfg)
