from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.identity.errors import AuthenticationRequired, IdentityResourceNotFound, InvitationUnavailable, OrganisationRequired, PermissionDenied
from app.identity.models import (
    LEGACY_ORGANISATION_ID, LEGACY_USER_ID, ExternalIdentityRecord, InvitationRecord,
    MembershipRole, OrganisationMembershipRecord, OrganisationRecord, UserRecord,
    UserSessionRecord,
)
from app.persistence.models import utc_now


DEVELOPMENT_SECRET = "development-only-change-me"


def digest(value: str, secret: str = DEVELOPMENT_SECRET) -> str:
    return hmac.new(secret.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()


def normalise_email(value: str) -> str:
    return value.strip().casefold()


def is_expired(value) -> bool:
    now = utc_now()
    if value.tzinfo is None:
        now = now.replace(tzinfo=None)
    return value <= now


@dataclass(frozen=True)
class TenantContext:
    user_id: str
    organisation_id: str
    role: MembershipRole
    session_id: str | None


LEGACY_CONTEXT = TenantContext(LEGACY_USER_ID, LEGACY_ORGANISATION_ID, MembershipRole.OWNER, None)


class IdentityService:
    def __init__(self, session: Session, *, session_seconds: int = 28_800, invitation_hours: int = 168, application_secret: str = DEVELOPMENT_SECRET) -> None:
        self.session = session
        self.session_seconds = session_seconds
        self.invitation_hours = invitation_hours
        self.application_secret = application_secret

    def _digest(self, value: str) -> str:
        return digest(value, self.application_secret)

    def authenticate(self, raw_session: str | None, *, touch: bool = True) -> tuple[UserRecord, UserSessionRecord, OrganisationMembershipRecord | None]:
        if not raw_session:
            raise AuthenticationRequired()
        now = utc_now()
        record = self.session.scalar(select(UserSessionRecord).where(UserSessionRecord.session_hash == self._digest(raw_session)))
        if record is None or record.revoked_at is not None or is_expired(record.expires_at):
            raise AuthenticationRequired("The session is missing, expired, or revoked.")
        user = self.session.get(UserRecord, record.user_id)
        if user is None or not user.active:
            raise AuthenticationRequired("The user account is unavailable.")
        membership = None
        if record.active_organisation_id:
            membership = self.session.scalar(select(OrganisationMembershipRecord).join(OrganisationRecord).where(
                OrganisationMembershipRecord.user_id == user.id,
                OrganisationMembershipRecord.organisation_id == record.active_organisation_id,
                OrganisationRecord.active.is_(True),
            ))
            if membership is None:
                record.active_organisation_id = None
        if touch:
            record.last_activity_at = now
            self.session.commit()
        return user, record, membership

    def tenant_context(self, raw_session: str | None) -> TenantContext:
        _, record, membership = self.authenticate(raw_session)
        if membership is None:
            raise OrganisationRequired()
        return TenantContext(record.user_id, membership.organisation_id, MembershipRole(membership.role), record.id)

    def login_identity(self, claims: dict[str, object]) -> tuple[str, str]:
        issuer, subject = str(claims["iss"]), str(claims["sub"])
        email = normalise_email(str(claims.get("email") or ""))
        if not email:
            raise AuthenticationRequired("The identity provider did not supply an email address.")
        display_name = str(claims.get("name") or claims.get("preferred_username") or email)[:200]
        now = utc_now()
        identity = self.session.scalar(select(ExternalIdentityRecord).where(ExternalIdentityRecord.issuer == issuer, ExternalIdentityRecord.subject == subject))
        if identity is None:
            user = self.session.scalar(select(UserRecord).where(UserRecord.email == email))
            if user is not None:
                # Never auto-link a new provider subject by a mutable email claim.
                raise AuthenticationRequired("This email is already associated with another external identity.")
            user = UserRecord(email=email, display_name=display_name)
            self.session.add(user)
            self.session.flush()
            self.session.add(ExternalIdentityRecord(user_id=user.id, issuer=issuer, subject=subject))
        else:
            user = self.session.get(UserRecord, identity.user_id)
            if user is None:
                raise AuthenticationRequired()
        if not user.active:
            raise AuthenticationRequired("The user account is disabled.")
        email_owner = self.session.scalar(select(UserRecord).where(UserRecord.email == email, UserRecord.id != user.id))
        if email_owner is not None:
            raise AuthenticationRequired("This email is already associated with another external identity.")
        user.email, user.display_name, user.last_login_at, user.updated_at = email, display_name, now, now
        membership = self.session.scalar(select(OrganisationMembershipRecord).where(OrganisationMembershipRecord.user_id == user.id).order_by(OrganisationMembershipRecord.created_at))
        raw_session, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
        self.session.add(UserSessionRecord(
            session_hash=self._digest(raw_session), csrf_token_hash=self._digest(csrf), user_id=user.id,
            active_organisation_id=membership.organisation_id if membership else None,
            expires_at=now + timedelta(seconds=self.session_seconds),
        ))
        self.session.commit()
        return raw_session, csrf

    def revoke_session(self, raw_session: str) -> None:
        record = self.session.scalar(select(UserSessionRecord).where(UserSessionRecord.session_hash == self._digest(raw_session)))
        if record is not None and record.revoked_at is None:
            record.revoked_at = utc_now()
            self.session.commit()

    def validate_csrf(self, raw_session: str | None, csrf_cookie: str | None, csrf_header: str | None) -> None:
        _, record, _ = self.authenticate(raw_session, touch=False)
        if not csrf_cookie or not csrf_header or not secrets.compare_digest(csrf_cookie, csrf_header) or not secrets.compare_digest(record.csrf_token_hash, self._digest(csrf_header)):
            from app.identity.errors import CsrfFailed
            raise CsrfFailed()

    def session_view(self, raw_session: str) -> dict[str, object]:
        user, record, active = self.authenticate(raw_session)
        memberships = list(self.session.scalars(select(OrganisationMembershipRecord).join(OrganisationRecord).where(OrganisationMembershipRecord.user_id == user.id, OrganisationRecord.active.is_(True)).order_by(OrganisationRecord.name)))
        organisations = [{"id": item.organisation.id, "name": item.organisation.name, "slug": item.organisation.slug, "role": item.role} for item in memberships]
        current = next((item for item in organisations if item["id"] == record.active_organisation_id), None)
        return {"auth_enabled": True, "authenticated": True, "user": {"id": user.id, "email": user.email, "display_name": user.display_name}, "active_organisation": current, "organisations": organisations}

    def create_organisation(self, user_id: str, session_id: str, name: str, slug: str) -> dict[str, object]:
        if self.session.scalar(select(OrganisationRecord).where(OrganisationRecord.slug == slug)):
            raise PermissionDenied("That organisation slug is already in use.")
        organisation = OrganisationRecord(name=name.strip(), slug=slug)
        self.session.add(organisation); self.session.flush()
        self.session.add(OrganisationMembershipRecord(organisation_id=organisation.id, user_id=user_id, role=MembershipRole.OWNER.value))
        session_record = self.session.get(UserSessionRecord, session_id)
        session_record.active_organisation_id = organisation.id
        self.session.commit()
        return {"id": organisation.id, "name": organisation.name, "slug": organisation.slug, "role": "OWNER"}

    def switch_organisation(self, user_id: str, session_id: str, organisation_id: str) -> None:
        membership = self.session.scalar(select(OrganisationMembershipRecord).where(OrganisationMembershipRecord.user_id == user_id, OrganisationMembershipRecord.organisation_id == organisation_id))
        if membership is None:
            raise IdentityResourceNotFound()
        self.session.get(UserSessionRecord, session_id).active_organisation_id = organisation_id
        self.session.commit()

    def _owner(self, context: TenantContext) -> None:
        if context.role != MembershipRole.OWNER:
            raise PermissionDenied()

    def members(self, context: TenantContext) -> list[dict[str, object]]:
        rows = self.session.execute(select(OrganisationMembershipRecord, UserRecord).join(UserRecord, UserRecord.id == OrganisationMembershipRecord.user_id).where(OrganisationMembershipRecord.organisation_id == context.organisation_id).order_by(UserRecord.email)).all()
        return [{"user_id": user.id, "email": user.email, "display_name": user.display_name, "role": membership.role, "joined_at": membership.created_at} for membership, user in rows]

    def invite(self, context: TenantContext, email: str, role: str) -> tuple[InvitationRecord, str]:
        self._owner(context)
        raw = secrets.token_urlsafe(48)
        invitation = InvitationRecord(organisation_id=context.organisation_id, invited_email=normalise_email(email), invited_role=role, token_hash=self._digest(raw), inviter_user_id=context.user_id, expires_at=utc_now() + timedelta(hours=self.invitation_hours))
        self.session.add(invitation); self.session.commit()
        return invitation, raw

    def invitations(self, context: TenantContext) -> list[InvitationRecord]:
        self._owner(context)
        return list(self.session.scalars(select(InvitationRecord).where(InvitationRecord.organisation_id == context.organisation_id).order_by(InvitationRecord.created_at.desc())))

    def revoke_invitation(self, context: TenantContext, invitation_id: str) -> None:
        self._owner(context)
        invitation = self.session.scalar(select(InvitationRecord).where(InvitationRecord.id == invitation_id, InvitationRecord.organisation_id == context.organisation_id))
        if invitation is None or invitation.accepted_at is not None or invitation.revoked_at is not None:
            raise InvitationUnavailable()
        invitation.revoked_at = utc_now(); self.session.commit()

    def accept_invitation(self, user_id: str, raw_token: str, session_id: str) -> str:
        invitation = self.session.scalar(select(InvitationRecord).where(InvitationRecord.token_hash == self._digest(raw_token)))
        user = self.session.get(UserRecord, user_id)
        now = utc_now()
        if invitation is None or user is None or invitation.accepted_at is not None or invitation.revoked_at is not None or is_expired(invitation.expires_at) or invitation.invited_email != normalise_email(user.email):
            raise InvitationUnavailable()
        existing = self.session.scalar(select(OrganisationMembershipRecord).where(OrganisationMembershipRecord.organisation_id == invitation.organisation_id, OrganisationMembershipRecord.user_id == user_id))
        if existing is None:
            self.session.add(OrganisationMembershipRecord(organisation_id=invitation.organisation_id, user_id=user_id, role=invitation.invited_role))
        invitation.accepted_at = now
        self.session.get(UserSessionRecord, session_id).active_organisation_id = invitation.organisation_id
        self.session.commit()
        return invitation.organisation_id

    def update_member_role(self, context: TenantContext, user_id: str, role: str) -> None:
        self._owner(context)
        member = self.session.scalar(select(OrganisationMembershipRecord).where(OrganisationMembershipRecord.organisation_id == context.organisation_id, OrganisationMembershipRecord.user_id == user_id))
        if member is None:
            raise IdentityResourceNotFound()
        if member.role == "OWNER" and role != "OWNER" and self._owner_count(context.organisation_id) == 1:
            raise PermissionDenied("The final OWNER cannot be demoted.")
        member.role = role; member.updated_at = utc_now(); self.session.commit()

    def remove_member(self, context: TenantContext, user_id: str) -> None:
        self._owner(context)
        member = self.session.scalar(select(OrganisationMembershipRecord).where(OrganisationMembershipRecord.organisation_id == context.organisation_id, OrganisationMembershipRecord.user_id == user_id))
        if member is None:
            raise IdentityResourceNotFound()
        if member.role == "OWNER" and self._owner_count(context.organisation_id) == 1:
            raise PermissionDenied("The final OWNER cannot be removed.")
        self.session.delete(member)
        for record in self.session.scalars(select(UserSessionRecord).where(UserSessionRecord.user_id == user_id, UserSessionRecord.active_organisation_id == context.organisation_id)):
            record.active_organisation_id = None
        self.session.commit()

    def _owner_count(self, organisation_id: str) -> int:
        return int(self.session.scalar(select(func.count()).select_from(OrganisationMembershipRecord).where(OrganisationMembershipRecord.organisation_id == organisation_id, OrganisationMembershipRecord.role == "OWNER")) or 0)
