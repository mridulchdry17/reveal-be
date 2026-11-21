import uuid

from pydantic import BaseModel, Field

from src.auth.constants import VerificationMethod


class GoogleSignInRequest(BaseModel):
    credential: str = Field(
        min_length=1, max_length=4096, description="ID token from Google Identity Services"
    )


class CollegeEmailRequest(GoogleSignInRequest):
    """A credential for the user's college Google account (not the one they signed in with)."""


class Me(BaseModel):
    id: uuid.UUID
    email: str
    name: str
    is_admin: bool
    verified: bool = Field(description="Proved they're a student at the college")
    verified_via: VerificationMethod | None


class SignInResponse(BaseModel):
    token: str = Field(description="Send as 'Authorization: Bearer <token>'")
    user: Me
