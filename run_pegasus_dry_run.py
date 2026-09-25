"""Dry-run réel et strict du pipeline Pegasus.

Le script ne fabrique aucune donnée et ne modifie aucun module du cœur. Il
s'arrête dès qu'une étape est vide, incohérente ou qu'une donnée indispensable
reste manquante. L'URL de marché doit être fournie explicitement : elle vient
d'une identification séparée de la course et n'est jamais reconstruite ici.

Exemple (course principale du 24/09/2026) :
    python3 run_pegasus_dry_run.py \
      --market-url 'https://www.canalturf.com/pronostics-PMU/2026-09-24/compiegne/418641_prix-de-la-basse-automne.html'
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import sys

from .canalturf_provider import CanalTurfQuoteProvider
from .consensus import compute_classement
from .discipline import detect_discipline
from .filter import apply_filter
from .ingestion import LonabIngestion
from .marketwatch import MarketWatch
from .scorer import score_group


def _print_header() -> None:
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    print(f"Pegasus — exécution dry-run — {stamp}")
    print("Mode : intégration réelle, arrêt strict sur donnée vide/incohérente")


def _stop(stage: str, reason: str) -> None:
    print(f"\nARRÊT INTÉGRATION — étape {stage}")
    print(f"Motif exact : {reason}")
    raise SystemExit(2)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=date.fromisoformat, default=date.today(),
                        help="date ISO du journal LONAB (défaut : date système)")
    parser.add_argument("--market-url", required=True,
                        help="URL exacte de la page Canal Turf de la course")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    _print_header()
    print(f"Date demandée : {args.date.isoformat()}")
    print(f"URL MarketWatch fournie explicitement : {args.market_url}")

    # 1. Ingestion officielle LONAB.
    print("\n[1/6] Ingestion LONAB/PMU'B")
    try:
        ingestion = LonabIngestion().fetch(args.date)
    except Exception as exc:
        _stop("1 — ingestion", f"{type(exc).__name__}: {exc}")
    if not ingestion.horses:
        _stop("1 — ingestion", "la liste Horse est vide")
    numbers = [horse.numero for horse in ingestion.horses]
    if len(numbers) != len(set(numbers)):
        _stop("1 — ingestion", f"numéros dupliqués : {numbers}")
    invalid = [horse.numero for horse in ingestion.horses if horse.cote_pdf <= 0]
    if invalid:
        _stop("1 — ingestion", f"cote_pdf absente ou non positive pour : {invalid}")
    print(f"Journal : {ingestion.journal.title}")
    print(f"PDF : {ingestion.journal.pdf_url}")
    print(f"Chevaux extraits : {len(ingestion.horses)}")
    if ingestion.warnings:
        print(f"Avertissements ingestion : {' | '.join(ingestion.warnings)}")
    print("Numéros : " + ", ".join(map(str, numbers)))

    # 2. Discipline officielle ou repli explicite par texte PDF.
    print("\n[2/6] Détection de discipline")
    try:
        detection = detect_discipline(None, ingestion.text)
    except Exception as exc:
        _stop("2 — discipline", f"{type(exc).__name__}: {exc}")
    if detection.discipline not in {"trot", "plat", "obstacle"}:
        _stop("2 — discipline", f"étiquette inconnue : {detection.discipline!r}")
    print(f"Discipline : {detection.discipline}")
    print(f"Source : {detection.source}; confiance : {detection.confidence}")
    for warning in detection.warnings:
        print(f"Avertissement discipline : {warning}")

    # 3. MarketWatch obligatoire avant le filtre.
    print("\n[3/6] MarketWatch — avant filtrage")
    try:
        market_result = MarketWatch([
            CanalTurfQuoteProvider(args.market_url),
        ]).update(ingestion.horses)
    except Exception as exc:
        _stop("3 — MarketWatch", f"{type(exc).__name__}: {exc}")
    recovered = sum(
        1 for horse in ingestion.horses
        if horse.cote_actuelle is not None and horse.cote_actuelle > 0
    )
    print(f"Cotes récupérées : {recovered}/{len(ingestion.horses)}")
    print(f"Cotes manquantes/non-partants : {len(market_result.missing_numbers)}")
    if market_result.missing_numbers:
        print("Numéros concernés : " + ", ".join(map(str, market_result.missing_numbers)))
        for warning in market_result.warnings:
            print(f"Avertissement MarketWatch : {warning}")
        _stop("3 — MarketWatch", "au moins une cote actuelle indispensable est absente")
    if recovered != len(ingestion.horses):
        _stop("3 — MarketWatch", "le nombre de cotes récupérées ne correspond pas au peloton")
    print("Toutes les cotes actuelles sont remplies.")

    # 4. Filtrage binaire.
    print("\n[4/6] Filtrage")
    try:
        filter_result = apply_filter(ingestion.horses)
    except Exception as exc:
        _stop("4 — filtrage", f"{type(exc).__name__}: {exc}")
    if not filter_result.retenus:
        _stop("4 — filtrage", "aucun cheval retenu")
    if len(filter_result.retenus) + len(filter_result.ecartes) != len(ingestion.horses):
        _stop("4 — filtrage", "retenus + écartés ne couvre pas le peloton")
    print(f"Retenus : {len(filter_result.retenus)}")
    print("Numéros retenus : " + ", ".join(str(h.numero) for h in filter_result.retenus))
    print(f"Écartés : {len(filter_result.ecartes)}")
    if filter_result.reintegration_appliquee:
        print("Réintégration du minimum appliquée par le filtre.")
    for eliminated in filter_result.ecartes:
        print(f"  - n°{eliminated.numero} {eliminated.nom} : "
              f"score risque {eliminated.score_risque}; {eliminated.motif}")

    print("\nChamps bruts extraits — retenus, sans interprétation :")
    print(f"  Distance brute course : {ingestion.course_distance_raw!r}")
    print(f"  Discipline brute course : {ingestion.course_discipline_raw!r}")
    for horse in filter_result.retenus:
        raw = ingestion.raw_fields.get(horse.numero)
        if raw is None:
            _stop("4 — champs bruts", f"aucun enregistrement brut pour n°{horse.numero}")
        print(f"  n°{horse.numero} — champs bruts associés :")
        print(f"    musique brute      = {raw.musique!r}")
        print(f"    driver brut        = {raw.driver!r}")
        print(f"    commentaire brut   = {raw.commentaire!r}")

    # Les notes neutres ne doivent pas masquer une absence de données réelles.
    missing_scoring = {
        horse.numero: ingestion.missing_fields.get(horse.numero, [])
        for horse in filter_result.retenus
        if any(field in {"notes BaseScorer", "ferrure_stats / historique ferrure"}
               for field in ingestion.missing_fields.get(horse.numero, []))
    }
    if missing_scoring:
        _stop(
            "5 — BaseScorer",
            "données de scoring manquantes pour les retenus ; refus d’exécuter "
            f"sur valeurs neutres : {missing_scoring}",
        )

    # 5. Score de compétitivité.
    print("\n[5/6] BaseScorer")
    try:
        scores = score_group(filter_result.retenus, detection.discipline)
    except Exception as exc:
        _stop("5 — BaseScorer", f"{type(exc).__name__}: {exc}")
    if len(scores) != len(filter_result.retenus):
        _stop("5 — BaseScorer", "le nombre de scores diffère du nombre de retenus")
    for score in scores:
        print(f"  - n°{score.numero} {score.nom} : compétitivité {score.score_competitivite:.3f}/10")

    # 6. Consensus interne.
    print("\n[6/6] Consensus interne")
    try:
        classement = compute_classement(scores)
    except Exception as exc:
        _stop("6 — consensus", f"{type(exc).__name__}: {exc}")
    if set(classement.classement) != {score.numero for score in scores}:
        _stop("6 — consensus", "le classement ne couvre pas exactement les scores")
    print("Classement final (score de fusion) :")
    for rank, numero in enumerate(classement.classement, start=1):
        print(f"  {rank:>2}. n°{numero} — proba victoire "
              f"{classement.proba_victoire[numero]:.4f}; fusion "
              f"{classement.score_fusion[numero]:.6f}")
    print("Stabilité Top 3 : "
          f"{classement.stabilite_top3_sur_5_seeds}/5 seeds — "
          f"stable={classement.top3_stable}")
    print("\nDRY-RUN TERMINÉ : les six étapes ont été exécutées sur données réelles.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:
        print(f"\nARRÊT INTÉGRATION — erreur non gérée : {type(exc).__name__}: {exc}")
        raise SystemExit(2)
