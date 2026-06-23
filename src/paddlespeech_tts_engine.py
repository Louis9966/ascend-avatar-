"""PaddleSpeech TTS engine wrapper for ascend-avatar.

This module wraps the local PaddleSpeech TTS CLI executor so it can be used
interchangeably with the existing edge-tts engine. Inference runs on CPU in a
background thread to avoid blocking the asyncio event loop.
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path
from types import ModuleType
from typing import Optional, Union

# The PaddleSpeech repository is checked out next to the project root.
PADDLESPEECH_ROOT = Path(os.environ.get("PADDLESPEECH_ROOT", "/ascend-avatar/PaddleSpeech"))
if str(PADDLESPEECH_ROOT) not in sys.path:
    sys.path.insert(0, str(PADDLESPEECH_ROOT))

# g2p_en (pulled in by PaddleSpeech) blocks on first import trying to download
# NLTK tagger data. We only use Chinese TTS here, so monkey-patch NLTK to
# bypass the network access and avoid the hang.
try:
    import nltk.data as _nltk_data  # type: ignore[import]
    import nltk as _nltk  # type: ignore[import]

    _orig_find = _nltk_data.find

    def _patched_find(resource_name, *args, **kwargs):
        if isinstance(resource_name, str) and "averaged_perceptron_tagger" in resource_name:
            return "/dev/null"
        return _orig_find(resource_name, *args, **kwargs)

    _nltk_data.find = _patched_find
    _nltk.download = lambda *args, **kwargs: True  # type: ignore[assignment]
except Exception:
    pass


try:
    import paddle  # noqa: F401
    from paddlespeech.cli.tts.infer import TTSExecutor
except Exception as _import_exc:  # pragma: no cover - imports may fail before install
    import traceback as _tb
    print("[PaddleSpeechTTS] import failed:", _import_exc)
    print(_tb.format_exc())
    TTSExecutor = None  # type: ignore[misc,assignment]


class PaddleSpeechTTSError(Exception):
    """Raised when PaddleSpeech TTS inference fails."""


class PaddleSpeechTTSEngine:
    """Local TTS engine backed by PaddleSpeech.

    Example:
        engine = PaddleSpeechTTSEngine(
            am="fastspeech2_aishell3",
            voc="hifigan_aishell3",
            lang="zh",
            spk_id=0,
            device="cpu",
        )
        await engine.synthesize("你好，欢迎使用 PaddleSpeech。", Path("/tmp/out.wav"))
    """

    def __init__(
        self,
        am: str = "fastspeech2_aishell3",
        voc: str = "hifigan_aishell3",
        lang: str = "zh",
        spk_id: int = 0,
        device: str = "cpu",
    ):
        if TTSExecutor is None:
            raise PaddleSpeechTTSError(
                "PaddleSpeech is not available. Please install it in the container: "
                "pip install paddlepaddle && cd /ascend-avatar/PaddleSpeech && pip install -e ."
            )
        self.am = am
        self.voc = voc
        self.lang = lang
        self.spk_id = spk_id
        self.device = device
        self._executor: Optional[TTSExecutor] = None
        self._init_lock = asyncio.Lock()

    def _ensure_executor(self) -> "TTSExecutor":
        if self._executor is None:
            self._executor = TTSExecutor()
        return self._executor

    def _synthesize_sync(self, text: str, output_wav: Union[str, Path]) -> Path:
        """Synchronous wrapper around TTSExecutor.__call__."""
        output_wav = Path(output_wav)
        output_wav.parent.mkdir(parents=True, exist_ok=True)
        executor = self._ensure_executor()
        t0 = time.perf_counter()
        try:
            result = executor(
                text=text,
                am=self.am,
                voc=self.voc,
                spk_id=self.spk_id,
                lang=self.lang,
                device=self.device,
                output=str(output_wav),
            )
        except Exception as exc:
            raise PaddleSpeechTTSError(f"PaddleSpeech TTS failed: {exc}") from exc
        latency_ms = (time.perf_counter() - t0) * 1000
        print(f"[PaddleSpeechTTS] synthesized in {latency_ms:.1f} ms -> {result}")
        return Path(result)

    async def synthesize(self, text: str, output_wav: Union[str, Path]) -> Path:
        """Asynchronously synthesize ``text`` to ``output_wav``.

        The underlying PaddleSpeech inference is CPU-bound, so it is offloaded
        to the default thread pool.
        """
        if not text or not text.strip():
            raise PaddleSpeechTTSError("Empty text for TTS")
        # Model initialization is not asyncio-aware; serialize it to avoid
        # concurrent downloads/races on first use.
        async with self._init_lock:
            executor = self._ensure_executor()
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self._synthesize_sync,
            text,
            output_wav,
        )

    async def list_voices(self) -> list[dict]:
        """Return available speakers for the configured multi-speaker model.

        For ``fastspeech2_aishell3`` the valid ``spk_id`` range is typically
        0–173. For single-speaker models an empty list is returned.
        """
        # PaddleSpeech does not expose a discovery API; we return the documented
        # ranges for the known multi-speaker models.
        if self.am.endswith("_aishell3"):
            return [{"id": i, "name": f"speaker_{i}"} for i in range(174)]
        if self.am.endswith("_vctk"):
            return [{"id": i, "name": f"speaker_{i}"} for i in range(109)]
        return []


async def _smoke_test():
    engine = PaddleSpeechTTSEngine(
        am="fastspeech2_aishell3",
        voc="hifigan_aishell3",
        lang="zh",
        spk_id=0,
        device="cpu",
    )
    out = Path("/tmp/paddlespeech_test.wav")
    result = await engine.synthesize("你好，这是 PaddleSpeech 本地 TTS 测试。", out)
    print(f"Smoke test passed: {result}")
    voices = await engine.list_voices()
    print(f"Available voices sample: {voices[:3]} ... total {len(voices)}")


if __name__ == "__main__":
    asyncio.run(_smoke_test())
