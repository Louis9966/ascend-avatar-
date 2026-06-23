"""Streaming TTS engine using edge-tts."""
from __future__ import annotations

import asyncio
import io
import os
import re
import tempfile
from pathlib import Path
from typing import AsyncIterator, List

import edge_tts
from pydub import AudioSegment


VOICE_OPTIONS = {
    "zh-CN-XiaoxiaoNeural": "中文-女声（晓晓）",
    "zh-CN-YunxiNeural": "中文-男声（云希）",
    "zh-CN-YunjianNeural": "中文-男声（云健）",
    "en-US-AriaNeural": "English - Female (Aria)",
    "en-US-GuyNeural": "English - Male (Guy)",
    "zh-HK-HiuMaanNeural": "粤语-女声",
    "zh-TW-HsiaoChenNeural": "台湾国语-女声",
}


def detect_language(text: str) -> str:
    """Simple language detection: Chinese characters -> zh, otherwise en."""
    if re.search(r"[一-鿿]", text):
        return "zh"
    return "en"


def pick_voice(language: str, voice_id: str | None = None) -> str:
    if voice_id and voice_id in VOICE_OPTIONS:
        return voice_id
    if language == "zh":
        return "zh-CN-XiaoxiaoNeural"
    return "en-US-AriaNeural"


class EdgeTTSEngine:
    """Offline-ish TTS via Microsoft Edge TTS service."""

    def __init__(
        self,
        voice: str = "zh-CN-XiaoxiaoNeural",
        rate: str = "+0%",
        pitch: str = "+0Hz",
        sample_rate: int = 16000,
    ):
        self.voice = voice
        self.rate = rate
        self.pitch = pitch
        self.sample_rate = sample_rate

    async def synthesize(self, text: str, output_wav: str | Path) -> Path:
        """Synthesize full text to a mono WAV file."""
        output_wav = Path(output_wav)
        output_wav.parent.mkdir(parents=True, exist_ok=True)
        mp3_buffer = io.BytesIO()
        communicate = edge_tts.Communicate(text, self.voice, rate=self.rate, pitch=self.pitch)
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                mp3_buffer.write(chunk["data"])
        mp3_buffer.seek(0)
        audio = AudioSegment.from_mp3(mp3_buffer)
        audio = audio.set_frame_rate(self.sample_rate).set_channels(1)
        audio.export(output_wav, format="wav")
        return output_wav

    async def synthesize_stream(
        self, text: str
    ) -> AsyncIterator[bytes]:
        """Yield MP3 audio chunks as they arrive."""
        communicate = edge_tts.Communicate(text, self.voice, rate=self.rate, pitch=self.pitch)
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                yield chunk["data"]

    async def list_voices(self, language: str | None = None) -> List[dict]:
        voices = await edge_tts.list_voices()
        if language:
            voices = [v for v in voices if v.get("Locale", "").startswith(language)]
        return voices


async def _test():
    engine = EdgeTTSEngine(voice="zh-CN-XiaoxiaoNeural")
    out = await engine.synthesize("你好，这是一个测试。", "/tmp/edge_tts_test.wav")
    print("saved", out, "size", os.path.getsize(out))


if __name__ == "__main__":
    asyncio.run(_test())
