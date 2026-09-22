"""Détection de discipline à partir du libellé officiel de course."""
from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class DisciplineDetection:
    discipline: str
    source: str
    confidence: str
    warnings: tuple[str, ...] = ()


_DIRECT = {
    "trot": ("trot", "trot attelé", "trot monté"),
    "plat": ("plat",),
    "obstacle": ("obstacle", "haies", "steeple", "steeple-chase", "cross"),
}


def detect_discipline(course_type: str | None, pdf_text: str = "") -> DisciplineDetection:
    raw = " ".join((course_type or "").lower().split())
    for discipline, labels in _DIRECT.items():
        if any(label in raw for label in labels):
            return DisciplineDetection(discipline, "champ officiel", "élevée")
    haystack = f"{raw} {pdf_text.lower()}"
    matches: list[str] = []
    for discipline, labels in _DIRECT.items():
        if any(re.search(rf"\b{re.escape(label)}\b", haystack) for label in labels):
            matches.append(discipline)
    if len(matches) == 1:
        return DisciplineDetection(matches[0], "mots-clés PDF", "moyenne",
                                   ("Champ type absent ou ambigu : repli par mots-clés.",))
    if not matches:
        raise ValueError("discipline indéterminée : aucun champ ou mot-clé exploitable")
    raise ValueError(f"discipline ambiguë : {matches}")
