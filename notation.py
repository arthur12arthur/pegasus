"""
Pegasus — notation.py

Conversion déterministe des champs bruts extraits du PDF LONAB (musique,
gains) vers deux des cinq notes attendues par BaseScorer (config.py,
scorer.py) : note_historique et note_forme.

RÈGLE : ce module ne modifie ni les poids, ni les seuils, ni la logique de
filter.py / scorer.py / consensus.py. Il produit seulement les entrées
qui leur manquaient. Comme scorer.py, il ne fabrique jamais une note à
partir de rien : si la donnée brute est absente, la note reste None et le
champ correspondant doit être signalé comme manquant par l'appelant —
exactement le même principe que le repli neutre déjà utilisé par
scorer.py pour driver_config_note.

Portée volontairement limitée : ce module ne calcule PAS note_aptitude ni
note_fraicheur. Rien dans les champs bruts actuellement extraits
(musique, gains, driver, commentaire libre) ne permet de les déterminer
de façon fiable sans inventer une donnée (aptitude nécessiterait un
historique par distance/terrain ; fraîcheur nécessiterait la date de la
dernière course). Elles restent la prochaine étape d'ingestion à
construire, pas un calcul à approximer ici.
"""

from __future__ import annotations

from dataclasses import dataclass

# Poids de récence appliqués aux caractères de la musique, du plus récent
# (gauche) au plus ancien. Décroissance géométrique fixe — ne pas modifier
# sans revalidation, au même titre que les poids de config.py.
DECAY = 0.65


@dataclass(frozen=True)
class NotationResult:
    note_historique: float | None
    note_forme: float | None
    historique_manquant: bool
    forme_manquante: bool


def _points_position(caractere: str) -> float:
    """
    Convertit un caractère de musique en points (0 à 10).

    Convention musique française : chiffres 1-9 = place d'arrivée
    (1 = victoire -> 10 points, 9 = 9e -> 2 points), '0' = non classé
    (hors des 9 premiers) -> 0 point. Tout caractère non numérique
    (D, T, A, Ret., ... disqualifié/tombé/arrêté/retiré) est traité par
    défaut comme 0 point — approximation prudente et documentée : si un
    de ces codes doit être nuancé (ex. tombé sans faute du cheval), ce
    sera une évolution explicite de cette fonction, pas une exception
    silencieuse.
    """
    if caractere.isdigit():
        d = int(caractere)
        if d == 0:
            return 0.0
        return float(11 - d)  # place 1 -> 10, place 9 -> 2
    return 0.0


def note_forme_depuis_musique(musique_brute: str | None) -> tuple[float | None, bool]:
    """
    Calcule note_forme (0-10) à partir de la musique brute, pondérée par
    récence (le caractère le plus à gauche compte le plus).

    Retourne (note, manquant). manquant=True si aucune musique exploitable
    n'a été fournie — la note vaut alors None, jamais une valeur inventée.
    """
    if not musique_brute:
        return None, True

    caracteres = [c for c in musique_brute.strip().split(".") if c != ""]
    if not caracteres:
        return None, True

    poids_bruts = [DECAY**i for i in range(len(caracteres))]
    somme_poids = sum(poids_bruts)
    poids = [p / somme_poids for p in poids_bruts]

    note = sum(w * _points_position(c) for w, c in zip(poids, caracteres))
    return round(note, 2), False


def notes_historique_depuis_gains(
    gains_par_numero: dict[int, float | None],
) -> dict[int, tuple[float | None, bool]]:
    """
    Calcule note_historique (0-10) par normalisation min-max des gains
    DANS LE GROUPE FOURNI (le groupe déjà filtré par DataFilter, pas
    l'ensemble des partants du jour).

    Limite assumée et documentée : c'est une mesure de classe relative au
    champ du jour, pas un indice de carrière absolu — deux courses
    différentes ne donneront pas la même note pour le même cheval. C'est
    un choix délibéré : normaliser sur un référentiel absolu demanderait
    un historique global qu'on ne possède pas encore, et inventer une
    échelle absolue serait moins honnête qu'une mesure relative assumée
    comme telle.

    Retourne un dict numero -> (note, manquant). manquant=True si les
    gains de ce cheval sont absents (jamais remplacé par une valeur
    inventée) ou si aucun gain n'est disponible dans tout le groupe.
    """
    valeurs_connues = {n: g for n, g in gains_par_numero.items() if g is not None}

    if not valeurs_connues:
        return {n: (None, True) for n in gains_par_numero}

    minimum = min(valeurs_connues.values())
    maximum = max(valeurs_connues.values())

    resultats: dict[int, tuple[float | None, bool]] = {}
    for numero, gains in gains_par_numero.items():
        if gains is None:
            resultats[numero] = (None, True)
            continue
        if maximum == minimum:
            # tout le groupe a les mêmes gains connus : aucune information
            # discriminante, note neutre plutôt qu'un artefact de division par zéro
            resultats[numero] = (5.0, False)
            continue
        note = 10.0 * (gains - minimum) / (maximum - minimum)
        resultats[numero] = (round(note, 2), False)

    return resultats


def calculer_notes(
    musiques_par_numero: dict[int, str | None],
    gains_par_numero: dict[int, float | None],
) -> dict[int, NotationResult]:
    """Point d'entrée unique : calcule historique + forme pour tout un groupe."""
    notes_historique = notes_historique_depuis_gains(gains_par_numero)

    resultats: dict[int, NotationResult] = {}
    for numero in gains_par_numero:
        note_hist, hist_manquant = notes_historique[numero]
        musique = musiques_par_numero.get(numero)
        note_forme, forme_manquante = note_forme_depuis_musique(musique)
        resultats[numero] = NotationResult(
            note_historique=note_hist,
            note_forme=note_forme,
            historique_manquant=hist_manquant,
            forme_manquante=forme_manquante,
        )
    return resultats
