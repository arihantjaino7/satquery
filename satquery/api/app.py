"""FastAPI app: an upload+SSE endpoint that drives the Step 5 agent pipeline
and streams each `TraceEntry` to the browser as its node completes.

Presentation/transport only, same spirit as `satquery.cli` — all real logic
lives in `satquery.agent.*`; this module saves the upload, drives
`run_streaming`, and formats each step as an SSE event.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from satquery.agent.graph import run_streaming
from satquery.api.render import array_to_png_data_uri, change_mask_overlay_png
from satquery.models.stub import CHANGE_DIFF_THRESHOLD
from satquery.serialize import to_jsonable

app = FastAPI(title="SatQuery AI API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_UPLOAD_ROOT = Path(tempfile.gettempdir()) / "satquery-uploads"


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/ask")
async def ask(question: str = Form(...), images: list[UploadFile] = File(...)) -> StreamingResponse:
    if not (1 <= len(images) <= 2):
        async def bad_request() -> AsyncIterator[str]:
            yield _sse("error", {"message": f"expected 1-2 images, got {len(images)}"})
            yield _sse("end", {})

        return StreamingResponse(bad_request(), media_type="text/event-stream")

    run_dir = _UPLOAD_ROOT / uuid.uuid4().hex
    run_dir.mkdir(parents=True, exist_ok=True)
    saved_paths: list[Path] = []
    for upload in images:
        dest = run_dir / (upload.filename or "image.tif")
        dest.write_bytes(await upload.read())
        saved_paths.append(dest)

    async def event_stream() -> AsyncIterator[str]:
        state = None
        try:
            for state, entry in run_streaming(question, saved_paths):
                payload = to_jsonable(entry)

                if entry.node == "preprocess" and state.display_arrays:
                    payload["data"]["previews"] = [
                        {"index": i, "modality": mod, "png": array_to_png_data_uri(arr)}
                        for i, (arr, mod) in enumerate(zip(state.display_arrays, state.image_modalities))
                    ]

                if (
                    entry.node == "execute"
                    and state.task == "change_detection"
                    and state.display_arrays
                    and len(state.display_arrays) == 2
                ):
                    payload["data"]["mask_overlay_png"] = change_mask_overlay_png(
                        state.display_arrays[0], state.display_arrays[1], CHANGE_DIFF_THRESHOLD,
                    )

                yield _sse("trace", payload)

            yield _sse("final", {
                "outcome": state.outcome,
                "task": state.task,
                "answer": state.answer,
                "confidence": state.confidence,
                "plan": {"chosen": state.plan.chosen} if state.plan is not None else None,
            })
        except Exception as exc:  # noqa: BLE001 - surface any pipeline failure to the client, not a hung stream
            yield _sse("error", {"message": str(exc)})
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)
        yield _sse("end", {})

    return StreamingResponse(event_stream(), media_type="text/event-stream")
