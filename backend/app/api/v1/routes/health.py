from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse, JSONResponse

from app.core.config import get_settings
from app.schemas.health import HealthResponse, ReadinessResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    settings = request.app.state.settings
    return HealthResponse(
        status="healthy",
        service=settings.app_name,
        version=settings.app_version,
    )


@router.get("/ready", response_model=ReadinessResponse)
def ready(request: Request):
    database = getattr(request.app.state, "database", None)
    ready_now = database is not None and database.is_ready() and hasattr(request.app.state, "regpack_registry")
    request.app.state.metrics.set_db_ready(ready_now)
    payload = ReadinessResponse(status="ready" if ready_now else "not_ready", service=request.app.state.settings.app_name)
    if ready_now:
        return payload
    return JSONResponse(status_code=503, content=payload.model_dump())


@router.get("/metrics", response_class=PlainTextResponse)
def metrics(request: Request) -> PlainTextResponse:
    if not request.app.state.settings.metrics_enabled:
        return PlainTextResponse("", status_code=404)
    return PlainTextResponse(request.app.state.metrics.render(), media_type="text/plain; version=0.0.4")
