"""Shared utilities for ascend-avatar."""
from __future__ import annotations

import re
from typing import List


SENTENCE_END_PUNCT = r"[。！？；.!?;]"


def segment_text(text: str, max_chars: int = 40) -> List[str]:
    """Split text into TTS-ready chunks by punctuation.

    Long sentences without terminal punctuation are further split by commas
    or by max_chars to keep each chunk short and low-latency.
    """
    text = text.strip()
    if not text:
        return []

    # Split by sentence-ending punctuation but keep the punctuation
    parts = re.split(f"({SENTENCE_END_PUNCT}+)", text)
    sentences: List[str] = []
    i = 0
    while i < len(parts):
        chunk = parts[i]
        if i + 1 < len(parts) and re.match(SENTENCE_END_PUNCT, parts[i + 1]):
            chunk += parts[i + 1]
            i += 2
        else:
            i += 1
        chunk = chunk.strip()
        if not chunk:
            continue
        if len(chunk) <= max_chars:
            sentences.append(chunk)
            continue
        # Long chunk: split by commas/顿号 first
        sub_parts = re.split(r"([，、,])", chunk)
        cur = ""
        for sp in sub_parts:
            if len(cur) + len(sp) > max_chars and cur:
                sentences.append(cur.strip())
                cur = sp
            else:
                cur += sp
        if cur.strip():
            sentences.append(cur.strip())
    return [s for s in sentences if s]


if __name__ == "__main__":
    samples = [
        "你好，这是一个测试。今天天气不错！",
        "First sentence. Second one, with a comma and more words to split.",
        "这是一个非常长的句子没有任何标点但是为了测试我们把它切开因为它太长了",
    ]
    for s in samples:
        print(s, "->", segment_text(s))
