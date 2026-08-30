from decimal import Decimal
from typing import Any, Optional

import httpx

from ..config import Settings


class LipilaError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        payload: Optional[dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload or {}


class LipilaClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.base_url = settings.safe_lipila_base_url
        self.headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "x-api-key": settings.lipila_api_key,
        }
        self.timeout = httpx.Timeout(settings.lipila_timeout_seconds)

    # ------------------------------------------------------------------
    # Collections: money coming in from a member.
    # ------------------------------------------------------------------

    async def create_mobile_money_collection(
        self,
        *,
        reference_id: str,
        amount_major: Decimal,
        account_number: str,
        currency: str,
        email: Optional[str],
        narration: str,
        reference_data: str,
        callback_url: str,
    ) -> dict[str, Any]:
        return await self._post(
            "/api/v1/collections/mobile-money",
            {
                "referenceId": reference_id,
                "amount": _decimal_json(amount_major),
                "narration": narration,
                "accountNumber": account_number,
                "currency": currency,
                "email": email,
                "referenceData": reference_data,
            },
            extra_headers={"callbackUrl": callback_url},
        )

    async def create_card_collection(
        self,
        *,
        reference_id: str,
        amount_major: Decimal,
        account_number: str,
        currency: str,
        email: Optional[str],
        member_name: Optional[str],
        narration: str,
        reference_data: str,
        back_url: str,
    ) -> dict[str, Any]:
        first_name, last_name = _split_name(member_name)
        return await self._post(
            "/api/v1/collections/card",
            {
                "customerInfo": {
                    "firstName": first_name,
                    "lastName": last_name,
                    "phoneNumber": account_number,
                    "city": "Lusaka",
                    "country": "ZM",
                    "address": "Not provided",
                    "email": email,
                    "zip": "10101",
                },
                "collectionRequest": {
                    "referenceId": reference_id,
                    "amount": _decimal_json(amount_major),
                    "narration": narration,
                    "accountNumber": account_number,
                    "currency": currency,
                    "backUrl": back_url,
                    "referenceData": reference_data,
                },
            },
        )

    async def check_collection_status(self, *, reference_id: str) -> dict[str, Any]:
        return await self._get("/api/v1/collections/check-status", params={"referenceId": reference_id})

    # ------------------------------------------------------------------
    # Payouts: money going out to a member.
    #
    # UNVERIFIED. The collections calls above are ported from an integration
    # that ran against Lipila in production; the payout calls are not. They
    # follow the same request shape and the same path convention, but no
    # disbursement request has ever been sent. Confirm the paths and payload
    # against the Lipila dashboard docs before enabling
    # `lipila_disbursements_enabled` — every path is settings-driven so a
    # correction is an .env change, not a code change.
    # ------------------------------------------------------------------

    async def create_mobile_money_payout(
        self,
        *,
        reference_id: str,
        amount_major: Decimal,
        account_number: str,
        currency: str,
        narration: str,
        reference_data: str,
        callback_url: str,
    ) -> dict[str, Any]:
        return await self._post(
            self.settings.lipila_disbursement_mobile_money_path,
            {
                "referenceId": reference_id,
                "amount": _decimal_json(amount_major),
                "narration": narration,
                "accountNumber": account_number,
                "currency": currency,
                "referenceData": reference_data,
            },
            extra_headers={"callbackUrl": callback_url},
        )

    async def create_bank_payout(
        self,
        *,
        reference_id: str,
        amount_major: Decimal,
        account_number: str,
        bank_code: str,
        account_name: str,
        currency: str,
        narration: str,
        reference_data: str,
        callback_url: str,
    ) -> dict[str, Any]:
        return await self._post(
            self.settings.lipila_disbursement_bank_path,
            {
                "referenceId": reference_id,
                "amount": _decimal_json(amount_major),
                "narration": narration,
                "accountNumber": account_number,
                "accountName": account_name,
                "bankCode": bank_code,
                "currency": currency,
                "referenceData": reference_data,
            },
            extra_headers={"callbackUrl": callback_url},
        )

    async def check_payout_status(self, *, reference_id: str) -> dict[str, Any]:
        return await self._get(
            self.settings.lipila_disbursement_status_path,
            params={"referenceId": reference_id},
        )

    # ------------------------------------------------------------------

    async def _post(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        extra_headers: Optional[dict[str, str]] = None,
    ) -> dict[str, Any]:
        headers = {**self.headers, **(extra_headers or {})}
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
            try:
                response = await client.post(path, json=payload, headers=headers)
            except httpx.TimeoutException as exc:
                raise LipilaError("lipila_timeout") from exc
            except httpx.HTTPError as exc:
                raise LipilaError("lipila_network_error") from exc
        return _json_or_error(response)

    async def _get(self, path: str, *, params: dict[str, str]) -> dict[str, Any]:
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
            try:
                response = await client.get(path, params=params, headers=self.headers)
            except httpx.TimeoutException as exc:
                raise LipilaError("lipila_timeout") from exc
            except httpx.HTTPError as exc:
                raise LipilaError("lipila_network_error") from exc
        return _json_or_error(response)


def _json_or_error(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        payload = {"message": response.text[:500]}
    if response.status_code >= 400:
        raise LipilaError("lipila_error_response", status_code=response.status_code, payload=payload)
    if not isinstance(payload, dict):
        raise LipilaError("lipila_invalid_response", status_code=response.status_code)
    return payload


def _decimal_json(value: Decimal) -> int | str:
    """Render an amount for Lipila's JSON body.

    A whole number of kwacha goes as an integer, anything else as a decimal
    *string*. Serialising through `float` would hand the provider a value such
    as 100.05000000000001 for K100.05, and the amount echoed back on the webhook
    is checked against our ledger exactly — a float artefact there would park a
    perfectly good payment on `needs_review`.
    """
    quantized = value.quantize(Decimal("0.01"))
    if quantized == quantized.to_integral_value():
        return int(quantized)
    return format(quantized, "f")


def _split_name(value: Optional[str]) -> tuple[str, str]:
    parts = (value or "Village Banking Member").strip().split()
    if not parts:
        return "Village Banking", "Member"
    if len(parts) == 1:
        return parts[0], "Member"
    return parts[0], " ".join(parts[1:])
