"""Dynamic avatar management for user-uploaded videos.

Each uploaded video becomes a ``MuseTalkAvatar`` that is prepared once and
cached. The manager validates uploads (duration, fps, face detection) and
 serializes heavy THG operations to avoid cwd/NPU races.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import subprocess
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, Optional

import cv2
import numpy as np

from src.config import Config
from src.thg_engine import MuseTalkAvatar


class AvatarValidationError(Exception):
    """Raised when an uploaded video fails validation."""


class AvatarNotReadyError(Exception):
    """Raised when a requested avatar is not ready yet."""


class AvatarManager:
    """Manage uploaded videos as MuseTalk avatars.

    Usage:
        manager = AvatarManager(cfg, device=torch.device("npu:0"))
        info = await manager.upload_video(file_bytes, "me.mp4")
        # ... poll manager.get_status(info["upload_id"]) ...
        output = await manager.render(upload_id, audio_path, output_mp4_path)
    """

    def __init__(self, cfg: Config, device):
        self.cfg = cfg
        self.device = device
        self._avatars: "OrderedDict[str, MuseTalkAvatar]" = OrderedDict()
        self._statuses: Dict[str, Dict[str, Any]] = {}
        self._lock: Optional[asyncio.Lock] = None
        self._prepare_sem: Optional[asyncio.Semaphore] = None
        self._thg_lock: Optional[asyncio.Lock] = None
        self._face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )

    def _ensure_locks(self) -> None:
        """Lazily create asyncio primitives once an event loop exists."""
        if self._lock is None:
            self._lock = asyncio.Lock()
        if self._prepare_sem is None:
            self._prepare_sem = asyncio.Semaphore(1)
        if self._thg_lock is None:
            self._thg_lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def upload_video(self, file_bytes: bytes, filename: str) -> Dict[str, Any]:
        """Validate, save, and start preparing an uploaded video.

        Returns a status dict containing ``upload_id`` and ``status``.
        """
        self._ensure_locks()
        max_size = self.cfg.max_upload_size_mb * 1024 * 1024
        if len(file_bytes) > max_size:
            raise AvatarValidationError(
                f"文件过大：{len(file_bytes)/(1024*1024):.1f} MB > "
                f"{self.cfg.max_upload_size_mb} MB"
            )

        upload_id = hashlib.sha256(file_bytes).hexdigest()[:16]
        upload_root = self.cfg.upload_dir / upload_id
        upload_root.mkdir(parents=True, exist_ok=True)

        async with self._lock:
            if upload_id in self._statuses:
                existing = self._statuses[upload_id]
                # Allow retrying previously failed uploads.
                if existing.get("status") != "error":
                    return {**existing, "upload_id": upload_id}
                self._statuses.pop(upload_id, None)

            self._statuses[upload_id] = {
                "upload_id": upload_id,
                "status": "preprocessing",
                "message": "保存并转码视频中...",
                "progress": 0.0,
                "created_at": time.time(),
                "filename": filename,
                "video_path": None,
            }

        original_path = upload_root / f"original_{Path(filename).name}"
        original_path.write_bytes(file_bytes)

        try:
            video_path = await self._transcode_to_25fps(original_path, upload_root / "video.mp4")
            await self._update_status(upload_id, video_path=str(video_path))
            info = await self._get_video_info(video_path)
            duration = info.get("duration", 0.0)
            if duration > self.cfg.max_upload_duration_s:
                raise AvatarValidationError(
                    f"视频时长 {duration:.1f}s 超过限制 {self.cfg.max_upload_duration_s}s"
                )
            if duration < 1.0:
                raise AvatarValidationError("视频时长不足 1 秒")

            await self._update_status(upload_id, status="preprocessing", progress=0.3, message="人脸检测中...")
            face_ok = await self._detect_faces(video_path)
            if not face_ok:
                raise AvatarValidationError("未检测到稳定人脸，请上传正面清晰的人脸视频")

            await self._update_status(upload_id, status="preprocessing", progress=0.5, message="初始化 MuseTalk Avatar...")
            avatar = MuseTalkAvatar(
                avatar_id=upload_id,
                video_path=video_path,
                model_dir=self.cfg.muse_model_dir,
                whisper_dir=self.cfg.muse_whisper_dir,
                device=self.device,
                batch_size=self.cfg.muse_batch_size,
                fps=self.cfg.muse_fps,
                bbox_shift=self.cfg.muse_bbox_shift,
                version=self.cfg.muse_version,
                result_dir=self.cfg.output_dir,
            )

            async with self._lock:
                self._avatars[upload_id] = avatar
                self._trim_cache()

            asyncio.create_task(self._prepare_avatar(upload_id, avatar))

        except Exception as exc:
            await self._update_status(
                upload_id,
                status="error",
                message=str(exc),
            )
            raise

        return {**self._statuses[upload_id], "upload_id": upload_id}

    def get_status(self, upload_id: str) -> Optional[Dict[str, Any]]:
        return self._statuses.get(upload_id)

    @staticmethod
    def _prepare_on_device(avatar: MuseTalkAvatar, device) -> None:
        import torch_npu

        torch_npu.npu.set_device(device)
        avatar.prepare()

    @staticmethod
    def _render_on_device(
        avatar: MuseTalkAvatar,
        audio_path: Path,
        output_path: Path,
        device,
    ) -> Path:
        import torch_npu

        torch_npu.npu.set_device(device)
        return avatar.render_to_video(audio_path, output_path)

    async def render(
        self,
        upload_id: str,
        audio_path: Path,
        output_path: Path,
    ) -> Path:
        """Render a lip-sync MP4 using the prepared avatar."""
        self._ensure_locks()
        avatar = await self._get_ready_avatar(upload_id)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        async with self._thg_lock:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None,
                self._render_on_device,
                avatar,
                audio_path,
                output_path,
                self.device,
            )

    async def get_avatar(self, upload_id: str) -> MuseTalkAvatar:
        """Return a ready avatar, raising if not prepared."""
        return await self._get_ready_avatar(upload_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _prepare_avatar(self, upload_id: str, avatar: MuseTalkAvatar) -> None:
        """Run MuseTalk prepare() under a semaphore and update status."""
        self._ensure_locks()
        try:
            await self._update_status(upload_id, status="preprocessing", progress=0.6, message="MuseTalk 预处理中（首次较慢）...")
            async with self._prepare_sem:
                async with self._thg_lock:
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(
                        None,
                        self._prepare_on_device,
                        avatar,
                        self.device,
                    )
            await self._update_status(upload_id, status="ready", progress=1.0, message="准备完成")
        except Exception as exc:
            await self._update_status(upload_id, status="error", message=f"预处理失败: {exc}")

    def _create_avatar_for_upload(self, upload_id: str, video_path: Path) -> MuseTalkAvatar:
        return MuseTalkAvatar(
            avatar_id=upload_id,
            video_path=video_path,
            model_dir=self.cfg.muse_model_dir,
            whisper_dir=self.cfg.muse_whisper_dir,
            device=self.device,
            batch_size=self.cfg.muse_batch_size,
            fps=self.cfg.muse_fps,
            bbox_shift=self.cfg.muse_bbox_shift,
            version=self.cfg.muse_version,
            result_dir=self.cfg.output_dir,
        )

    async def _get_ready_avatar(self, upload_id: str) -> MuseTalkAvatar:
        self._ensure_locks()
        async with self._lock:
            avatar = self._avatars.get(upload_id)
            if avatar is None:
                status = self._statuses.get(upload_id, {})
                if status.get("status") != "ready":
                    raise AvatarNotReadyError(f"Avatar {upload_id} 尚未准备完成")
                video_path = status.get("video_path")
                if not video_path:
                    raise AvatarNotReadyError(f"缺少视频路径: {upload_id}")
                # Recreate from cached assets on disk; prepare() will load them.
                avatar = self._create_avatar_for_upload(upload_id, Path(video_path))
                self._avatars[upload_id] = avatar
                self._trim_cache()
            self._avatars.move_to_end(upload_id)
        status = self._statuses.get(upload_id, {})
        if status.get("status") != "ready":
            raise AvatarNotReadyError(f"Avatar {upload_id} 尚未准备完成")
        return avatar

    async def _update_status(
        self,
        upload_id: str,
        status: Optional[str] = None,
        progress: Optional[float] = None,
        message: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        self._ensure_locks()
        async with self._lock:
            st = self._statuses.setdefault(upload_id, {"upload_id": upload_id})
            if status is not None:
                st["status"] = status
            if progress is not None:
                st["progress"] = progress
            if message is not None:
                st["message"] = message
            st.update(kwargs)
            st["updated_at"] = time.time()

    def _trim_cache(self) -> None:
        """Evict oldest avatars when cache size is exceeded.

        Only the in-memory instance is removed; the prepared assets on disk
        remain so the avatar can be recreated cheaply later.
        """
        while len(self._avatars) > self.cfg.avatar_cache_size:
            oldest_id, oldest_avatar = self._avatars.popitem(last=False)
            print(f"[AvatarManager] Evicting avatar {oldest_id} from memory cache")
            # Explicitly release references to large tensors.
            del oldest_avatar

    # ------------------------------------------------------------------
    # Video validation
    # ------------------------------------------------------------------

    async def _transcode_to_25fps(self, input_path: Path, output_path: Path) -> Path:
        """Transcode video to H.264 25fps; raises AvatarValidationError on failure."""
        cmd = [
            str(self.cfg.project_root / "bin" / "ffmpeg"),
            "-y",
            "-i", str(input_path),
            "-r", "25",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-an",
            str(output_path),
        ]
        loop = asyncio.get_event_loop()
        proc = await loop.run_in_executor(
            None,
            lambda: subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE),
        )
        if proc.returncode != 0:
            err = proc.stderr.decode("utf-8", errors="ignore")[-500:]
            raise AvatarValidationError(f"视频转码失败: {err}")
        return output_path

    async def _get_video_info(self, video_path: Path) -> Dict[str, Any]:
        cmd = [
            str(self.cfg.project_root / "bin" / "ffprobe"),
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=duration,r_frame_rate,width,height",
            "-of", "json",
            str(video_path),
        ]
        loop = asyncio.get_event_loop()
        proc = await loop.run_in_executor(
            None,
            lambda: subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE),
        )
        if proc.returncode != 0:
            err = proc.stderr.decode("utf-8", errors="ignore")[-500:]
            raise AvatarValidationError(f"ffprobe 失败: {err}")
        data = json.loads(proc.stdout)
        stream = (data.get("streams") or [{}])[0]
        duration = float(stream.get("duration") or 0.0)
        fps_str = stream.get("r_frame_rate", "0/1")
        try:
            num, den = fps_str.split("/")
            fps = float(num) / float(den) if den != "0" else 0.0
        except Exception:
            fps = 0.0
        return {
            "duration": duration,
            "fps": fps,
            "width": stream.get("width", 0),
            "height": stream.get("height", 0),
        }

    async def _detect_faces(self, video_path: Path, sample_count: int = 5) -> bool:
        """Sample frames and require a face in at least 80% of them."""
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return False
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames <= 0:
            cap.release()
            return False

        indices = [int(total_frames * i / max(sample_count - 1, 1)) for i in range(sample_count)]
        indices = [min(i, total_frames - 1) for i in indices]
        ok = 0
        for idx in indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = cap.read()
            if not ret or frame is None:
                continue
            if self._has_face(frame):
                ok += 1
        cap.release()
        return ok >= max(1, int(sample_count * 0.8))

    def _has_face(self, frame: np.ndarray) -> bool:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self._face_cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=4, minSize=(64, 64)
        )
        return len(faces) > 0


if __name__ == "__main__":
    import torch

    async def _test():
        cfg = Config()
        manager = AvatarManager(cfg, torch.device("cpu"))
        print("AvatarManager created")

    asyncio.run(_test())
