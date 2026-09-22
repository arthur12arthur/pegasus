"""
DataFilter — portillon éliminatoire.

Répond uniquement à "ce cheval appartient-il au groupe compétitif ?".
Ne produit AUCUN score propre : le score de compétitivité est calculé
ensuite, uniquement pour le groupe retenu ici, par scorer.py.
"""

from __future__ import annotations

from . import config
from .models import EliminatedHorse, FilterResult, Horse


def _score_risque(horse: Horse, seuil_cote_extreme: float) -> tuple[int, list[str]]:
    """Calcule le score de risque d'un cheval et la liste des motifs déclenchés.

    seuil_cote_extreme : cote PDF au-delà de laquelle "cote_extreme" est
    déclenché. Doit être fourni par l'appelant (dépend du nombre de
    partants et du niveau de la course) plutôt que figé ici en dur.
    """
    score = 0
    motifs: list[str] = []

    if horse.gains_euros <= 0:
        score += config.RISK_POINTS["gains_insuffisants"]
        motifs.append("gains insuffisants")

    if horse.disqualifications_recentes >= 3:
        score += config.RISK_POINTS["forme_catastrophique"]
        motifs.append(f"{horse.disqualifications_recentes} disqualifications récentes")

    if horse.cote_pdf >= seuil_cote_extreme:
        score += config.RISK_POINTS["cote_extreme"]
        motifs.append(f"cote extrême ({horse.cote_pdf}/1)")

    if horse.courses_sans_rentree_jours is not None and horse.courses_sans_rentree_jours > 180:
        score += config.RISK_POINTS["absence_prolongee"]
        motifs.append("absence prolongée sans rentrée récente")

    if horse.surclasse_signale:
        score += config.RISK_POINTS["surclassement_signale"]
        motifs.append("surclassement signalé par le commentaire officiel")

    if horse.cote_actuelle is not None and horse.cote_pdf > 0:
        hausse_relative = (horse.cote_actuelle - horse.cote_pdf) / horse.cote_pdf
        if hausse_relative >= 1.0:  # cote au moins doublée depuis le PDF
            score += config.RISK_POINTS["delta_cote_hausse_forte"]
            motifs.append(
                f"forte hausse de cote MarketWatch ({horse.cote_pdf}/1 -> {horse.cote_actuelle}/1)"
            )

    return score, motifs


def apply_filter(
    horses: list[Horse],
    seuil_cote_extreme: float | None = None,
) -> FilterResult:
    """Applique le portillon éliminatoire.

    seuil_cote_extreme : si None, calculé automatiquement comme 6x la
    médiane des cotes PDF du peloton (repli raisonnable si l'appelant ne
    fournit pas de seuil explicite adapté à la course).
    """
    if not horses:
        raise ValueError("apply_filter: la liste de partants est vide")

    if seuil_cote_extreme is None:
        cotes_triees = sorted(h.cote_pdf for h in horses)
        mediane = cotes_triees[len(cotes_triees) // 2]
        seuil_cote_extreme = mediane * 6

    scores: dict[int, int] = {}
    motifs_par_cheval: dict[int, list[str]] = {}
    for h in horses:
        score, motifs = _score_risque(h, seuil_cote_extreme)
        scores[h.numero] = score
        motifs_par_cheval[h.numero] = motifs

    favoris_forces = {
        h.numero
        for h in sorted(horses, key=lambda h: h.cote_pdf)[: config.FORCE_KEEP_LOWEST_COTE_COUNT]
    }

    retenus: list[Horse] = []
    ecartes: list[EliminatedHorse] = []
    for h in horses:
        est_ecarte = (
            scores[h.numero] >= config.RISK_ELIMINATION_THRESHOLD
            and h.numero not in favoris_forces
        )
        if est_ecarte:
            ecartes.append(
                EliminatedHorse(
                    numero=h.numero,
                    nom=h.nom,
                    motif="; ".join(motifs_par_cheval[h.numero]) or "score de risque élevé",
                    score_risque=scores[h.numero],
                )
            )
        else:
            retenus.append(h)

    reintegration_appliquee = False
    if len(retenus) < config.MIN_RETAINED_HORSES:
        reintegration_appliquee = True
        # Réintègre les mieux notés (score de risque le plus bas) parmi les écartés,
        # jusqu'à atteindre le minimum.
        manquants = config.MIN_RETAINED_HORSES - len(retenus)
        ecartes_tries = sorted(ecartes, key=lambda e: e.score_risque)
        a_reintegrer_numeros = {e.numero for e in ecartes_tries[:manquants]}
        for h in horses:
            if h.numero in a_reintegrer_numeros:
                retenus.append(h)
        ecartes = [e for e in ecartes if e.numero not in a_reintegrer_numeros]

    return FilterResult(
        retenus=retenus,
        ecartes=ecartes,
        reintegration_appliquee=reintegration_appliquee,
    )
