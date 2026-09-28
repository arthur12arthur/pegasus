"""
Pegasus — assembly.py

Dernier maillon avant le cœur : prend un IngestionResult (Manus,
ingestion.py) + des cotes actuelles (MarketWatch) et produit des `Horse`
réellement prêts pour filter.py / scorer.py — en appelant notation.py et
signal_textuel.py, sans jamais modifier models.py, filter.py, scorer.py
ni consensus.py.

Politique de repli, identique dans l'esprit à celle déjà utilisée par
scorer.py pour driver_config_note : une dimension sans signal fiable
reçoit une valeur neutre (5.0) et est listée dans missing_fields — elle
n'empêche pas le pipeline d'avancer, mais elle reste tracée et visible
dans le rapport final (Laboratoire interne, section 10 du Système Prompt
Canonique). Seules les données structurellement impossibles à obtenir
(cote_actuelle, gains) bloquent réellement l'exécution.
"""

from __future__ import annotations

from dataclasses import dataclass

from .ingestion import IngestionResult
from .models import Horse
from .notation import calculer_notes
from .signal_textuel import note_aptitude_depuis_commentaire, note_fraicheur_depuis_commentaire

NOTE_NEUTRE = 5.0


@dataclass
class AssemblyResult:
    horses: list[Horse]
    missing_fields: dict[int, list[str]]
    bloquant: dict[int, list[str]]  # sous-ensemble de missing_fields qui empêche vraiment l'exécution


def construire_horses(
    ingestion: IngestionResult,
    cotes_actuelles: dict[int, float | None],
    discipline: str,
) -> AssemblyResult:
    """
    Construit la liste de Horse prête pour apply_filter/score_group, à
    partir des champs bruts exposés par ingestion.py.

    discipline : "trot" | "plat" | "obstacle" — pour savoir si
    la discipline courante ; seul le trot trace l'absence de ferrure_stats.
    """
    musiques = {n: rf.musique for n, rf in ingestion.raw_fields.items()}
    # 0 € de gains est une donnée réelle (débutant) ; seule l'absence (None) est un manque.
    gains = {h.numero: h.gains_euros for h in ingestion.horses}

    notes = calculer_notes(musiques, gains)

    horses: list[Horse] = []
    missing_fields: dict[int, list[str]] = {}
    bloquant: dict[int, list[str]] = {}

    for horse in ingestion.horses:
        numero = horse.numero
        raw = ingestion.raw_fields.get(numero)
        commentaire = raw.commentaire if raw else None
        resultat_notation = notes[numero]

        manquants: list[str] = []
        bloquants_horse: list[str] = []

        # --- historique / forme : notation.py, source fiable (musique/gains)
        if resultat_notation.historique_manquant:
            manquants.append("note_historique (gains absents)")
            bloquants_horse.append("note_historique")
        if resultat_notation.forme_manquante:
            manquants.append("note_forme (musique absente)")
            bloquants_horse.append("note_forme")

        note_historique = resultat_notation.note_historique if not resultat_notation.historique_manquant else NOTE_NEUTRE
        note_forme = resultat_notation.note_forme if not resultat_notation.forme_manquante else NOTE_NEUTRE

        # --- aptitude / fraîcheur : signal_textuel.py, source faible (commentaire libre)
        # Un repli neutre + mention dans missing_fields, jamais bloquant :
        # même statut que le repli driver_config_note déjà accepté dans scorer.py.
        note_aptitude, confiant_aptitude = note_aptitude_depuis_commentaire(commentaire)
        if not confiant_aptitude:
            manquants.append("note_aptitude (aucun signal textuel fiable — repli neutre)")
            note_aptitude = NOTE_NEUTRE

        note_fraicheur, confiant_fraicheur = note_fraicheur_depuis_commentaire(commentaire)
        if not confiant_fraicheur:
            manquants.append("note_fraicheur (aucun signal textuel fiable — repli neutre)")
            note_fraicheur = NOTE_NEUTRE

        # --- cote actuelle (MarketWatch) : structurellement bloquant si absente
        cote_actuelle = cotes_actuelles.get(numero)
        if cote_actuelle is None:
            manquants.append("cote_actuelle (MarketWatch non fourni pour ce cheval)")
            bloquants_horse.append("cote_actuelle")

        # --- ferrure (trot) : NON bloquant. scorer.py applique déjà un repli
        # neutre (5.0) quand ferrure_stats est absent, testé dans test_core.py.
        # On le trace pour le rapport (Laboratoire interne) sans arrêter le
        # pipeline — sinon aucune course de trot ne pourrait jamais tourner,
        # puisque l'ingestion n'extrait pas encore l'historique de ferrure.
        if discipline == "trot" and horse.ferrure_stats is None:
            manquants.append(
                "ferrure_stats / historique ferrure absent — technique en repli neutre (trot)"
            )

        horses.append(
            Horse(
                numero=horse.numero,
                nom=horse.nom,
                cote_pdf=horse.cote_pdf,
                cote_actuelle=cote_actuelle,
                gains_euros=horse.gains_euros,
                disqualifications_recentes=horse.disqualifications_recentes,
                courses_sans_rentree_jours=horse.courses_sans_rentree_jours,
                surclasse_signale=horse.surclasse_signale,
                note_historique=note_historique,
                note_forme=note_forme,
                note_aptitude=note_aptitude,
                note_technique=horse.note_technique,  # laissé tel quel (trot: scorer.py le calcule via ferrure_stats)
                note_fraicheur=note_fraicheur,
                ferrure_stats=horse.ferrure_stats,
            )
        )

        if manquants:
            missing_fields[numero] = manquants
        if bloquants_horse:
            bloquant[numero] = bloquants_horse

    return AssemblyResult(horses=horses, missing_fields=missing_fields, bloquant=bloquant)
