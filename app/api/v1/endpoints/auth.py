from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.config import settings
from app.core.security import create_access_token, set_auth_cookie, delete_auth_cookie
from app.db.session import get_async_db
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    TokenResponse,
    MessageResponse,
)
from app.schemas.user import UserResponse
from app.services.auth_service import (
    authenticate_user,
    register_customer_user,
    request_password_reset,
    reset_password_with_token,
    AuthenticationError,
    TenantInactiveError,
    UserInactiveError,
    RegistrationError,
    ResetPasswordError,
)
from app.services.password_service import PasswordValidationError

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    db: AsyncSession = Depends(get_async_db),
):
    """
    Public registration endpoint.
    Creates a Customer-role user in the specified (or default) tenant.
    Never allows public registration of Admin or Staff roles.
    """
    try:
        user = await register_customer_user(
            session=db,
            full_name=payload.full_name,
            email=payload.email,
            password=payload.password,
            organization_slug=payload.organization_slug,
        )
        return user
    except PasswordValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except RegistrationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_async_db),
):
    """
    Authenticates user and returns JWT token.
    Sets secure HTTP-only cookie.
    """
    try:
        user = await authenticate_user(
            session=db,
            email=payload.email,
            password=payload.password,
        )
    except UserInactiveError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except TenantInactiveError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except AuthenticationError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    access_token = create_access_token(
        subject=str(user.id),
        organization_id=user.organization_id,
        role=user.role.value,
    )

    set_auth_cookie(response, access_token)

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/logout", response_model=MessageResponse)
async def logout(response: Response):
    """
    Logs out user by clearing the HTTP-only authentication cookie.
    """
    delete_auth_cookie(response)
    return MessageResponse(message="Successfully logged out.")


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """
    Returns profile of the currently authenticated user.
    """
    return current_user


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(
    payload: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_async_db),
):
    """
    Initiates password reset flow.
    Returns generic success message to prevent account enumeration.
    In development mode with simulation enabled, returns the reset token.
    """
    raw_token = await request_password_reset(db, payload.email)

    dev_token = None
    if settings.ENABLE_DEV_PASSWORD_RESET_SIMULATION and not settings.is_production:
        dev_token = raw_token

    return MessageResponse(
        message="If this email is registered, password reset instructions have been sent.",
        dev_token=dev_token,
    )


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
    payload: ResetPasswordRequest,
    db: AsyncSession = Depends(get_async_db),
):
    """
    Validates reset token and sets new password.
    Invalidates token upon success.
    """
    try:
        await reset_password_with_token(
            session=db,
            token=payload.token,
            new_password=payload.new_password,
        )
        return MessageResponse(message="Password reset successfully. You can now log in.")
    except PasswordValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except ResetPasswordError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

