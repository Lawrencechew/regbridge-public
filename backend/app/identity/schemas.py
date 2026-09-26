from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class IdentityModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UserView(IdentityModel):
    id: str
    email: str
    display_name: str


class OrganisationView(IdentityModel):
    id: str
    name: str
    slug: str
    role: Literal["OWNER", "MEMBER"]


class SessionView(IdentityModel):
    auth_enabled: bool = True
    authenticated: bool
    user: UserView | None = None
    active_organisation: OrganisationView | None = None
    organisations: tuple[OrganisationView, ...] = ()


class CreateOrganisationRequest(IdentityModel):
    name: str = Field(min_length=2, max_length=200)
    slug: str = Field(min_length=2, max_length=100, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class SwitchOrganisationRequest(IdentityModel):
    organisation_id: str = Field(min_length=36, max_length=36)


class MemberView(IdentityModel):
    user_id: str
    email: str
    display_name: str
    role: Literal["OWNER", "MEMBER"]
    joined_at: datetime


class InviteRequest(IdentityModel):
    email: str = Field(min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    role: Literal["OWNER", "MEMBER"] = "MEMBER"


class InvitationView(IdentityModel):
    id: str
    invited_email: str
    invited_role: Literal["OWNER", "MEMBER"]
    expires_at: datetime
    state: Literal["PENDING", "ACCEPTED", "REVOKED", "EXPIRED"]
    invitation_token: str | None = None


class AcceptInvitationRequest(IdentityModel):
    token: str = Field(min_length=32, max_length=500)


class UpdateMemberRoleRequest(IdentityModel):
    role: Literal["OWNER", "MEMBER"]
