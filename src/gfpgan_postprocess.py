"""Optional GFPGAN face enhancement post-processing for generated videos."""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Optional

import cv2


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


class GFPGANPostProcessor:
    """Enhance a MuseTalk output video frame-by-frame using GFPGAN.

    This is intentionally CPU-only by default so it does not compete with
    the NPU for MuseTalk inference. It is best suited for the offline
    video-generation path rather than real-time streaming.
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

        self.restorer = GFPGANer(
            model_path=str(self.model_path),
            upscale=upscale,
            arch=arch,
            channel_multiplier=channel_multiplier,
            device=device,
        )

    def enhance_frame(self, frame_bgr: cv2.Mat) -> cv2.Mat:
        """Enhance a single BGR frame and return a BGR frame."""
        _, _, restored = self.restorer.enhance(
            frame_bgr,
            has_aligned=False,
            only_center_face=True,
            paste_back=True,
        )
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
        ret = os.system(" ".join(cmd))
        shutil.rmtree(tmp_dir)
        if ret != 0 or not output_path.exists():
            raise RuntimeError(f"GFPGAN video mux failed for {input_path}")
        return output_path


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 4:
        print("Usage: python -m src.gfpgan_postprocess <input.mp4> <output.mp4> <model.pth>")
        sys.exit(1)
    proc = GFPGANPostProcessor(Path(sys.argv[3]))
    proc.enhance_video(Path(sys.argv[1]), Path(sys.argv[2]))
    print("Enhanced video saved to", sys.argv[2])
