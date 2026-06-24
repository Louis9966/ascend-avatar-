"""Talking-head generation engine wrapping MuseTalk."""
from __future__ import annotations

import glob
import os
import pickle
import shutil
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Iterator, List, Tuple

import cv2
import numpy as np
import torch
from transformers import WhisperModel

# Ensure the checked-out MuseTalk repo is importable
THG_ROOT = Path(os.environ.get("THG_DIR", "/ascend-avatar/thg"))
if str(THG_ROOT) not in sys.path:
    sys.path.insert(0, str(THG_ROOT))

# Inject a face-alignment based replacement for musetalk.utils.preprocessing.
# This avoids building mmcv/mmpose from source on ARM.
from src import _preprocessing_patch  # noqa: E402
sys.modules["musetalk.utils.preprocessing"] = _preprocessing_patch

from musetalk.utils.audio_processor import AudioProcessor  # noqa: E402
from musetalk.utils.blending import get_image_blending, get_image_prepare_material  # noqa: E402
from musetalk.utils.face_parsing import FaceParsing  # noqa: E402
from musetalk.utils.preprocessing import get_landmark_and_bbox, read_imgs  # noqa: E402
from musetalk.utils.utils import datagen, load_all_model  # noqa: E402


class MuseTalkAvatar:
    """Prepare and render a MuseTalk avatar."""

    def __init__(
        self,
        avatar_id: str,
        video_path: Path,
        model_dir: Path,
        whisper_dir: Path,
        device: torch.device,
        batch_size: int = 8,
        fps: int = 25,
        bbox_shift: int = 0,
        version: str = "v15",
        result_dir: Path = Path("/ascend-avatar/output"),
        extra_margin: int = 10,
        parsing_mode: str = "jaw",
        left_cheek_width: int = 90,
        right_cheek_width: int = 90,
        vae_type: str = "sd-vae",
        upper_boundary_ratio: float = 0.5,
        expand: float = 1.5,
        blur_ratio: float = 0.03,
        render_interpolation: str = "lanczos4",
        ffmpeg_crf: int = 18,
        ffmpeg_preset: str = "medium",
        prepare_resolution: str = "",
    ):
        self.avatar_id = avatar_id
        self.video_path = Path(video_path)
        self.model_dir = Path(model_dir)
        self.whisper_dir = Path(whisper_dir)
        self.device = device
        self.batch_size = batch_size
        self.fps = fps
        self.bbox_shift = bbox_shift
        self.version = version
        self.extra_margin = extra_margin
        self.parsing_mode = parsing_mode
        self.left_cheek_width = left_cheek_width
        self.right_cheek_width = right_cheek_width
        self.muse_vae_type = vae_type
        self.upper_boundary_ratio = upper_boundary_ratio
        self.expand = expand
        self.blur_ratio = blur_ratio
        self.render_interpolation = render_interpolation
        self.ffmpeg_crf = ffmpeg_crf
        self.ffmpeg_preset = ffmpeg_preset
        self.prepare_resolution = prepare_resolution.strip().lower()

        self.interpolation_map = {
            "lanczos4": cv2.INTER_LANCZOS4,
            "cubic": cv2.INTER_CUBIC,
            "linear": cv2.INTER_LINEAR,
            "area": cv2.INTER_AREA,
            "nearest": cv2.INTER_NEAREST,
        }

        if version == "v15":
            self.base_path = result_dir / version / "avatars" / avatar_id
        else:
            self.base_path = result_dir / "avatars" / avatar_id

        self.full_imgs_path = self.base_path / "full_imgs"
        self.coords_path = self.base_path / "coords.pkl"
        self.latents_out_path = self.base_path / "latents.pt"
        self.video_out_path = self.base_path / "vid_output"
        self.mask_out_path = self.base_path / "mask"
        self.mask_coords_path = self.base_path / "mask_coords.pkl"
        self.avatar_info_path = self.base_path / "avator_info.json"

        self._models_loaded = False
        self.vae = None
        self.unet = None
        self.pe = None
        self.audio_processor = None
        self.whisper = None
        self.weight_dtype = None
        self.timesteps = None
        self.fp = None

        self.frame_list_cycle: List[np.ndarray] = []
        self.coord_list_cycle: List[Tuple[int, int, int, int]] = []
        self.mask_list_cycle: List[np.ndarray] = []
        self.mask_coords_list_cycle: List = []
        self.input_latent_list_cycle: List[torch.Tensor] = []

    def load_models(self) -> None:
        """Load VAE, UNet, Whisper, face parser once."""
        if self._models_loaded:
            return
        print("[THG] Loading MuseTalk models...")
        t0 = time.time()
        if self.version == "v15":
            unet_config = self.model_dir / "musetalkV15" / "musetalk.json"
            unet_path = self.model_dir / "musetalkV15" / "unet.pth"
        else:
            unet_config = self.model_dir / "musetalk" / "musetalk.json"
            unet_path = self.model_dir / "musetalk" / "pytorch_model.bin"

        self.vae, self.unet, self.pe = load_all_model(
            unet_model_path=str(unet_path),
            vae_type=str(self.model_dir / self.muse_vae_type),
            unet_config=str(unet_config),
            device=self.device,
        )
        self.timesteps = torch.tensor([0], device=self.device)
        # NPU supports half precision and benefits from it; CPU conv2d does not.
        if self.device.type == "npu":
            self.pe = self.pe.half().to(self.device)
            self.vae.vae = self.vae.vae.half().to(self.device)
            self.unet.model = self.unet.model.half().to(self.device)
        else:
            self.pe = self.pe.to(self.device)
            self.vae.vae = self.vae.vae.to(self.device)
            self.unet.model = self.unet.model.to(self.device)
        self.weight_dtype = self.unet.model.dtype

        self.audio_processor = AudioProcessor(feature_extractor_path=str(self.whisper_dir))
        self.whisper = WhisperModel.from_pretrained(str(self.whisper_dir))
        self.whisper = self.whisper.to(device=self.device, dtype=self.weight_dtype).eval()
        self.whisper.requires_grad_(False)

        if self.version == "v15":
            self.fp = FaceParsing(
                left_cheek_width=self.left_cheek_width,
                right_cheek_width=self.right_cheek_width,
            )
        else:
            self.fp = FaceParsing()

        self._models_loaded = True
        print(f"[THG] Models loaded in {time.time() - t0:.2f}s")

    def _video_to_imgs(self, src: Path, dst: Path) -> None:
        dst.mkdir(parents=True, exist_ok=True)
        cap = cv2.VideoCapture(str(src))
        count = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            cv2.imwrite(str(dst / f"{count:08d}.png"), frame)
            count += 1
        cap.release()
        if count == 0:
            raise RuntimeError(f"No frames read from {src}")
        print(f"[THG] Extracted {count} frames from base video")

    def _preprocess_input_video(self, src: Path) -> Path:
        """Resize/crop the input video to a target square resolution before prepare.

        This reduces the upsampling blur that occurs when MuseTalk's 256x256
        generated mouth region is pasted back onto a much larger original frame.
        The target format is 'WxH' (e.g. '512x512'); a center square crop is
        applied first to preserve aspect ratio.
        """
        target = self.prepare_resolution
        if "x" not in target:
            print(f"[THG] prepare_resolution '{target}' is not in WxH format, skipping")
            return src
        width, height = target.split("x")
        width, height = int(width), int(height)
        dst = self.base_path / f"prepare_{target}.mp4"
        dst.parent.mkdir(parents=True, exist_ok=True)
        print(f"[THG] Preprocessing input to {target} (center-crop square) -> {dst}")
        cmd = [
            "ffmpeg",
            "-y",
            "-loglevel", "warning",
            "-i", str(src),
            "-vf",
            f"crop=min(iw\\,ih):min(iw\\,ih):(iw-min(iw\\,ih))/2:(ih-min(iw\\,ih))/2,scale={width}:{height}:flags=lanczos",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-r", str(self.fps),
            "-an",
            str(dst),
        ]
        ret = subprocess.run(cmd, capture_output=True, text=True).returncode
        if ret != 0 or not dst.exists():
            raise RuntimeError(f"Failed to preprocess input video to {target}")
        return dst

    def _assets_ready(self) -> bool:
        return (
            self.latents_out_path.exists()
            and self.coords_path.exists()
            and self.mask_coords_path.exists()
            and self.full_imgs_path.exists()
            and any(self.full_imgs_path.glob("*.png"))
        )

    def prepare(self, force: bool = False) -> None:
        """Precompute avatar latents, masks and coords."""
        # MuseTalk internal paths are relative to the repository root.
        original_cwd = os.getcwd()
        os.chdir(str(THG_ROOT))
        try:
            self.load_models()
            if self.base_path.exists() and not force and self._assets_ready():
                print(f"[THG] Loading existing avatar assets from {self.base_path}")
                self._load_assets()
                return

            if self.base_path.exists():
                shutil.rmtree(self.base_path)

            self.base_path.mkdir(parents=True, exist_ok=True)
            self.full_imgs_path.mkdir(parents=True, exist_ok=True)
            self.video_out_path.mkdir(parents=True, exist_ok=True)
            self.mask_out_path.mkdir(parents=True, exist_ok=True)

            print(f"[THG] Preparing avatar {self.avatar_id} from {self.video_path}")

            src_video = self.video_path
            if self.prepare_resolution:
                src_video = self._preprocess_input_video(self.video_path)

            self._video_to_imgs(src_video, self.full_imgs_path)
            input_img_list = sorted(
                glob.glob(str(self.full_imgs_path / "*.[jpJP][pnPN]*[gG]"))
            )

            print("[THG] Extracting landmarks and bounding boxes...")
            coord_list, frame_list = get_landmark_and_bbox(input_img_list, self.bbox_shift)

            input_latent_list = []
            coord_placeholder = (0.0, 0.0, 0.0, 0.0)
            for idx, (bbox, frame) in enumerate(zip(coord_list, frame_list)):
                if bbox == coord_placeholder:
                    continue
                x1, y1, x2, y2 = bbox
                if self.version == "v15":
                    y2 = min(y2 + self.extra_margin, frame.shape[0])
                    coord_list[idx] = [x1, y1, x2, y2]
                crop = frame[y1:y2, x1:x2]
                crop = cv2.resize(crop, (256, 256), interpolation=cv2.INTER_LANCZOS4)
                latent = self.vae.get_latents_for_unet(crop)
                input_latent_list.append(latent)

            # Seamless loop by palindroming
            self.frame_list_cycle = frame_list + frame_list[::-1]
            self.coord_list_cycle = coord_list + coord_list[::-1]
            self.input_latent_list_cycle = input_latent_list + input_latent_list[::-1]
            self.mask_coords_list_cycle = []
            self.mask_list_cycle = []

            # Avatar base video is usually static/looping; cache masks by frame content
            # to avoid running face parsing hundreds of times on CPU.
            mask_cache: dict[int, tuple] = {}
            for i, frame in enumerate(self.frame_list_cycle):
                cv2.imwrite(str(self.full_imgs_path / f"{i:08d}.png"), frame)
                x1, y1, x2, y2 = self.coord_list_cycle[i]
                cache_key = hash(frame.tobytes())
                if cache_key in mask_cache:
                    mask, crop_box = mask_cache[cache_key]
                else:
                    mode = self.parsing_mode if self.version == "v15" else "raw"
                    mask, crop_box = get_image_prepare_material(
                        frame, [x1, y1, x2, y2], fp=self.fp, mode=mode,
                        upper_boundary_ratio=self.upper_boundary_ratio,
                        expand=self.expand,
                        blur_ratio=self.blur_ratio,
                    )
                    mask_cache[cache_key] = (mask, crop_box)
                cv2.imwrite(str(self.mask_out_path / f"{i:08d}.png"), mask)
                self.mask_coords_list_cycle.append(crop_box)
                self.mask_list_cycle.append(mask)

            with open(self.mask_coords_path, "wb") as f:
                pickle.dump(self.mask_coords_list_cycle, f)
            with open(self.coords_path, "wb") as f:
                pickle.dump(self.coord_list_cycle, f)
            torch.save(self.input_latent_list_cycle, self.latents_out_path)
            print(f"[THG] Avatar prepared and cached at {self.base_path}")
        finally:
            os.chdir(original_cwd)

    def _load_assets(self) -> None:
        self.input_latent_list_cycle = torch.load(self.latents_out_path)
        with open(self.coords_path, "rb") as f:
            self.coord_list_cycle = pickle.load(f)
        input_img_list = sorted(
            glob.glob(str(self.full_imgs_path / "*.[jpJP][pnPN]*[gG]"))
        )
        self.frame_list_cycle = read_imgs(input_img_list)
        with open(self.mask_coords_path, "rb") as f:
            self.mask_coords_list_cycle = pickle.load(f)
        input_mask_list = sorted(
            glob.glob(str(self.mask_out_path / "*.[jpJP][pnPN]*[gG]"))
        )
        self.mask_list_cycle = read_imgs(input_mask_list)

    @torch.no_grad()
    def infer(self, audio_path: Path) -> Iterator[np.ndarray]:
        """Yield rendered BGR frames for the given audio file."""
        self.load_models()
        audio_path = Path(audio_path)
        if not audio_path.exists():
            raise FileNotFoundError(audio_path)

        t0 = time.time()
        whisper_input_features, librosa_length = self.audio_processor.get_audio_feature(
            str(audio_path), weight_dtype=self.weight_dtype
        )
        whisper_chunks = self.audio_processor.get_whisper_chunk(
            whisper_input_features,
            self.device,
            self.weight_dtype,
            self.whisper,
            librosa_length,
            fps=self.fps,
            audio_padding_length_left=2,
            audio_padding_length_right=2,
        )
        print(f"[THG] Audio feature extraction took {time.time() - t0:.2f}s")

        video_num = len(whisper_chunks)
        gen = datagen(
            whisper_chunks,
            self.input_latent_list_cycle,
            batch_size=self.batch_size,
            device=str(self.device),
        )

        idx = 0
        for whisper_batch, latent_batch in gen:
            audio_feature_batch = self.pe(whisper_batch.to(self.device))
            latent_batch = latent_batch.to(device=self.device, dtype=self.unet.model.dtype)
            pred_latents = self.unet.model(
                latent_batch,
                self.timesteps,
                encoder_hidden_states=audio_feature_batch,
            ).sample
            pred_latents = pred_latents.to(device=self.device, dtype=self.vae.vae.dtype)
            recon = self.vae.decode_latents(pred_latents)

            for res_frame in recon:
                bbox = self.coord_list_cycle[idx % len(self.coord_list_cycle)]
                ori_frame = np.copy(self.frame_list_cycle[idx % len(self.frame_list_cycle)])
                x1, y1, x2, y2 = bbox
                try:
                    interp = self.interpolation_map.get(self.render_interpolation, cv2.INTER_LANCZOS4)
                    res_frame = cv2.resize(
                        res_frame.astype(np.uint8),
                        (x2 - x1, y2 - y1),
                        interpolation=interp,
                    )
                except Exception as e:
                    print(f"[THG] Resize error at frame {idx}: {e}")
                    idx += 1
                    continue
                mask = self.mask_list_cycle[idx % len(self.mask_list_cycle)]
                mask_crop_box = self.mask_coords_list_cycle[idx % len(self.mask_coords_list_cycle)]
                combine = get_image_blending(ori_frame, res_frame, bbox, mask, mask_crop_box)
                yield combine
                idx += 1

    def render_to_video(
        self,
        audio_path: Path,
        output_path: Path,
    ) -> Path:
        """Render all frames and mux with audio to an MP4 file."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_dir = output_path.parent / "tmp_frames"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        for f in tmp_dir.glob("*.png"):
            f.unlink()

        for i, frame in enumerate(self.infer(audio_path)):
            cv2.imwrite(str(tmp_dir / f"{i:08d}.png"), frame)

        cmd = [
            "ffmpeg",
            "-y",
            "-loglevel",
            "warning",
            "-r",
            str(self.fps),
            "-i",
            str(tmp_dir / "%08d.png"),
            "-i",
            str(audio_path),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-crf",
            str(self.ffmpeg_crf),
            "-preset",
            self.ffmpeg_preset,
            "-c:a",
            "aac",
            "-ar",
            "16000",
            "-ac",
            "1",
            str(output_path),
        ]
        os.system(" ".join(cmd))
        shutil.rmtree(tmp_dir)
        return output_path


if __name__ == "__main__":
    import asyncio

    async def _main():
        from src.tts_engine import EdgeTTSEngine

        device = torch.device("npu:0")
        avatar = MuseTalkAvatar(
            avatar_id="default",
            video_path=Path("/ascend-avatar/avatars/default_base.mp4"),
            model_dir=Path("/ascend-avatar/thg/models"),
            whisper_dir=Path("/ascend-avatar/thg/models/whisper_hf"),
            device=device,
            batch_size=8,
        )
        avatar.prepare()
        tts = EdgeTTSEngine(voice="zh-CN-XiaoxiaoNeural")
        wav = await tts.synthesize("你好，这是数字人测试。", "/tmp/thg_test.wav")
        out = avatar.render_to_video(Path(wav), Path("/tmp/thg_test.mp4"))
        print("saved", out)

    asyncio.run(_main())
