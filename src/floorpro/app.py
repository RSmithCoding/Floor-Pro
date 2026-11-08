"""FastAPI application factory."""

from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from floorpro import paths
from floorpro.db import make_engine, make_sessionmaker
from floorpro.logging_setup import configure_logging
from floorpro.migrate import upgrade_to_head
from floorpro.services import backup_service, recovery_service
from floorpro.services.settings_service import ensure_settings
from floorpro.templating import render

log = logging.getLogger(__name__)

RECOVERY_ALLOWED = ("/static", "/healthz", "/recovery")


def _start_thread(fn) -> None:
    threading.Thread(target=fn, name="floorpro-background", daemon=True).start()


def create_app(data_dir: Path | None = None) -> FastAPI:
    if data_dir is not None:
        import os

        os.environ[paths.DATA_DIR_ENV] = str(data_dir)

    def open_database(app: FastAPI) -> None:
        """Migrate, connect and make sure the settings row exists."""
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

    def reopen_database() -> None:
        """Leave recovery mode after a restore or Start with no data, without restarting."""
        old = getattr(app.state, "engine", None)
        if old is not None:
            old.dispose()
        open_database(app)
        app.state.recovery = None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        configure_logging()
        app.state.engine = None
        app.state.recovery = recovery_service.check_database(paths.db_path())
        if app.state.recovery is None:
            try:
                open_database(app)
            except Exception as exc:  # any failure to open or migrate → recovery screen
                app.state.recovery = recovery_service.recovery_for(exc)
        backup_service.cleanup_partials()
        if app.state.recovery is None:
            backup_service.maybe_run_daily(app)
        yield
        if app.state.engine is not None:
            app.state.engine.dispose()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    # Set by the desktop launcher to a NativeDialogs (save_path, choose_folder, open_file).
    # None in browser mode and tests, where HTML fallbacks are shown instead.
    app.state.dialogs = None
    # Runs automatic backups off the request/startup path; tests replace it with a sync call.
    app.state.run_in_background = _start_thread
    app.mount("/static", StaticFiles(directory=paths.resource_path("static")), name="static")

    app.state.reopen_database = reopen_database
    app.state.recovery = None

    @app.middleware("http")
    async def load_settings(request: Request, call_next):
        if (
            not request.url.path.startswith("/static")
            and app.state.recovery is None
            and hasattr(app.state, "sessionmaker")
        ):
            with app.state.sessionmaker() as session:
                settings, _ = ensure_settings(session)
                session.commit()
                session.expunge(settings)
            request.state.settings = settings
        return await call_next(request)

    @app.middleware("http")
    async def recovery_redirect(request: Request, call_next):
        """While the database can't be opened, every page leads to the recovery screen."""
        path = request.url.path
        if app.state.recovery is not None and not path.startswith(RECOVERY_ALLOWED):
            if request.headers.get("HX-Request") == "true":
                return Response(status_code=200, headers={"HX-Redirect": "/recovery"})
            return RedirectResponse("/recovery", status_code=303)
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

    from floorpro.routes import backups, customers, dashboard, recovery, settings

    app.include_router(dashboard.router)
    app.include_router(customers.router)
    app.include_router(settings.router)
    app.include_router(backups.router)
    app.include_router(recovery.router)
    return app
