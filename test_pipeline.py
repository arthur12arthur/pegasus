from __future__ import annotations

from datetime import date
import json
import unittest
from unittest.mock import Mock

from .discipline import detect_discipline
from .ingestion import find_journal_link, parse_horses
from .marketwatch import MarketQuote, MarketWatch, MappingQuoteProvider
from .models import Horse
from .open_pmu_api import OpenPmuApiClient


class TestIngestion(unittest.TestCase):
    def test_match_exact_date_et_vrai_href(self):
        html = '''<table><tr><td class="views-field-title">journal hippique PMU&#039;B du 21 septembre 2026</td><td><a href="/old.pdf">Télécharger</a></td></tr><tr><td class="views-field-title">journal hippique PMU&#039;B du 22 septembre 2026</td><td><a href="/actual.pdf">Télécharger</a></td></tr></table>'''
        link = find_journal_link(html, date(2026, 9, 22), "https://lonab.bf/programme-pmub")
        self.assertEqual(link.pdf_url, "https://lonab.bf/actual.pdf")

    def test_date_absente_de_la_page_courante_est_signalee(self):
        html = '<table><tr><td class="views-field-title">journal hippique PMU&#039;B du 21 septembre 2026</td><td><a href="/old.pdf">Télécharger</a></td></tr></table>'
        with self.assertRaises(LookupError):
            find_journal_link(html, date(2026, 9, 22))

    def test_champs_absents_restant_neutres_et_signales(self):
        text = "01 CHEVAL TEST       DRIVER X       100 000   12/1\n"
        horses, missing, warnings = parse_horses(text)
        self.assertEqual(len(horses), 1)
        self.assertEqual(horses[0].nom, "CHEVAL TEST")
        self.assertEqual(horses[0].note_forme, 0.0)
        self.assertIn("notes BaseScorer", missing[1])
        self.assertFalse(warnings)


class TestDiscipline(unittest.TestCase):
    def test_direct_et_repli(self):
        self.assertEqual(detect_discipline("Trot attelé").discipline, "trot")
        result = detect_discipline(None, "PRIX DE HAIES — 3500 mètres")
        self.assertEqual(result.discipline, "obstacle")
        self.assertEqual(result.confidence, "moyenne")


class TestMarketWatch(unittest.TestCase):
    def test_delta_et_non_partant_sont_explicites(self):
        horses = [Horse(1, "A", 10.0), Horse(2, "B", 20.0)]
        provider = MappingQuoteProvider({1: MarketQuote(1, 15.0, source="test"), 2: MarketQuote(2, None, True, "test")})
        result = MarketWatch([provider]).update(horses)
        self.assertEqual(horses[0].cote_actuelle, 15.0)
        self.assertAlmostEqual(result.deltas_relatives[1], 0.5)
        self.assertEqual(result.missing_numbers, [2])
        self.assertTrue(any("non-partant" in warning for warning in result.warnings))


class TestOpenPmuApi(unittest.TestCase):
    def test_schema_et_conversion_position(self):
        session = Mock()
        response = Mock(status_code=200)
        response.json.return_value = {"error": False, "message": [{"arrivee": [2, 9, 13]}]}
        session.get.return_value = response
        client = OpenPmuApiClient(session=session)
        result = client.results_by_date(date(2026, 8, 18))
        session.get.assert_called_once()
        self.assertEqual(result.races[0]["arrivee"], [2, 9, 13])
        self.assertEqual(client.arrival_for_horse(result.races[0], 9), 2)


if __name__ == "__main__":
    unittest.main()
