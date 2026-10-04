from fastapi import APIRouter, Depends

from auth import require_api_key

router = APIRouter()


@router.get("/health", dependencies=[Depends(require_api_key)])
def voice_health():
    return {"status": "ok", "route": "voice"}
