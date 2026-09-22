"""
Consensus interne — score de classement.

Prend les scores de compétitivité (scorer.score_group, déjà filtrés) et
produit un ordre probable : Monte Carlo (Plackett-Luce, seeds figées) +
Borda, fusionnés par comparaison pairwise (Copeland).

Distinct et jamais fusionné avec le score de compétitivité de BaseScorer.

Note d'implémentation : la formule exacte de "MetaFusion pairwise" des
versions précédentes n'a pas été retrouvée telle quelle. Ce module en
propose une version concrète et déterministe (comparaison de Copeland sur
deux critères : probabilité de victoire Monte Carlo et score de Borda) —
à valider/ajuster si la formule d'origine était différente.
"""

from __future__ import annotations

import random
from collections import Counter

from . import config
from .models import ClassementResult, ScoreResult, SeedResult


def _simulate_one_race(numeros: list[int], strengths: dict[int, float], rng: random.Random) -> list[int]:
    """Tire un ordre d'arrivée complet par échantillonnage Plackett-Luce :
    à chaque étape, le prochain cheval est tiré parmi les restants avec une
    probabilité proportionnelle à sa force."""
    restants = list(numeros)
    ordre: list[int] = []
    while restants:
        poids = [strengths[n] for n in restants]
        choix = rng.choices(restants, weights=poids, k=1)[0]
        ordre.append(choix)
        restants.remove(choix)
    return ordre


def _run_seed(scores: list[ScoreResult], seed: int, n_sims: int) -> SeedResult:
    numeros = [s.numero for s in scores]
    # Force > 0 toujours : exp() du score de compétitivité pour amplifier les
    # écarts sans jamais donner une probabilité nulle à un cheval retenu.
    strengths = {s.numero: pow(2.71828, s.score_competitivite / 3.0) for s in scores}

    rng = random.Random(seed)
    victoires: Counter[int] = Counter()
    somme_rangs: Counter[int] = Counter()

    for _ in range(n_sims):
        ordre = _simulate_one_race(numeros, strengths, rng)
        victoires[ordre[0]] += 1
        for rang, numero in enumerate(ordre, start=1):
            somme_rangs[numero] += rang

    rang_moyen = {n: somme_rangs[n] / n_sims for n in numeros}
    top3 = tuple(sorted(numeros, key=lambda n: rang_moyen[n])[:3])  # type: ignore[assignment]

    return SeedResult(seed=seed, victoires=dict(victoires), top3=top3)  # type: ignore[arg-type]


def _borda(scores: list[ScoreResult]) -> dict[int, float]:
    classement = sorted(scores, key=lambda s: s.score_competitivite, reverse=True)
    n = len(classement)
    if n <= 1:
        return {classement[0].numero: 1.0} if classement else {}
    points = {s.numero: (n - 1 - rang) / (n - 1) for rang, s in enumerate(classement)}
    return points


def _metafusion_pairwise(
    proba_victoire: dict[int, float], score_borda: dict[int, float]
) -> dict[int, float]:
    """Fusion par comparaison de Copeland sur deux critères (proba MC, Borda).

    Pour chaque paire, le cheval qui gagne sur les deux critères marque +1,
    celui qui perd sur les deux marque -1, un partage marque 0 pour les deux.
    Le score Copeland brut est ensuite renormalisé en 0-1 pour lisibilité,
    avec un départage par la moyenne simple des deux critères en cas d'égalité
    Copeland stricte."""
    numeros = list(proba_victoire.keys())
    copeland: dict[int, int] = {n: 0 for n in numeros}

    for i in numeros:
        for j in numeros:
            if i == j:
                continue
            i_gagne = (proba_victoire[i] > proba_victoire[j]) + (score_borda[i] > score_borda[j])
            j_gagne = (proba_victoire[j] > proba_victoire[i]) + (score_borda[j] > score_borda[i])
            if i_gagne > j_gagne:
                copeland[i] += 1
            elif j_gagne > i_gagne:
                copeland[i] -= 1
            # égalité stricte (1-1 ou 0-0 sur les deux critères) : aucun point

    min_c, max_c = min(copeland.values()), max(copeland.values())
    etendue = (max_c - min_c) or 1
    tiebreak = {n: (proba_victoire[n] + score_borda[n]) / 2 for n in numeros}

    fusion = {}
    for n in numeros:
        base = (copeland[n] - min_c) / etendue
        fusion[n] = round(base + tiebreak[n] * 1e-6, 6)  # tiebreak infinitésimal, jamais dominant
    return fusion


def compute_classement(scores: list[ScoreResult]) -> ClassementResult:
    if not scores:
        raise ValueError("compute_classement: aucun cheval noté en entrée")

    resultats_par_seed = [_run_seed(scores, seed, config.SIMULATIONS_PER_SEED) for seed in config.SEEDS]

    # Moyenne des probabilités de victoire sur les 5 seeds.
    numeros = [s.numero for s in scores]
    proba_victoire: dict[int, float] = {}
    for n in numeros:
        total = sum(r.victoires.get(n, 0) for r in resultats_par_seed)
        proba_victoire[n] = total / (len(config.SEEDS) * config.SIMULATIONS_PER_SEED)

    # Stabilité : le Top 3 (ensemble, ordre ignoré) le plus fréquent parmi les 5 seeds.
    top3_sets = [frozenset(r.top3) for r in resultats_par_seed if r.top3]
    compte_top3 = Counter(top3_sets)
    top3_majoritaire, stabilite = compte_top3.most_common(1)[0]

    score_borda = _borda(scores)
    score_fusion = _metafusion_pairwise(proba_victoire, score_borda)

    classement = sorted(numeros, key=lambda n: score_fusion[n], reverse=True)

    return ClassementResult(
        classement=classement,
        proba_victoire=proba_victoire,
        score_borda=score_borda,
        score_fusion=score_fusion,
        stabilite_top3_sur_5_seeds=stabilite,
        top3_stable=stabilite >= config.MIN_STABLE_SEEDS_FOR_TOP3,
    )
