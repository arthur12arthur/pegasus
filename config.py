"""
Grille numérique figée de Pegasus.

Toute valeur ici doit rester identique d'une exécution à l'autre pour une
même course. Ne jamais faire varier ces paramètres au niveau du code appelant
— si une valeur doit changer, elle change ici, une fois, avec une raison
documentée en commentaire.
"""

from __future__ import annotations

# --- Protocole Monte Carlo ---------------------------------------------
SEEDS: list[int] = [42, 43, 44, 45, 46]
SIMULATIONS_PER_SEED: int = 10_000
# Le Top 3 (ensemble, ordre non pris en compte) doit être identique sur au
# moins ce nombre de seeds sur 5 pour ne pas abaisser l'indice de confiance.
MIN_STABLE_SEEDS_FOR_TOP3: int = 4

# --- Filtrage (portillon éliminatoire) ----------------------------------
RISK_ELIMINATION_THRESHOLD: int = 3          # score de risque >= seuil -> écarté
MIN_RETAINED_HORSES: int = 5                  # taille minimale du groupe filtré
FORCE_KEEP_LOWEST_COTE_COUNT: int = 5         # favoris aux cotes les plus basses, maintien forcé

# Points de risque par critère (ajustables ici uniquement — documentés pour
# rester auditables ; Manus ne doit jamais les modifier sans le signaler).
RISK_POINTS = {
    "gains_insuffisants": 1,
    "forme_catastrophique": 2,      # ex. 3+ disqualifications sur les 5 dernières
    "cote_extreme": 1,              # cote PDF au-delà d'un seuil élevé (configurable à l'appel)
    "absence_prolongee": 1,         # pas couru depuis longtemps sans rentrée récente
    "surclassement_signale": 1,     # commentaire officiel indique surclassement
    "delta_cote_hausse_forte": 1,   # MarketWatch : forte hausse de cote (délaissement marché)
}

# --- BaseScorer : pondération par discipline ----------------------------
WEIGHTS_BY_DISCIPLINE = {
    "trot": {
        "historique": 0.30,
        "forme": 0.25,
        "aptitude": 0.15,
        "technique": 0.20,
        "fraicheur": 0.10,
    },
    "plat": {
        "historique": 0.30,
        "forme": 0.25,
        "aptitude": 0.20,
        "technique": 0.15,
        "fraicheur": 0.10,
    },
    "obstacle": {
        "historique": 0.25,
        "forme": 0.25,
        "aptitude": 0.15,
        "technique": 0.20,
        "fraicheur": 0.15,
    },
}

# --- Sous-composante Technique (trot uniquement) — historique de ferrure
TECHNIQUE_TROT_SUBWEIGHTS = {
    "ferrure_adequation": 0.60,
    "driver_configuration": 0.25,
    "fiabilite_historique": 0.15,
}

FERRURE_ADEQUATION_SUBWEIGHTS = {
    "efficacite_configuration_exacte": 0.40,
    "conditions_comparables": 0.30,
    "regularite": 0.20,
    "recence": 0.10,
}

# Lissage bayésien : efficacité_lissée = (n*observé + K*baseline) / (n+K)
BAYESIAN_SMOOTHING_K: float = 3.0

VALID_DISCIPLINES = tuple(WEIGHTS_BY_DISCIPLINE.keys())
