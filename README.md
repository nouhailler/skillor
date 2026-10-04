# Skillor — Skill Intelligence MVP

Skillor est un moteur de connaissance du marché des compétences. Ce dépôt contient :

- un frontend PWA responsive dans `dist/` ;
- une API FastAPI dans `backend/` ;
- un fichier SQLite local avec migrations Alembic, sans serveur de base de données ;
- des connecteurs ESCO, France Travail et Eurostat ;
- une ingestion traçable avec conservation des réponses brutes ;
- des scores de tendance et de confiance explicitement identifiés comme internes.

## Démarrage rapide

```bash
cp .env.example .env
docker compose up --build
```

L'API est disponible sur `http://localhost:8000`, sa documentation sur
`http://localhost:8000/docs` et le frontend sur `http://localhost:8080`.

Le stockage standard est `backend/skillor.sqlite3`, configuré par :

```env
DATABASE_URL=sqlite:///./skillor.sqlite3
```

Docker Compose ne lance aucun service de base de données. Le fichier SQLite est
persisté sur l'hôte par le montage de `backend/` dans le conteneur API. SQLite
fonctionne en mode WAL, avec clés étrangères actives et un délai d'attente de
30 secondes pour limiter les erreurs de verrouillage pendant les imports.

La base démarre vide : aucun chiffre de démonstration n'est injecté
automatiquement. Les connecteurs ESCO et Eurostat ne demandent pas de secret.
France Travail nécessite un client OAuth ; ajoutez `FRANCE_TRAVAIL_CLIENT_ID` et
`FRANCE_TRAVAIL_CLIENT_SECRET` dans `.env`.

Pour les tests visuels locaux uniquement, un jeu synthétique reste disponible
sur demande avec `docker compose exec api python -m app.cli seed`.

## Synchronisation

```bash
docker compose exec api python -m app.cli sync esco --query data --limit 50
docker compose exec api python -m app.cli sync-eurostat --profiles all --geography FR --since 2021
docker compose exec api python -m app.cli sync eurostat --profile regional_unemployment --since 2021
docker compose exec api python -m app.cli sync-rome-esco
docker compose exec api python -m app.cli sync france_travail --dataset market --territory FR
docker compose exec api python -m app.cli sync france_travail --dataset offers --query python --territory 75 --limit 150
```

Les imports sont enregistrés dans `import_jobs` et les réponses sources sont
conservées sous `data/raw/<source>/`.

L'import ESCO enrichit les métiers avec leurs libellés, descriptions et
synonymes multilingues, leur groupe ISCO, puis construit les relations vers les
compétences essentielles et optionnelles. Les fiches de compétences liées sont
récupérées par lots. `--max-relation-skills` permet de borner un import de test ;
la valeur par défaut est configurable avec `ESCO_MAX_RELATION_SKILLS`.

L'import France Travail résout les codes et libellés ROME vers les métiers ESCO
déjà présents en base. `sync-rome-esco` charge le tableau officiel EURES France
ROME–ESCO et conserve la relation de mapping ainsi que son niveau de confiance.
Les indicateurs de marché (offres, demandeurs, embauches, difficultés de
recrutement) et les offres détaillées sont ensuite rattachés aux fiches métiers,
avec leur territoire et leur secteur. L'import des offres agrège également les
compétences demandées et les salaires structurés lorsqu'ils sont fournis par la
source. Les rapprochements non résolus sont conservés comme tels dans les
métadonnées, sans attribution métier hasardeuse.

La recherche repose sur une table d'index dédiée. Elle contient les libellés
canoniques, synonymes ESCO, traductions, URI ESCO, codes ISCO et mappings
externes ROME. Les appellations réellement observées dans les offres France
Travail sont ajoutées comme alias traçables. Tout mapping externe dont le
`source_system` vaut `onet` est automatiquement indexé de la même manière ; le
dépôt ne télécharge toutefois pas encore le référentiel O*NET lui-même.
La tolérance aux fautes est calculée sur les termes présélectionnés dans SQLite.
L'index est entretenu pendant les imports et peut être reconstruit avec :

```bash
docker compose exec api python -m app.cli reindex-search
```

Le pipeline TrendScore calcule ses composantes à partir des séries historiques.
Il privilégie les mentions de compétences directement observées ; à défaut, il
utilise les offres des métiers ESCO liés, pondérées par le poids et la confiance
de la relation. Deux périodes au minimum sont exigées. La croissance et
l'accélération sont normalisées autour de 50, le volume est normalisé de façon
logarithmique, la diffusion géographique vient des territoires observés et la
confiance conserve le statut de la source. Chaque score stocke le signal choisi,
les volumes avant/après, le nombre d'observations, de sources et de territoires.
Le résultat reste toujours marqué `is_official = false`.

Le recalcul est automatique après un import France Travail et peut aussi être
lancé explicitement :

```bash
docker compose exec api python -m app.cli recompute-trends
curl -X POST -H "X-Admin-Key: $ADMIN_API_KEY" http://localhost:8000/api/v1/trends/recompute
```

Le ConfidenceScore est alimenté par une chaîne Data Quality exécutée après
chaque import. Elle mesure, par source, dataset et métrique : la fiabilité de la
source à partir du type, du taux de succès des imports et du statut officiel ;
la récence du chargement ; la complétude des dimensions et rattachements ; la
cohérence des valeurs, unités et clés naturelles ; enfin l'accord sur les mêmes
points entre plusieurs sources. Sans recouvrement inter-sources, la composante
prend une valeur neutre de 50 et le diagnostic l'indique explicitement. Tous les
détails sont stockés dans `data_quality_scores`, restent non officiels et sont
visibles dans la page Sources.

```bash
docker compose exec api python -m app.cli recompute-quality
curl -X POST -H "X-Admin-Key: $ADMIN_API_KEY" http://localhost:8000/api/v1/quality/recompute
```

Eurostat est organisé en six profils configurables dans
`backend/app/eurostat_catalog.py` : chômage, emploi, rémunérations, éducation,
emploi par secteur NACE et chômage régional NUTS 2. Chaque profil définit son
code de dataset, sa métrique, son niveau géographique et ses filtres de
dimensions. `EUROSTAT_DATASETS_JSON` permet de surcharger ou d'ajouter des
profils sans modifier le connecteur. Les libellés de dimensions, statuts
Eurostat, territoires et réponses JSON-stat brutes sont conservés.

Le frontend ne contient aucun jeu de données métier de repli. Au démarrage, il
charge le tableau de bord, les catalogues métiers et compétences, les tendances,
les séries territoriales et la provenance depuis FastAPI. Une API indisponible
ou une base vide produit un état d'erreur ou un état vide explicite, jamais des
chiffres simulés. Les exports CSV sont construits à partir des réponses API.

Chaque métier ouvre désormais une page dynamique et partageable via
`#occupation/{id}`. Elle rassemble les informations de référentiel, les
compétences essentielles et optionnelles, les agrégats de marché, les dernières
valeurs géographiques, les séries temporelles et la provenance détaillée. La
réponse `GET /api/v1/occupations/{id}` conserve ses champs historiques et expose
en plus `market_summary`, `geographies`, `timeline` et `sources`. Les métriques
de volume sont additionnées ; les taux, scores et rémunérations sont moyennés
sans conversion implicite d'unité. Les observations brutes restent consultables
dans la fiche pour permettre l'audit des agrégats.

Les compétences disposent elles aussi d'une page partageable via `#skill/{id}`.
Elle croise les métiers liés avec leurs observations réelles pour exposer les
secteurs, régions, offres, salaires et indicateurs de tension disponibles. Les
compétences voisines sont déduites des métiers partagés ; la tendance conserve
son historique et reste explicitement identifiée comme un calcul interne. Une
section de provenance indique, pour chaque source, le nombre d'observations et
de relations mobilisées.

Le dashboard agrège les observations réellement importées : offres sur les
douze dernières périodes mensuelles, pays et régions déduits des niveaux
géographiques, salaires conservés dans leur unité source, tension observée ou
calculée clairement identifiée, métiers et compétences en hausse, ainsi que la
fraîcheur de chaque source. Les bornes salariales peuvent produire un point
central interne, signalé par la méthode `range_midpoint` ; aucune conversion
entre salaire horaire, mensuel et annuel n'est effectuée.

## Tests

```bash
docker compose run --rm api pytest
```

## API principale

- `GET /api/v1/dashboard`
- `GET /api/v1/search?q=pythn&entity_type=skill&language=fr&source=esco`
- `GET /api/v1/search/suggestions?q=data`
- `GET /api/v1/search/filters`
- `GET /api/v1/occupations`
- `GET /api/v1/occupations/{id}`
- `GET /api/v1/skills`
- `GET /api/v1/skills/{id}`
- `GET /api/v1/trends/skills`
- `POST /api/v1/trends/recompute` (clé d'administration)
- `GET /api/v1/sources`
- `GET /api/v1/quality/scores`
- `GET /api/v1/catalog/occupations`
- `GET /api/v1/catalog/skills`
- `GET /api/v1/market/series`
- `GET /api/v1/market/geographies`
- `GET /api/v1/sources/france_travail/coverage`
- `GET /api/v1/eurostat/datasets`
- `GET /api/v1/eurostat/indicators`
- `POST /api/v1/imports/{source}` (clé d'administration)
- `POST /api/v1/imports/france_travail/crosswalk` (clé d'administration)
- `POST /api/v1/imports/eurostat/catalog` (clé d'administration)
- `POST /api/v1/quality/recompute` (clé d'administration)

Les valeurs calculées exposent toujours `is_official: false`, leur version de
méthode et leurs composantes.
