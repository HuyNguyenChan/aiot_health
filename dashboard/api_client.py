from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import requests


DEFAULT_API_BASE = "http://localhost:5000/api"


@dataclass(frozen=True)
class ApiResult:
    data: Any = None
    error: str | None = None
    status_code: int | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


class HealthApiClient:
    """Small wrapper around the Flask API that reads/writes Firebase data."""

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or os.getenv("AIOT_API_BASE") or DEFAULT_API_BASE).rstrip("/")

    def _get(self, path: str, *, timeout: int = 5, as_bytes: bool = False) -> ApiResult:
        try:
            response = requests.get(f"{self.base_url}{path}", timeout=timeout)
            response.raise_for_status()
            return ApiResult(
                data=response.content if as_bytes else response.json(),
                status_code=response.status_code,
            )
        except requests.RequestException as exc:
            status = exc.response.status_code if exc.response is not None else None
            return ApiResult(error=str(exc), status_code=status)
        except ValueError as exc:
            return ApiResult(error=f"Invalid JSON response: {exc}")

    def _post(self, path: str, payload: dict[str, Any] | None = None, *, timeout: int = 10) -> ApiResult:
        try:
            response = requests.post(f"{self.base_url}{path}", json=payload or {}, timeout=timeout)
            response.raise_for_status()
            return ApiResult(data=response.json(), status_code=response.status_code)
        except requests.RequestException as exc:
            status = exc.response.status_code if exc.response is not None else None
            return ApiResult(error=str(exc), status_code=status)
        except ValueError as exc:
            return ApiResult(error=f"Invalid JSON response: {exc}")

    def status(self) -> ApiResult:
        return self._get("/health/status", timeout=3)

    def patients(self) -> ApiResult:
        return self._get("/patients", timeout=5)

    def latest(self, patient_id: str) -> ApiResult:
        return self._get(f"/health/{patient_id}/latest", timeout=5)

    def history(self, patient_id: str, days: int = 1) -> ApiResult:
        return self._get(f"/health/{patient_id}/history?days={days}", timeout=8)

    def alerts(self, patient_id: str, limit: int = 20) -> ApiResult:
        return self._get(f"/alerts/{patient_id}?limit={limit}", timeout=5)

    def ecg_latest(self, patient_id: str) -> ApiResult:
        return self._get(f"/health/{patient_id}/ecg_latest", timeout=5)

    def predict(self, patient_id: str, horizon_hours: int = 6) -> ApiResult:
        return self._post(f"/predict/{patient_id}", {"horizon_hours": horizon_hours}, timeout=15)

    def report_pdf(self, patient_id: str) -> ApiResult:
        return self._get(f"/report/{patient_id}", timeout=20, as_bytes=True)
