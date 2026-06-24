"""Replacement for musetalk.utils.preprocessing that avoids mmpose/mmcv.

Uses MediaPipe Face Mesh to derive a tight, mouth-focused bounding box.
If MediaPipe fails on a frame, falls back to the legacy OpenCV Haar detector.
This avoids building mmpose/mmcv on Ascend while still using accurate
facial landmarks for lip alignment.
"""
from __future__ import annotations

import glob
import os
from pathlib import Path
from typing import List, Tuple

import cv2
import numpy as np
from tqdm import tqdm

try:
    # Silence MediaPipe's verbose C++ logs by default.
    os.environ.setdefault("GLOG_minloglevel", "2")
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
    import mediapipe as mp

    _MP_FACE_MESH = mp.solutions.face_mesh.FaceMesh(
        static_image_mode=True,
        max_num_faces=1,
        refine_landmarks=True,
        min_detection_confidence=0.5,
    )
except Exception:  # pragma: no cover
    _MP_FACE_MESH = None

# Legacy Haar fallback
_FACE_CASCADE = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
)

# MediaPipe Face Mesh outer lip landmark indices (ordered around the mouth).
_OUTER_LIP_INDICES = [
    61, 185, 40, 39, 37, 0, 267, 269, 270, 409,
    291, 375, 321, 405, 314, 17, 84, 181, 91, 146,
]


def read_imgs(img_list: List[str]) -> List[np.ndarray]:
    frames = []
    print("reading images...")
    for img_path in tqdm(img_list):
        frame = cv2.imread(img_path)
        frames.append(frame)
    return frames


def _detect_face_haar(frame: np.ndarray) -> Tuple[int, int, int, int] | None:
    """Return a full-face bbox using the legacy Haar cascade."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = _FACE_CASCADE.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4)
    if len(faces) == 0:
        return None
    if len(faces) > 1:
        areas = faces[:, 2] * faces[:, 3]
        faces = faces[np.argmax(areas)]
    else:
        faces = faces[0]
    x, y, w, h = faces.astype(int)
    return int(x), int(y), int(x + w), int(y + h)


def _haar_to_mouth_bbox(
    face_bbox: Tuple[int, int, int, int]
) -> Tuple[int, int, int, int]:
    """Convert a full-face bbox into a mouth-focused bbox (legacy heuristic)."""
    x1, y1, x2, y2 = face_bbox
    w = x2 - x1
    h = y2 - y1
    # Focus on the lower face (mouth + chin), roughly 65% of face height.
    my1 = int(y1 + h * 0.40)
    my2 = y2
    return x1, my1, x2, my2


def _detect_mouth_bbox_mediapipe(
    frame: np.ndarray,
) -> Tuple[int, int, int, int] | None:
    """Return a tight mouth bbox from MediaPipe Face Mesh lip landmarks."""
    if _MP_FACE_MESH is None:
        return None

    h, w = frame.shape[:2]
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = _MP_FACE_MESH.process(rgb)
    if not results.multi_face_landmarks:
        return None

    landmarks = results.multi_face_landmarks[0].landmark
    xs = [landmarks[i].x * w for i in _OUTER_LIP_INDICES]
    ys = [landmarks[i].y * h for i in _OUTER_LIP_INDICES]

    margin_x = (max(xs) - min(xs)) * 0.25
    margin_y = (max(ys) - min(ys)) * 0.35

    x1 = int(max(0, min(xs) - margin_x))
    y1 = int(max(0, min(ys) - margin_y))
    x2 = int(min(w, max(xs) + margin_x))
    y2 = int(min(h, max(ys) + margin_y))

    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2


def _detect_mouth_bbox(
    frame: np.ndarray,
) -> Tuple[int, int, int, int] | None:
    """Best-effort mouth bbox: MediaPipe first, Haar heuristic fallback."""
    det = _detect_mouth_bbox_mediapipe(frame)
    if det is not None:
        return det
    face = _detect_face_haar(frame)
    if face is None:
        return None
    return _haar_to_mouth_bbox(face)


def get_landmark_and_bbox(
    img_list: List[str], upperbondrange: int = 0
) -> Tuple[List, List[np.ndarray]]:
    """Detect faces and derive a mouth-focused bounding box."""
    frames = read_imgs(img_list)
    coords_list: List = []
    average_range_minus: List[int] = []
    average_range_plus: List[int] = []
    coord_placeholder = (0.0, 0.0, 0.0, 0.0)

    if upperbondrange != 0:
        print(
            "get key_landmark and face bounding boxes with the bbox_shift:",
            upperbondrange,
        )
    else:
        print("get key_landmark and face bounding boxes with the default value")

    fallback_count = 0
    for frame in tqdm(frames):
        det = _detect_mouth_bbox(frame)
        if det is None:
            coords_list.append(coord_placeholder)
            continue
        x1, y1, x2, y2 = det

        # Shift the mouth box up/down to fine-tune alignment.
        if upperbondrange != 0:
            y1 = y1 + upperbondrange
            y2 = y2 + upperbondrange

        # Clamp to frame bounds.
        x1 = max(0, x1)
        y1 = max(0, y1)
        x2 = min(frame.shape[1], x2)
        y2 = min(frame.shape[0], y2)

        if y2 - y1 <= 0 or x2 - x1 <= 0:
            coords_list.append(coord_placeholder)
            print("error bbox:", (x1, y1, x2, y2))
        else:
            coords_list.append((x1, y1, x2, y2))
            h = y2 - y1
            average_range_minus.append(int(h * 0.25))
            average_range_plus.append(int(h * 0.25))

    if fallback_count:
        print(f"[preprocessing] MediaPipe failed on {fallback_count} frames; used Haar fallback")

    print(
        "********************************************bbox_shift parameter adjustment**********************************************************"
    )
    if average_range_minus and average_range_plus:
        print(
            f"Total frame:「{len(frames)}」 Manually adjust range : [ -{int(sum(average_range_minus) / len(average_range_minus))}~{int(sum(average_range_plus) / len(average_range_plus))} ] , the current value: {upperbondrange}"
        )
    print(
        "*************************************************************************************************************************************"
    )
    return coords_list, frames


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m src._preprocessing_patch <image_dir>")
        sys.exit(1)
    img_dir = Path(sys.argv[1])
    imgs = sorted(glob.glob(str(img_dir / "*.png")))
    if not imgs:
        imgs = sorted(glob.glob(str(img_dir / "*.jpg")))
    coords, frames = get_landmark_and_bbox(imgs, upperbondrange=0)
    print("Detected coords sample:", coords[:5])
