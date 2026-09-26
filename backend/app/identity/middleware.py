from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.identity.errors import IdentityError
from app.identity.service import IdentityService, LEGACY_CONTEXT, TenantContext


class AuthenticationMiddleware(BaseHTTPMiddleware):
    PROTECTED_PREFIXES = (
        "/api/v1/imports", "/api/v1/outputs", "/api/v1/regflow",
        "/api/v1/mapping-profiles", "/api/v1/organisations",
    )
    UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}

    async def dispatch(self, request: Request, call_next):
        settings = request.app.state.settings
        if not settings.auth_enabled:
            request.state.tenant_context = LEGACY_CONTEXT
            return await call_next(request)
        if request.url.path.startswith(self.PROTECTED_PREFIXES):
            database = request.app.state.database
            try:
                with database.session_factory() as session:
                    service = IdentityService(session, session_seconds=settings.session_expiry_seconds, invitation_hours=settings.invitation_expiry_hours, application_secret=settings.application_secret)
                    user, record, membership = service.authenticate(request.cookies.get(settings.session_cookie_name))
                    request.state.auth_user = user
                    request.state.auth_session = record
                    request.state.tenant_context = TenantContext(user.id, membership.organisation_id, membership.role, record.id) if membership else None
                    if request.method in self.UNSAFE:
                        service.validate_csrf(request.cookies.get(settings.session_cookie_name), request.cookies.get("regbridge_csrf"), request.headers.get(settings.csrf_header_name))
            except IdentityError as exc:
                return JSONResponse(status_code=exc.status_code, content={"error": {"code": exc.code, "message": exc.message, "request_id": getattr(request.state, "request_id", None)}})
        return await call_next(request)
