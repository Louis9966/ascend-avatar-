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


# MediaPipe mouth bbox margins relative to the lip span.
# Larger values include more cheek/chin context and usually look more natural;
# smaller values are sharper but may lose jaw-line context.
_MP_MARGIN_X = float(os.environ.get("MEDIAPIPE_MOUTH_MARGIN_X", "0.6"))
_MP_MARGIN_Y = float(os.environ.get("MEDIAPIPE_MOUTH_MARGIN_Y", "0.6"))

# Temporal smoothing window for mouth bboxes (frames).  A small moving average
# removes per-frame jitter without adding visible lag.
_MP_SMOOTH_WINDOW = max(1, int(os.environ.get("MEDIAPIPE_SMOOTHING_WINDOW", "5")))


def _detect_mouth_bbox_mediapipe(
    frame: np.ndarray,
) -> Tuple[int, int, int, int] | None:
    """Return a mouth bbox from MediaPipe Face Mesh lip landmarks."""
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

    margin_x = (max(xs) - min(xs)) * _MP_MARGIN_X
    margin_y = (max(ys) - min(ys)) * _MP_MARGIN_Y

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


def _smooth_bboxes(
    coords: List[Tuple[int, int, int, int]],
    window: int = _MP_SMOOTH_WINDOW,
) -> List[Tuple[int, int, int, int]]:
    """Apply a temporal moving-average to mouth bboxes.

    Invalid / placeholder bboxes (all zeros) are treated as NaN and filled by
    nearest valid neighbour so the crop does not jump on occasional detection
    failures.
    """
    if window <= 1 or len(coords) <= 1:
        return coords

    arr = np.array(coords, dtype=np.float32)
    placeholder = np.array([0.0, 0.0, 0.0, 0.0])
    valid = ~np.all(arr == placeholder, axis=1)
    if not valid.any():
        return coords

    # Fill short invalid gaps with nearest valid value.
    last_valid = np.argmax(valid)
    for i in range(len(arr)):
        if valid[i]:
            last_valid = i
        else:
            arr[i] = arr[last_valid]
    # Backfill leading invalid frames.
    if not valid[0]:
        first_valid = np.argmax(valid)
        arr[:first_valid] = arr[first_valid]

    # Causal + anti-causal smoothing with a small lag-free window.
    # Use a triangular-ish kernel by averaging the current frame with the
    # equally-weighted neighbours inside ``window``.
    half = window // 2
    kernel = np.ones(window, dtype=np.float32) / window
    smoothed = np.zeros_like(arr)
    for d in range(4):
        # Pad by edge values to keep the same length.
        padded = np.pad(arr[:, d], (half, half), mode="edge")
        smoothed[:, d] = np.convolve(padded, kernel, mode="valid")[: len(arr)]
    return [tuple(int(v) for v in row) for row in smoothed]


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
            fallback_count += 1
            coords_list.append(coord_placeholder)
            continue
        x1, y1, x2, y2 = det
        coords_list.append((x1, y1, x2, y2))

    if fallback_count:
        print(f"[preprocessing] MediaPipe failed on {fallback_count} frames; used Haar fallback")

    # Temporal smoothing makes the mouth crop stable across frames.
    coords_list = _smooth_bboxes(coords_list)

    final_coords: List = []
    for frame, bbox in zip(frames, coords_list):
        if bbox == coord_placeholder:
            final_coords.append(coord_placeholder)
            continue
        x1, y1, x2, y2 = bbox

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
            final_coords.append(coord_placeholder)
            print("error bbox:", (x1, y1, x2, y2))
        else:
            final_coords.append((x1, y1, x2, y2))
            h = y2 - y1
            average_range_minus.append(int(h * 0.25))
            average_range_plus.append(int(h * 0.25))

    coords_list = final_coords

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
