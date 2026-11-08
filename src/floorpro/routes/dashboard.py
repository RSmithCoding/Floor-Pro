"""Dashboard (home screen) and the health check used by the desktop launcher."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from floorpro.templating import render

router = APIRouter()


@router.get("/")
def dashboard(request: Request):
    return render(request, "dashboard.html", context={"nav": "dashboard"})


@router.get("/healthz", response_class=PlainTextResponse)
def healthz() -> str:
    return "ok"
