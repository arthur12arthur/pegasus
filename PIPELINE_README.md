# Pegasus — modules périphériques du palier 1

Ces modules entourent le cœur verrouillé (`models.py`, `config.py`, `filter.py`, `scorer.py`, `consensus.py`) sans en modifier les seuils, poids, seeds ni formules.

## Ordre d’appel

`LonabIngestion.fetch(date)` localise la ligne exacte du journal demandé, suit le vrai lien `Télécharger`, télécharge le PDF et produit des `Horse`. `detect_discipline(type_officiel, texte_pdf)` renvoie `trot`, `plat` ou `obstacle`. `MarketWatch.update(horses)` doit être appelé avant `apply_filter`; il remplit `cote_actuelle` seulement quand une cote vérifiée est reçue et conserve `None` sinon. Le cœur peut ensuite être appelé avec `apply_filter`, `score_group` puis `compute_classement`.

## Extraction et données manquantes

L’extraction déterministe s’appuie sur `pypdf` et le repli `pdftotext -layout`, particulièrement utile pour les tableaux de partants LONAB. Les champs effectivement lisibles dans le PDF sont les numéros, noms, gains et première cote imprimée dans la colonne officielle du document. Les notes BaseScorer, l’historique ferrure et la cote actuelle ne sont pas inventés : ils restent neutres/`None` conformément au contrat et sont inscrits dans `missing_fields` ou les avertissements du résultat.

Le nom et la cote sont extraits de manière conservatrice. Une validation métier reste nécessaire avant production si un nouveau gabarit PDF apparaît. Le module ne transforme pas automatiquement les commentaires narratifs en notes historiques ou forme, car cela introduirait une donnée non vérifiée.

## MarketWatch

`MarketWatch` est un orchestrateur d’adaptateurs gratuits. Il essaie les fournisseurs dans l’ordre donné, s’arrête au premier résultat non vide, calcule le delta relatif et signale toute cote manquante ou tout non-partant. `CanalTurfQuoteProvider` lit la colonne publique **ZEturf** du tableau HTML Canal Turf. `GenyQuoteProvider` ajoute un second fournisseur : il lit le rapport probable courant exposé dans la page publique Geny « Cotes » et le marque explicitement `Geny/rapport-probable`. Ce rapport de marché ne doit pas être interprété comme une cote PMU garantie ; si cette distinction est incompatible avec l’étape de production, Geny doit rester un repli informatif et non être fusionné avec une cote décimale. Les deux fournisseurs reçoivent l’URL exacte d’une course déjà identifiée et ne reconstruisent aucune URL. Une cellule vide ou `--` reste manquante. Les fixtures `fixtures/canalturf_r1c8_2026-09-23.html` et `fixtures/geny_cotes_2026-09-24.html` permettent de tester les parseurs hors réseau. L’API open-pmu-api n’est pas une source de cotes live ; elle sert aux résultats officiels et à l’évaluation J+1.

`run_pegasus_dry_run.py` fournit une vérification d’intégration stricte sur une course réelle. Il appelle les six étapes demandées et s’arrête si une étape est vide, incohérente ou si une donnée indispensable du BaseScorer reste manquante. Il ne transforme pas les valeurs neutres du modèle en fausse donnée réelle.

## Résultats officiels

`OpenPmuApiClient` utilise `https://open-pmu-api.vercel.app/api/arrivees` avec le format de date MM/DD/YYYY observé dans l’implémentation et les exemples fonctionnels du dépôt `nanaelie/open-pmu-api`. La réponse historique est distincte de MarketWatch et ne doit pas être injectée dans le scoring pré-course.

## Tests exécutés

```bash
python3 -m unittest pegasus_core.test_pipeline -v
python3 -m unittest pegasus_core.test_core -v
```

Le test live réalisé le 22 septembre 2026 a récupéré le journal LONAB du 17 septembre 2026 et 15 partants. Le test live open-pmu-api réalisé sur le 18 août 2026 a renvoyé HTTP 200 et une course avec arrivée. La page LONAB accessible ne contenait pas le 22 septembre au moment de l’exécution ; le code parcourt les liens `rel=next` avant de conclure à l’absence.

Le test live du 23 septembre 2026 a appelé la page Canal Turf du 23 septembre, course R1C8, et injecté les cotes 2,7, 4,4 et 20,3 pour les numéros 1, 2 et 18 sans avertissement. Les cotes de sites de paris restent un signal de marché secondaire ; elles ne sont jamais transmises au BaseScorer comme dimension pondérée.

La fixture Geny du 24 septembre 2026 contient 16 partants et a été extraite avec succès par le nouveau parseur, y compris la conservation explicite de la cellule manquante du n°11. Lors du smoke test direct suivant, Geny a alternativement renvoyé la page complète puis une réponse réduite sans tableau ; dans ce dernier cas, l’adaptateur lève une erreur contrôlée et MarketWatch peut passer au fournisseur suivant. Ce comportement intermittent reste à surveiller avant une dépendance exclusive à Geny.

Le dry-run réel du 24 septembre 2026 a extrait 15 partants depuis le journal LONAB, détecté `plat` par mots-clés PDF avec confiance moyenne, récupéré 15/15 cotes Canal Turf et retenu les 15 chevaux. Il s’est arrêté à l’étape BaseScorer, car `ingestion.py` ne fournit pas encore les notes BaseScorer ; aucun score de compétitivité ni classement de consensus n’a été exécuté ou présenté.
