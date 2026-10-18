from fastapi import APIRouter, Response, status

from app.routers.common import SessionId, not_implemented
from app.schemas import EmailPassword, EmailRequest, EmailVerification

router = APIRouter(prefix="/api/auth", tags=["Auth"])


@router.post("/register", status_code=status.HTTP_201_CREATED, operation_id="register")
async def register(payload: EmailPassword) -> Response:
    del payload
    not_implemented()


@router.post("/login", status_code=status.HTTP_204_NO_CONTENT, operation_id="login")
async def login(payload: EmailPassword) -> None:
    del payload
    not_implemented()


@router.post("/verify-email", status_code=status.HTTP_204_NO_CONTENT, operation_id="verifyEmail")
async def verify_email(payload: EmailVerification) -> None:
    del payload
    not_implemented()


@router.post(
    "/verification-token/refresh",
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="refreshEmailVerificationToken",
)
async def refresh_verification_token(payload: EmailRequest) -> Response:
    del payload
    not_implemented()


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, operation_id="logout")
async def logout(session_id: SessionId) -> None:
    del session_id
    not_implemented()
