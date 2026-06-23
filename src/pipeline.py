"""End-to-end conversation pipeline: LLM -> TTS -> THG -> RTMP."""
from __future__ import annotations

import asyncio
import os
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
import numpy as np
import torch
from pydub import AudioSegment

from src.config import Config
from src.llm_client import LLMClient
from src.streaming import RTMPStreamer
from src.thg_engine import MuseTalkAvatar
from src.tts_engine import EdgeTTSEngine, detect_language, pick_voice
from src.utils import segment_text


@dataclass
class PipelineEvent:
    event: str  # llm_text, stream_ready, sentence_stream_done, done, error
    payload: Dict[str, Any] = field(default_factory=dict)


class ConversationPipeline:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.client = LLMClient(
            base_url=cfg.llm_base_url,
            api_key=cfg.llm_api_key or None,
            model=cfg.llm_model,
        )
        self.avatar = MuseTalkAvatar(
            avatar_id=cfg.avatar_id,
            video_path=cfg.avatar_video,
            model_dir=cfg.muse_model_dir,
            whisper_dir=cfg.muse_whisper_dir,
            device=torch.device(cfg.ascend_npu_device),
            batch_size=cfg.muse_batch_size,
            fps=cfg.muse_fps,
            bbox_shift=cfg.muse_bbox_shift,
            version=cfg.muse_version,
            result_dir=cfg.output_dir,
        )
        self.avatar.prepare()
        self.history: List[Dict[str, str]] = []
        self._prewarm_done = False

    def _emit(self, event: str, **kwargs: Any) -> PipelineEvent:
        return PipelineEvent(event=event, payload=kwargs)

    async def prewarm(self) -> None:
        """Trigger a dummy inference so torch.compile graphs are warm."""
        if self._prewarm_done:
            return
        dummy_wav = "/tmp/dummy_prewarm.wav"
        import subprocess as sp

        sp.run(
            [
                str(self.cfg.project_root / "bin" / "ffmpeg"),
                "-y",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=r=16000:cl=mono",
                "-t",
                "3",
                "-acodec",
                "pcm_s16le",
                dummy_wav,
            ],
            check=True,
            stdout=sp.DEVNULL,
            stderr=sp.DEVNULL,
        )
        # Run one dummy inference to warm the NPU graphs.
        _ = list(self.avatar.infer(Path(dummy_wav)))
        self._prewarm_done = True

    async def run(
        self,
        user_text: str,
        voice_id: Optional[str] = None,
        language: str = "auto",
        max_tokens: int = 256,
    ) -> asyncio.Queue[PipelineEvent]:
        """Start a conversation and return an async event queue."""
        event_q: asyncio.Queue[PipelineEvent] = asyncio.Queue()
        asyncio.create_task(
            self._process(user_text, voice_id, language, max_tokens, event_q)
        )
        return event_q

    async def _process(
        self,
        user_text: str,
        voice_id: Optional[str],
        language: str,
        max_tokens: int,
        event_q: asyncio.Queue[PipelineEvent],
    ) -> None:
        session_id = uuid.uuid4().hex[:8]
        start_ts = time.perf_counter()
        first_stream_emitted = False
        active_streamers: List[RTMPStreamer] = []
        sentence_index = 0

        try:
            await event_q.put(self._emit("start", session_id=session_id))

            messages = LLMClient.build_messages(self.history, user_text)
            full_text = ""
            sentence_buffer = ""

            async for delta, meta in self.client.chat_stream(messages, max_tokens=max_tokens):
                full_text += delta
                sentence_buffer += delta
                await event_q.put(
                    self._emit(
                        "llm_text",
                        delta=delta,
                        text=full_text,
                        first_token_latency_ms=meta.get("first_token_latency_ms"),
                    )
                )

                if self._should_flush(sentence_buffer):
                    sentences = segment_text(sentence_buffer)
                    for sent in sentences:
                        sentence_index += 1
                        first_stream_emitted = await self._stream_sentence(
                            session_id,
                            sentence_index,
                            sent,
                            voice_id,
                            language,
                            start_ts,
                            event_q,
                            first_stream_emitted,
                        )
                    sentence_buffer = ""

            # Flush remaining text
            if sentence_buffer.strip():
                for sent in segment_text(sentence_buffer):
                    sentence_index += 1
                    first_stream_emitted = await self._stream_sentence(
                        session_id,
                        sentence_index,
                        sent,
                        voice_id,
                        language,
                        start_ts,
                        event_q,
                        first_stream_emitted,
                    )

            self.history.append({"role": "user", "content": user_text})
            self.history.append({"role": "assistant", "content": full_text})
            await event_q.put(self._emit("done", session_id=session_id, text=full_text))
        except Exception as exc:
            await event_q.put(self._emit("error", session_id=session_id, message=str(exc)))
        finally:
            for s in active_streamers:
                try:
                    s.finish()
                except Exception:
                    pass
            # Do NOT close self.client here — the pipeline is long-lived and
            # reused across requests.  The client will be closed when the
            # pipeline is garbage-collected or on process exit.

    def _should_flush(self, buffer: str) -> bool:
        return any(p in buffer for p in ".。！？；!?;")

    async def _stream_sentence(
        self,
        session_id: str,
        sentence_index: int,
        sentence: str,
        voice_id: Optional[str],
        language: str,
        start_ts: float,
        event_q: asyncio.Queue[PipelineEvent],
        first_stream_emitted: bool,
    ) -> None:
        lang = language if language != "auto" else detect_language(sentence)
        voice = pick_voice(lang, voice_id)
        tts_engine = EdgeTTSEngine(voice=voice)

        base_name = f"{session_id}_{sentence_index:04d}"
        wav_path = self.cfg.output_dir / f"{base_name}.wav"

        t0 = time.perf_counter()
        await tts_engine.synthesize(sentence, wav_path)
        tts_latency_ms = round((time.perf_counter() - t0) * 1000, 1)

        # Pad very short audio with silence so the RTMP stream stays alive
        # long enough for MediaMTX to register the path and browsers to connect.
        try:
            audio = AudioSegment.from_wav(str(wav_path))
            min_duration_ms = 5000
            if len(audio) < min_duration_ms:
                padding = AudioSegment.silent(duration=min_duration_ms - len(audio))
                audio = audio + padding
                audio.export(str(wav_path), format="wav")
        except Exception as e:
            print(f"[PIPELINE] Failed to pad audio: {e}")

        # Unique RTMP path per sentence stream.
        rtmp_url = f"{self.cfg.rtmp_url}/{session_id}_{sentence_index:04d}"

        # Determine frame size from the first avatar base frame.
        base_frame = self.avatar.frame_list_cycle[0]
        height, width = base_frame.shape[:2]

        streamer = RTMPStreamer(
            frame_size=(width, height),
            fps=self.cfg.muse_fps,
            rtmp_url=rtmp_url,
            audio_path=wav_path,
            ffmpeg_path=str(self.cfg.project_root / "bin" / "ffmpeg"),
        )

        # Run streaming in executor to avoid blocking the event loop.
        loop = asyncio.get_event_loop()
        stream_task = loop.run_in_executor(
            None,
            streamer.stream,
            self.avatar.infer(wav_path),
            start_ts,
        )

        # Wait until ffmpeg has consumed the first frame.
        try:
            await asyncio.wait_for(
                loop.run_in_executor(None, streamer.ready_event.wait),
                timeout=30.0,
            )
        except asyncio.TimeoutError:
            pass

        # Wait until MediaMTX reports the path online before telling the browser
        # to play. Emitting stream_ready too early causes the WebRTC player to
        # retry a non-existent path.
        path_online = await self._wait_for_path_online(session_id, sentence_index, 15.0)

        # Emit stream_ready on first sentence only after the path is confirmed
        # online so the browser does not try to play a missing stream.
        first_video_latency_ms = round((time.perf_counter() - start_ts) * 1000, 1)
        if not first_stream_emitted and path_online:
            await event_q.put(
                self._emit(
                    "stream_ready",
                    session_id=session_id,
                    rtmp_url=rtmp_url,
                    webrtc_url=f"{self.cfg.webrtc_play_url.rstrip('/')}/{session_id}_{sentence_index:04d}/",
                    tts_latency_ms=tts_latency_ms,
                    first_video_latency_ms=first_video_latency_ms,
                )
            )
            first_stream_emitted = True
        elif not path_online:
            print(f"[PIPELINE] Skipping stream_ready for {session_id}_{sentence_index:04d}: path not online")

        await stream_task
        await event_q.put(
            self._emit(
                "sentence_stream_done",
                session_id=session_id,
                sentence_index=sentence_index,
                sentence=sentence,
            )
        )
        return first_stream_emitted

    async def _wait_for_path_online(
        self, session_id: str, sentence_index: int, timeout: float = 10.0
    ) -> bool:
        """Poll MediaMTX API until the RTMP path is reported online.

        MediaMTX's default internal auth only allows API access from 127.0.0.1,
        so we query the API on localhost regardless of the public RTMP/WebRTC
        host configured in the environment.
        """
        import urllib.parse
        path_name = f"live/{session_id}_{sentence_index:04d}"
        encoded_name = urllib.parse.quote(path_name, safe="")
        api_url = f"http://127.0.0.1:9997/v3/paths/get/{encoded_name}"
        t0 = time.perf_counter()
        async with httpx.AsyncClient() as client:
            while time.perf_counter() - t0 < timeout:
                try:
                    r = await client.get(api_url, timeout=2.0)
                    if r.status_code == 200:
                        data = r.json()
                        if data.get("ready"):
                            print(f"[PIPELINE] Path {path_name} is online")
                            return True
                except Exception as exc:
                    print(f"[PIPELINE] API poll error for {path_name}: {exc}")
                await asyncio.sleep(0.2)
        print(f"[PIPELINE] Path {path_name} did not come online within {timeout}s")
        return False


if __name__ == "__main__":
    async def _test():
        cfg = Config()
        pipe = ConversationPipeline(cfg)
        await pipe.prewarm()
        q = await pipe.run("你好，请简单介绍一下自己。", max_tokens=40)
        while True:
            ev = await q.get()
            print(ev.event, ev.payload.get("sentence") or ev.payload.get("delta", ""))
            if ev.event in ("done", "error"):
                break

    asyncio.run(_test())
