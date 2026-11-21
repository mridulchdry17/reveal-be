from src.exceptions import Conflict, DomainError


class NotCollegeAccount(DomainError):
    status_code = 403
    code = "not_college_account"


class CollegeEmailTaken(Conflict):
    code = "college_email_taken"
