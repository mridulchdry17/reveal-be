from src.exceptions import Conflict, NotFound


class ProfileIncomplete(Conflict):
    code = "profile_incomplete"


class PromptNotFound(NotFound):
    code = "prompt_not_found"
