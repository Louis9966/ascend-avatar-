"""Audio utilities for MuseTalk preprocessing.

Provides lightweight helpers that run on CPU and do not depend on the NPU.
"""
from __future__ import annotations

from pathlib import Path
from typing import Tuple, Union

import librosa
import numpy as np
import soundfile as sf


def load_audio(
    path: Union[str, Path],
    sample_rate: int = 16000,
    mono: bool = True,
) -> Tuple[np.ndarray, int]:
    """Load an audio file and resample to the target sample rate."""
    y, sr = librosa.load(str(path), sr=sample_rate, mono=mono)
    return y, sr


def trim_silence(
    input_path: Union[str, Path],
    output_path: Union[str, Path],
    sample_rate: int = 16000,
    top_db: int = 30,
    keep_leading_ms: float = 20.0,
    keep_trailing_ms: float = 50.0,
) -> Path:
    """Trim leading / trailing silence and resample to ``sample_rate``.

    MuseTalk's audio features are extracted at 16 kHz.  Removing silence at the
    edges makes the first rendered frame align with the first audible phoneme,
    which fixes the "mouth starts too late" perception without changing the
    neural model.

    Args:
        input_path: Source audio file (any format librosa can read).
        output_path: Destination WAV file.
        sample_rate: Target sample rate (MuseTalk expects 16 kHz).
        top_db: Silence threshold for librosa.effects.trim.
        keep_leading_ms: Short padding kept before speech onset.
        keep_trailing_ms: Short padding kept after speech end.

    Returns:
        Path to the trimmed WAV file.
    """
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    y, sr = load_audio(input_path, sample_rate=sample_rate, mono=True)
    if y.size == 0:
        sf.write(str(output_path), y, sr)
        return output_path

    yt, idx = librosa.effects.trim(y, top_db=top_db)
    lead = int(keep_leading_ms * sr / 1000)
    trail = int(keep_trailing_ms * sr / 1000)
    start = max(0, idx[0] - lead)
    end = min(len(y), idx[1] + trail)
    yt = y[start:end]

    sf.write(str(output_path), yt, sr)
    return output_path


def audio_duration(path: Union[str, Path], sample_rate: int = 16000) -> float:
    """Return the duration of ``path`` in seconds."""
    y, sr = load_audio(path, sample_rate=sample_rate)
    return len(y) / sr


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 3:
        print("Usage: python -m src.audio_utils <input.wav> <output.wav>")
        sys.exit(1)
    trim_silence(sys.argv[1], sys.argv[2])
    print("Trimmed audio saved to", sys.argv[2])
