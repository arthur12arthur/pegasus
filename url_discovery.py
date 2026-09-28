"""
Pegasus — url_discovery.py

Retrouve automatiquement la page Canal Turf de la course relayée par LONAB,
pour ne plus avoir à coller de lien à la main.

Principe :
1. Le PDF LONAB contient, en en-tête, l'hippodrome et le nom de la course
   (ex. "COMPIEGNE - PRIX DE LA BASSE AUTOMNE"), le nombre de concurrents,
   la discipline et la distance.
2. Canal Turf publie une page de liste par jour ; chaque course y a un lien
   de la forme  /pronostics-PMU/AAAA-MM-JJ/<hippodrome>/<id>_<nom-de-la-course>.html
   (structure vérifiée sur la vraie page du 28/09/2026).
3. On fait correspondre les deux par "slug" (minuscules, sans accents, sans
   ponctuation).

Règle de fond, la même que partout dans Pegasus : en cas de doute, on ne
devine pas. Aucune correspondance, ou plusieurs correspondances proches ->
erreur explicite qui liste les candidats. Une mauvaise page de cotes
donnerait des cotes d'une AUTRE course, sans que rien ne le signale : c'est
pire qu'un arrêt propre.
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, timedelta

import requests

CANALTURF_BASE = "https://www.canalturf.com"

_JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
_MOIS = ["janvier", "fevrier", "mars", "avril", "mai", "juin", "juillet",
         "aout", "septembre", "octobre", "novembre", "decembre"]

# Seuil de correspondance approximative sur le nom de course, quand le nom
# LONAB et le nom Canal Turf ne sont pas strictement identiques (abréviation,
# mot en plus ou en moins). Volontairement strict.
SEUIL_SIMILARITE = 0.90
MARGE_MIN_SUR_SECOND = 0.05


class DecouverteError(RuntimeError):
    """Impossible de retrouver la course de façon fiable."""


# --------------------------------------------------------------------------
# 1. En-tête du PDF LONAB
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class CourseHeader:
    hippodrome: str
    nom_course: str
    nb_concurrents: int | None = None
    discipline_brute: str | None = None
    distance_metres: int | None = None


_RE_CONCURRENTS = re.compile(r"(?P<nb>\d{1,2})\s+CONCURRENTS", re.IGNORECASE)
_RE_HIPPO_NOM = re.compile(
    r"^(?P<hippo>[A-ZÀ-ÝŒ][A-ZÀ-ÝŒ0-9'’.\- ]{1,60}?)\s+[-–—]\s+(?P<nom>\S.*?)\s*$"
)
_RE_DISCIPLINE = re.compile(r"COURSE\s*[-–—]\s*(?P<disc>[A-ZÉÈÀ ]+?)\s*$", re.IGNORECASE)
_RE_DISTANCE = re.compile(r"(?P<d>\d[\d  ]*)\s*M[ÈE]TRES", re.IGNORECASE)


def parse_course_header(text: str) -> CourseHeader:
    """
    Lit l'hippodrome et le nom de la course dans l'en-tête du journal.

    Tolère la mise en page de `pdftotext -layout` (lignes centrées, colonnes
    séparées par de grands espaces). Lève DecouverteError, avec un extrait du
    texte reçu, si l'en-tête n'est pas reconnu — plutôt que de deviner.
    """
    texte = text.replace("\u00a0", " ")
    lignes = texte.splitlines()

    for index, ligne in enumerate(lignes[:200]):
        m = _RE_CONCURRENTS.search(ligne)
        if not m:
            continue

        # L'hippodrome et le nom de la course sont sur l'une des lignes
        # juste avant "N CONCURRENTS". On regarde jusqu'à 4 lignes en arrière.
        for k in range(index - 1, max(-1, index - 5), -1):
            for segment in re.split(r"\s{3,}", lignes[k].strip()):
                h = _RE_HIPPO_NOM.match(segment.strip())
                if h and "CONCURRENTS" not in segment.upper():
                    disc = _RE_DISCIPLINE.search(ligne)
                    # la distance est dans la ligne suivante (allocation + mètres)
                    suite = " ".join(lignes[index: index + 3])
                    dist = _RE_DISTANCE.search(suite)
                    return CourseHeader(
                        hippodrome=h.group("hippo").strip(),
                        nom_course=h.group("nom").strip(),
                        nb_concurrents=int(m.group("nb")),
                        discipline_brute=disc.group("disc").strip() if disc else None,
                        distance_metres=(
                            int(re.sub(r"\D", "", dist.group("d"))) if dist else None
                        ),
                    )
        break  # une seule ligne "CONCURRENTS" fait foi : la première

    extrait = " | ".join(l.strip() for l in lignes[:12] if l.strip())[:400]
    raise DecouverteError(
        "En-tête du journal LONAB non reconnu (hippodrome / nom de course). "
        f"Début du texte reçu : {extrait!r}"
    )


# --------------------------------------------------------------------------
# 2. Slugs et pages de liste Canal Turf
# --------------------------------------------------------------------------

def slugify(text: str) -> str:
    """minuscules, sans accents, tout ce qui n'est pas lettre/chiffre -> '-'"""
    sans_accents = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", sans_accents.lower()).strip("-")


@dataclass(frozen=True)
class CanalTurfRace:
    jour: date
    hippodrome_slug: str
    race_id: str
    race_slug: str
    url: str
    distance_metres: int | None = None


_RE_HREF = re.compile(
    r"""href=["'](?P<url>(?:https?://www\.canalturf\.com)?"""
    r"""/pronostics-PMU/(?P<date>\d{4}-\d{2}-\d{2})/(?P<hippo>[a-z0-9\-]+)/"""
    r"""(?P<id>\d+)_(?P<slug>[a-z0-9\-]+)\.html)["']""",
    re.IGNORECASE,
)
_RE_DISTANCE_LISTE = re.compile(r"(\d[\d  ]{2,5})\s*m\b")


def parse_canalturf_listing(html: str) -> list[CanalTurfRace]:
    """Extrait toutes les courses d'une page de liste Canal Turf (par les href)."""
    courses: dict[str, CanalTurfRace] = {}
    for m in _RE_HREF.finditer(html):
        url = m.group("url")
        if url.startswith("/"):
            url = CANALTURF_BASE + url
        if url in courses:
            continue
        # distance : dans le texte de l'ancre qui suit, si présent (vérification seulement)
        apres = html[m.end(): m.end() + 400]
        ancre = re.sub(r"<[^>]+>", " ", apres.split("</a>")[0])
        d = _RE_DISTANCE_LISTE.search(ancre)
        courses[url] = CanalTurfRace(
            jour=date.fromisoformat(m.group("date")),
            hippodrome_slug=m.group("hippo").lower(),
            race_id=m.group("id"),
            race_slug=m.group("slug").lower(),
            url=url,
            distance_metres=int(re.sub(r"\D", "", d.group(1))) if d else None,
        )
    return list(courses.values())


def candidate_listing_urls(race_date: date, today: date | None = None) -> list[str]:
    """
    Pages de liste où chercher la course, dans l'ordre. Les pages "aujourd'hui"
    et "demain" (structure vérifiée) passent avant la page datée, dont le
    format d'URL n'a été confirmé que pour un jour de septembre.
    """
    today = today or date.today()
    urls: list[str] = []
    if race_date == today:
        urls.append(f"{CANALTURF_BASE}/courses_liste_pronostics.php")
    if race_date == today + timedelta(days=1):
        urls.append(f"{CANALTURF_BASE}/courses_liste_pronostics_demain.php")
    jour = _JOURS[race_date.weekday()]
    mois = _MOIS[race_date.month - 1]
    urls.append(
        f"{CANALTURF_BASE}/pronostics-PMU/{race_date.isoformat()}"
        f"_pronostics-cotes-des-courses-du-{jour}-{race_date.day}-{mois}-{race_date.year}.html"
    )
    return urls


# --------------------------------------------------------------------------
# 3. Correspondance
# --------------------------------------------------------------------------

@dataclass
class DiscoveryResult:
    race: CanalTurfRace
    methode: str  # "exacte" | "approchee"
    avertissements: list[str] = field(default_factory=list)


def match_race(header: CourseHeader, races: list[CanalTurfRace], race_date: date) -> DiscoveryResult:
    du_jour = [r for r in races if r.jour == race_date]
    if not du_jour:
        raise DecouverteError(f"Aucune course datée du {race_date.isoformat()} dans la page analysée.")

    hippo = slugify(header.hippodrome)
    nom = slugify(header.nom_course)
    meme_hippo = [r for r in du_jour if r.hippodrome_slug == hippo]
    if not meme_hippo:
        dispo = sorted({r.hippodrome_slug for r in du_jour})
        raise DecouverteError(
            f"Hippodrome {header.hippodrome!r} (slug {hippo!r}) absent de la liste du "
            f"{race_date.isoformat()}. Hippodromes trouvés : {dispo}"
        )

    avertissements: list[str] = []

    exactes = [r for r in meme_hippo if r.race_slug == nom]
    if len(exactes) == 1:
        trouvee, methode = exactes[0], "exacte"
    elif len(exactes) > 1:
        raise DecouverteError(
            f"Plusieurs courses au même nom {nom!r} sur {hippo!r} : {[r.url for r in exactes]}"
        )
    else:
        scores = sorted(
            ((difflib.SequenceMatcher(None, nom, r.race_slug).ratio(), r) for r in meme_hippo),
            key=lambda x: x[0], reverse=True,
        )
        meilleur, r_meilleur = scores[0]
        second = scores[1][0] if len(scores) > 1 else 0.0
        if meilleur < SEUIL_SIMILARITE or (meilleur - second) < MARGE_MIN_SUR_SECOND:
            candidats = [(round(s, 2), r.race_slug) for s, r in scores[:5]]
            raise DecouverteError(
                f"Course {header.nom_course!r} non retrouvée sur {header.hippodrome!r} "
                f"(meilleure similarité {meilleur:.2f}, seuil {SEUIL_SIMILARITE}). "
                f"Candidats : {candidats}"
            )
        trouvee, methode = r_meilleur, "approchee"
        avertissements.append(
            f"Correspondance approchée ({meilleur:.2f}) : {header.nom_course!r} ~ {r_meilleur.race_slug!r}"
        )

    # Vérification croisée (jamais bloquante seule, mais toujours signalée)
    if header.distance_metres and trouvee.distance_metres and header.distance_metres != trouvee.distance_metres:
        avertissements.append(
            f"Distance différente : LONAB {header.distance_metres} m, Canal Turf {trouvee.distance_metres} m"
        )

    return DiscoveryResult(race=trouvee, methode=methode, avertissements=avertissements)


def discover_canalturf_url(
    header: CourseHeader,
    race_date: date,
    *,
    today: date | None = None,
    session: requests.Session | None = None,
    timeout: float = 20.0,
) -> DiscoveryResult:
    """Cherche la course dans les pages de liste candidates ; renvoie la première correspondance sûre."""
    session = session or requests.Session()
    essais: list[str] = []
    for url in candidate_listing_urls(race_date, today):
        try:
            reponse = session.get(
                url, timeout=timeout,
                headers={"User-Agent": "Pegasus/1.0 (research; contact unavailable)"},
            )
            reponse.raise_for_status()
            courses = parse_canalturf_listing(reponse.text)
            return match_race(header, courses, race_date)
        except (requests.RequestException, DecouverteError) as exc:
            essais.append(f"{url} -> {type(exc).__name__}: {exc}")
    raise DecouverteError("Course introuvable sur Canal Turf. Essais : " + " || ".join(essais))
