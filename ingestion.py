"""Ingestion officielle LONAB/PMU'B, sans réécriture du cœur Pegasus.

Le module localise le lien PDF affiché pour la date demandée, télécharge ce
lien tel quel, extrait le texte et transforme uniquement les champs réellement
lisibles en :class:`Horse`. Les dimensions BaseScorer non présentes dans le PDF
restent à leur valeur neutre du contrat et sont listées comme manquantes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from io import BytesIO
from pathlib import Path
import re
import subprocess
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

from .models import Horse

LONAB_PROGRAMME_URL = "https://lonab.bf/programme-pmub"


@dataclass(frozen=True)
class JournalLink:
    journal_date: date
    title: str
    pdf_url: str


@dataclass
class IngestionResult:
    journal: JournalLink
    pdf_bytes: bytes
    text: str
    horses: list[Horse]
    missing_fields: dict[int, list[str]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def _french_months() -> dict[str, int]:
    return {"janvier": 1, "février": 2, "mars": 3, "avril": 4, "mai": 5,
            "juin": 6, "juillet": 7, "août": 8, "septembre": 9,
            "octobre": 10, "novembre": 11, "décembre": 12}


def _parse_journal_date(title: str) -> date | None:
    match = re.search(r"du\s+(\d{1,2})\s+([A-Za-zÀ-ÿ]+)\s+(\d{4})", title, re.I)
    if not match:
        return None
    month = _french_months().get(match.group(2).lower())
    return date(int(match.group(3)), month, int(match.group(1))) if month else None


def find_journal_link(html: str, wanted_date: date, base_url: str = LONAB_PROGRAMME_URL) -> JournalLink:
    """Trouve la ligne correspondant exactement à ``wanted_date``.

    Le sélecteur travaille ligne par ligne : il ne prend jamais le premier PDF
    trouvé et ne reconstruit jamais le chemin du fichier.
    """
    soup = BeautifulSoup(html, "html.parser")
    for row in soup.find_all("tr"):
        title_node = row.find(class_=re.compile(r"views-field-title"))
        download = row.find("a", string=lambda s: bool(s and "télécharger" in s.lower()))
        if title_node is None or download is None or not download.get("href"):
            continue
        title = " ".join(title_node.get_text(" ", strip=True).split())
        parsed = _parse_journal_date(title)
        if parsed == wanted_date:
            return JournalLink(parsed, title, urljoin(base_url, download["href"]))
    raise LookupError(f"journal hippique PMU'B introuvable pour {wanted_date.isoformat()}")


def extract_pdf_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(BytesIO(pdf_bytes))
    pypdf_text = "\n".join(page.extract_text() or "" for page in reader.pages)
    # Les tableaux de partants perdent leurs colonnes avec pypdf. Le binaire
    # gratuit poppler est utilisé en repli pour conserver la mise en page.
    try:
        layout = subprocess.run(
            ["pdftotext", "-layout", "-", "-"], input=pdf_bytes,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
        ).stdout.decode("utf-8", errors="replace")
        return layout if len(layout) >= len(pypdf_text) else pypdf_text
    except (OSError, subprocess.CalledProcessError):
        return pypdf_text


# Format observé dans le PDF LONAB : numéro, nom, champs textuels, gains, puis
# une ou plusieurs cotes. On s’arrête à la prochaine ligne numérotée.
_LINE = re.compile(
    r"^\s*(?P<num>\d{1,2})\s+(?P<rest>[A-ZÀ-ÖØ-Ý0-9][^\n]+?)\s*$",
    re.MULTILINE,
)
_GAINS_ODDS = re.compile(
    r"(?<![\d.])(?P<gains>\d{1,3}(?: \d{3})?)\s{2,}"
    r"(?P<odds>\d+(?:[.,]\d+)?)/1"
)


def _horse_from_line(line: str) -> Horse | None:
    match = _LINE.match(line)
    if not match:
        return None
    number = int(match.group("num"))
    if number < 1 or number > 99:
        return None
    raw_rest = match.group("rest")
    rest = " ".join(raw_rest.split())
    parsed = _GAINS_ODDS.search(raw_rest)
    if not parsed:
        return None
    # Les colonnes de commentaires peuvent contenir des chiffres : le nom est
    # donc pris avant le premier nom de driver/colonne, avec un repli borné.
    before = raw_rest[: parsed.start("gains")].strip()
    columns = [part.strip() for part in re.split(r"\s{2,}", before) if part.strip()]
    # Le PDF texte conserve des séparateurs de colonnes de plusieurs espaces :
    # la première colonne est le nom, sans concaténer driver/entraîneur.
    tokens = before.split()
    driver_start = next((i for i, token in enumerate(tokens)
                         if re.fullmatch(r"[A-Z]{1,3}(?:\.[A-Z]{0,3})+", token)), None)
    if driver_start is not None and driver_start > 0:
        name = " ".join(tokens[:driver_start])
    else:
        name = (columns[0] if columns else before.split()[0] if before.split() else f"Numéro {number}")
    gains = float(parsed.group("gains").replace(" ", ""))
    cote = float(parsed.group("odds").replace(",", "."))
    return Horse(numero=number, nom=name, cote_pdf=cote, gains_euros=gains)


def parse_horses(text: str) -> tuple[list[Horse], dict[int, list[str]], list[str]]:
    horses: list[Horse] = []
    missing: dict[int, list[str]] = {}
    warnings: list[str] = []
    for raw in text.splitlines():
        horse = _horse_from_line(raw)
        if horse is None:
            continue
        horse_missing = ["cote_actuelle (MarketWatch non exécuté)", "notes BaseScorer",
                         "ferrure_stats / historique ferrure", "non-partant actualisé"]
        horses.append(horse)
        missing[horse.numero] = horse_missing
    if not horses:
        warnings.append("Aucune ligne de partant avec gains+cote n’a été extraite.")
    return horses, missing, warnings


class LonabIngestion:
    def __init__(self, session: requests.Session | None = None, timeout: float = 20.0):
        self.session = session or requests.Session()
        self.timeout = timeout

    def fetch(self, wanted_date: date, programme_url: str = LONAB_PROGRAMME_URL) -> IngestionResult:
        page_url = programme_url
        journal: JournalLink | None = None
        for _ in range(20):
            page = self.session.get(page_url, timeout=self.timeout)
            page.raise_for_status()
            try:
                journal = find_journal_link(page.text, wanted_date, page_url)
                break
            except LookupError:
                soup = BeautifulSoup(page.text, "html.parser")
                next_link = soup.find("a", rel="next")
                if next_link is None or not next_link.get("href"):
                    break
                page_url = urljoin(page_url, next_link["href"])
        if journal is None:
            raise LookupError(f"journal hippique PMU'B introuvable pour {wanted_date.isoformat()} après pagination")
        pdf = self.session.get(journal.pdf_url, timeout=self.timeout)
        pdf.raise_for_status()
        content = pdf.content
        text = extract_pdf_text(content)
        horses, missing, warnings = parse_horses(text)
        return IngestionResult(journal, content, text, horses, missing, warnings)

    def save_pdf(self, result: IngestionResult, destination: str | Path) -> Path:
        path = Path(destination)
        path.write_bytes(result.pdf_bytes)
        return path
