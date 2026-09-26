from __future__ import annotations

from datetime import timezone

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.dependencies import get_database_session, get_tenant_context
from app.identity.errors import AuthenticationRequired, OrganisationRequired
from app.identity.models import MembershipRole
from app.identity.oidc import OidcClient
from app.identity.schemas import (
    AcceptInvitationRequest, CreateOrganisationRequest, InvitationView, InviteRequest,
    MemberView, OrganisationView, SessionView, SwitchOrganisationRequest,
    UpdateMemberRoleRequest,
)
from app.identity.service import IdentityService, TenantContext, is_expired
from app.persistence.models import utc_now

auth_router = APIRouter(prefix="/auth", tags=["authentication"])
organisation_router = APIRouter(prefix="/organisations", tags=["organisations"])


def service(request: Request, session: Session) -> IdentityService:
    settings = request.app.state.settings
    return IdentityService(session, session_seconds=settings.session_expiry_seconds, invitation_hours=settings.invitation_expiry_hours, application_secret=settings.application_secret)


@auth_router.get("/login")
async def login(request: Request, return_to: str = Query(default="/"), session: Session = Depends(get_database_session)):
    settings = request.app.state.settings
    if not settings.auth_enabled:
        raise AuthenticationRequired("Authentication is disabled in this environment.")
    url, transaction = await OidcClient(session, settings).begin(return_to)
    response = RedirectResponse(url, status_code=302)
    response.set_cookie(settings.oidc_transaction_cookie_name, transaction, max_age=settings.oidc_transaction_expiry_seconds, httponly=True, secure=settings.secure_cookies, samesite=settings.cookie_samesite, path="/auth/callback")
    return response


@auth_router.get("/callback")
async def callback(request: Request, state: str | None = None, code: str | None = None, error: str | None = None, session: Session = Depends(get_database_session)):
    settings = request.app.state.settings
    if error is not None:
        return_to = OidcClient(session, settings).cancel(request.cookies.get(settings.oidc_transaction_cookie_name), state)
        response = RedirectResponse(f"{settings.frontend_url}{return_to}{'&' if '?' in return_to else '?'}auth_error=login_cancelled", status_code=302)
        response.delete_cookie(settings.oidc_transaction_cookie_name, path="/auth/callback")
        return response
    claims, return_to = await OidcClient(session, settings).complete(request.cookies.get(settings.oidc_transaction_cookie_name), state, code)
    raw_session, csrf = service(request, session).login_identity(claims)
    response = RedirectResponse(f"{settings.frontend_url}{return_to}", status_code=302)
    response.set_cookie(settings.session_cookie_name, raw_session, max_age=settings.session_expiry_seconds, httponly=True, secure=settings.secure_cookies, samesite=settings.cookie_samesite, path="/")
    response.set_cookie("regbridge_csrf", csrf, max_age=settings.session_expiry_seconds, httponly=False, secure=settings.secure_cookies, samesite=settings.cookie_samesite, path="/")
    response.delete_cookie(settings.oidc_transaction_cookie_name, path="/auth/callback")
    return response


@auth_router.get("/session", response_model=SessionView)
def current_session(request: Request, session: Session = Depends(get_database_session)):
    settings = request.app.state.settings
    if not settings.auth_enabled:
        return SessionView(auth_enabled=False, authenticated=False)
    try:
        return SessionView.model_validate(service(request, session).session_view(request.cookies.get(settings.session_cookie_name) or ""))
    except AuthenticationRequired:
        return SessionView(auth_enabled=True, authenticated=False)


@auth_router.post("/logout", status_code=204)
def logout(request: Request, session: Session = Depends(get_database_session)):
    settings = request.app.state.settings
    service(request, session).validate_csrf(request.cookies.get(settings.session_cookie_name), request.cookies.get("regbridge_csrf"), request.headers.get(settings.csrf_header_name))
    service(request, session).revoke_session(request.cookies.get(settings.session_cookie_name) or "")
    response = Response(status_code=204)
    response.delete_cookie(settings.session_cookie_name, path="/")
    response.delete_cookie("regbridge_csrf", path="/")
    return response


@organisation_router.get("", response_model=tuple[OrganisationView, ...])
def organisations(request: Request, session: Session = Depends(get_database_session)):
    view = service(request, session).session_view(request.cookies.get(request.app.state.settings.session_cookie_name) or "")
    return tuple(view["organisations"])


@organisation_router.post("", response_model=OrganisationView, status_code=201)
def create_organisation(payload: CreateOrganisationRequest, request: Request, session: Session = Depends(get_database_session)):
    user = request.state.auth_user; auth_session = request.state.auth_session
    return service(request, session).create_organisation(user.id, auth_session.id, payload.name, payload.slug)


@organisation_router.post("/active", status_code=204)
def switch_organisation(payload: SwitchOrganisationRequest, request: Request, session: Session = Depends(get_database_session)):
    service(request, session).switch_organisation(request.state.auth_user.id, request.state.auth_session.id, payload.organisation_id)
    return Response(status_code=204)


@organisation_router.get("/active", response_model=OrganisationView)
def active_organisation(context: TenantContext = Depends(get_tenant_context), request: Request = None, session: Session = Depends(get_database_session)):
    return next(item for item in service(request, session).session_view(request.cookies.get(request.app.state.settings.session_cookie_name) or "")["organisations"] if item["id"] == context.organisation_id)


@organisation_router.get("/active/members", response_model=tuple[MemberView, ...])
def members(context: TenantContext = Depends(get_tenant_context), request: Request = None, session: Session = Depends(get_database_session)):
    return tuple(service(request, session).members(context))


def invitation_view(record, token: str | None = None) -> InvitationView:
    now = utc_now()
    state = "ACCEPTED" if record.accepted_at else "REVOKED" if record.revoked_at else "EXPIRED" if is_expired(record.expires_at) else "PENDING"
    return InvitationView(id=record.id, invited_email=record.invited_email, invited_role=record.invited_role, expires_at=record.expires_at, state=state, invitation_token=token)


@organisation_router.get("/active/invitations", response_model=tuple[InvitationView, ...])
def invitations(context: TenantContext = Depends(get_tenant_context), request: Request = None, session: Session = Depends(get_database_session)):
    return tuple(invitation_view(item) for item in service(request, session).invitations(context))


@organisation_router.post("/active/invitations", response_model=InvitationView, status_code=201)
def invite(payload: InviteRequest, context: TenantContext = Depends(get_tenant_context), request: Request = None, session: Session = Depends(get_database_session)):
    record, token = service(request, session).invite(context, payload.email, payload.role)
    return invitation_view(record, token)


@organisation_router.delete("/active/invitations/{invitation_id}", status_code=204)
def revoke_invitation(invitation_id: str, context: TenantContext = Depends(get_tenant_context), request: Request = None, session: Session = Depends(get_database_session)):
    service(request, session).revoke_invitation(context, invitation_id)
    return Response(status_code=204)


@organisation_router.post("/invitations/accept", status_code=204)
def accept_invitation(payload: AcceptInvitationRequest, request: Request, session: Session = Depends(get_database_session)):
    service(request, session).accept_invitation(request.state.auth_user.id, payload.token, request.state.auth_session.id)
    return Response(status_code=204)


@organisation_router.patch("/active/members/{user_id}", status_code=204)
def update_member(user_id: str, payload: UpdateMemberRoleRequest, context: TenantContext = Depends(get_tenant_context), request: Request = None, session: Session = Depends(get_database_session)):
    service(request, session).update_member_role(context, user_id, payload.role)
    return Response(status_code=204)


@organisation_router.delete("/active/members/{user_id}", status_code=204)
def remove_member(user_id: str, context: TenantContext = Depends(get_tenant_context), request: Request = None, session: Session = Depends(get_database_session)):
    service(request, session).remove_member(context, user_id)
    return Response(status_code=204)
