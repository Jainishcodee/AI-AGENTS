"""ASGI entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .api import router
from .core.config import get_settings
from .core.logging import get_logger, setup_logging
from .council import Council
from .programs import loader

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings.log_level)

    # Programs are validated here, at boot. A malformed program refuses to let the
    # server start rather than failing halfway through someone's deliberation.
    programs = loader.programs()
    presets = loader.presets()
    log.info(
        "loaded %d modules (%s) and %d presets",
        len(programs),
        ", ".join(sorted(programs)),
        len(presets),
    )

    app.state.council = Council(settings)
    try:
        yield
    finally:
        await app.state.council.aclose()


app = FastAPI(
    title="Cognitive OS",
    version=__version__,
    summary="Six thinking engines, one recommendation, the dissent kept intact.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
