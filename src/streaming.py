"""Stream generated frames to RTMP/WebRTC via ffmpeg + mediamtx."""
from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path
from typing import Iterator, Optional, Tuple
from urllib.parse import urlparse

import numpy as np


class RTMPStreamer:
    """Pipe BGR frames into ffmpeg and push to an RTMP endpoint."""

    def __init__(
        self,
        frame_size: Tuple[int, int],
        fps: int,
        rtmp_url: str,
        audio_path: Optional[Path] = None,
        ffmpeg_path: str = "ffmpeg",
        video_codec: str = "libx264",
        padding_seconds: float = 0.0,
    ):
        self.width, self.height = frame_size
        self.fps = fps
        self.rtmp_url = rtmp_url
        self.audio_path = Path(audio_path) if audio_path else None
        self.ffmpeg_path = ffmpeg_path
        self.video_codec = video_codec
        self.padding_seconds = padding_seconds
        self.proc: Optional[subprocess.Popen] = None
        self._first_frame_time: Optional[float] = None
        self._frames_written = 0
        self._finished = False
        # Per-path log file so concurrent/sequential streams do not overwrite
        # each other's diagnostics.
        path_slug = Path(urlparse(rtmp_url).path).name or "unknown"
        self.ffmpeg_log_path = Path(f"/tmp/rtmp_ffmpeg_{path_slug}.log")
        self.ready_event = threading.Event()

    def start(self) -> None:
        cmd = [
            self.ffmpeg_path,
            "-y",
            "-loglevel",
            "warning",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "bgr24",
            "-s",
            f"{self.width}x{self.height}",
            "-r",
            str(self.fps),
            "-thread_queue_size",
            "512",
            "-i",
            "-",
        ]
        if self.audio_path and self.audio_path.exists():
            cmd += [
                "-thread_queue_size",
                "512",
                "-i",
                str(self.audio_path),
                "-c:a",
                "aac",
                "-ar",
                "16000",
                "-ac",
                "1",
            ]
        else:
            cmd += ["-an"]

        cmd += [
            "-c:v",
            self.video_codec,
            "-pix_fmt",
            "yuv420p",
            "-preset",
            "ultrafast",
            "-tune",
            "zerolatency",
            "-g",
            str(self.fps),
            "-keyint_min",
            str(self.fps),
            "-sc_threshold",
            "0",
            "-f",
            "flv",
            "-flvflags",
            "no_duration_filesize",
            self.rtmp_url,
        ]
        self.ffmpeg_log = open(self.ffmpeg_log_path, "wb")
        self.proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=self.ffmpeg_log,
        )

    def write_frame(self, frame: np.ndarray) -> None:
        if self.proc is None or self.proc.stdin is None:
            raise RuntimeError("ffmpeg not started")
        if self._first_frame_time is None:
            self._first_frame_time = time.perf_counter()
        self.proc.stdin.write(frame.tobytes())
        self._frames_written += 1

    def finish(self) -> None:
        if self.proc is None:
            return
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=30)
        except Exception:
            self.proc.kill()
        finally:
            self.ffmpeg_log.close()
        self._finished = True

    @property
    def first_frame_latency_ms(self) -> Optional[float]:
        if self._first_frame_time is None or self._start_time is None:
            return None
        return (self._first_frame_time - self._start_time) * 1000

    def stream(self, frames: Iterator[np.ndarray], start_time: Optional[float] = None) -> None:
        self._start_time = start_time or time.perf_counter()
        self.start()
        last_frame = None
        for frame in frames:
            self.write_frame(frame)
            last_frame = frame
            if self._frames_written == 1:
                # Signal that the first frame has been fed to ffmpeg; the caller
                # can now wait for the RTMP path to come online before telling
                # the browser to play it.
                self.ready_event.set()

        # Keep the stream alive for a short padding period so that MediaMTX has
        # time to register the path and browsers/WebRTC clients can connect.
        # Short sentences (e.g. "你好！") render too few frames for a stable
        # RTMP registration otherwise.
        if last_frame is not None and self.padding_seconds > 0:
            padding_frames = int(self.fps * self.padding_seconds)
            for _ in range(padding_frames):
                self.write_frame(last_frame)

        self.finish()

    def stream_async(self, frames: Iterator[np.ndarray], start_time: Optional[float] = None) -> threading.Thread:
        t = threading.Thread(target=self.stream, args=(frames, start_time))
        t.start()
        return t
