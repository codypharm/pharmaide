import functools
import inspect
from collections.abc import Awaitable, Callable, Mapping
from typing import Protocol, cast
from uuid import uuid4

import structlog
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

REQUEST_ID_HEADER = "X-Request-ID"


class AsyncInvokable(Protocol):
    """Minimal interface a LangGraph compiled graph (or test stub) satisfies."""

    async def ainvoke(
        self,
        input_state: Mapping[str, object],
        config: Mapping[str, object] | None = ...,
    ) -> object: ...


async def run_graph(
    graph: AsyncInvokable,
    *,
    thread_id: str,
    input_state: Mapping[str, object],
) -> object:
    """Invoke a LangGraph thread with structured logging around the call.

    Binds thread_id to structlog contextvars for the duration so that any
    log line emitted inside the graph carries the thread_id automatically.
    """
    log = structlog.get_logger(__name__)
    with structlog.contextvars.bound_contextvars(thread_id=thread_id):
        try:
            result = await graph.ainvoke(
                input_state,
                config={"configurable": {"thread_id": thread_id}},
            )
        except Exception:
            log.error("graph_failed", thread_id=thread_id, exc_info=True)
            raise
        log.info("graph_invoked", thread_id=thread_id)
        return result


def logged[**P, R](fn: Callable[P, R]) -> Callable[P, R]:
    """Wrap fn so that any exception is logged with full context, then re-raised.

    Use sparingly — only on functions where failure context (args, bound
    contextvars) materially aids debugging. Pure helpers stay undecorated.
    """
    log = structlog.get_logger(fn.__module__)

    if inspect.iscoroutinefunction(fn):

        @functools.wraps(fn)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            try:
                return cast("R", await fn(*args, **kwargs))
            except Exception:
                log.error("function_failed", function=fn.__name__, exc_info=True)
                raise

        return cast("Callable[P, R]", async_wrapper)

    @functools.wraps(fn)
    def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return fn(*args, **kwargs)
        except Exception:
            log.error("function_failed", function=fn.__name__, exc_info=True)
            raise

    return sync_wrapper


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid4().hex
        request.state.request_id = request_id
        with structlog.contextvars.bound_contextvars(request_id=request_id):
            response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response


async def global_exception_handler(request: Request, exc: Exception) -> Response:
    """Catch any unhandled exception, log with full context, return sanitised 500.

    Body contains only an opaque error code and the request_id breadcrumb.
    No stack, no exception class name, no internal field names — those go
    to the structured log, not the wire.
    """
    log = structlog.get_logger(__name__)
    request_id = getattr(request.state, "request_id", "")
    log.error(
        "unhandled_exception",
        path=request.url.path,
        method=request.method,
        request_id=request_id,
        exc_info=exc,
    )
    return JSONResponse(
        status_code=500,
        content={"error": "internal_error", "request_id": request_id},
    )
