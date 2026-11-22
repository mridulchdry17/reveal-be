from src.exceptions import Conflict, NotFound


class AccountNotFound(NotFound):
    code = "account_not_found"


class AlreadyVerified(Conflict):
    code = "already_verified"
