from __future__ import annotations

import logging
import re
import secrets
import time
from collections import defaultdict, deque
from threading import Lock

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.logging import organisation_id_context, request_id_context, user_id_context


logger = logging.getLogger("app.http")
REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,100}$")


def error_response(request: Request, status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message, "request_id": getattr(request.state, "request_id", None)}})


class RequestBoundaryMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        supplied = request.headers.get("X-Request-ID", "")
        request_id = supplied if REQUEST_ID.fullmatch(supplied) else secrets.token_hex(16)
        request.state.request_id = request_id
        request_token = request_id_context.set(request_id)
        started = time.perf_counter()
        status = 500
        try:
            content_length = request.headers.get("content-length")
            if content_length:
                try:
                    too_large = int(content_length) > request.app.state.settings.request_max_body_mb * 1024 * 1024
                except ValueError:
                    response = error_response(request, 400, "INVALID_CONTENT_LENGTH", "The request Content-Length is invalid.")
                    status = response.status_code
                    return response
                if too_large:
                    response = error_response(request, 413, "REQUEST_TOO_LARGE", "The request body exceeds the configured limit.")
                    status = response.status_code
                    return response
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            duration = time.perf_counter() - started
            context = getattr(request.state, "tenant_context", None)
            org_token = organisation_id_context.set(getattr(context, "organisation_id", None))
            user_token = user_id_context.set(getattr(context, "user_id", None))
            metrics = getattr(request.app.state, "metrics", None)
            if metrics is not None:
                metrics.observe_request(request.method, request.url.path, status, duration)
            logger.info("http_request", extra={"event": "http_request", "method": request.method, "path": request.url.path, "status": status, "duration_ms": round(duration * 1000, 2), "result": "success" if status < 400 else "failure"})
            organisation_id_context.reset(org_token)
            user_id_context.reset(user_token)
            request_id_context.reset(request_token)


class BodyLimitMiddleware:
    """Enforce the body limit even when a client uses chunked transfer encoding."""

    def __init__(self, app, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise _BodyTooLarge
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _BodyTooLarge:
            request_id = scope.get("state", {}).get("request_id")
            response = JSONResponse(
                status_code=413,
                content={"error": {"code": "REQUEST_TOO_LARGE", "message": "The request body exceeds the configured limit.", "request_id": request_id}},
            )
            await response(scope, receive, send)


class _BodyTooLarge(Exception):
    pass


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Request-ID"] = getattr(request.state, "request_id", "")
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'none'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
        if request.url.path.startswith(("/auth", "/api/v1/organisations", "/api/v1/regflow", "/api/v1/imports", "/api/v1/outputs", "/api/v1/mapping-profiles")):
            response.headers["Cache-Control"] = "no-store"
        settings = request.app.state.settings
        if settings.app_env == "production" and settings.https_boundary:
            response.headers["Strict-Transport-Security"] = f"max-age={settings.hsts_max_age_seconds}; includeSubDomains"
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app) -> None:
        super().__init__(app)
        self._lock = Lock()
        self._events: dict[tuple[str, str], deque[float]] = defaultdict(deque)

    def _policy(self, request: Request) -> tuple[str, int] | None:
        settings = request.app.state.settings
        path = request.url.path
        if path in {"/auth/login", "/auth/callback"}:
            return "auth", settings.rate_limit_auth_requests
        if "invitations" in path and request.method in {"POST", "DELETE"}:
            return "invitation", settings.rate_limit_invitation_requests
        if request.method == "POST" and path.startswith(("/api/v1/imports", "/api/v1/outputs", "/api/v1/regflow/preflight")):
            return "expensive", settings.rate_limit_expensive_requests
        return None

    async def dispatch(self, request: Request, call_next):
        policy = self._policy(request)
        if policy is not None:
            name, limit = policy
            now = time.monotonic()
            client = request.client.host if request.client else "unknown"
            key = (client, name)
            with self._lock:
                events = self._events[key]
                threshold = now - request.app.state.settings.rate_limit_window_seconds
                while events and events[0] <= threshold:
                    events.popleft()
                if len(events) >= limit:
                    return error_response(request, 429, "RATE_LIMITED", "Too many requests. Try again later.")
                events.append(now)
        return await call_next(request)
