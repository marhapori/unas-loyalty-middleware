from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles

from loyalty_app.api import auth_routes, health_routes, loyalty_routes, pages, scan_routes, webhook_routes
from loyalty_app.config import get_settings
from loyalty_app.db import SessionLocal
from loyalty_app.security import RedactingFilter
from loyalty_app.unas.client import UnasClient
from loyalty_app.worker import run_worker_loop

STATIC_DIR = Path(__file__).parent / "static"


def _configure_logging(level: str) -> None:
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logging.getLogger().addFilter(RedactingFilter())


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    _configure_logging(settings.log_level)

    unas_client = UnasClient(
        api_key=settings.unas_api_key,
        base_url=settings.unas_api_base_url,
        timeout_seconds=settings.unas_request_timeout_seconds,
        requests_per_second=settings.unas_max_requests_per_second,
    )
    app.state.unas_client = unas_client

    worker_task = asyncio.create_task(run_worker_loop(SessionLocal, unas_client, settings))

    try:
        yield
    finally:
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass
        await unas_client.aclose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="UNAS husegpont middleware", lifespan=lifespan)

    https_only = settings.app_base_url.startswith("https://")
    app.add_middleware(
        SessionMiddleware, secret_key=settings.session_secret, same_site="strict", https_only=https_only
    )
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    app.include_router(pages.router)
    app.include_router(auth_routes.router)
    app.include_router(scan_routes.router)
    app.include_router(loyalty_routes.router)
    app.include_router(webhook_routes.router)
    app.include_router(health_routes.router)

    return app


app = create_app()
