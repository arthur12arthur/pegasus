"""MarketWatch avant filtrage : aucune cote n’est inventée en cas d’échec."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, Mapping

from .models import Horse


@dataclass(frozen=True)
class MarketQuote:
    numero: int
    cote: float | None
    non_partant: bool = False
    source: str = "inconnue"


@dataclass
class MarketWatchResult:
    quotes: dict[int, MarketQuote]
    deltas_relatives: dict[int, float | None]
    missing_numbers: list[int] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class QuoteProvider(Protocol):
    name: str
    def fetch_quotes(self, horses: list[Horse]) -> Mapping[int, MarketQuote]: ...


class MarketWatch:
    def __init__(self, providers: list[QuoteProvider]):
        self.providers = providers

    def update(self, horses: list[Horse]) -> MarketWatchResult:
        quotes: dict[int, MarketQuote] = {}
        warnings: list[str] = []
        for provider in self.providers:
            try:
                received = provider.fetch_quotes(horses)
                for number, quote in received.items():
                    quotes.setdefault(number, quote)
                if quotes:
                    break
            except Exception as exc:  # fournisseur de secours suivant
                warnings.append(f"{getattr(provider, 'name', provider.__class__.__name__)} indisponible: {exc}")
        missing: list[int] = []
        deltas: dict[int, float | None] = {}
        for horse in horses:
            quote = quotes.get(horse.numero)
            if quote is None or quote.cote is None or quote.non_partant:
                missing.append(horse.numero)
                deltas[horse.numero] = None
                continue
            horse.cote_actuelle = quote.cote
            deltas[horse.numero] = ((quote.cote - horse.cote_pdf) / horse.cote_pdf
                                     if horse.cote_pdf > 0 else None)
        if missing:
            warnings.append("Cote actuelle indisponible ou non-partant pour: " + ", ".join(map(str, missing)))
        if not quotes:
            warnings.append("MarketWatch n’a fourni aucune cote : ne pas filtrer sans le signaler dans le rapport.")
        return MarketWatchResult(quotes, deltas, missing, warnings)


class MappingQuoteProvider:
    """Adaptateur gratuit/testable pour une source déjà collectée."""
    def __init__(self, quotes: Mapping[int, MarketQuote], name: str = "mapping-test"):
        self.quotes = quotes
        self.name = name

    def fetch_quotes(self, horses: list[Horse]) -> Mapping[int, MarketQuote]:
        return self.quotes
