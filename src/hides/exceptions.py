from src.exceptions import Conflict, NotFound


class HiddenContactNotFound(NotFound):
    code = "hidden_contact_not_found"


class HideListFull(Conflict):
    code = "hide_list_full"
