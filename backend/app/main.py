"""FastAPI application entrypoint."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import complaints, health
from app.compat import configure_event_loop
from app.config import get_settings
from app.db.session import dispose_engine
from app.llm.registry import registry
from app.services.runner import runner


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s  %(levelname)-8s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    _configure_logging(settings.aivoa_log_level)
    log = logging.getLogger("aivoa")

    log.info("Probing Groq for available models...")
    await registry.probe()

    log.info("Compiling LangGraph...")
    await runner.start()

    yield

    await runner.stop()
    await dispose_engine()


app = FastAPI(
    title="AIVOA Complaint Management API",
    description=(
        "AI-powered Customer Complaint Management for pharmaceutical "
        "manufacturing (API & FDF). LangGraph agent over Groq."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(complaints.router, prefix="/api", tags=["complaints"])


@app.get("/")
async def root() -> dict:
    return {"service": "aivoa-complaint-api", "docs": "/docs"}
