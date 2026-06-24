"""Optional GFPGAN face enhancement post-processing for generated videos."""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

import cv2
import torch

try:
    import torch_npu  # noqa: F401
except Exception:  # pragma: no cover
    torch_npu = None

logger = logging.getLogger(__name__)


def _find_ffmpeg() -> str:
    """Return the ffmpeg binary path; prefer the bundled one."""
    candidates = [
        "/ascend-avatar/bin/ffmpeg",
        "ffmpeg",
    ]
    for c in candidates:
        if os.path.exists(c) or shutil.which(c):
            return c
    return "ffmpeg"


def _parse_npu_id(device: str) -> int:
    """Extract the NPU device id from strings like ``npu`` or ``npu:7``."""
    device = str(device).lower()
    if device.startswith("npu:"):
        try:
            return int(device.split(":", 1)[1])
        except ValueError:
            return 0
    return 0


def _npu_available() -> bool:
    """Return True if torch_npu is installed and at least one NPU is visible."""
    if torch_npu is None:
        return False
    try:
        return torch_npu.npu.is_available()
    except Exception:
        return False


class GFPGANPostProcessor:
    """Enhance a MuseTalk output video frame-by-frame using GFPGAN.

    Supports both CPU and Ascend NPU inference.  When ``device`` contains
    ``npu``, ``torch_npu`` is imported and the NPU context is initialized in
    the worker thread before inference.  If NPU initialization or inference
    fails, the restorer automatically falls back to CPU so the pipeline still
    completes.
    """

    def __init__(
        self,
        model_path: Path,
        upscale: int = 2,
        arch: str = "clean",
        channel_multiplier: int = 2,
        device: str = "cpu",
    ):
        from gfpgan import GFPGANer

        self.model_path = Path(model_path)
        if not self.model_path.exists():
            raise FileNotFoundError(f"GFPGAN model not found: {self.model_path}")

        self.upscale = upscale
        self.arch = arch
        self.channel_multiplier = channel_multiplier
        self.requested_device = device
        self._npu_device_id: Optional[int] = None
        self.restorer = self._build_restorer(device)

    def _build_restorer(self, device: str):
        """Build a GFPGANer restorer on the requested device with CPU fallback."""
        from gfpgan import GFPGANer

        requested = str(device).lower()
        if "npu" in requested and _npu_available():
            npu_id = _parse_npu_id(requested)
            try:
                torch_npu.npu.set_device(npu_id)
                restorer = GFPGANer(
                    model_path=str(self.model_path),
                    upscale=self.upscale,
                    arch=self.arch,
                    channel_multiplier=self.channel_multiplier,
                    device=torch.device(f"npu:{npu_id}"),
                )
                self._npu_device_id = npu_id
                logger.info("GFPGAN initialized on npu:%s", npu_id)
                return restorer
            except Exception as exc:
                logger.warning(
                    "GFPGAN NPU init failed (%s), falling back to CPU", exc
                )
                self._npu_device_id = None

        return GFPGANer(
            model_path=str(self.model_path),
            upscale=self.upscale,
            arch=self.arch,
            channel_multiplier=self.channel_multiplier,
            device=torch.device("cpu"),
        )

    def _ensure_npu_context(self) -> None:
        """Initialize the NPU context for the current thread."""
        if self._npu_device_id is not None and torch_npu is not None:
            torch_npu.npu.set_device(self._npu_device_id)

    def enhance_frame(self, frame_bgr: cv2.Mat) -> cv2.Mat:
        """Enhance a single BGR frame and return a BGR frame."""
        self._ensure_npu_context()
        try:
            _, _, restored = self.restorer.enhance(
                frame_bgr,
                has_aligned=False,
                only_center_face=True,
                paste_back=True,
            )
        except Exception as exc:
            if self._npu_device_id is not None:
                logger.warning(
                    "GFPGAN NPU inference failed on a frame (%s); "
                    "falling back to CPU for this frame",
                    exc,
                )
                self._npu_device_id = None
                self.restorer = self._build_restorer("cpu")
                _, _, restored = self.restorer.enhance(
                    frame_bgr,
                    has_aligned=False,
                    only_center_face=True,
                    paste_back=True,
                )
            else:
                raise

        if restored is None:
            return frame_bgr
        # GFPGAN returns RGB numpy array
        if restored.shape[2] == 3:
            restored = cv2.cvtColor(restored, cv2.COLOR_RGB2BGR)
        return restored

    def enhance_video(
        self,
        input_path: Path,
        output_path: Path,
        fps: Optional[float] = None,
        crf: int = 18,
        preset: str = "medium",
    ) -> Path:
        """Enhance every frame of ``input_path`` and mux with original audio."""
        input_path = Path(input_path)
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize NPU context in the worker thread before any inference.
        self._ensure_npu_context()

        cap = cv2.VideoCapture(str(input_path))
        if fps is None:
            fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        tmp_dir = output_path.parent / "gfpgan_frames"
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir)
        tmp_dir.mkdir(parents=True, exist_ok=True)

        frame_count = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            enhanced = self.enhance_frame(frame)
            # Keep the same resolution as the input to avoid downstream size changes.
            if enhanced.shape[:2] != (height, width):
                enhanced = cv2.resize(
                    enhanced,
                    (width, height),
                    interpolation=cv2.INTER_LANCZOS4,
                )
            cv2.imwrite(str(tmp_dir / f"{frame_count:08d}.png"), enhanced)
            frame_count += 1
        cap.release()

        if frame_count == 0:
            raise RuntimeError(f"No frames read from {input_path}")

        ffmpeg = _find_ffmpeg()
        cmd = [
            ffmpeg,
            "-y",
            "-loglevel", "warning",
            "-r", str(fps),
            "-i", str(tmp_dir / "%08d.png"),
            "-i", str(input_path),
            "-map", "0:v",
            "-map", "1:a",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-crf", str(crf),
            "-preset", preset,
            "-c:a", "copy",
            str(output_path),
        ]
        ret = subprocess.run(cmd, check=False).returncode
        shutil.rmtree(tmp_dir)
        if ret != 0 or not output_path.exists():
            raise RuntimeError(f"GFPGAN video mux failed for {input_path}")
        return output_path


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 5:
        print("Usage: python -m src.gfpgan_postprocess <input.mp4> <output.mp4> <model.pth> <cpu|npu>")
        sys.exit(1)
    proc = GFPGANPostProcessor(Path(sys.argv[3]), device=sys.argv[4])
    proc.enhance_video(Path(sys.argv[1]), Path(sys.argv[2]))
    print("Enhanced video saved to", sys.argv[2])
