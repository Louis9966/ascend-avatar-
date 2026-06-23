import asyncio
import time
from pathlib import Path

import torch

from src.config import Config
from src.thg_engine import MuseTalkAvatar
from src.tts_engine import EdgeTTSEngine
from src.streaming import RTMPStreamer


async def main():
    cfg = Config()
    device = torch.device("npu:0")
    avatar = MuseTalkAvatar(
        avatar_id=cfg.avatar_id,
        video_path=cfg.avatar_video,
        model_dir=cfg.muse_model_dir,
        whisper_dir=cfg.muse_whisper_dir,
        device=device,
        batch_size=cfg.muse_batch_size,
        fps=cfg.muse_fps,
    )
    avatar.prepare()

    # Pre-warm NPU compile with a dummy audio so the real stream is fast.
    dummy_wav = "/tmp/dummy_3s.wav"
    import subprocess as sp
    sp.run([
        str(Path(cfg.project_root) / "bin" / "ffmpeg"), "-y", "-f", "lavfi",
        "-i", "anullsrc=r=16000:cl=mono", "-t", "3", "-acodec", "pcm_s16le", dummy_wav
    ], check=True, stdout=sp.DEVNULL, stderr=sp.DEVNULL)
    print("[STREAM] pre-warming compile...")
    pw_start = time.perf_counter()
    list(avatar.infer(Path(dummy_wav)))
    print(f"[STREAM] pre-warm done in {(time.perf_counter()-pw_start)*1000:.1f}ms")

    tts = EdgeTTSEngine(voice="zh-CN-XiaoxiaoNeural")
    text = "你好，这是数字人测试。"
    wav_path = "/tmp/stream_test.wav"

    start = time.perf_counter()
    await tts.synthesize(text, wav_path)
    tts_ms = (time.perf_counter() - start) * 1000
    print(f"[STREAM] TTS done in {tts_ms:.1f}ms")

    frame0 = avatar.frame_list_cycle[0]
    h, w = frame0.shape[:2]
    streamer = RTMPStreamer(
        frame_size=(w, h),
        fps=cfg.muse_fps,
        rtmp_url=cfg.rtmp_url,
        audio_path=Path(wav_path),
        ffmpeg_path=str(Path(cfg.project_root) / "bin" / "ffmpeg"),
    )

    infer_gen = avatar.infer(Path(wav_path))
    first_frame = next(infer_gen)
    first_infer_ms = (time.perf_counter() - start) * 1000
    print(f"[STREAM] first inference frame ready at {first_infer_ms:.1f}ms")

    streamer.start()
    streamer.write_frame(first_frame)
    first_write_ms = (time.perf_counter() - start) * 1000
    print(f"[STREAM] first frame written to ffmpeg at {first_write_ms:.1f}ms")

    for frame in infer_gen:
        streamer.write_frame(frame)
    streamer.finish()
    total_ms = (time.perf_counter() - start) * 1000
    print(f"[STREAM] stream finished in {total_ms:.1f}ms, frames={streamer._frames_written}")


if __name__ == "__main__":
    asyncio.run(main())
