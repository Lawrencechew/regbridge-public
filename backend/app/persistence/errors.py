class PersistenceError(Exception):
    code = "PERSISTENCE_ERROR"
    status_code = 500
    message = "RegBridge could not persist the workflow update."

    def __init__(self, message: str | None = None, *, metadata: dict | None = None) -> None:
        super().__init__(message or self.message)
        self.message = message or self.message
        self.metadata = metadata or {}


class RunNotFoundError(PersistenceError):
    code = "RUN_NOT_FOUND"
    status_code = 404
    message = "The requested RegFlow run was not found."


class RunRevisionConflictError(PersistenceError):
    code = "RUN_REVISION_CONFLICT"
    status_code = 409
    message = "The RegFlow run changed. Refresh its current state before continuing."


class InvalidRunTransitionError(PersistenceError):
    code = "INVALID_RUN_TRANSITION"
    status_code = 409
    message = "The RegFlow run is not ready for this operation."


class MappingProfileNotFoundError(PersistenceError):
    code = "MAPPING_PROFILE_NOT_FOUND"
    status_code = 404
    message = "The requested mapping profile was not found."


class MappingProfileStaleError(PersistenceError):
    code = "MAPPING_PROFILE_STALE"
    status_code = 409
    message = "The mapping profile is not compatible with the current run."


class IdempotencyKeyReuseError(PersistenceError):
    code = "IDEMPOTENCY_KEY_REUSE"
    status_code = 409
    message = "The idempotency key was already used for a different request."


class RegPackIntegrityError(PersistenceError):
    code = "REGPACK_VERSION_UNAVAILABLE"
    status_code = 409
    message = "The exact RegPack version used by this run is unavailable."


class PersistenceUnavailableError(PersistenceError):
    code = "PERSISTENCE_UNAVAILABLE"
    status_code = 503
    message = "Workflow persistence is temporarily unavailable."
