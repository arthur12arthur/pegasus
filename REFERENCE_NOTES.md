# Notes de référence — Pegasus/Hyperion

Sources : `hyperion/SKILL.md`, `Hyperion_Architecture_Unique (3).docx`, `Hyperion_Systeme_Prompt_Canonique (3).docx`, README et code du cœur.

- LONAB est un relais : la course se déroule en France, jamais au Burkina Faso.
- Source officielle : ouvrir `https://lonab.bf/programme-pmub`, matcher exactement `journal hippique PMU'B du [date du jour]`, suivre le vrai lien Télécharger ; ne jamais reconstruire l’URL. Pagination si nécessaire.
- Ordre strict : DataIngestion → DisciplineDetector → MarketWatch (avant filtrage) → DataFilter → BaseScorer → Consensus interne → HADES → consensus externe → laboratoire/confiance.
- MarketWatch compare cote PDF et cote actuelle, détecte les non-partants tardifs, signale toute indisponibilité.
- Donnée manquante : champ neutre selon le contrat du cœur, mais omission explicitement signalée ; aucune invention.
- Disciplines : `trot`, `plat`, `obstacle`. Détection directe du type officiel, repli par mots-clés seulement si champ absent/ambigu.
- Le cœur verrouillé est `models.py`, `config.py`, `filter.py`, `scorer.py`, `consensus.py` ; ne pas modifier leur logique.
- Grille, seuils, seeds et formules sont figés dans `config.py`/cœur.
- Le PDF peut être publié J-2/J-3 : MarketWatch obligatoire avant filtrage.
- Résultats officiels : tester en priorité `nanaelie/open-pmu-api`, sans contourner par scraping PMU direct.
- IA : si une étape LLM est ajoutée, rotation/repli multi-fournisseurs gratuits, jamais fournisseur unique. Cette première implémentation vise un parsing déterministe sans IA.
- Rapport : signature d’ouverture et de clôture `Hyperion — exécution [plateforme] — [horodatage]`; jamais conseil de pari/mise.
- Architecture précise : DataIngestion renvoie PDF + métadonnées ; DisciplineDetector renvoie étiquette ; MarketWatch renvoie delta/alerte/non-partant ; stockage/livraison ne sont pas demandés dans ce palier.
