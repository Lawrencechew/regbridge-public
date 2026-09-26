import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy.exc import SQLAlchemyError

from app.api.v1.router import api_router
from app.canonical.models import CanonicalSchema
from app.canonical.registry import CanonicalSchemaRegistry
from app.core.config import get_settings
from app.core.capacity import GenerationCapacityExceeded, GenerationLimiter
from app.core.logging import configure_logging
from app.core.http import BodyLimitMiddleware, RequestBoundaryMiddleware, SecurityHeadersMiddleware, RateLimitMiddleware
from app.core.metrics import MetricsRegistry
from app.imports.errors import ImportRequestError
from app.imports.security import ImportLimits
from app.imports.service import ImportService
from app.outputs.errors import OutputRequestError
from app.outputs.service import OutputService
from app.persistence.database import Database
from app.persistence.errors import PersistenceError
from app.regflow.service import RegFlowPreflightService
from app.regpacks.errors import RegPackNotFoundError, RegPackVersionError
from app.regpacks.registry import RegPackRegistry
from app.regpacks.runner import RegPackRunner
from app.reconciliation.engine import ReconciliationEngine
from app.validation.engine import ValidationEngine
from app.api.v1.routes.identity import auth_router
from app.identity.errors import IdentityError
from app.identity.middleware import AuthenticationMiddleware
from app.identity import models as identity_models  # noqa: F401

logger = logging.getLogger(__name__)


async def regpack_not_found_handler(
    request: Request, exc: RegPackNotFoundError
) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={
            "error": {
                "code": "REGPACK_NOT_FOUND",
                "message": "The requested RegPack was not found.",
                "request_id": getattr(request.state, "request_id", None),
            }
        },
    )


async def invalid_version_handler(
    request: Request, exc: RegPackVersionError
) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={
            "error": {
                "code": "INVALID_REGPACK_VERSION",
                "message": "The requested RegPack version is invalid.",
                "request_id": getattr(request.state, "request_id", None),
            }
        },
    )


async def import_request_error_handler(
    request: Request, exc: ImportRequestError
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": str(exc.code), "message": exc.message, "request_id": getattr(request.state, "request_id", None)}},
    )


async def output_request_error_handler(
    request: Request, exc: OutputRequestError
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message, "request_id": getattr(request.state, "request_id", None)}},
    )


async def generation_capacity_error_handler(
    request: Request, exc: GenerationCapacityExceeded
) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        headers={"Retry-After": str(exc.retry_after_seconds)},
        content={
            "error": {
                "code": "GENERATION_CAPACITY_EXCEEDED",
                "message": "Output generation is busy. Retry the request later.",
                "request_id": getattr(request.state, "request_id", None),
            }
        },
    )


async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("internal_error", extra={"event": "internal_error", "path": request.url.path, "result": "failure"})
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred.",
                "request_id": getattr(request.state, "request_id", None),
            }
        },
    )


async def persistence_error_handler(
    request: Request, exc: PersistenceError
) -> JSONResponse:
    error = {"code": exc.code, "message": exc.message, "request_id": getattr(request.state, "request_id", None)}
    if exc.metadata:
        error["metadata"] = exc.metadata
    return JSONResponse(status_code=exc.status_code, content={"error": error})


async def identity_error_handler(request: Request, exc: IdentityError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message, "request_id": getattr(request.state, "request_id", None)}},
    )


async def request_validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"error": {"code": "INVALID_REQUEST", "message": "The request is invalid.", "request_id": getattr(request.state, "request_id", None)}},
    )


async def database_error_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    logger.exception("database_request_failed", extra={"event": "database_request_failed", "path": request.url.path, "result": "failure"})
    return JSONResponse(status_code=503, content={"error": {"code": "DATABASE_UNAVAILABLE", "message": "The service dependency is temporarily unavailable.", "request_id": getattr(request.state, "request_id", None)}})


async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = "NOT_FOUND" if exc.status_code == 404 else "METHOD_NOT_ALLOWED" if exc.status_code == 405 else "HTTP_ERROR"
    message = "The requested resource was not found." if exc.status_code == 404 else "The request could not be processed."
    return JSONResponse(status_code=exc.status_code, content={"error": {"code": code, "message": message, "request_id": getattr(request.state, "request_id", None)}})


def create_app(*, settings_override=None) -> FastAPI:
    settings = settings_override or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        logger.info(
            "application_starting",
            extra={
                "event": "application_starting",
                "version": settings.app_version,
                "environment": settings.app_env,
                "result": "started",
            },
        )
        database = None
        if settings.persistence_enabled:
            database = Database(settings.database_url, echo=settings.database_sql_echo)
            database.validate()
            logger.info("database_ready", extra={"event": "database_ready", "result": "success"})
        application.state.database = database
        application.state.settings = settings
        registry = RegPackRegistry(settings.regpacks_path)
        registry.discover()
        application.state.regpack_registry = registry
        logger.info(
            "RegPack registry initialised: %d packs, %d versions",
            registry.pack_count,
            registry.version_count,
        )
        canonical_registry = CanonicalSchemaRegistry()
        for pack in registry.list_loaded_versions():
            if isinstance(pack.canonical_schema, CanonicalSchema):
                canonical_registry.register(pack.canonical_schema)
        application.state.canonical_schema_registry = canonical_registry
        logger.info(
            "Canonical schema registry initialised: %d schemas",
            canonical_registry.schema_count,
        )
        application.state.validation_engine = ValidationEngine()
        validation_rules = sum(
            len(pack.validation_rules.rules)
            for pack in registry.list_loaded_versions()
            if pack.validation_rules is not None
        )
        logger.info(
            "Validation engine initialised: %d production rules", validation_rules
        )
        application.state.reconciliation_engine = ReconciliationEngine()
        application.state.regpack_runner = RegPackRunner()
        application.state.import_service = ImportService(
            ImportLimits.from_settings(settings), settings.mapping_max_characters
        )
        application.state.output_service = OutputService(
            settings.output_max_file_size_mb * 1024 * 1024,
            application.state.regpack_runner,
        )
        application.state.regflow_preflight_service = RegFlowPreflightService(
            application.state.import_service,
            application.state.regpack_runner,
            settings.preflight_max_findings,
        )
        production_rules = sum(
            len(pack.reconciliation_rules.rules)
            for pack in registry.list_loaded_versions()
            if pack.reconciliation_rules is not None
        )
        logger.info(
            "Reconciliation engine initialised: %d production rules",
            production_rules,
        )
        try:
            yield
        finally:
            if database is not None:
                database.dispose()
            logger.info("application_shutdown", extra={"event": "application_shutdown", "result": "success"})

    application = FastAPI(
        title="RegBridge API", version=settings.app_version, lifespan=lifespan,
        debug=settings.app_debug,
        docs_url=None if settings.app_env == "production" else "/docs",
        redoc_url=None if settings.app_env == "production" else "/redoc",
        openapi_url=None if settings.app_env == "production" else "/openapi.json",
    )
    # Middleware can run in lightweight TestClient usage before lifespan startup.
    # Configuration is immutable, so expose it as soon as the application exists.
    application.state.settings = settings
    application.state.database = None
    application.state.metrics = MetricsRegistry()
    application.state.generation_limiter = GenerationLimiter(
        settings.generation_max_concurrency,
        settings.generation_retry_after_seconds,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["*"],
    )
    application.add_middleware(AuthenticationMiddleware)
    application.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
    application.add_middleware(RateLimitMiddleware)
    application.add_middleware(BodyLimitMiddleware, max_bytes=settings.request_max_body_mb * 1024 * 1024)
    application.add_middleware(RequestBoundaryMiddleware)
    application.add_middleware(SecurityHeadersMiddleware)
    application.include_router(api_router, prefix="/api/v1")
    application.include_router(auth_router)
    application.add_exception_handler(RegPackNotFoundError, regpack_not_found_handler)
    application.add_exception_handler(RegPackVersionError, invalid_version_handler)
    application.add_exception_handler(ImportRequestError, import_request_error_handler)
    application.add_exception_handler(OutputRequestError, output_request_error_handler)
    application.add_exception_handler(
        GenerationCapacityExceeded, generation_capacity_error_handler
    )
    application.add_exception_handler(PersistenceError, persistence_error_handler)
    application.add_exception_handler(IdentityError, identity_error_handler)
    application.add_exception_handler(RequestValidationError, request_validation_error_handler)
    application.add_exception_handler(SQLAlchemyError, database_error_handler)
    application.add_exception_handler(StarletteHTTPException, http_error_handler)
    application.add_exception_handler(Exception, unexpected_error_handler)
    return application


app = create_app()
