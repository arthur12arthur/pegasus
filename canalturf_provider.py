"""QuoteProvider gratuit basé sur le tableau public Canal Turf.

Canal Turf expose sur ses pages de course un tableau serveur avec une colonne
ZEturf. L’URL de course est fournie par l’appelant : ce module ne reconstruit
aucune URL et ne prétend pas obtenir une cote quand la cellule vaut ``--``.
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
    cleaned = text.replace("\\.", ".").replace("\\,", ",").strip()
    if cleaned in {"", "--", "-", "NP", "N.P.", "N/P", "NPO"}:
        return None
    cleaned = cleaned.replace("\u202f", "").replace(" ", "").replace(",", ".")
    match = re.search(r"\d+(?:\.\d+)?", cleaned)
    return float(match.group(0)) if match else None


def parse_canalturf_quotes(html: str | bytes, source_url: str = "") -> dict[int, MarketQuote]:
    """Extrait la colonne ZEturf du tableau de partants/cotes.

    Le tableau est identifié par son en-tête, pas par sa position dans la page.
    Une cellule vide ou ``--`` devient une cote manquante ; elle n’est jamais
    remplacée par une estimation.
    """
    soup = BeautifulSoup(html, "html.parser")
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        header_row_index = next(
            (i for i, row in enumerate(rows)
             if "zeturf" in " ".join([
                 row.get_text(" ", strip=True),
                 *(node.get("alt", "") for node in row.find_all("img")),
                 *(node.get("title", "") for node in row.find_all(["img", "a"])),
             ]).lower()),
            None,
        )
        if header_row_index is None:
            continue
        header_cells = rows[header_row_index].find_all(["th", "td"])
        headers = []
        for cell in header_cells:
            label = " ".join(cell.get_text(" ", strip=True).split())
            labels = [label, *(node.get("alt", "") for node in cell.find_all("img")),
                      *(node.get("title", "") for node in cell.find_all(["img", "a"]))]
            headers.append(" ".join(part for part in labels if part).lower())
        zeturf_index = next((i for i, header in enumerate(headers) if "zeturf" in header), None)
        if zeturf_index is None:
            continue
        quotes: dict[int, MarketQuote] = {}
        for row in rows[header_row_index + 1:]:
            cells = row.find_all(["th", "td"])
            if len(cells) <= zeturf_index:
                continue
            numero = _number(cells[0].get_text(" ", strip=True))
            if numero is None:
                continue
            raw = " ".join(cells[zeturf_index].get_text(" ", strip=True).split())
            upper = raw.upper().replace(" ", "")
            non_partant = upper in {"NP", "N.P.", "N/P", "NPO"}
            quotes[numero] = MarketQuote(numero, _quote(raw), non_partant, "CanalTurf/ZEturf")
        if quotes:
            return quotes
    raise ValueError("tableau Canal Turf avec colonne ZEturf introuvable")


@dataclass
class CanalTurfQuoteProvider:
    """Adaptateur réel compatible avec ``MarketWatch``.

    ``url`` doit être l’URL exacte d’une page de course obtenue par une étape
    d’identification séparée. Le fournisseur refuse les URL non HTTP(S).
    """
    url: str
    session: requests.Session | None = None
    timeout: float = DEFAULT_TIMEOUT
    name: str = "Canal Turf — colonne ZEturf"

    def __post_init__(self) -> None:
        parsed = urlparse(self.url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("CanalTurfQuoteProvider: URL HTTP(S) obligatoire")
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
        return parse_canalturf_quotes(response.content, self.url)
