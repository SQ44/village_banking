from __future__ import annotations

import hmac
from hashlib import sha256
from typing import Any, Dict, Optional

import httpx

from .config import get_settings


class LencoPayClient:
    """Client used by the village-banking API to trigger Lenco operations.

    If `lenco_pay_base` is configured, calls are proxied through the local `lenco_pay`
    service (recommended). Otherwise, calls are sent directly to the upstream Lenco API.
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self.base_url = self.settings.lenco_api_base.rstrip("/")
        self.lenco_pay_base = self.settings.lenco_pay_base.rstrip("/")

    def _headers(self) -> Dict[str, str]:
        key = self.settings.lenco_api_key
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = f"Bearer {key}"
        return headers

    def _target_base(self) -> str:
        return self.lenco_pay_base or self.base_url

    async def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self.settings.lenco_api_key:
            # Simulate a response in development so flows can be tested offline.
            return {
                "simulated": True,
                "via": "lenco_pay" if self.lenco_pay_base else "upstream",
                "path": path,
                "payload": payload,
                "status": "queued",
            }
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{self._target_base()}{path}",
                headers=self._headers(),
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    async def create_transfer(
        self,
        *,
        amount: float,
        reference: str,
        recipient_account_number: str,
        recipient_bank_code: str,
        recipient_name: str,
        currency: str = "ZMW",
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        if self.lenco_pay_base:
            payload = {
                "amount": amount,
                "currency": currency,
                "recipient_account_number": recipient_account_number,
                "recipient_bank_code": recipient_bank_code,
                "recipient_name": recipient_name,
                "description": description,
                "reference": reference,
            }
            return await self._post("/transfers/initiate", payload)

        payload = {"amount": amount, "reference": reference, "account_number": recipient_account_number}
        return await self._post("/transfers", payload)

    async def collect_payment(
        self,
        *,
        amount: float,
        reference: str,
        customer_email: Optional[str] = None,
        customer_phone: Optional[str] = None,
        customer_name: Optional[str] = None,
        currency: str = "ZMW",
        description: str = "Village Banking collection",
        callback_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not customer_email and customer_phone:
            normalized = "".join(ch for ch in customer_phone if ch.isdigit()) or "unknown"
            customer_email = f"phone_{normalized}@example.com"

        if self.lenco_pay_base:
            payload = {
                "amount": amount,
                "currency": currency,
                "description": description,
                "customer_email": customer_email,
                "customer_name": customer_name,
                "reference": reference,
                "callback_url": callback_url,
            }
            return await self._post("/payments/initiate", payload)

        payload: Dict[str, Any] = {"amount": amount, "reference": reference}
        if customer_phone:
            payload["customer_phone"] = customer_phone
        if customer_email:
            payload["customer_email"] = customer_email
        return await self._post("/collections", payload)

    def verify_webhook(self, payload: bytes, signature: str) -> bool:
        secret = self.settings.lenco_webhook_secret
        if not secret:
            # Without a configured secret we treat payloads as trusted for local dev.
            return True
        digest = hmac.new(secret.encode(), payload, sha256).hexdigest()
        return hmac.compare_digest(digest, signature)
