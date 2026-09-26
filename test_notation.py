"""
Tests de verrouillage pour notation.py.
Exécution : python -m unittest pegasus_repo.test_notation -v
"""

from __future__ import annotations

import unittest

from .notation import (
    calculer_notes,
    note_forme_depuis_musique,
    notes_historique_depuis_gains,
)


class TestNoteFormeDepuisMusique(unittest.TestCase):
    def test_musique_absente_est_signalee_pas_inventee(self):
        note, manquant = note_forme_depuis_musique(None)
        self.assertIsNone(note)
        self.assertTrue(manquant)

        note, manquant = note_forme_depuis_musique("")
        self.assertIsNone(note)
        self.assertTrue(manquant)

    def test_victoires_recentes_donnent_une_note_elevee(self):
        note, manquant = note_forme_depuis_musique("1.1.1.1.1")
        self.assertFalse(manquant)
        self.assertAlmostEqual(note, 10.0, places=1)

    def test_non_classe_repete_donne_une_note_basse(self):
        note, _ = note_forme_depuis_musique("0.0.0.0.0")
        self.assertAlmostEqual(note, 0.0, places=1)

    def test_recence_pese_plus_que_l_anciennete(self):
        """Une victoire récente suivie de mauvais résultats anciens doit
        noter mieux que l'inverse (mauvais résultat récent, victoires
        anciennes) — la pondération doit privilégier le caractère le plus
        à gauche."""
        note_victoire_recente, _ = note_forme_depuis_musique("1.9.9.9.9")
        note_victoire_ancienne, _ = note_forme_depuis_musique("9.9.9.9.1")
        self.assertGreater(note_victoire_recente, note_victoire_ancienne)

    def test_caractere_non_numerique_traite_comme_pire_cas_documente(self):
        note, manquant = note_forme_depuis_musique("D.1.1.1.1")
        self.assertFalse(manquant)
        # le 'D' (disqualifié, par convention prudente) compte 0 point en
        # position la plus pesante -> note nettement inférieure à 5 victoires
        note_toutes_victoires, _ = note_forme_depuis_musique("1.1.1.1.1")
        self.assertLess(note, note_toutes_victoires)

    def test_musique_courte_reste_valide(self):
        note, manquant = note_forme_depuis_musique("1.3")
        self.assertFalse(manquant)
        self.assertGreater(note, 0)


class TestNotesHistoriqueDepuisGains(unittest.TestCase):
    def test_gains_absents_signales_pas_inventes(self):
        resultats = notes_historique_depuis_gains({1: None, 2: 50000.0})
        note1, manquant1 = resultats[1]
        self.assertIsNone(note1)
        self.assertTrue(manquant1)

    def test_meilleur_gains_du_groupe_note_dix(self):
        resultats = notes_historique_depuis_gains({1: 10000.0, 2: 90000.0})
        note_max, _ = resultats[2]
        self.assertAlmostEqual(note_max, 10.0, places=1)

    def test_pire_gains_du_groupe_note_zero(self):
        resultats = notes_historique_depuis_gains({1: 10000.0, 2: 90000.0})
        note_min, _ = resultats[1]
        self.assertAlmostEqual(note_min, 0.0, places=1)

    def test_gains_identiques_donnent_note_neutre_sans_erreur(self):
        resultats = notes_historique_depuis_gains({1: 50000.0, 2: 50000.0})
        note1, manquant1 = resultats[1]
        note2, manquant2 = resultats[2]
        self.assertAlmostEqual(note1, 5.0)
        self.assertAlmostEqual(note2, 5.0)
        self.assertFalse(manquant1)
        self.assertFalse(manquant2)

    def test_tous_gains_manquants_ne_leve_aucune_exception(self):
        resultats = notes_historique_depuis_gains({1: None, 2: None})
        for _, manquant in resultats.values():
            self.assertTrue(manquant)


class TestCalculerNotes(unittest.TestCase):
    def test_groupe_reel_compiegne_24_09(self):
        """Reproduit les 15 musiques réellement extraites par Manus le
        24/09/2026 (Compiègne, Prix de la Basse Automne) — vérifie que le
        calcul tourne sans erreur sur un cas réel et que l'ordre relatif
        est cohérent avec les commentaires officiels reçus."""
        musiques = {
            1: "1.1.3.9.3", 2: "8.5.1.2.2", 3: "1.2.1.6.9", 4: "2.1.2.0.5",
            5: "0.1.2.7.5", 6: "1.3.3.9", 7: "3.5.7.1.3", 8: "4.1.5.2.2",
            9: "0.7.1.2", 10: "2.2.9.4.5", 12: "1.5.1.2.1", 13: "0.3.1.4.2",
            14: "1.6.3.0.8", 15: "0.0.9.8.5", 16: "4.3.2.1.4",
        }
        gains = {n: 100000.0 for n in musiques}  # isole la composante forme
        resultats = calculer_notes(musiques, gains)

        self.assertEqual(len(resultats), 15)
        for r in resultats.values():
            self.assertFalse(r.forme_manquante)
            self.assertFalse(r.historique_manquant)

        # n°15 (musique "0.0.9.8.5", commentaire défavorable côté Manus)
        # doit noter nettement plus bas que n°12 (musique "1.5.1.2.1",
        # "impressionnant lauréat" selon le commentaire officiel)
        self.assertLess(resultats[15].note_forme, resultats[12].note_forme)


if __name__ == "__main__":
    unittest.main()
