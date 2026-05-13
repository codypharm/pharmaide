"""FastAPI application factory and route definitions.

create_app() takes a Settings instance so tests can flip the debug-routes
flag without touching env vars or the lru_cached get_settings() singleton.
The module-level `app` is what `uvicorn app.main:app` imports — it uses the
real Settings parsed from the environment.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.api.internal import router as internal_router
from app.api.knowledge import router as knowledge_router
from app.api.prescriptions import router as prescriptions_router
from app.api.treatments import router as treatments_router
from app.config import Settings, get_settings
from app.errors import RequestIdMiddleware, global_exception_handler, run_graph
from app.graph import open_counter_graph
from app.logging_setup import configure_logging
from app.services import task_runner

VERSION = "0.1.0"


class DebugGraphRequest(BaseModel):
    thread_id: str = Field(min_length=1)


class DebugGraphResponse(BaseModel):
    turn: int


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Drain in-process background tasks during application shutdown.

    Analysis work is allowed to outlive the request that scheduled it, but
    shutdown should wait for those tasks so audit/status writes are not cut off.
    """
    try:
        yield
    finally:
        await task_runner.drain()


def create_app(settings: Settings) -> FastAPI:
    configure_logging(settings.log_mode)

    app = FastAPI(title="PharmAide API", version=VERSION, lifespan=lifespan)

    # Middleware order: RequestIdMiddleware is added last so it runs first
    # (Starlette stacks middleware LIFO). The request_id is bound before any
    # downstream handler runs, so every log line in the request inherits it.
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_exception_handler(Exception, global_exception_handler)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": VERSION}

    app.include_router(treatments_router, tags=["treatments"])
    app.include_router(prescriptions_router, tags=["prescriptions"])
    app.include_router(knowledge_router, tags=["knowledge"])
    app.include_router(internal_router, tags=["internal"])

    # Mount-time gating, not request-time. When the flag is False the route
    # literally does not exist — no 403, no soft denial, no OpenAPI entry.
    # Defence in depth against future routes that might leak more than a turn
    # counter inheriting this same gate.
    if settings.debug_routes_enabled:

        @app.post("/debug/graph", response_model=DebugGraphResponse)
        async def debug_graph(body: DebugGraphRequest) -> DebugGraphResponse:
            async with open_counter_graph(settings.checkpoint_db_path) as graph:
                result = await run_graph(graph, thread_id=body.thread_id, input_state={})
            state = cast("dict[str, int]", result)
            return DebugGraphResponse(turn=state["turn"])

    return app


app = create_app(get_settings())
