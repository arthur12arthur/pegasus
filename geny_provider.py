"""QuoteProvider gratuit basé sur la page publique Geny « Cotes ».

Geny expose des rapports probables par opérateur. L’adaptateur retient le
rapport numérique courant le plus à droite avant la colonne d’évolution ; une
cellule vide ou ``-`` reste manquante. Cette unité est documentée comme
rapport probable de marché, et non comme une cote PMU garantie.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Mapping
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from .marketwatch import MarketQuote
from .models import Horse

DEFAULT_TIMEOUT = 20.0


def _number(text: str) -> int | None:
    match = re.search(r"\b(\d{1,2})\b", text)
    return int(match.group(1)) if match else None


def _quote(text: str) -> float | None:
    cleaned = " ".join(text.replace("\\.", ".").split())
    if cleaned.upper() in {"", "-", "--", "NP", "N.P.", "N/P", "NPO"}:
        return None
    if "%" in cleaned or "▼" in cleaned or "▲" in cleaned:
        return None
    cleaned = cleaned.replace("\u202f", "").replace(" ", "").replace(",", ".")
    match = re.fullmatch(r"\d+(?:\.\d+)?", cleaned)
    return float(match.group(0)) if match else None


def parse_geny_quotes(html: str | bytes, source_url: str = "") -> dict[int, MarketQuote]:
    """Extrait les rapports probables courants du tableau Geny.

    Le tableau est identifié par son en-tête ``Rap. prob.``. Pour chaque ligne,
    on prend le dernier nombre situé avant la colonne d’évolution ; cela évite
    de confondre le pourcentage d’enjeux avec le rapport probable.
    """
    soup = BeautifulSoup(html, "html.parser")
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        header_index = next(
            (i for i, row in enumerate(rows)
             if "rap. prob." in " ".join(row.get_text(" ", strip=True).split()).lower()),
            None,
        )
        if header_index is None:
            continue
        quotes: dict[int, MarketQuote] = {}
        for row in rows[header_index + 1:]:
            cells = row.find_all(["th", "td"])
            if len(cells) < 6:
                continue
            numero = _number(cells[0].get_text(" ", strip=True))
            if numero is None:
                continue
            evolution_index = next(
                (i for i, cell in enumerate(cells[5:], 5)
                 if any(marker in cell.get_text(" ", strip=True) for marker in ("▼", "▲"))),
                len(cells) - 1,
            )
            candidates = [_quote(cell.get_text(" ", strip=True)) for cell in cells[5:evolution_index]]
            current = next((value for value in reversed(candidates) if value is not None), None)
            raw = " ".join(cells[5:evolution_index][-1].get_text(" ", strip=True).split()) if evolution_index > 5 else ""
            quotes[numero] = MarketQuote(numero, current, False, "Geny/rapport-probable")
        if quotes:
            return quotes
    raise ValueError("tableau Geny avec rapports probables introuvable")


@dataclass
class GenyQuoteProvider:
    """Adaptateur HTTP compatible avec ``MarketWatch``.

    ``url`` doit être l’URL exacte d’une page Geny déjà identifiée.
    """
    url: str
    session: requests.Session | None = None
    timeout: float = DEFAULT_TIMEOUT
    name: str = "Geny — rapport probable"

    def __post_init__(self) -> None:
        parsed = urlparse(self.url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("GenyQuoteProvider: URL HTTP(S) obligatoire")
        if self.session is None:
            self.session = requests.Session()

    def fetch_quotes(self, horses: list[Horse]) -> Mapping[int, MarketQuote]:
        assert self.session is not None
        response = self.session.get(
            self.url,
            timeout=self.timeout,
            headers={"User-Agent": "Pegasus/1.0 (research; contact unavailable)"},
        )
        response.raise_for_status()
        return parse_geny_quotes(response.content, self.url)
