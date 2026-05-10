"""structlog wiring with two renderers.

console = colored, key=value, scannable in a terminal during dev.
json    = structured JSON, what GCP Cloud Logging auto-parses into queryable
          fields once we deploy. Same call sites, different output shape.
"""

from typing import Literal

import structlog
from structlog.types import Processor

LogMode = Literal["console", "json"]


def configure_logging(mode: LogMode) -> None:
    # Processor order matters. merge_contextvars must run before any renderer
    # so that bound request_id / thread_id end up in the rendered record.
    # format_exc_info must run before the renderer so exceptions become
    # serialisable strings rather than live traceback objects.
    shared: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    renderer: Processor = (
        structlog.dev.ConsoleRenderer(colors=True)
        if mode == "console"
        else structlog.processors.JSONRenderer()
    )

    structlog.configure(
        processors=[*shared, renderer],
        # 20 = INFO. Drop debug logs in prod-ish modes; flip if you need them.
        wrapper_class=structlog.make_filtering_bound_logger(20),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        # Bound loggers are immutable once cached; safe across the request
        # lifecycle and avoids re-running the processor chain setup per call.
        cache_logger_on_first_use=True,
    )
