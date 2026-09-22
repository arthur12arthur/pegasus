"""Client minimal de l’API publique open-pmu-api.

Cette API fournit les résultats officiels historiques, pas les cotes actuelles.
Elle sert donc à l’évaluation J+1 et ne remplace pas MarketWatch.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any
import requests

BASE_URL = "https://open-pmu-api.vercel.app/api/arrivees"


@dataclass
class OfficialResultResponse:
    ok: bool
    races: list[dict[str, Any]]
    error: str | None = None
    status_code: int = 0


class OpenPmuApiClient:
    def __init__(self, base_url: str = BASE_URL, session: requests.Session | None = None, timeout: float = 20.0):
        self.base_url = base_url
        self.session = session or requests.Session()
        self.timeout = timeout

    def results_by_date(self, day: date) -> OfficialResultResponse:
        # Le dépôt documente MM/DD/YYYY dans ses exemples et son implémentation
        # attend ce format malgré une phrase README contradictoire.
        params = {"date": day.strftime("%m/%d/%Y")}
        response = self.session.get(self.base_url, params=params, timeout=self.timeout)
        status = response.status_code
        response.raise_for_status()
        payload = response.json()
        message = payload.get("message", [])
        if payload.get("error"):
            return OfficialResultResponse(False, [], str(message), status)
        return OfficialResultResponse(True, message if isinstance(message, list) else [], None, status)

    @staticmethod
    def arrival_for_horse(race: dict[str, Any], numero: int) -> int | None:
        arrival = race.get("arrivee", [])
        try:
            return arrival.index(numero) + 1
        except (ValueError, AttributeError):
            return None
