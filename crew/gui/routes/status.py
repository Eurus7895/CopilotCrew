"""GET /status — polled every 30s for the header dot."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from crew.gui.routes._shared import get_config
from crew.gui.services import status_service

router = APIRouter()


@router.get("/status")
async def status(request: Request) -> JSONResponse:
    cfg = get_config(request)
    return JSONResponse(asdict(status_service.probe(cfg)))
