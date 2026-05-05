from hmac import compare_digest
from typing import Annotated, Optional

from fastapi import Header, HTTPException, status

from app.core.config import settings


def require_admin_token(
    x_admin_token: Annotated[Optional[str], Header(alias="X-Admin-Token")] = None,
) -> None:
    expected_token = settings.ADMIN_TOKEN
    if not x_admin_token or not expected_token or not compare_digest(x_admin_token, expected_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing admin token",
        )
