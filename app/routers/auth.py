from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from starlette.concurrency import run_in_threadpool

from app.config import Settings, get_settings
from app.models import User, UserSession
from app.routers.common import SessionId
from app.schemas import CurrentUserOut, EmailPassword, EmailRequest, EmailVerification
from app.security import (
    SESSION_COOKIE_NAME,
    CurrentUser,
    DatabaseSession,
    expires_in,
    hash_password,
    new_token,
    verify_password,
)
from app.services.mailer import send_verification_email

router = APIRouter(prefix="/api/auth", tags=["Auth"])
AppSettings = Annotated[Settings, Depends(get_settings)]


@router.get("/me", response_model=CurrentUserOut, operation_id="getCurrentUser")
async def get_current_user(current_user: CurrentUser) -> User:
    return current_user


@router.post("/register", status_code=status.HTTP_201_CREATED, operation_id="register")
async def register(
    payload: EmailPassword,
    db: DatabaseSession,
    settings: AppSettings,
) -> Response:
    email = payload.email.lower()
    if await db.scalar(select(User.id).where(User.email == email)) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    verification_token = new_token()
    user = User(
        email=email,
        password_hash=await run_in_threadpool(hash_password, payload.password),
        verification_token=verification_token,
        verification_token_expires_at=expires_in(settings.verification_token_ttl_seconds),
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        ) from error
    await send_verification_email(email, verification_token, settings)
    return Response(status_code=status.HTTP_201_CREATED)


@router.post("/login", status_code=status.HTTP_204_NO_CONTENT, operation_id="login")
async def login(
    payload: EmailPassword,
    response: Response,
    db: DatabaseSession,
    settings: AppSettings,
) -> None:
    user = await db.scalar(select(User).where(User.email == payload.email.lower()))
    password_is_valid = user is not None and await run_in_threadpool(
        verify_password, payload.password, user.password_hash
    )
    if user is None or not password_is_valid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_verified:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Email not verified")

    session = UserSession(
        id=new_token(),
        user_id=user.id,
        expires_at=expires_in(settings.session_ttl_seconds),
    )
    db.add(session)
    await db.commit()
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session.id,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.session_ttl_seconds,
    )


@router.post("/verify-email", status_code=status.HTTP_204_NO_CONTENT, operation_id="verifyEmail")
async def verify_email(payload: EmailVerification, db: DatabaseSession) -> None:
    user = await db.scalar(
        select(User).where(
            User.verification_token == payload.token,
            User.verification_token_expires_at > datetime.now(UTC),
        )
    )
    if user is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token")

    user.is_verified = True
    user.verification_token = None
    user.verification_token_expires_at = None
    await db.commit()


@router.post(
    "/verification-token/refresh",
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="refreshEmailVerificationToken",
)
async def refresh_verification_token(
    payload: EmailRequest,
    db: DatabaseSession,
    settings: AppSettings,
) -> Response:
    user = await db.scalar(select(User).where(User.email == payload.email.lower()))
    if user is not None and not user.is_verified:
        verification_token = new_token()
        user.verification_token = verification_token
        user.verification_token_expires_at = expires_in(settings.verification_token_ttl_seconds)
        await db.commit()
        await send_verification_email(user.email, verification_token, settings)
    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, operation_id="logout")
async def logout(
    response: Response,
    session_id: SessionId,
    db: DatabaseSession,
    current_user: CurrentUser,
    settings: AppSettings,
) -> None:
    del current_user
    if session_id is not None:
        await db.execute(delete(UserSession).where(UserSession.id == session_id))
        await db.commit()
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )
