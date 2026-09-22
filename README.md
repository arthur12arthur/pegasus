# Pegasus — cœur algorithmique (`pegasus_core`)

Ce dossier contient le code écrit et verrouillé par Claude : `filter.py`,
`scorer.py`, `consensus.py`, `models.py`, `config.py`. Il implémente
fidèlement les sections 4, 6 et 7 du Système Prompt Canonique (portillon de
filtrage, score de compétitivité BaseScorer, score de classement Monte
Carlo/Borda/MetaFusion).

## Règle d'or pour Manus (ou toute autre plateforme qui assemble le reste)

**Ne modifiez jamais la logique interne de ces fichiers** (seuils, poids,
formules, seeds). Importez-les et appelez-les. Si un comportement semble
incohérent une fois branché sur les vraies données, **signalez-le** plutôt
que de corriger silencieusement — le contrat est vérifié par
`test_core.py`, pas par une relecture au cas par cas.

Une exception documentée : `consensus.py` reconstruit la formule
"MetaFusion pairwise" (comparaison de Copeland sur probabilité Monte Carlo
et score de Borda) car la formule exacte des versions précédentes n'a pas
été retrouvée. C'est une interprétation raisonnable et déterministe, pas
une improvisation — mais elle doit être signalée comme telle si on
retrouve un jour la formule d'origine.

## Ce que ce code fait (et ne fait pas)

- `filter.apply_filter(horses)` → portillon binaire (retenu/écarté). Ne
  renvoie **aucun score**.
- `scorer.score_group(horses, discipline)` → score de compétitivité
  (0-10) par cheval retenu, y compris la sous-composante ferrure en trot
  avec lissage bayésien sur petits échantillons.
- `consensus.compute_classement(scores)` → classement final (Monte Carlo
  5 seeds fixes × 10 000 simulations + Borda, fusionnés), avec indicateur
  de stabilité inter-seeds.

Ce que ce dossier **ne fait pas** (à la charge du reste du pipeline) :
ingestion du PDF LONAB, MarketWatch (cotes actuelles), HADES, consensus
externe (12 sources), indice de confiance final, livraison, stockage.

## Utilisation

```python
from pegasus_core.filter import apply_filter
from pegasus_core.scorer import score_group
from pegasus_core.consensus import compute_classement

resultat_filtre = apply_filter(liste_de_chevaux)   # liste de Horse (models.py)
scores = score_group(resultat_filtre.retenus, "trot")  # "trot" | "plat" | "obstacle"
classement = compute_classement(scores)

print(classement.classement)        # numéros, du plus probable au moins probable
print(classement.top3_stable)       # False -> abaisser l'indice de confiance
```

## Tests

```bash
python -m unittest pegasus_core.test_core -v
```

14 tests, tous verts. Ils verrouillent notamment :
- le filtrage ne produit jamais de score ;
- les 5 favoris aux cotes les plus basses sont toujours maintenus ;
- la taille minimale du groupe filtré est respectée ;
- les poids de BaseScorer somment à 1 pour chaque discipline ;
- le lissage bayésien empêche une victoire isolée de dominer le score
  technique ;
- le classement est parfaitement reproductible à scores égaux (mêmes
  seeds → même résultat, à chaque exécution).

Si vous ajoutez un module autour de ce cœur et qu'un de ces tests casse,
c'est le nouveau module qu'il faut corriger — pas le test.
