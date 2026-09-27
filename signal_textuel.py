"""
Pegasus — signal_textuel.py

Deuxième étage de conversion, après notation.py (musique/gains -> historique,
forme). Ce module tente d'extraire un signal d'aptitude terrain/distance et
de fraîcheur à partir du COMMENTAIRE OFFICIEL en texte libre du PDF LONAB.

C'est un signal plus faible que notation.py : la musique et les gains sont
des données structurées et fiables, alors que le commentaire est du texte
libre, parfois tronqué à l'extraction, parfois ambigu. En conséquence :

- Une note n'est renvoyée QUE si un motif textuel reconnu est trouvé.
  Dans tous les autres cas (aucun motif, commentaire absent ou tronqué),
  la fonction renvoie None et confiant=False — jamais une note "au
  jugé". C'est le même principe que note_forme_depuis_musique, appliqué
  à une source plus fragile, donc avec un seuil de déclenchement plus
  strict.
- Quand aucun signal fiable n'est trouvé, l'appelant doit utiliser un
  repli neutre (5.0) et le signaler comme tel — exactement le mécanisme
  déjà en place dans scorer.py pour driver_config_note manquant. Ce
  module ne décide pas du repli, il se contente de dire "signal trouvé"
  ou "signal absent".

Les motifs ci-dessous ont été construits et testés sur 15 commentaires
réels (Compiègne, Prix de la Basse Automne, 24/09/2026) — voir
test_signal_textuel.py. Ils devront être enrichis au fil de vrais cas
rencontrés, jamais élargis pour "faire mieux" sur un cas isolé sans
nouveau test qui le justifie.
"""

from __future__ import annotations

import re

# --- Aptitude terrain / distance -------------------------------------------

_APTITUDE_POSITIFS = [
    r"conna[iî]t(?:re)?\s+(?:bien\s+)?(?:la\s+piste|le\s+parcours|[A-ZÀ-Ý][\wÀ-ÿ-]+)",
    r"ne\s+devraient?\s+pas\s+la?\s?contrarier",
    r"le\s+parcours\s+de\s+son\s+unique\s+succ[eè]s",
    r"a\s+d[eé]j[aà]\s+gagn[eé]\s+en\s+bon\s+terrain",
    r"n['’]a\s+jamais\s+d[eé][cç]u.{0,40}sur\s+ce\s+parcours",
    r"s['’]adapte\s+[aà]\s+tous\s+les\s+terrains",
]

_APTITUDE_NEGATIFS = [
    r"aurait\s+pr[eé]f[eé]r[eé]\s+(?:un(?:e)?\s+)?(?:piste|terrain)",
    r"distance\s+trop\s+longue",
    r"[eé]voluait\s+sur\s+une\s+distance\s+trop\s+longue",
    r"ne\s+lui\s+convient\s+pas",
]
# Note : "desservie par le terrain" volontairement exclu — décrit le plus
# souvent une malchance ponctuelle ("terrain collant CE jour-là"), pas un
# désaccord d'aptitude durable. Confirmé par un cas réel (commentaire du
# n°5, Compiègne 24/09/2026) où ce motif capturait à tort un cheval par
# ailleurs positif sur son aptitude ("connaît Compiègne").


def note_aptitude_depuis_commentaire(
    commentaire: str | None,
) -> tuple[float | None, bool]:
    """
    Cherche un signal explicite d'adéquation terrain/distance dans le
    commentaire officiel. Retourne (note, confiant).

    confiant=False -> aucun motif reconnu, l'appelant doit utiliser un
    repli neutre documenté, pas cette valeur.
    """
    if not commentaire:
        return None, False

    texte = commentaire.replace("\n", " ")

    positif = any(re.search(p, texte, re.IGNORECASE) for p in _APTITUDE_POSITIFS)
    negatif = any(re.search(p, texte, re.IGNORECASE) for p in _APTITUDE_NEGATIFS)

    if positif and not negatif:
        return 7.5, True
    if negatif and not positif:
        return 3.0, True
    # positif et négatif tous les deux trouvés, ou aucun des deux :
    # signal ambigu ou absent -> pas confiant, laisser le repli neutre décider
    return None, False


# --- Fraîcheur / préparation -------------------------------------------------

_FRAICHEUR_NEGATIFS = [
    r"apr[eè]s\s+une\s+longue\s+absence",
    r"rentr[eé]e\s+apr[eè]s\s+une\s+absence",
    r"n['’]a\s+couru\s+qu['’]une\s+(?:seule\s+)?course",
    r"aprè?s\s+une\s+coupure",
]

_FRAICHEUR_POSITIFS = [
    r"r[eé]apparition\s+victorieuse",
    r"en\s+pleine\s+forme",
    r"regain\s+de\s+forme",
]


def note_fraicheur_depuis_commentaire(
    commentaire: str | None,
) -> tuple[float | None, bool]:
    """
    Cherche un signal explicite de fraîcheur/préparation dans le
    commentaire officiel. Retourne (note, confiant) — même contrat que
    note_aptitude_depuis_commentaire.

    Note pour la suite du projet : ce motif est volontairement restreint.
    Sur les 15 commentaires réels testés (Compiègne 24/09/2026), aucun ne
    déclenche ces motifs — ce n'est pas un défaut du module, c'est une
    illustration honnête que la fraîcheur reste, pour l'instant, très
    majoritairement "non déterminée" avec les seules données du PDF. Une
    vraie amélioration demanderait la date de la dernière course de
    chaque cheval, pas seulement le commentaire libre.
    """
    if not commentaire:
        return None, False

    texte = commentaire.replace("\n", " ")

    negatif = any(re.search(p, texte, re.IGNORECASE) for p in _FRAICHEUR_NEGATIFS)
    positif = any(re.search(p, texte, re.IGNORECASE) for p in _FRAICHEUR_POSITIFS)

    if positif and not negatif:
        return 7.5, True
    if negatif and not positif:
        return 3.5, True
    return None, False
