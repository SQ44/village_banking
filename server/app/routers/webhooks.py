import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlmodel import Session

from ..config import get_settings
from ..database import get_session
from ..lipila import service as lipila
from ..lipila.security import verify_lipila_signature

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])

# Lipila posts a small JSON body. Anything larger is not one of its events, and
# is refused before it is parsed.
MAX_WEBHOOK_BODY_BYTES = 262_144


@router.post("/lipila")
async def lipila_webhook(
    request: Request,
    session: Session = Depends(get_session),
) -> JSONResponse:
    """Receive a payment update from Lipila.

    Unauthenticated by design — Lipila cannot carry a session — so the HMAC
    signature is the only thing that makes this endpoint safe. Nothing is
    recorded or applied until it verifies.
    """
    settings = get_settings()
    if not settings.lipila_webhook_secret_current:
        raise HTTPException(status_code=503, detail="webhook secret is not configured")

    raw_body = await request.body()
    if len(raw_body) > MAX_WEBHOOK_BODY_BYTES:
        raise HTTPException(status_code=413, detail="request_body_too_large")

    headers = {key: value for key, value in request.headers.items()}
    if not verify_lipila_signature(raw_body, headers, settings):
        raise HTTPException(status_code=401, detail="invalid_webhook_signature")

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="invalid_json") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="invalid_webhook_payload")

    webhook_id = request.headers.get("webhook-id")
    webhook_timestamp = request.headers.get("webhook-timestamp")
    if not webhook_id or not webhook_timestamp:
        raise HTTPException(status_code=400, detail="missing_webhook_headers")

    outcome = lipila.process_webhook(session, payload, webhook_id, webhook_timestamp)
    return JSONResponse({"status": outcome, "provider": "lipila"}, status_code=202)
