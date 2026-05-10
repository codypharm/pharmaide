from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.errors import RequestIdMiddleware, global_exception_handler
from app.logging_setup import configure_logging

VERSION = "0.1.0"

configure_logging(get_settings().log_mode)

app = FastAPI(title="PharmAide API", version=VERSION)

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
