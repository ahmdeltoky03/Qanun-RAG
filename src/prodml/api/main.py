"""FastAPI application: /ask, /ask/stream, /health, /metrics."""

from __future__ import annotations

import json
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from prodml import __version__
from prodml.api.schemas import AskRequest, AskResponse, HealthResponse
from prodml.config import Settings, get_settings
from prodml.embeddings import get_embedder
from prodml.llm import get_llm
from prodml.observability import DOCS, LATENCY, REGISTRY, REQUESTS, Tracer, refresh_eval_gauges
from prodml.rag import AskResult, RagPipeline
from prodml.retrieval import Retriever
from prodml.vectorstore import VectorStore

log = logging.getLogger("prodml.api")


def build_pipeline(s: Settings) -> RagPipeline:
    store = VectorStore(s)
    return RagPipeline(s, Retriever(s, store, get_embedder(s)), get_llm(s), Tracer(s))


def _response(r: AskResult) -> AskResponse:
    return AskResponse(**{k: getattr(r, k) for k in AskResponse.model_fields})


def create_app(pipeline: RagPipeline | None = None, settings: Settings | None = None) -> FastAPI:
    s = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.pipeline = pipeline or build_pipeline(s)
        app.state.docs = app.state.pipeline.retriever.store.distinct_articles()
        DOCS.set(app.state.docs)
        log.info("ready: %d articles indexed", app.state.docs)
        yield
        app.state.pipeline.tracer.flush()

    app = FastAPI(title="Egyptian Civil Code Q&A", version=__version__, lifespan=lifespan)

    @app.middleware("http")
    async def timing(request: Request, call_next):
        t0 = time.perf_counter()
        response = await call_next(request)
        if request.url.path in ("/ask", "/ask/stream"):
            LATENCY.observe(time.perf_counter() - t0)
            REQUESTS.labels("ok" if response.status_code < 400 else "error", s.release).inc()
        response.headers["X-Release"] = s.release
        return response

    @app.post("/ask", response_model=AskResponse)
    def ask(req: AskRequest) -> AskResponse:
        return _response(app.state.pipeline.ask(req.question))

    @app.post("/ask/stream")
    def ask_stream(req: AskRequest) -> StreamingResponse:
        def sse():
            for ev in app.state.pipeline.ask_stream(req.question):
                if ev["event"] == "done":
                    yield f"event: done\ndata: {_response(ev['data']).model_dump_json()}\n\n"
                else:
                    yield f"event: {ev['event']}\ndata: {json.dumps({k: v for k, v in ev.items() if k != 'event'}, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            sse(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
        )

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        p: RagPipeline = app.state.pipeline
        n = app.state.docs
        return HealthResponse(
            status="ok" if n > 0 else "degraded",
            documents_indexed=n,
            release=s.release,
            embedding_model=p.retriever.embedder.name,
            llm_model=p.llm.name,
            tracing=p.tracer.enabled,
        )

    @app.get("/metrics")
    def metrics() -> Response:
        refresh_eval_gauges(s.eval_report_path)
        return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)

    return app


def get_app() -> FastAPI:  # uvicorn --factory prodml.api.main:get_app
    return create_app()
