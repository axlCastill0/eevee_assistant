import os

from fastapi import Header, HTTPException, status

API_KEY_HEADER = "X-API-Key"

def require_api_key(x_api_key: str | None = Header(default=None, alias=API_KEY_HEADER)):
    """Reject requests lacking a valid API key header.

    The expected key is read from the API_KEY environment variable (loaded
    from a .env file if present).
    """
    expected = os.environ.get("API_KEY")

    if not expected:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server API key not configured",
        )

    if not x_api_key or x_api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": API_KEY_HEADER},
        )

    return x_api_key
