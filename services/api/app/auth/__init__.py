from .service import (
    LOGIN_TOKEN_MINUTES,
    SESSION_DAYS,
    AuthError,
    LoggedIn,
    MagicLink,
    logout,
    normalize_email,
    request_login,
    revoke_all,
    student_for_token,
    verify_login,
)

__all__ = [
    "LOGIN_TOKEN_MINUTES",
    "SESSION_DAYS",
    "AuthError",
    "LoggedIn",
    "MagicLink",
    "logout",
    "normalize_email",
    "request_login",
    "revoke_all",
    "student_for_token",
    "verify_login",
]
