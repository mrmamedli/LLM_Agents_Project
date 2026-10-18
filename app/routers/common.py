from typing import Annotated, NoReturn

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyCookie

cookie_scheme = APIKeyCookie(name="session_id", scheme_name="CookieAuth", auto_error=False)
SessionId = Annotated[str | None, Security(cookie_scheme)]


def not_implemented() -> NoReturn:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="This endpoint is not implemented yet",
    )
