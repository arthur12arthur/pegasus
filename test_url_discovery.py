"""
Tests de url_discovery.py.

Données de test :
- HEADER_REEL_24_09 : en-tête réel du journal LONAB du 24/09/2026, tel que
  renvoyé par un extracteur de texte PDF.
- HEADER_LAYOUT : même contenu mis en page comme `pdftotext -layout` (lignes
  centrées, colonnes séparées par de grands espaces) — variante construite à
  la main pour vérifier la tolérance à la mise en page.
- LISTING_HTML : extrait construit à la main d'une page de liste Canal Turf.
  Les href sont ceux réellement observés (page "demain" du 28/09/2026, et
  le lien Compiègne 24/09 réellement utilisé lors du dry-run) ; seul
  l'habillage HTML est reconstitué, car seuls les href sont exploités.

Exécution : python -m unittest pegasus_repo.test_url_discovery -v
"""

from __future__ import annotations

import unittest
from datetime import date
from unittest import mock

import requests

from .url_discovery import (
    DecouverteError,
    candidate_listing_urls,
    discover_canalturf_url,
    match_race,
    parse_canalturf_listing,
    parse_course_header,
    slugify,
)

HEADER_REEL_24_09 = """Numéros clientèle : 25 49 72 00 / 70 20 01 10
AN XXV - N° 44 478 - GRATUIT
"QUARTE" DU JEUDI 24 SEPTEMBRE 2026
COMPIEGNE - PRIX DE LA BASSE AUTOMNE
 16 CONCURRENTS - 1ère COURSE - PLAT
52 800 EUROS (ENV. 34 500 000 F CFA) - 1 600 METRES
Pour son premier essai dans un gros handicap, VICTORY PACE (8) a remarquablement tenu sa partie
"""

HEADER_LAYOUT = """
        Numéros clientèle : 25 49 72 00 / 70 20 01 10          AN XXV - N° 44 478 - GRATUIT

                    "QUARTE" DU JEUDI 24 SEPTEMBRE 2026
                  COMPIEGNE - PRIX DE LA BASSE AUTOMNE
                16 CONCURRENTS - 1ère COURSE - PLAT
          52 800 EUROS (ENV. 34 500 000 F CFA) - 1 600 METRES
"""

# Course de trot (en-tête reconstitué d'après les données du 20/09 : Vincennes,
# Prix d'Ancenis, 13 concurrents, 2 700 m) — construit, pas copié d'un PDF.
HEADER_TROT = """
"4+1" DU DIMANCHE 20 SEPTEMBRE 2026
PARIS-VINCENNES - PRIX D'ANCENIS
 13 CONCURRENTS - 4ème COURSE - TROT ATTELE
59 000 EUROS (ENV. 38 500 000 F CFA) - 2 700 METRES
"""

LISTING_HTML = """
<h2>Réunion 1 - ENGHIEN</h2>
<a href="https://www.canalturf.com/pronostics-PMU/2026-09-28/enghien/419008_prix-de-saint-chamond.html">1 13:55 <strong>PRIX DE SAINT-CHAMOND</strong> TROT ATTELE - 2150m - 59 000.00€</a>
<a href="https://www.canalturf.com/pronostics-PMU/2026-09-28/enghien/419015_prix-d-egletons.html">8 18:00 <strong>PRIX D'EGLETONS</strong> TROT ATTELE - 2875m - 60 000.00€</a>
<h2>Réunion 2 - CRAON</h2>
<a href="https://www.canalturf.com/pronostics-PMU/2026-09-28/craon/419016_prix-groupama-prix-de-champagne.html">1 10:50 <strong>PRIX GROUPAMA (PRIX DE CHAMPAGNE)</strong> PLAT - 1300m - 14 600.00€</a>
<h2>Réunion 5 - LE CROISE-LAROCHE</h2>
<a href="https://www.canalturf.com/pronostics-PMU/2026-09-28/le-croise-laroche/419031_prix-croise-laroche-fr.html">3 19:37 <strong>PRIX CROISE-LAROCHE.FR</strong> TROT ATTELE - 2700m - 19 000.00€</a>
<a href="/pronostics-PMU/2026-09-28/le-croise-laroche/419033_prix-de-loos.html">5 20:37 <strong>PRIX DE LOOS</strong> TROT ATTELE - 2700m - 21 000.00€</a>
<h2>Compiègne (autre jour)</h2>
<a href="https://www.canalturf.com/pronostics-PMU/2026-09-24/compiegne/418641_prix-de-la-basse-automne.html">8 13:55 <strong>PRIX DE LA BASSE AUTOMNE</strong> PLAT - 1600m - 52 800.00€</a>
<a href="https://www.canalturf.com/pronostics-PMU/2026-09-24/compiegne/418640_prix-de-la-basse.html">7 13:20 <strong>PRIX DE LA BASSE</strong> PLAT - 1600m - 20 000.00€</a>
<a href="https://www.canalturf.com/pronostics-PMU/2026-09-24/compiegne/418641_prix-de-la-basse-automne.html">doublon du même lien</a>
"""


class TestParseCourseHeader(unittest.TestCase):
    def test_entete_reel_du_24_09(self):
        h = parse_course_header(HEADER_REEL_24_09)
        self.assertEqual(h.hippodrome, "COMPIEGNE")
        self.assertEqual(h.nom_course, "PRIX DE LA BASSE AUTOMNE")
        self.assertEqual(h.nb_concurrents, 16)
        self.assertEqual(h.distance_metres, 1600)
        self.assertEqual(h.discipline_brute, "PLAT")

    def test_mise_en_page_pdftotext_layout(self):
        h = parse_course_header(HEADER_LAYOUT)
        self.assertEqual(h.hippodrome, "COMPIEGNE")
        self.assertEqual(h.nom_course, "PRIX DE LA BASSE AUTOMNE")
        self.assertEqual(h.distance_metres, 1600)

    def test_hippodrome_avec_tiret_et_nom_avec_apostrophe(self):
        h = parse_course_header(HEADER_TROT)
        self.assertEqual(h.hippodrome, "PARIS-VINCENNES")
        self.assertEqual(h.nom_course, "PRIX D'ANCENIS")
        self.assertEqual(h.distance_metres, 2700)

    def test_entete_absent_leve_une_erreur_avec_extrait(self):
        with self.assertRaises(DecouverteError) as ctx:
            parse_course_header("Rien de reconnaissable ici\nAutre ligne")
        self.assertIn("Rien de reconnaissable", str(ctx.exception))

    def test_ligne_de_titre_du_journal_nest_pas_prise_pour_la_course(self):
        """'AN XXV - N° 44 478 - GRATUIT' contient ' - ' mais ne doit jamais
        être lu comme hippodrome/nom de course."""
        h = parse_course_header(HEADER_REEL_24_09)
        self.assertNotIn("GRATUIT", h.nom_course)


class TestSlugify(unittest.TestCase):
    def test_cas_observes_sur_canalturf(self):
        self.assertEqual(slugify("PRIX D'ANCENIS"), "prix-d-ancenis")
        self.assertEqual(slugify("PRIX GROUPAMA (PRIX DE CHAMPAGNE)"), "prix-groupama-prix-de-champagne")
        self.assertEqual(slugify("PRIX CROISE-LAROCHE.FR"), "prix-croise-laroche-fr")
        self.assertEqual(slugify("PARIS-VINCENNES"), "paris-vincennes")
        self.assertEqual(slugify("BORDEAUX-LE BOUSCAT"), "bordeaux-le-bouscat")

    def test_accents(self):
        self.assertEqual(slugify("Thiérache Été"), "thierache-ete")


class TestParseListing(unittest.TestCase):
    def setUp(self):
        self.courses = parse_canalturf_listing(LISTING_HTML)

    def test_extrait_les_courses_sans_doublon(self):
        urls = [c.url for c in self.courses]
        self.assertEqual(len(urls), len(set(urls)))
        # 7 liens distincts dans l'extrait ; le 8e href est un doublon volontaire
        self.assertEqual(len(self.courses), 7)

    def test_href_relatif_devient_absolu(self):
        loos = next(c for c in self.courses if c.race_id == "419033")
        self.assertTrue(loos.url.startswith("https://www.canalturf.com/"))

    def test_date_hippodrome_et_slug(self):
        c = next(c for c in self.courses if c.race_id == "418641")
        self.assertEqual(c.jour, date(2026, 9, 24))
        self.assertEqual(c.hippodrome_slug, "compiegne")
        self.assertEqual(c.race_slug, "prix-de-la-basse-automne")
        self.assertEqual(c.distance_metres, 1600)


class TestMatchRace(unittest.TestCase):
    def setUp(self):
        self.courses = parse_canalturf_listing(LISTING_HTML)

    def test_correspondance_exacte_compiegne(self):
        h = parse_course_header(HEADER_REEL_24_09)
        r = match_race(h, self.courses, date(2026, 9, 24))
        self.assertEqual(r.methode, "exacte")
        self.assertEqual(
            r.race.url,
            "https://www.canalturf.com/pronostics-PMU/2026-09-24/compiegne/418641_prix-de-la-basse-automne.html",
        )
        self.assertEqual(r.avertissements, [])

    def test_ne_confond_pas_avec_le_prix_voisin_de_meme_debut(self):
        """'prix-de-la-basse' et 'prix-de-la-basse-automne' existent tous deux
        sur Compiègne : le nom exact doit gagner."""
        h = parse_course_header(HEADER_REEL_24_09)
        r = match_race(h, self.courses, date(2026, 9, 24))
        self.assertEqual(r.race.race_id, "418641")

    def test_ignore_les_courses_dun_autre_jour(self):
        h = parse_course_header(HEADER_REEL_24_09)
        with self.assertRaises(DecouverteError):
            match_race(h, self.courses, date(2026, 9, 28))  # Compiègne n'y est pas

    def test_hippodrome_inconnu_liste_les_hippodromes_disponibles(self):
        h = parse_course_header(HEADER_TROT)  # Paris-Vincennes absent de la liste
        with self.assertRaises(DecouverteError) as ctx:
            match_race(h, self.courses, date(2026, 9, 28))
        self.assertIn("enghien", str(ctx.exception))

    def test_nom_absent_sur_le_bon_hippodrome_ne_devine_pas(self):
        h = parse_course_header(HEADER_REEL_24_09.replace("BASSE AUTOMNE", "VALLEE DES ROIS"))
        with self.assertRaises(DecouverteError):
            match_race(h, self.courses, date(2026, 9, 24))

    def test_correspondance_approchee_signalee(self):
        courses = parse_canalturf_listing(
            '<a href="/pronostics-PMU/2026-09-28/craon/419016_prix-groupama-prix-de-champagne.html">x</a>'
        )
        h = parse_course_header(
            "CRAON - PRIX GROUPAMA PRIX DE CHAMPAGNES\n 12 CONCURRENTS - 1ère COURSE - PLAT\n"
            "14 600 EUROS - 1 300 METRES\n"
        )
        r = match_race(h, courses, date(2026, 9, 28))
        self.assertEqual(r.methode, "approchee")
        self.assertTrue(any("approchée" in a for a in r.avertissements))

    def test_distance_differente_est_signalee_sans_bloquer(self):
        h = parse_course_header(HEADER_REEL_24_09.replace("1 600 METRES", "1 800 METRES"))
        r = match_race(h, self.courses, date(2026, 9, 24))
        self.assertTrue(any("Distance différente" in a for a in r.avertissements))


class TestCandidateListingUrls(unittest.TestCase):
    def test_aujourdhui_utilise_la_page_du_jour_en_premier(self):
        urls = candidate_listing_urls(date(2026, 9, 28), today=date(2026, 9, 28))
        self.assertTrue(urls[0].endswith("/courses_liste_pronostics.php"))

    def test_demain_utilise_la_page_demain_en_premier(self):
        urls = candidate_listing_urls(date(2026, 9, 28), today=date(2026, 9, 27))
        self.assertTrue(urls[0].endswith("/courses_liste_pronostics_demain.php"))

    def test_url_datee_identique_a_lexemple_reel_du_26_09(self):
        urls = candidate_listing_urls(date(2026, 9, 26), today=date(2026, 9, 1))
        self.assertEqual(
            urls[-1],
            "https://www.canalturf.com/pronostics-PMU/2026-09-26_pronostics-cotes-des-courses-du-samedi-26-septembre-2026.html",
        )


class TestDiscoverAvecReseauSimule(unittest.TestCase):
    def _reponse(self, texte="", status=200):
        r = mock.Mock()
        r.text = texte
        r.status_code = status
        if status >= 400:
            r.raise_for_status.side_effect = requests.HTTPError(f"{status}")
        else:
            r.raise_for_status.return_value = None
        return r

    def test_bascule_sur_la_page_suivante_si_la_premiere_echoue(self):
        session = mock.Mock()
        session.get.side_effect = [self._reponse(status=500), self._reponse(LISTING_HTML)]
        h = parse_course_header(HEADER_REEL_24_09)
        r = discover_canalturf_url(h, date(2026, 9, 24), today=date(2026, 9, 24), session=session)
        self.assertEqual(r.race.race_id, "418641")
        self.assertEqual(session.get.call_count, 2)

    def test_toutes_les_pages_echouent_erreur_explicite(self):
        session = mock.Mock()
        session.get.return_value = self._reponse(status=503)
        h = parse_course_header(HEADER_REEL_24_09)
        with self.assertRaises(DecouverteError) as ctx:
            discover_canalturf_url(h, date(2026, 9, 24), today=date(2026, 9, 24), session=session)
        self.assertIn("introuvable", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
