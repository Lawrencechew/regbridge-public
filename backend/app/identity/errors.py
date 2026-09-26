class IdentityError(Exception):
    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class AuthenticationRequired(IdentityError):
    def __init__(self, message: str = "Authentication is required.") -> None:
        super().__init__("AUTHENTICATION_REQUIRED", message, 401)


class PermissionDenied(IdentityError):
    def __init__(self, message: str = "You do not have permission to perform this action.") -> None:
        super().__init__("PERMISSION_DENIED", message, 403)


class CsrfFailed(IdentityError):
    def __init__(self) -> None:
        super().__init__("CSRF_VALIDATION_FAILED", "The CSRF token is missing or invalid.", 403)


class InvalidOidcResponse(IdentityError):
    def __init__(self, message: str = "The identity provider response could not be validated.") -> None:
        super().__init__("OIDC_VALIDATION_FAILED", message, 400)


class InvitationUnavailable(IdentityError):
    def __init__(self) -> None:
        super().__init__("INVITATION_UNAVAILABLE", "The invitation is invalid or unavailable.", 404)


class OrganisationRequired(IdentityError):
    def __init__(self) -> None:
        super().__init__("ORGANISATION_REQUIRED", "Create or join an organisation to continue.", 409)


class IdentityResourceNotFound(IdentityError):
    def __init__(self) -> None:
        super().__init__("RESOURCE_NOT_FOUND", "The requested resource was not found.", 404)
