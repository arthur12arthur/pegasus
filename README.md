# Pegasus

Pegasus est un système explicable d’analyse de la course française relayée par LONAB/PMU'B pour le marché burkinabè. LONAB est une source relais : les courses analysées se déroulent en France.

## Organisation du dépôt

| Élément | Rôle |
| --- | --- |
| `models.py` | Structures de données partagées (`Horse`, résultats de filtrage, scores et classement) |
| `config.py` | Paramètres numériques figés : pondérations, seuils et seeds |
| `filter.py` | Portillon binaire d’élimination |
| `scorer.py` | `BaseScorer`, score de compétitivité par discipline et ferrure au trot |
| `consensus.py` | Monte Carlo, Borda et MetaFusion pour le score de classement |
| `test_core.py` | Tests de verrouillage du cœur algorithmique |
| `ingestion.py` | Localisation du journal LONAB du jour, téléchargement du PDF et extraction conservatrice |
| `discipline.py` | Détection `trot`, `plat` ou `obstacle` |
| `marketwatch.py` | Orchestrateur des fournisseurs de cotes avant le filtrage |
| `canalturf_provider.py` | Adaptateur gratuit réel : colonne publique ZEturf de Canal Turf |
| `open_pmu_api.py` | Client gratuit des résultats officiels historiques via open-pmu-api |
| `test_pipeline.py` | Tests des modules périphériques et de leur intégration |
| `fixtures/` | Page HTML Canal Turf sauvegardée pour tests reproductibles hors réseau |
| `Hyperion_Systeme_Prompt_Canonique (3).docx` | Source de vérité méthodologique |
| `Hyperion_Architecture_Unique (3).docx` | Source de vérité architecturale |
| `PIPELINE_README.md` | Contrat d’utilisation et limites connues des modules périphériques |

Le lien symbolique `pegasus_core` conserve l’import historique utilisé par les tests (`python -m unittest pegasus_core.test_core -v`) tout en gardant les fichiers sources visibles à la racine du dépôt.

## Règle absolue du cœur

Les fichiers `models.py`, `config.py`, `filter.py`, `scorer.py` et `consensus.py` sont verrouillés. Le code périphérique les importe et les appelle ; il ne modifie jamais leurs seuils, poids, seeds, formules ou logique interne. Toute incohérence observée sur des données réelles doit être signalée plutôt que corrigée silencieusement.

Le score de compétitivité produit par `BaseScorer` reste distinct du score de classement produit par le consensus interne. MarketWatch s’exécute avant `apply_filter`, mais les cotes restent un signal de marché secondaire et ne sont pas injectées comme dimension pondérée dans `BaseScorer`.

## Installation minimale

Le projet utilise Python 3.11 ou plus récent et les bibliothèques suivantes : `requests`, `beautifulsoup4` et `pypdf`. L’extraction PDF utilise également `pdftotext` lorsqu’il est disponible, afin de préserver les colonnes des tableaux LONAB.

```bash
python -m pip install requests beautifulsoup4 pypdf
```

## Tests

```bash
python -m unittest pegasus_core.test_core -v
python -m unittest pegasus_core.test_pipeline -v
```

Le cœur contient 14 tests de verrouillage. Les modules périphériques contiennent actuellement 8 tests, dont un test sur fixture Canal Turf et un test d’injection dans MarketWatch.

## Exemple MarketWatch

L’URL Canal Turf doit être fournie par une étape d’identification séparée ; l’adaptateur ne reconstruit pas d’URL et ne fabrique jamais une cote manquante.

```python
from pegasus_core.canalturf_provider import CanalTurfQuoteProvider
from pegasus_core.marketwatch import MarketWatch

provider = CanalTurfQuoteProvider(
    "https://www.canalturf.com/pronostics-PMU/2026-09-23/argentan/418606_prix-paristurf-x-pmu.html"
)
market = MarketWatch([provider])
result = market.update(horses)  # obligatoire avant apply_filter(...)
```

## Données manquantes et limites

Aucune donnée manquante n’est inventée. Si une source ne fournit pas une cote ou si un cheval est absent de la source actuelle, le champ reste `None` et MarketWatch ajoute un avertissement. `open-pmu-api` fournit des résultats historiques officiels ; il ne remplace pas une source de cote actuelle.

Le système ne produit jamais de conseil de pari ou de mise. Les rapports de production doivent conserver les signatures d’ouverture et de clôture prévues par le Système Prompt Canonique.

## Statut de validation

L’état publié a été testé avec succès : 14 tests du cœur et 8 tests périphériques passent. L’adaptateur Canal Turf a également été exercé contre une page publique réelle et a injecté des cotes pour les partants demandés.
