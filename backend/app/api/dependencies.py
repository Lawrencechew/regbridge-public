from collections.abc import Iterator

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.canonical.registry import CanonicalSchemaRegistry
from app.imports.service import ImportService
from app.outputs.service import OutputService
from app.persistence.errors import PersistenceUnavailableError
from app.persistence.service import PersistenceService
from app.identity.errors import OrganisationRequired
from app.identity.service import LEGACY_CONTEXT, TenantContext
from app.regflow.service import RegFlowPreflightService
from app.regpacks.registry import RegPackRegistry


def get_regpack_registry(request: Request) -> RegPackRegistry:
    return request.app.state.regpack_registry


def get_canonical_schema_registry(request: Request) -> CanonicalSchemaRegistry:
    return request.app.state.canonical_schema_registry


def get_import_service(request: Request) -> ImportService:
    return request.app.state.import_service


def get_output_service(request: Request) -> OutputService:
    return request.app.state.output_service


def get_regflow_preflight_service(request: Request) -> RegFlowPreflightService:
    return request.app.state.regflow_preflight_service


def get_database_session(request: Request) -> Iterator[Session]:
    database = getattr(request.app.state, "database", None)
    if database is None:
        raise PersistenceUnavailableError()
    yield from database.sessions()


def get_persistence_service(
    request: Request,
    session: Session = Depends(get_database_session),
) -> PersistenceService:
    context = get_tenant_context(request)
    return PersistenceService(session, context.organisation_id, getattr(request.state, "request_id", None))


def get_tenant_context(request: Request) -> TenantContext:
    if not request.app.state.settings.auth_enabled:
        return LEGACY_CONTEXT
    context = getattr(request.state, "tenant_context", None)
    if context is None:
        raise OrganisationRequired()
    return context


def get_optional_persistence_service(request: Request) -> Iterator[PersistenceService | None]:
    database = getattr(request.app.state, "database", None)
    if database is None:
        yield None
        return
    with database.session_factory() as session:
        context = get_tenant_context(request)
        yield PersistenceService(session, context.organisation_id, getattr(request.state, "request_id", None))
