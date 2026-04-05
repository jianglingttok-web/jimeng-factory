from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from src.auth.password import hash_password, verify_password
from src.auth.token import create_access_token
from src.models.user import User, UserRole
from src.web.dependencies import get_current_user, require_admin

auth_router = APIRouter(prefix="/api/auth")


# ── Request / Response models ─────────────────────────────────────────────────

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserPublic(BaseModel):
    username: str
    role: UserRole
    is_active: bool


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str = "operator"


# ── Routes ────────────────────────────────────────────────────────────────────

@auth_router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
) -> TokenResponse:
    """Authenticate user and return JWT access token."""
    config = request.app.state.config
    user_store = request.app.state.user_store

    user = user_store.get_user_by_username(form_data.username)
    if user is None or not user.is_active or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(
        data={"sub": user.username},
        secret_key=config.auth.secret_key,
        algorithm=config.auth.algorithm,
        expires_delta_minutes=config.auth.token_expire_minutes,
    )
    return TokenResponse(access_token=token)


@auth_router.get("/me", response_model=UserPublic)
async def get_me(current_user: User = Depends(get_current_user)) -> UserPublic:
    """Return current authenticated user info (without hashed_password)."""
    return UserPublic(
        username=current_user.username,
        role=current_user.role,
        is_active=current_user.is_active,
    )


@auth_router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Change the authenticated user's password."""
    if not verify_password(body.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_store = request.app.state.user_store
    user_store.update_user(
        current_user.username,
        hashed_password=hash_password(body.new_password),
    )
    return {"message": "Password updated successfully"}


@auth_router.post("/users", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: CreateUserRequest,
    request: Request,
    _admin: User = Depends(require_admin),
) -> UserPublic:
    """Create a new user (admin only)."""
    import sqlite3

    user_store = request.app.state.user_store
    try:
        user = user_store.create_user(
            username=body.username,
            hashed_password=hash_password(body.password),
            role=body.role,
            is_active=True,
        )
    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"User '{body.username}' already exists",
        )
    return UserPublic(username=user.username, role=user.role, is_active=user.is_active)


@auth_router.get("/users", response_model=list[UserPublic])
async def list_users(
    request: Request,
    _admin: User = Depends(require_admin),
) -> list[UserPublic]:
    """List all users (admin only)."""
    user_store = request.app.state.user_store
    users = user_store.list_users()
    return [UserPublic(username=u.username, role=u.role, is_active=u.is_active) for u in users]
