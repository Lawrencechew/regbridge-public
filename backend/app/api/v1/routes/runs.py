from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Response

from app.api.dependencies import get_persistence_service, get_regpack_registry
from app.persistence.models import RunState
from app.persistence.schemas import CreateRunRequest, RunDetail, RunList
from app.persistence.service import PersistenceService
from app.regpacks.registry import RegPackRegistry

router = APIRouter(prefix="/regflow/runs", tags=["regflow-runs"])
Persistence = Annotated[PersistenceService, Depends(get_persistence_service)]
Registry = Annotated[RegPackRegistry, Depends(get_regpack_registry)]


@router.post("", response_model=RunDetail, status_code=201)
def create_run(
    request: CreateRunRequest,
    persistence: Persistence,
    registry: Registry,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> RunDetail:
    pack = registry.get(request.pack_id, request.pack_version)
    return persistence.create_run(pack, idempotency_key)


@router.get("", response_model=RunList)
def list_runs(
    persistence: Persistence,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    state: RunState | None = None,
) -> RunList:
    return persistence.list_runs(limit=limit, state=state)


@router.get("/{run_id}", response_model=RunDetail)
def get_run(run_id: str, persistence: Persistence) -> RunDetail:
    return persistence.get_run(run_id)


@router.delete("/{run_id}", status_code=204)
def delete_run(run_id: str, persistence: Persistence) -> Response:
    persistence.delete_run(run_id)
    return Response(status_code=204)
