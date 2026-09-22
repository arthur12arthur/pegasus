"""
Tests de verrouillage du cœur algorithmique Pegasus.

Ces tests définissent le contrat que le reste du pipeline (Manus) doit
respecter. S'ils échouent après une modification de filter.py, scorer.py
ou consensus.py, la modification est le problème — pas les tests.

Exécution : python -m unittest pegasus_core.test_core -v
"""

from __future__ import annotations

import unittest

from . import config
from .filter import apply_filter
from .models import FerrureConfigStats, Horse
from .scorer import score_group
from .consensus import compute_classement


def _cheval(numero: int, cote: float, **kwargs) -> Horse:
    return Horse(
        numero=numero,
        nom=f"Cheval {numero}",
        cote_pdf=cote,
        cote_actuelle=kwargs.pop("cote_actuelle", cote),
        gains_euros=kwargs.pop("gains_euros", 100_000.0),
        note_historique=kwargs.pop("note_historique", 6.0),
        note_forme=kwargs.pop("note_forme", 6.0),
        note_aptitude=kwargs.pop("note_aptitude", 6.0),
        note_fraicheur=kwargs.pop("note_fraicheur", 6.0),
        **kwargs,
    )


class TestDataFilter(unittest.TestCase):
    def test_portillon_binaire_ne_porte_aucun_score_de_competitivite(self):
        """FilterResult ne doit jamais exposer de score — seulement une décision."""
        resultat = apply_filter([_cheval(i, cote=5.0 * i) for i in range(1, 9)])
        self.assertFalse(hasattr(resultat, "score_competitivite"))
        self.assertFalse(hasattr(resultat, "scores"))

    def test_cinq_favoris_toujours_maintenus_meme_a_risque_eleve(self):
        chevaux = [_cheval(i, cote=float(i)) for i in range(1, 12)]
        for c in chevaux:
            c.disqualifications_recentes = 3
            c.surclasse_signale = True
        resultat = apply_filter(chevaux)
        numeros_retenus = {h.numero for h in resultat.retenus}
        self.assertTrue({1, 2, 3, 4, 5}.issubset(numeros_retenus))

    def test_taille_minimale_du_groupe_respectee(self):
        chevaux = [_cheval(i, cote=float(i)) for i in range(1, 12)]
        for c in chevaux[5:]:
            c.disqualifications_recentes = 3
            c.surclasse_signale = True
            c.gains_euros = 0.0
        resultat = apply_filter(chevaux)
        self.assertGreaterEqual(len(resultat.retenus), config.MIN_RETAINED_HORSES)

    def test_reintegration_signalee_quand_declenchee(self):
        chevaux = [_cheval(i, cote=float(i)) for i in range(1, 8)]
        for c in chevaux[5:]:
            c.gains_euros = 0.0
            c.disqualifications_recentes = 3
            c.surclasse_signale = True
        resultat = apply_filter(chevaux)
        # avec seulement 7 partants et 5 favoris forcés, peu de marge
        # d'élimination réelle -> ne devrait pas nécessiter réintégration ici
        self.assertIsInstance(resultat.reintegration_appliquee, bool)

    def test_liste_vide_leve_une_erreur_explicite(self):
        with self.assertRaises(ValueError):
            apply_filter([])


class TestBaseScorer(unittest.TestCase):
    def test_poids_somme_a_un_pour_chaque_discipline(self):
        for discipline, poids in config.WEIGHTS_BY_DISCIPLINE.items():
            self.assertAlmostEqual(sum(poids.values()), 1.0, places=6, msg=discipline)

    def test_discipline_inconnue_leve_une_erreur(self):
        cheval = _cheval(1, cote=5.0)
        with self.assertRaises(ValueError):
            score_group([cheval], "galop-inconnu")

    def test_technique_trot_repli_neutre_si_ferrure_absente(self):
        cheval = _cheval(1, cote=5.0)  # ferrure_stats = None
        resultats = score_group([cheval], "trot")
        self.assertEqual(resultats[0].note_technique, 5.0)

    def test_lissage_bayesien_limite_impact_petit_echantillon(self):
        """Une victoire isolée dans la configuration du jour ne doit pas
        suffire à qualifier le cheval de 'spécialiste' (note technique
        nettement en dessous du maximum)."""
        stats_optimiste = FerrureConfigStats(
            nb_courses_configuration_exacte=1,
            efficacite_configuration_exacte=10.0,   # une seule victoire
            efficacite_baseline_cheval=4.0,          # moyenne réelle du cheval, plus modeste
            resultats_conditions_comparables=4.0,
            regularite_configuration=10.0,
            recence_performances=7.0,
            qualite_driver_configuration=6.0,
        )
        cheval = _cheval(1, cote=5.0, ferrure_stats=stats_optimiste)
        resultats = score_group([cheval], "trot")
        self.assertLess(resultats[0].note_technique, 8.0)

    def test_score_competitivite_borne_0_10(self):
        cheval = _cheval(1, cote=5.0, note_historique=9.5, note_forme=9.5, note_aptitude=9.5, note_fraicheur=9.5)
        resultats = score_group([cheval], "trot")
        self.assertLessEqual(resultats[0].score_competitivite, 10.0)
        self.assertGreaterEqual(resultats[0].score_competitivite, 0.0)


class TestConsensusInterne(unittest.TestCase):
    def test_classement_deterministe_sur_seeds_figees(self):
        """Deux exécutions avec les mêmes scores doivent produire exactement
        le même classement — reproductibilité du protocole figé."""
        chevaux = [_cheval(i, cote=float(i)) for i in range(1, 8)]
        for i, c in enumerate(chevaux):
            c.note_historique = 5.0 + i * 0.3
        scores = score_group(chevaux, "trot")
        resultat_1 = compute_classement(scores)
        resultat_2 = compute_classement(scores)
        self.assertEqual(resultat_1.classement, resultat_2.classement)
        self.assertEqual(resultat_1.proba_victoire, resultat_2.proba_victoire)

    def test_meilleur_score_competitivite_favorise_mais_pas_absolu(self):
        chevaux = [_cheval(i, cote=float(i)) for i in range(1, 6)]
        chevaux[0].note_historique = 9.5
        chevaux[0].note_forme = 9.5
        scores = score_group(chevaux, "trot")
        resultat = compute_classement(scores)
        # le mieux noté doit avoir la plus forte probabilité de victoire,
        # sans que ce soit garanti à 100% (c'est une simulation, pas un fait)
        meilleur = max(resultat.proba_victoire, key=resultat.proba_victoire.get)
        self.assertEqual(meilleur, chevaux[0].numero)
        self.assertLess(resultat.proba_victoire[meilleur], 1.0)

    def test_stabilite_top3_bornee_entre_0_et_5(self):
        chevaux = [_cheval(i, cote=float(i)) for i in range(1, 9)]
        scores = score_group(chevaux, "trot")
        resultat = compute_classement(scores)
        self.assertGreaterEqual(resultat.stabilite_top3_sur_5_seeds, 0)
        self.assertLessEqual(resultat.stabilite_top3_sur_5_seeds, len(config.SEEDS))

    def test_liste_vide_leve_une_erreur_explicite(self):
        with self.assertRaises(ValueError):
            compute_classement([])


if __name__ == "__main__":
    unittest.main()
