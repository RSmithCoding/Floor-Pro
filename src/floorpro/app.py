"""FastAPI application factory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from floorpro import paths
from floorpro.db import make_engine, make_sessionmaker
from floorpro.logging_setup import configure_logging
from floorpro.migrate import upgrade_to_head
from floorpro.services.settings_service import ensure_settings
from floorpro.templating import render

log = logging.getLogger(__name__)


def create_app(data_dir: Path | None = None) -> FastAPI:
    if data_dir is not None:
        import os

        os.environ[paths.DATA_DIR_ENV] = str(data_dir)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        configure_logging()
        db_path = paths.db_path()
        existed = db_path.exists()
        upgrade_to_head(db_path)
        engine = make_engine(db_path)
        app.state.engine = engine
        app.state.sessionmaker = make_sessionmaker(engine)
        with app.state.sessionmaker.begin() as session:
            _, created = ensure_settings(session)
        app.state.settings_notice = created and existed
        if app.state.settings_notice:
            log.warning("Business settings row was missing; defaults restored")
        yield
        engine.dispose()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.mount("/static", StaticFiles(directory=paths.resource_path("static")), name="static")

    @app.middleware("http")
    async def load_settings(request: Request, call_next):
        if not request.url.path.startswith("/static") and hasattr(app.state, "sessionmaker"):
            with app.state.sessionmaker() as session:
                settings, _ = ensure_settings(session)
                session.commit()
                session.expunge(settings)
            request.state.settings = settings
        return await call_next(request)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        if exc.status_code == 404:
            return render(request, "errors/404.html", "errors/_404.html", status_code=404)
        log.warning("HTTP %s on %s", exc.status_code, request.url.path)
        return render(request, "errors/500.html", "errors/_500.html", status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def server_error(request: Request, exc: Exception):
        log.exception("Unhandled error on %s", request.url.path)
        return render(request, "errors/500.html", "errors/_500.html", status_code=500)

    from floorpro.routes import customers, dashboard

    app.include_router(dashboard.router)
    app.include_router(customers.router)
    return app
