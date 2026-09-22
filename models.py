"""Structures de données du cœur Pegasus.

Ces objets sont le contrat entre le cœur (Claude) et le reste du pipeline
(Manus) : Manus doit produire des `Horse` valides en entrée, et consomme les
résultats (`FilterResult`, `ScoreResult`, `ClassementResult`) en sortie —
sans jamais modifier la logique interne des modules qui les produisent.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FerrureConfigStats:
    """Statistiques d'historique de ferrure pour UN cheval, dans UNE
    configuration donnée (celle annoncée pour la course du jour).
    Toute valeur non disponible doit rester `None` — jamais estimée."""

    nb_courses_configuration_exacte: int = 0
    efficacite_configuration_exacte: float | None = None   # 0-10, None si inconnu
    efficacite_baseline_cheval: float | None = None         # 0-10, moyenne toutes configs
    resultats_conditions_comparables: float | None = None   # 0-10, None si inconnu
    regularite_configuration: float | None = None            # 0-10 (absence de DQ), None si inconnu
    recence_performances: float | None = None                # 0-10, None si inconnu
    qualite_driver_configuration: float | None = None        # 0-10, None si inconnu


@dataclass
class Horse:
    """Un partant, tel que fourni au cœur après ingestion (module Manus)."""

    numero: int
    nom: str
    cote_pdf: float
    cote_actuelle: float | None = None     # None si MarketWatch indisponible
    gains_euros: float = 0.0
    disqualifications_recentes: int = 0
    courses_sans_rentree_jours: int | None = None
    surclasse_signale: bool = False

    # Dimensions BaseScorer déjà évaluées en amont (0-10), sauf "technique"
    # en trot qui peut être calculée ici à partir de ferrure_stats.
    note_historique: float = 0.0
    note_forme: float = 0.0
    note_aptitude: float = 0.0
    note_technique: float | None = None     # fourni directement (plat/obstacle),
                                             # ou None pour laisser le trot le calculer
    note_fraicheur: float = 0.0

    ferrure_stats: FerrureConfigStats | None = None  # trot uniquement


@dataclass
class EliminatedHorse:
    numero: int
    nom: str
    motif: str
    score_risque: int


@dataclass
class FilterResult:
    retenus: list[Horse]
    ecartes: list[EliminatedHorse]
    reintegration_appliquee: bool = False


@dataclass
class ScoreResult:
    numero: int
    nom: str
    note_historique: float
    note_forme: float
    note_aptitude: float
    note_technique: float
    note_fraicheur: float
    score_competitivite: float   # agrégat pondéré, 0-10


@dataclass
class SeedResult:
    seed: int
    victoires: dict[int, int] = field(default_factory=dict)     # numero -> nb victoires simulées
    top3: tuple[int, int, int] | None = None                     # numeros, ordre = probabilité décroissante


@dataclass
class ClassementResult:
    classement: list[int]                 # numeros, du plus probable au moins probable
    proba_victoire: dict[int, float]      # numero -> probabilité de victoire (Monte Carlo)
    score_borda: dict[int, float]         # numero -> score Borda normalisé (0-1)
    score_fusion: dict[int, float]        # numero -> score MetaFusion (0-1)
    stabilite_top3_sur_5_seeds: int       # nombre de seeds où le Top 3 (ensemble) est identique au majoritaire
    top3_stable: bool                     # True si stabilite >= MIN_STABLE_SEEDS_FOR_TOP3
