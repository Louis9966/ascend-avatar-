#!/bin/bash
# Full API verification for /data/ascend-avatar/sample/MyVideo_1.mp4
set -e

UPLOAD_ID="49a6c93f7de1f8a0"
LOG="/data/ascend-avatar/output/sample_video_verify.log"
OUT_MP4="/data/ascend-avatar/output/generated/MyVideo_1_verify.mp4"

echo "=== Sample video full-flow verification started at $(date) ===" > "$LOG"
echo "upload_id=$UPLOAD_ID" >> "$LOG"

# Poll upload status
while true; do
  st=$(curl -s "http://127.0.0.1:8188/api/upload/status/$UPLOAD_ID")
  echo "$(date '+%H:%M:%S') upload: $st" >> "$LOG"
  if echo "$st" | grep -q '"status": "ready"'; then
    break
  fi
  if echo "$st" | grep -q '"status": "error"'; then
    echo "Upload failed" >> "$LOG"
    exit 1
  fi
  sleep 10
done

echo "--- Upload ready, submitting generation ---" >> "$LOG"
gen=$(curl -s -X POST \
  -F "upload_id=$UPLOAD_ID" \
  -F "text=你好，这是用 MyVideo_1 做的数字人测试。" \
  -F "spk_id=0" \
  http://127.0.0.1:8188/api/generate)
echo "$(date '+%H:%M:%S') generate response: $gen" >> "$LOG"
JOB_ID=$(echo "$gen" | python3 -c "import sys, json; print(json.load(sys.stdin)['job_id'])")

# Poll generation status
while true; do
  st=$(curl -s "http://127.0.0.1:8188/api/generate/status/$JOB_ID")
  echo "$(date '+%H:%M:%S') generate: $st" >> "$LOG"
  if echo "$st" | grep -q '"status": "done"'; then
    break
  fi
  if echo "$st" | grep -q '"status": "error"'; then
    echo "Generation failed" >> "$LOG"
    exit 1
  fi
  sleep 5
done

# Download
curl -s -o "$OUT_MP4" "http://127.0.0.1:8188/api/download/$JOB_ID"
echo "$(date '+%H:%M:%S') downloaded to $OUT_MP4" >> "$LOG"
ls -lh "$OUT_MP4" >> "$LOG"

# Probe inside container
ffprobe_info=$(docker exec ascend-avatar-backend bash -c "export PATH=/ascend-avatar/bin:/home/HwHiAiUser/.local/bin:/usr/local/python3.9.2/bin:\$PATH; ffprobe -v error -select_streams v:0 -show_entries stream=duration,r_frame_rate,width,height -of json /ascend-avatar/output/generated/MyVideo_1_verify.mp4")
echo "Video info: $ffprobe_info" >> "$LOG"

# Mouth sharpness
python3 << PY >> "$LOG"
import cv2, numpy as np
cap = cv2.VideoCapture('/data/ascend-avatar/output/generated/MyVideo_1_verify.mp4')
total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
print(f'Total frames: {total}')
vals = []
for idx in [int(total * i / 4) for i in range(1, 4)]:
    cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
    ret, frame = cap.read()
    if not ret:
        continue
    h, w = frame.shape[:2]
    roi = frame[int(h*0.55):int(h*0.78), int(w*0.38):int(w*0.62)]
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    vals.append(cv2.Laplacian(gray, cv2.CV_64F).var())
print(f'Mouth Laplacian variance samples: {vals}')
print(f'Mean: {sum(vals)/len(vals):.2f}' if vals else 'no samples')
cap.release()
PY

echo "=== Verification completed at $(date) ===" >> "$LOG"
