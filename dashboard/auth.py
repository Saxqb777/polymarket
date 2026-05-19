"""
HTTP Basic Auth dependency for the SwingBot dashboard.

Username is hardcoded as "saaqib".
Password is read from the DASHBOARD_PASSWORD env var (required).
"""
import os
import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from dotenv import load_dotenv

load_dotenv()

_security = HTTPBasic()

_USERNAME = "saaqib"
_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "")

if not _PASSWORD:
    raise RuntimeError(
        "DASHBOARD_PASSWORD is not set. "
        "Add it to your .env file before starting the dashboard."
    )


def require_auth(credentials: HTTPBasicCredentials = Depends(_security)) -> str:
    """
    FastAPI dependency — gate any route behind HTTP Basic Auth.
    Returns the username on success; raises 401 on failure.
    Uses secrets.compare_digest to prevent timing attacks.
    """
    user_ok = secrets.compare_digest(credentials.username.encode(), _USERNAME.encode())
    pass_ok = secrets.compare_digest(credentials.password.encode(), _PASSWORD.encode())

    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": 'Basic realm="SwingBot Dashboard"'},
        )
    return credentials.username
