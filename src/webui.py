"""Gradio Web UI for ascend-avatar.

The Gradio app is mounted under a FastAPI application so we can expose a
Server-Sent Events (SSE) endpoint for the real-time streaming pipeline.
Gradio's own queue/async-generator path is avoided because of an environment
specific bug where the queue lock becomes None in the server thread.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import AsyncIterator, Optional

# Preload scikit-learn before torch/torch_npu to avoid "cannot allocate memory
# in static TLS block" when paddlespeech later imports sklearn.metrics.
import sklearn  # noqa: F401

import gradio as gr
import torch
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.routing import Mount, Route

from src.avatar_manager import AvatarManager, AvatarValidationError
from src.config import Config, load_config
from src.pipeline import ConversationPipeline
from src.tts_engine import VOICE_OPTIONS
from src.video_gen_pipeline import VideoGenPipeline


# ---------------------------------------------------------------------------
# Shared pipeline / managers (prewarmed once at startup)
# ---------------------------------------------------------------------------
_pipeline: Optional[ConversationPipeline] = None
_avatar_manager: Optional[AvatarManager] = None
_video_gen_pipeline: Optional[VideoGenPipeline] = None


def set_pipeline(p: ConversationPipeline) -> None:
    global _pipeline
    _pipeline = p


def get_pipeline() -> ConversationPipeline:
    if _pipeline is None:
        raise RuntimeError("Pipeline not initialized – call set_pipeline() first")
    return _pipeline


def set_avatar_manager(m: AvatarManager) -> None:
    global _avatar_manager
    _avatar_manager = m


def get_avatar_manager() -> AvatarManager:
    if _avatar_manager is None:
        raise RuntimeError("AvatarManager not initialized")
    return _avatar_manager


def set_video_gen_pipeline(v: VideoGenPipeline) -> None:
    global _video_gen_pipeline
    _video_gen_pipeline = v


def get_video_gen_pipeline() -> VideoGenPipeline:
    if _video_gen_pipeline is None:
        raise RuntimeError("VideoGenPipeline not initialized")
    return _video_gen_pipeline


# ---------------------------------------------------------------------------
# FastAPI SSE endpoint (existing real-time chat)
# ---------------------------------------------------------------------------

def _format_sse(data: str) -> str:
    return f"data: {data}\n\n"


async def chat_sse(request: Request) -> StreamingResponse:
    params = dict(request.query_params)
    user_text = params.get("text", "").strip()
    voice = params.get("voice", "zh-CN-XiaoxiaoNeural")
    language = params.get("lang", "zh")
    max_tokens = int(params.get("max_tokens", "128"))

    if not user_text:
        return StreamingResponse(
            iter([_format_sse('{"event":"error","payload":{"message":"空输入"}}')]),
            media_type="text/event-stream",
        )

    pipeline = get_pipeline()
    q = await pipeline.run(user_text, voice_id=voice, language=language, max_tokens=max_tokens)

    async def event_stream() -> AsyncIterator[str]:
        try:
            while True:
                event = await asyncio.wait_for(q.get(), timeout=300)
                yield _format_sse(json.dumps({"event": event.event, "payload": event.payload}))
                if event.event in ("done", "error"):
                    break
        except asyncio.TimeoutError:
            yield _format_sse('{"event":"error","payload":{"message":"请求超时"}}')

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Video upload / generation endpoints
# ---------------------------------------------------------------------------

async def upload_video(request: Request) -> JSONResponse:
    """Upload a source video and start MuseTalk avatar preparation."""
    manager = get_avatar_manager()
    try:
        form = await request.form()
        file = form.get("file")
        if file is None:
            return JSONResponse({"error": "缺少 file 字段"}, status_code=400)
        content = await file.read()
        result = await manager.upload_video(content, file.filename or "upload.mp4")
        return JSONResponse({
            "upload_id": result["upload_id"],
            "status": result["status"],
            "message": result.get("message"),
            "progress": result.get("progress"),
        })
    except AvatarValidationError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except Exception as exc:
        return JSONResponse({"error": f"上传失败: {exc}"}, status_code=500)


async def upload_status(request: Request) -> JSONResponse:
    upload_id = request.path_params.get("upload_id", "")
    manager = get_avatar_manager()
    status = manager.get_status(upload_id)
    if status is None:
        return JSONResponse({"error": "upload_id 不存在"}, status_code=404)
    return JSONResponse({
        "upload_id": status["upload_id"],
        "status": status["status"],
        "message": status.get("message"),
        "progress": status.get("progress"),
    })


async def generate_video(request: Request) -> JSONResponse:
    """Submit a text-to-lipsync generation job for a ready avatar."""
    pipeline = get_video_gen_pipeline()
    try:
        form = await request.form()
        upload_id = form.get("upload_id", "")
        text = form.get("text", "")
        spk_id = int(form.get("spk_id", 0) or 0)
        voice_id = form.get("voice_id") or None
    except Exception as exc:
        return JSONResponse({"error": f"表单解析失败: {exc}"}, status_code=400)

    if not text or not text.strip():
        return JSONResponse({"error": "文本不能为空"}, status_code=400)
    try:
        job_id = await pipeline.submit(upload_id, text.strip(), spk_id=spk_id, voice_id=voice_id)
        return JSONResponse({"job_id": job_id, "status": "queued"})
    except Exception as exc:
        return JSONResponse({"error": f"提交失败: {exc}"}, status_code=500)


async def generate_status(request: Request) -> JSONResponse:
    job_id = request.path_params.get("job_id", "")
    pipeline = get_video_gen_pipeline()
    status = pipeline.get_status(job_id)
    if status is None:
        return JSONResponse({"error": "job_id 不存在"}, status_code=404)
    return JSONResponse({
        "job_id": status["job_id"],
        "upload_id": status.get("upload_id"),
        "status": status["status"],
        "message": status.get("message"),
        "progress": status.get("progress"),
        "tts_engine_used": status.get("tts_engine_used"),
        "error": status.get("error"),
    })


async def download_video(request: Request):
    job_id = request.path_params.get("job_id", "")
    pipeline = get_video_gen_pipeline()
    status = pipeline.get_status(job_id)
    if status is None:
        return JSONResponse({"error": "job_id 不存在"}, status_code=404)
    if status.get("status") != "done":
        return JSONResponse({"error": "视频尚未生成完成"}, status_code=400)
    output_path = Path(status["output_path"])
    if not output_path.exists():
        return JSONResponse({"error": "MP4 文件不存在"}, status_code=500)
    return FileResponse(
        output_path,
        media_type="video/mp4",
        filename=f"{job_id}.mp4",
    )


async def list_voices(request: Request) -> JSONResponse:
    """Return voice lists for both edge-tts (chat) and PaddleSpeech (video gen)."""
    manager = get_avatar_manager()
    cfg = load_config()
    try:
        from src.paddlespeech_tts_engine import PaddleSpeechTTSEngine
        ps_engine = PaddleSpeechTTSEngine(
            am=cfg.paddlespeech_am,
            voc=cfg.paddlespeech_voc,
            lang=cfg.paddlespeech_lang,
            spk_id=cfg.paddlespeech_spk_id,
            device=cfg.paddlespeech_device,
        )
        ps_voices = await ps_engine.list_voices()
    except Exception:
        ps_voices = []

    return JSONResponse({
        "edge_tts": [{"id": k, "name": v} for k, v in VOICE_OPTIONS.items()],
        "paddlespeech": ps_voices,
    })


# ---------------------------------------------------------------------------
# Gradio UI (mounted at /gradio for admin/debug)
# ---------------------------------------------------------------------------

def create_ui() -> gr.Blocks:
    with gr.Blocks(title="Ascend Avatar Admin") as demo:
        gr.Markdown("# 🧑‍💼 Ascend Avatar Admin\n\n管理面板。主对话界面在 [/](/)。")
        gr.Markdown("### 状态\nPipeline 已预热，SSE 端点 `/api/chat` 与视频生成接口 `/api/upload`、`/api/generate` 可用。")
    return demo


# ---------------------------------------------------------------------------
# Build FastAPI app
# ---------------------------------------------------------------------------

def build_app(cfg: Config | None = None) -> FastAPI:
    cfg = cfg or load_config()
    cfg.ensure_dirs()

    custom_routes: list = [
        Route("/api/chat", chat_sse),
        Route("/api/upload", upload_video, methods=["POST"]),
        Route("/api/upload/status/{upload_id}", upload_status),
        Route("/api/generate", generate_video, methods=["POST"]),
        Route("/api/generate/status/{job_id}", generate_status),
        Route("/api/download/{job_id}", download_video),
        Route("/api/voices", list_voices),
    ]

    # Gradio mounted at /gradio (must come before the catch-all static mount).
    demo = create_ui()
    from gradio.routes import App as GradioApp
    gradio_app = GradioApp.create_app(demo)
    custom_routes.append(Mount("/gradio", app=gradio_app))

    # Static assets: avatar idle video and other files.
    custom_routes.append(
        Mount("/avatars", app=StaticFiles(directory=str(cfg.avatar_dir)))
    )

    # Main chat UI served from frontend/ (catch-all, must be last).
    frontend_dir = cfg.project_root / "frontend"
    custom_routes.append(
        Mount("/", app=StaticFiles(directory=str(frontend_dir), html=True))
    )

    app = FastAPI(title="Ascend Avatar", routes=custom_routes)
    return app


def main():
    cfg = load_config()
    pipeline = ConversationPipeline(cfg)
    set_pipeline(pipeline)
    print("[WEBUI] Pre-warming NPU compile, this may take ~7-8 minutes...")
    asyncio.run(pipeline.prewarm())
    print("[WEBUI] Pre-warm done, initializing video generation managers...")

    device = torch.device(cfg.ascend_npu_device)
    avatar_manager = AvatarManager(cfg, device)
    video_gen_pipeline = VideoGenPipeline(cfg, avatar_manager)
    set_avatar_manager(avatar_manager)
    set_video_gen_pipeline(video_gen_pipeline)

    app = build_app(cfg)
    import uvicorn

    uvicorn.run(
        app,
        host=cfg.webui_host,
        port=cfg.webui_port,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
