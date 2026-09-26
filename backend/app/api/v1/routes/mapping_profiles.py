from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.api.dependencies import get_persistence_service, get_regpack_registry
from app.persistence.schemas import (
    MappingProfileDetail,
    MappingProfileList,
    MappingProfileMatch,
    MappingProfileVersion,
    SaveMappingProfileRequest,
)
from app.persistence.service import PersistenceService
from app.regpacks.registry import RegPackRegistry

router = APIRouter(prefix="/mapping-profiles", tags=["mapping-profiles"])
Persistence = Annotated[PersistenceService, Depends(get_persistence_service)]
Registry = Annotated[RegPackRegistry, Depends(get_regpack_registry)]


@router.post("", response_model=MappingProfileVersion, status_code=201)
def create_profile(
    request: SaveMappingProfileRequest,
    persistence: Persistence,
    registry: Registry,
) -> MappingProfileVersion:
    return persistence.save_profile_from_run(
        run_id=request.run_id,
        display_name=request.display_name,
        base_profile_id=request.base_profile_id,
        recommendation_origins=request.recommendation_origins,
        pack_resolver=registry.get,
    )


@router.get("/match", response_model=MappingProfileMatch)
def match_profiles(
    persistence: Persistence,
    registry: Registry,
    pack_id: Annotated[str, Query(min_length=1, max_length=120)],
    pack_version: Annotated[str, Query(min_length=1, max_length=64)],
    canonical_schema_id: Annotated[str, Query(min_length=1, max_length=120)],
    canonical_schema_version: Annotated[str, Query(min_length=1, max_length=64)],
    source_header_signature: Annotated[str, Query(pattern=r"^[a-f0-9]{64}$")],
    section_id: Annotated[str | None, Query(max_length=120)] = None,
) -> MappingProfileMatch:
    pack = registry.get(pack_id, pack_version)
    return persistence.match_profiles(
        pack=pack,
        schema_id=canonical_schema_id,
        schema_version=canonical_schema_version,
        source_signature=source_header_signature,
        section_id=section_id,
    )


@router.get("", response_model=MappingProfileList)
def list_profiles(persistence: Persistence) -> MappingProfileList:
    return persistence.list_profiles()


@router.get("/{profile_id}", response_model=MappingProfileDetail)
def get_profile(profile_id: str, persistence: Persistence) -> MappingProfileDetail:
    return persistence.get_profile(profile_id)


@router.delete("/{profile_id}", status_code=204)
def delete_profile(profile_id: str, persistence: Persistence) -> Response:
    persistence.delete_profile(profile_id)
    return Response(status_code=204)
