import uuid

from pydantic import BaseModel, Field


class GoogleSignInRequest(BaseModel):
    credential: str = Field(
        min_length=1, max_length=4096, description="ID token from Google Identity Services"
    )


class Me(BaseModel):
    id: uuid.UUID
    email: str
    name: str
    is_admin: bool


class SignInResponse(BaseModel):
    token: str = Field(description="Send as 'Authorization: Bearer <token>'")
    user: Me
