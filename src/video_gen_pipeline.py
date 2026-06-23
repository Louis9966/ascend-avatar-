"""Video generation pipeline: text + uploaded avatar -> PaddleSpeech TTS -> MuseTalk -> MP4."""
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from src.avatar_manager import AvatarManager, AvatarNotReadyError
from src.config import Config
from src.paddlespeech_tts_engine import PaddleSpeechTTSEngine, PaddleSpeechTTSError
from src.tts_engine import EdgeTTSEngine, detect_language, pick_voice


@dataclass
class VideoGenEvent:
    event: str  # queued, tts, thg, muxing, done, error
    payload: Dict[str, Any] = field(default_factory=dict)


class VideoGenPipeline:
    """Generate a lip-sync MP4 from user text and an uploaded avatar video.

    The pipeline is intentionally separate from ``ConversationPipeline``:
    it is a stateful job pipeline rather than a long-lived streaming chat
    pipeline.
    """

    def __init__(self, cfg: Config, avatar_manager: AvatarManager):
        self.cfg = cfg
        self.avatar_manager = avatar_manager
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._lock: Optional[asyncio.Lock] = None
        self._paddlespeech_engine: Optional[PaddleSpeechTTSEngine] = None
        self._edge_engine: Optional[EdgeTTSEngine] = None

    def _ensure_lock(self) -> None:
        if self._lock is None:
            self._lock = asyncio.Lock()

    def _get_paddlespeech_engine(self) -> PaddleSpeechTTSEngine:
        if self._paddlespeech_engine is None:
            self._paddlespeech_engine = PaddleSpeechTTSEngine(
                am=self.cfg.paddlespeech_am,
                voc=self.cfg.paddlespeech_voc,
                lang=self.cfg.paddlespeech_lang,
                spk_id=self.cfg.paddlespeech_spk_id,
                device=self.cfg.paddlespeech_device,
            )
        return self._paddlespeech_engine

    def _get_edge_engine(self) -> EdgeTTSEngine:
        if self._edge_engine is None:
            self._edge_engine = EdgeTTSEngine()
        return self._edge_engine

    async def submit(
        self,
        upload_id: str,
        text: str,
        spk_id: Optional[int] = None,
        voice_id: Optional[str] = None,
    ) -> str:
        """Submit a generation job and return ``job_id``."""
        self._ensure_lock()
        job_id = uuid.uuid4().hex[:16]
        job_dir = self.cfg.generated_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        async with self._lock:
            self._jobs[job_id] = {
                "job_id": job_id,
                "upload_id": upload_id,
                "text": text,
                "status": "queued",
                "progress": 0.0,
                "message": "等待处理...",
                "created_at": time.time(),
                "updated_at": time.time(),
                "output_path": str(job_dir / "output.mp4"),
                "tts_engine_used": None,
                "error": None,
            }

        asyncio.create_task(
            self._generate(job_id, upload_id, text, spk_id, voice_id)
        )
        return job_id

    def get_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        return self._jobs.get(job_id)

    def get_output_path(self, job_id: str) -> Optional[Path]:
        status = self._jobs.get(job_id)
        if status is None:
            return None
        return Path(status["output_path"])

    async def _update_job(
        self,
        job_id: str,
        status: Optional[str] = None,
        progress: Optional[float] = None,
        message: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        self._ensure_lock()
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            if status is not None:
                job["status"] = status
            if progress is not None:
                job["progress"] = progress
            if message is not None:
                job["message"] = message
            job["updated_at"] = time.time()
            job.update(kwargs)

    async def _generate(
        self,
        job_id: str,
        upload_id: str,
        text: str,
        spk_id: Optional[int],
        voice_id: Optional[str],
    ) -> None:
        job_dir = self.cfg.generated_dir / job_id
        wav_path = job_dir / "tts.wav"
        output_path = job_dir / "output.mp4"

        try:
            # --- make sure avatar is ready --------------------------------
            avatar_status = self.avatar_manager.get_status(upload_id)
            if avatar_status is None:
                raise AvatarNotReadyError(f"未找到 upload_id: {upload_id}")
            if avatar_status.get("status") != "ready":
                raise AvatarNotReadyError("视频尚未预处理完成，请稍后再试")

            # --- TTS --------------------------------------------------------
            await self._update_job(job_id, status="tts", progress=0.1, message="PaddleSpeech 语音合成中...")
            tts_engine_name = self.cfg.video_gen_tts_engine
            tts_failed = False

            if tts_engine_name == "paddlespeech":
                try:
                    engine = self._get_paddlespeech_engine()
                    if spk_id is not None:
                        engine.spk_id = spk_id
                    await engine.synthesize(text, wav_path)
                    await self._update_job(job_id, tts_engine_used="paddlespeech")
                except PaddleSpeechTTSError as exc:
                    tts_failed = True
                    if not self.cfg.video_gen_fallback_tts:
                        raise
                    await self._update_job(
                        job_id,
                        status="tts",
                        progress=0.15,
                        message=f"PaddleSpeech 失败，回退 edge-tts: {exc}",
                    )

            if tts_engine_name != "paddlespeech" or tts_failed:
                lang = detect_language(text)
                voice = pick_voice(lang, voice_id)
                edge_engine = self._get_edge_engine()
                edge_engine.voice = voice
                await edge_engine.synthesize(text, wav_path)
                await self._update_job(job_id, tts_engine_used="edge-tts")

            if not wav_path.exists():
                raise RuntimeError("TTS 未生成音频文件")

            # --- THG / lip-sync -------------------------------------------
            await self._update_job(job_id, status="thg", progress=0.5, message="MuseTalk 唇形同步中...")
            await self.avatar_manager.render(upload_id, wav_path, output_path)

            if not output_path.exists():
                raise RuntimeError("MP4 生成失败")

            await self._update_job(
                job_id,
                status="done",
                progress=1.0,
                message="生成完成",
            )

        except Exception as exc:
            await self._update_job(
                job_id,
                status="error",
                message=str(exc),
                error=str(exc),
            )


async def _test():
    from src.config import Config
    import torch
    from src.avatar_manager import AvatarManager

    cfg = Config()
    manager = AvatarManager(cfg, torch.device("cpu"))
    pipeline = VideoGenPipeline(cfg, manager)
    print("VideoGenPipeline created")


if __name__ == "__main__":
    asyncio.run(_test())
