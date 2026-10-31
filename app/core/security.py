from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
import jwt
from fastapi import HTTPException, Response, status
from app.core.config import settings


def create_access_token(
    subject: str,
    organization_id: int,
    role: str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Creates a signed JWT access token.
    Subject is typically the user ID (as a string).
    """
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode: Dict[str, Any] = {
        "sub": str(subject),
        "org": organization_id,
        "role": str(role),
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }

    return jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> Dict[str, Any]:
    """
    Decodes and validates a JWT token signature and expiration.
    Raises HTTPException(401) on invalid or expired token.
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def set_auth_cookie(response: Response, token: str) -> None:
    """
    Sets the JWT in a secure HTTP-only cookie.
    """
    max_age = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    response.set_cookie(
        key=settings.COOKIE_NAME,
        value=token,
        max_age=max_age,
        expires=max_age,
        httponly=settings.COOKIE_HTTPONLY,
        secure=settings.resolved_cookie_secure,
        samesite=settings.COOKIE_SAMESITE,
        path="/",
    )


def delete_auth_cookie(response: Response) -> None:
    """
    Clears the authentication cookie.
    """
    response.delete_cookie(
        key=settings.COOKIE_NAME,
        httponly=settings.COOKIE_HTTPONLY,
        secure=settings.resolved_cookie_secure,
        samesite=settings.COOKIE_SAMESITE,
        path="/",
    )

