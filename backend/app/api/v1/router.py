from fastapi import APIRouter

from app.api.v1.routes.canonical import router as canonical_router
from app.api.v1.routes.health import router as health_router
from app.api.v1.routes.imports import router as imports_router
from app.api.v1.routes.mapping_profiles import router as mapping_profiles_router
from app.api.v1.routes.outputs import router as outputs_router
from app.api.v1.routes.regflow import router as regflow_router
from app.api.v1.routes.regpacks import router as regpacks_router
from app.api.v1.routes.runs import router as runs_router
from app.api.v1.routes.reconciliation import router as reconciliation_router
from app.api.v1.routes.validation import router as validation_router
from app.api.v1.routes.identity import organisation_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(regpacks_router)
api_router.include_router(canonical_router)
api_router.include_router(validation_router)
api_router.include_router(reconciliation_router)
api_router.include_router(imports_router)
api_router.include_router(mapping_profiles_router)
api_router.include_router(outputs_router)
api_router.include_router(regflow_router)
api_router.include_router(runs_router)
api_router.include_router(organisation_router)
