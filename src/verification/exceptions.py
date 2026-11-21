from src.exceptions import Conflict, DomainError


class AlreadyVerified(Conflict):
    code = "already_verified"


class AlreadySubmitted(Conflict):
    code = "already_submitted"


class PhotoTooLarge(DomainError):
    status_code = 413
    code = "photo_too_large"


class NotAPhoto(DomainError):
    status_code = 422
    code = "not_a_photo"
