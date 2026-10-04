"""
Tests du repli "colonnes complètes" (parse_horses_columnar), sur le vrai
texte extrait du journal LONAB d'Enghien du 28/09/2026 (trot, autostart) —
le premier PDF qui a fait échouer parse_horses() en conditions réelles
(workflow GitHub Actions, run manuel).

Exécution : python -m unittest pegasus_repo.test_ingestion_columnar -v
"""

from __future__ import annotations

import unittest
from pathlib import Path

from .ingestion import ColumnLayoutError, parse_horses, parse_horses_columnar

FIXTURE = Path(__file__).parent / "fixtures" / "lonab_enghien_28-09-2026_trot_colonnes.txt"
TEXTE_REEL = FIXTURE.read_text(encoding="utf-8")


class TestParseHorsesLigneParLigneNeTrouveRien(unittest.TestCase):
    def test_format_ligne_par_ligne_echoue_sur_ce_texte(self):
        """Confirme le diagnostic du run réel : parse_horses() (row-major)
        renvoie bien une liste vide sur ce PDF — c'est exactement pour ça
        que le repli colonnaire existe."""
        horses, missing, warnings = parse_horses(TEXTE_REEL)
        self.assertEqual(horses, [])
        self.assertTrue(warnings)


class TestParseHorsesColumnar(unittest.TestCase):
    def setUp(self):
        self.horses, self.raw_fields, self.missing, self.warnings = parse_horses_columnar(TEXTE_REEL)

    def test_quinze_chevaux_extraits(self):
        self.assertEqual(len(self.horses), 15)
        self.assertEqual({h.numero for h in self.horses}, set(range(1, 16)))

    def test_noms_corrects(self):
        noms = {h.numero: h.nom for h in self.horses}
        self.assertEqual(noms[1], "IDYLLE DU PERSIL")
        self.assertEqual(noms[4], "JOS MAZA")
        self.assertEqual(noms[15], "INTREPIDE DES BOIS")

    def test_gains_corrects(self):
        gains = {h.numero: h.gains_euros for h in self.horses}
        self.assertEqual(gains[1], 219700.0)
        self.assertEqual(gains[12], 202650.0)

    def test_musique_et_driver_extraits(self):
        self.assertEqual(self.raw_fields[10].musique, "1.1.1.2.2")
        self.assertEqual(self.raw_fields[10].driver, "P.L. DESAUNETTE")
        self.assertEqual(self.raw_fields[15].musique, "2.2.2.2.3")

    def test_commentaire_narratif_associe_au_bon_cheval(self):
        c4 = self.raw_fields[4].commentaire
        self.assertIsNotNone(c4)
        self.assertIn("Bird Parker", c4)
        self.assertIn("Pays-Bas", c4)
        # ne doit pas déborder sur le commentaire du cheval suivant
        self.assertNotIn("HAPPY PACHA", c4.upper())

    def test_cote_pdf_ambigue_reste_none_sur_les_deux_blocs_reels(self):
        """Le vrai PDF contient deux blocs de 15 cotes différents (cote
        PMU ? cote Paris Turf ? — ambigu depuis le texte seul). Le parseur
        ne doit jamais en choisir un au hasard."""
        for h in self.horses:
            self.assertIsNone(h.cote_pdf)
        self.assertTrue(any("ambigu" in w for w in self.warnings))

    def test_cote_manquante_tracee_dans_missing_fields(self):
        for numero in range(1, 16):
            self.assertTrue(
                any("cote_pdf" in champ for champ in self.missing[numero]),
                f"cote_pdf devrait être signalée manquante pour le n°{numero}",
            )


class TestParseHorsesColumnarCasLimites(unittest.TestCase):
    def test_aucun_format_reconnu_leve_column_layout_error(self):
        with self.assertRaises(ColumnLayoutError):
            parse_horses_columnar("Texte sans rapport avec un journal LONAB.\n5 CONCURRENTS\n")

    def test_bloc_numeros_non_sequentiel_leve_une_erreur_explicite(self):
        # 5 concurrents, bloc sexe/âge valide, mais les numéros précédents
        # ne sont pas 1..5 dans l'ordre -> ne doit pas être accepté en silence.
        texte = "5 CONCURRENTS\n" + "\n".join(["9", "9", "9", "9", "9"]) + "\n" + "\n".join(
            ["F.8", "H.7", "H.8", "H.7", "H.9"]
        )
        with self.assertRaises(ColumnLayoutError) as ctx:
            parse_horses_columnar(texte)
        self.assertIn("1..5", str(ctx.exception))

    def test_cote_unique_est_bien_utilisee_quand_non_ambigue(self):
        """Cas simple construit à la main : un seul bloc de cotes -> pas
        d'ambiguïté, la cote doit être utilisée normalement."""
        texte = "\n".join([
            "3 CONCURRENTS",
            "5/1", "10/1", "20/1",
            "1", "2", "3",
            "F.8", "H.7", "H.8",
            "2100.M", "2100.M", "2100.M",
            "1.11.00", "1.11.50", "1.12.00",
            "1.2.3", "4.5.6", "7.8.9",
            "100 000", "90 000", "80 000",
            "CHEVAL UN", "CHEVAL DEUX", "CHEVAL TROIS",
            "A. DRIVER", "B. DRIVER", "C. DRIVER",
        ])
        horses, raw, missing, warnings = parse_horses_columnar(texte)
        self.assertEqual(horses[0].cote_pdf, 5.0)
        self.assertEqual(horses[1].cote_pdf, 10.0)
        self.assertFalse(any("ambigu" in w for w in warnings))


if __name__ == "__main__":
    unittest.main()
