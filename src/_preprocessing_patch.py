"""Replacement for musetalk.utils.preprocessing that avoids mmpose/mmcv.

Uses OpenCV Haar face detector to derive a mouth-focused bounding box.
This is much faster on ARM than building mmpose/mmcv and avoids the large
SFD/2DFAN downloads required by face_alignment.
"""
from __future__ import annotations

import glob
import os
from pathlib import Path
from typing import List, Tuple

import cv2
import numpy as np
from tqdm import tqdm

# Use the Haar cascade bundled with opencv-python
_FACE_CASCADE = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
)


def read_imgs(img_list: List[str]) -> List[np.ndarray]:
    frames = []
    print("reading images...")
    for img_path in tqdm(img_list):
        frame = cv2.imread(img_path)
        frames.append(frame)
    return frames


def _detect_face(frame: np.ndarray) -> Tuple[int, int, int, int] | None:
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
    return int(x), int(y), int(w), int(h)


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
        print("get key_landmark and face bounding boxes with the bbox_shift:", upperbondrange)
    else:
        print("get key_landmark and face bounding boxes with the default value")

    for frame in tqdm(frames):
        det = _detect_face(frame)
        if det is None:
            coords_list.append(coord_placeholder)
            continue
        x, y, w, h = det
        # Focus on the lower face (mouth + chin), roughly 60% of face height.
        y1 = int(y + h * 0.35)
        y2 = y + h
        x1 = x
        x2 = x + w

        if upperbondrange != 0:
            y1 = max(0, y1 + upperbondrange)

        if y2 - y1 <= 0 or x2 - x1 <= 0 or x1 < 0 or y1 < 0:
            coords_list.append(coord_placeholder)
            print("error bbox:", (x1, y1, x2, y2))
        else:
            coords_list.append((x1, y1, x2, y2))
            average_range_minus.append(int(h * 0.25))
            average_range_plus.append(int(h * 0.25))

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
