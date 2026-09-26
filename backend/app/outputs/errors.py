from app.outputs.models import OutputIssueCode


class OutputGenerationError(Exception):
    def __init__(self, code: OutputIssueCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class OutputRequestError(Exception):
    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
