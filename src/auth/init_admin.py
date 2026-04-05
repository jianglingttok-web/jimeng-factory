from __future__ import annotations

import logging
import os

from src.auth.password import hash_password
from src.models.user import UserRole
from src.runtime.user_store import UserStore

logger = logging.getLogger(__name__)

_DEFAULT_PASSWORD = "changeme123"
_ENV_VAR = "JIMENG_ADMIN_PASSWORD"


def ensure_admin_user(user_store: UserStore) -> None:
    """Ensure at least one admin user exists in the database.

    Password priority:
    1. Environment variable JIMENG_ADMIN_PASSWORD
    2. Default "changeme123" (logs a warning urging rotation)

    Safe to call multiple times — does nothing if an admin already exists.
    """
    users = user_store.list_users()
    admin_exists = any(u.role == UserRole.admin for u in users)
    if admin_exists:
        return

    password = os.environ.get(_ENV_VAR)
    if password:
        logger.info("Creating default admin user with password from %s.", _ENV_VAR)
    else:
        password = _DEFAULT_PASSWORD
        logger.warning(
            "No %s environment variable set. "
            "Creating default admin with password '%s'. "
            "CHANGE THIS IMMEDIATELY after first login.",
            _ENV_VAR,
            _DEFAULT_PASSWORD,
        )

    user_store.create_user(
        username="admin",
        hashed_password=hash_password(password),
        role=UserRole.admin,
        is_active=True,
    )
    logger.info("Default admin user created.")
