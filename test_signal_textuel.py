"""
Tests de verrouillage pour signal_textuel.py, sur les 15 commentaires
officiels réels reçus le 24/09/2026 (Compiègne, Prix de la Basse Automne).
Exécution : python -m unittest pegasus_repo.test_signal_textuel -v
"""

from __future__ import annotations

import unittest

from .signal_textuel import note_aptitude_depuis_commentaire, note_fraicheur_depuis_commentaire

# Commentaires réels, tels que reçus (certains tronqués à l'extraction —
# conservés tronqués ici volontairement, pour tester le comportement sur
# des données réellement incomplètes, pas un cas d'école propre).
COMMENTAIRES_COMPIEGNE_24_09 = {
    1: "Irréprochable lorsqu'il était sous la férule de Tiago Martins, il s'est imposé dans des "
       "handicaps pour ses deux premières sorties sous la férule de Sandrine Gavilan. Il a été "
       "pénalisé de onze livres au total et monte nettement de catégorie. Il devra se surpasser "
       "pour espérer finir dans les cinq premiers.",
    4: "Prise en note en tout début de carrière, elle a toutefois dû attendre sa sixième sortie "
       "publique pour ouvrir son palmarès. Elle vient de montrer sa compétitivité en valeur 38 sur "
       "le \"toboggan\" de ParisLongchamp et les 200 mètres supplémentaires ne devraient pas la "
       "contrarier, bien au contraire. Une priorité !",
    5: "Délaissée par les parieurs pour son premier essai dans les Quinté+, dans la course clé du "
       "30 août, elle a été desservie par le terrain collant ce jour-là. Elle présente l'avantage "
       "de connaître Compiègne, mais sa compétitivité dans les handicaps reste à démontrer.",
    6: "Cette représentante des frères Wertheimer ne cesse de progresser et vient d'ouvrir son "
       "palmarès à la lutte à Clairefontaine. Elle débute dans les handicaps et affronte les mâles "
       "pour la première fois, mais elle connaît Compiègne et n'a sans doute pas encore tout montré.",
    7: "Chuchoté pour ses débuts dans les Quinté+, le 30 août à Deauville, il a fourni une belle "
       "valeur (3e). Les données changent, mais il a déjà gagné en bon terrain et à Compiègne.",
    8: "Elle n'a jamais déçu en deux essais sur ce parcours (1re et 2e) et a fourni un excellent "
       "effort final dans l'épreuve clé (4e), alors qu'elle n'était pas dans la bonne portion de "
       "piste. Elle est très compétitive à cette valeur et constitue un solide point d'appui.",
    9: "Après une réapparition victorieuse à Saint-Cloud, le 5 mai, elle nous a déçus à deux "
       "reprises. Ses débuts dans les Quinté+ n'ont pas été concluants (13e) et elle aurait "
       "préféré une piste bien plus souple. D'autres protagonistes lui sont préférables.",
    10: "Castré au printemps, ce fils",  # tronqué à l'extraction
    12: "Impressionnant lauréat d'un",  # tronqué à l'extraction
    16: "Il ne cesse de se distinguer dans les gros handicaps et a déjà brillé sur le tracé "
        "spécial de Compiègne. Il s'adapte à tous les terrains et a",
}


class TestNoteAptitudeDepuisCommentaire(unittest.TestCase):
    def test_commentaire_absent_non_confiant(self):
        note, confiant = note_aptitude_depuis_commentaire(None)
        self.assertIsNone(note)
        self.assertFalse(confiant)

    def test_connait_lhippodrome_est_un_signal_positif(self):
        note, confiant = note_aptitude_depuis_commentaire(COMMENTAIRES_COMPIEGNE_24_09[5])
        self.assertTrue(confiant)
        self.assertGreater(note, 5.0)

    def test_distance_ne_devrait_pas_contrarier_est_positif(self):
        note, confiant = note_aptitude_depuis_commentaire(COMMENTAIRES_COMPIEGNE_24_09[4])
        self.assertTrue(confiant)
        self.assertGreater(note, 5.0)

    def test_aurait_prefere_une_piste_est_negatif(self):
        note, confiant = note_aptitude_depuis_commentaire(COMMENTAIRES_COMPIEGNE_24_09[9])
        self.assertTrue(confiant)
        self.assertLess(note, 5.0)

    def test_sadapte_a_tous_les_terrains_est_positif(self):
        note, confiant = note_aptitude_depuis_commentaire(COMMENTAIRES_COMPIEGNE_24_09[16])
        self.assertTrue(confiant)
        self.assertGreater(note, 5.0)

    def test_commentaire_tronque_sans_motif_nest_pas_confiant(self):
        note, confiant = note_aptitude_depuis_commentaire(COMMENTAIRES_COMPIEGNE_24_09[10])
        self.assertFalse(confiant)
        self.assertIsNone(note)

    def test_commentaire_sans_signal_nest_pas_confiant(self):
        # n°1 : commentaire riche mais qui ne parle ni de terrain ni de distance
        note, confiant = note_aptitude_depuis_commentaire(COMMENTAIRES_COMPIEGNE_24_09[1])
        self.assertFalse(confiant)
        self.assertIsNone(note)


class TestNoteFraicheurDepuisCommentaire(unittest.TestCase):
    def test_reapparition_victorieuse_est_positive(self):
        note, confiant = note_fraicheur_depuis_commentaire(COMMENTAIRES_COMPIEGNE_24_09[9])
        self.assertTrue(confiant)
        self.assertGreater(note, 5.0)

    def test_aucun_signal_de_fraicheur_sur_le_reste_du_lot(self):
        """Vérifie honnêtement qu'aucun des autres commentaires réels ne
        déclenche de faux positif de fraîcheur — cohérent avec la
        documentation du module (signal rare sur ce type de texte)."""
        for numero, commentaire in COMMENTAIRES_COMPIEGNE_24_09.items():
            if numero == 9:
                continue
            with self.subTest(numero=numero):
                _, confiant = note_fraicheur_depuis_commentaire(commentaire)
                self.assertFalse(confiant)


if __name__ == "__main__":
    unittest.main()
