from src.exceptions import Conflict


class AlreadyRegistered(Conflict):
    code = "already_registered"
