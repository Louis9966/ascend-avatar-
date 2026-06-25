"""Test the live WebUI API with a 5s MyVideo_1 clip after restart."""
from __future__ import annotations

import sys
import time
from pathlib import Path

import httpx

VIDEO_PATH = Path("/ascend-avatar/sample/MyVideo_1_test_5s.mp4")
TEXT = "波坡摸佛吃葡萄不吐葡萄皮"
BASE = "http://127.0.0.1:8188"


def main():
    with httpx.Client(timeout=60.0) as client:
        # Upload
        print("[API-TEST] Uploading video...")
        with VIDEO_PATH.open("rb") as f:
            r = client.post(
                f"{BASE}/api/upload",
                files={"file": (VIDEO_PATH.name, f, "video/mp4")},
            )
        r.raise_for_status()
        upload_id = r.json()["upload_id"]
        print(f"[API-TEST] upload_id={upload_id}")

        # Wait for ready
        for i in range(600):
            r = client.get(f"{BASE}/api/upload/status/{upload_id}")
            st = r.json()
            if st.get("status") == "ready":
                print(f"[API-TEST] Avatar ready after {i*2}s")
                break
            if st.get("status") == "error":
                raise RuntimeError(f"Upload/prepare failed: {st}")
            if i % 15 == 0:
                print(f"[API-TEST] {time.strftime('%H:%M:%S')} status={st.get('status')} progress={st.get('progress')}")
            time.sleep(2.0)
        else:
            raise RuntimeError("Timeout waiting for avatar ready")

        # Generate
        print(f"[API-TEST] Submitting generation: {TEXT!r}")
        r = client.post(
            f"{BASE}/api/generate",
            data={"upload_id": upload_id, "text": TEXT},
        )
        r.raise_for_status()
        job_id = r.json()["job_id"]
        print(f"[API-TEST] job_id={job_id}")

        # Wait for done
        for i in range(600):
            r = client.get(f"{BASE}/api/generate/status/{job_id}")
            st = r.json()
            if st.get("status") == "done":
                print(f"[API-TEST] Job done after {i*2}s")
                break
            if st.get("status") == "error":
                raise RuntimeError(f"Job failed: {st}")
            if i % 15 == 0:
                print(f"[API-TEST] {time.strftime('%H:%M:%S')} status={st.get('status')} progress={st.get('progress')}")
            time.sleep(2.0)
        else:
            raise RuntimeError("Timeout waiting for job")

        # Download and check
        out_path = Path("/tmp/api_test_output.mp4")
        with client.stream("GET", f"{BASE}/api/download/{job_id}") as resp:
            resp.raise_for_status()
            out_path.write_bytes(resp.read())
        print(f"[API-TEST] Downloaded to {out_path}")

        import subprocess
        probe = subprocess.run(
            [
                "/ascend-avatar/bin/ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-show_entries", "stream=codec_type,duration",
                "-of", "default=noprint_wrappers=1",
                str(out_path),
            ],
            capture_output=True,
            text=True,
        )
        print("[API-TEST] ffprobe:\n" + probe.stdout)

        sys.path.insert(0, "/ascend-avatar/scripts")
        from ab_mouth_sharpness import _video_sharpness
        sharp, face, total = _video_sharpness(out_path)
        print(f"[API-TEST] sharpness={sharp:.2f} face_frames={face}/{total}")
        return out_path


if __name__ == "__main__":
    main()
