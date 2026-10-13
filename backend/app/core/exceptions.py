class AppError(Exception):
    """Base class for expected application errors mapped to HTTP responses."""

    status_code = 400

    def __init__(self, detail: str = "Error") -> None:
        self.detail = detail
        super().__init__(detail)


class UnauthorizedError(AppError):
    status_code = 401


class ForbiddenError(AppError):
    status_code = 403


class NotFoundError(AppError):
    status_code = 404


class ConflictError(AppError):
    status_code = 409


class PayloadTooLargeError(AppError):
    status_code = 413


class ValidationError(AppError):
    status_code = 422
