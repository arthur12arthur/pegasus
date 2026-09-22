"""
BaseScorer — score de compétitivité.

Unique score de compétitivité du pipeline. Appliqué uniquement au groupe
déjà filtré (filter.apply_filter). Ne modifie jamais le score de classement
(consensus.py) ni le consensus externe.
"""

from __future__ import annotations

from . import config
from .models import FerrureConfigStats, Horse, ScoreResult


def _lissage_bayesien(n: int, efficacite_observee: float | None, baseline: float | None) -> float:
    """efficacite_lissée = (n*observé + K*baseline) / (n+K)

    Repli explicite si une des deux valeurs manque : une victoire isolée sans
    baseline connue ne doit jamais dominer artificiellement le score."""
    k = config.BAYESIAN_SMOOTHING_K
    if efficacite_observee is None and baseline is None:
        return 5.0  # neutre (milieu d'échelle 0-10), aucune donnée exploitable
    if efficacite_observee is None:
        return baseline  # type: ignore[return-value]
    if baseline is None:
        baseline = 5.0  # repli neutre si le cheval n'a pas de baseline connue
    return (n * efficacite_observee + k * baseline) / (n + k)


def _ferrure_adequation(stats: FerrureConfigStats) -> float:
    """60% de la composante Technique en trot : adéquation de la ferrure du jour."""
    w = config.FERRURE_ADEQUATION_SUBWEIGHTS

    efficacite_lissee = _lissage_bayesien(
        n=stats.nb_courses_configuration_exacte,
        efficacite_observee=stats.efficacite_configuration_exacte,
        baseline=stats.efficacite_baseline_cheval,
    )

    conditions = stats.resultats_conditions_comparables
    conditions = 5.0 if conditions is None else conditions

    regularite = stats.regularite_configuration
    regularite = 5.0 if regularite is None else regularite

    recence = stats.recence_performances
    recence = 5.0 if recence is None else recence

    return (
        w["efficacite_configuration_exacte"] * efficacite_lissee
        + w["conditions_comparables"] * conditions
        + w["regularite"] * regularite
        + w["recence"] * recence
    )


def compute_technique_trot(stats: FerrureConfigStats | None) -> float:
    """Composante Technique complète pour le trot (0-10).

    Si aucune donnée de ferrure n'est disponible (stats est None), retourne
    une valeur neutre (5.0) plutôt que d'inventer un historique — cohérent
    avec la règle "donnée manquante = Non déterminée, jamais estimée"."""
    if stats is None:
        return 5.0

    w = config.TECHNIQUE_TROT_SUBWEIGHTS
    adequation = _ferrure_adequation(stats)

    driver = stats.qualite_driver_configuration
    driver = 5.0 if driver is None else driver

    # Fiabilité historique : plus on a de courses dans cette configuration,
    # plus la fiabilité est haute (plafonnée à 10 courses = confiance max).
    fiabilite = min(stats.nb_courses_configuration_exacte, 10) / 10 * 10

    return (
        w["ferrure_adequation"] * adequation
        + w["driver_configuration"] * driver
        + w["fiabilite_historique"] * fiabilite
    )


def score_horse(horse: Horse, discipline: str) -> ScoreResult:
    if discipline not in config.VALID_DISCIPLINES:
        raise ValueError(
            f"discipline inconnue: {discipline!r} (attendu: {config.VALID_DISCIPLINES})"
        )

    weights = config.WEIGHTS_BY_DISCIPLINE[discipline]

    if horse.note_technique is not None:
        note_technique = horse.note_technique
    elif discipline == "trot":
        note_technique = compute_technique_trot(horse.ferrure_stats)
    else:
        # Plat/obstacle : pas de sous-formule définie pour l'instant, la note
        # technique doit être fournie en amont (ingestion). Repli neutre
        # explicite plutôt qu'une erreur bloquante.
        note_technique = 5.0

    score_competitivite = (
        weights["historique"] * horse.note_historique
        + weights["forme"] * horse.note_forme
        + weights["aptitude"] * horse.note_aptitude
        + weights["technique"] * note_technique
        + weights["fraicheur"] * horse.note_fraicheur
    )

    return ScoreResult(
        numero=horse.numero,
        nom=horse.nom,
        note_historique=horse.note_historique,
        note_forme=horse.note_forme,
        note_aptitude=horse.note_aptitude,
        note_technique=note_technique,
        note_fraicheur=horse.note_fraicheur,
        score_competitivite=round(score_competitivite, 3),
    )


def score_group(horses: list[Horse], discipline: str) -> list[ScoreResult]:
    """Note tout le groupe (déjà filtré) et trie par compétitivité décroissante."""
    resultats = [score_horse(h, discipline) for h in horses]
    resultats.sort(key=lambda r: r.score_competitivite, reverse=True)
    return resultats
