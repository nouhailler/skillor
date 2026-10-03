# Skillor — Skill Intelligence MVP

Skillor est un moteur de connaissance du marché des compétences. Ce dépôt contient :

- un frontend PWA responsive dans `dist/` ;
- une API FastAPI dans `backend/` ;
- une base PostgreSQL avec migrations Alembic ;
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

Le jeu de démonstration est chargé au premier démarrage. Les connecteurs ESCO et
Eurostat ne demandent pas de secret. France Travail nécessite un client OAuth ;
ajoutez `FRANCE_TRAVAIL_CLIENT_ID` et `FRANCE_TRAVAIL_CLIENT_SECRET` dans `.env`.

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

## Tests

```bash
docker compose run --rm api pytest
```

## API principale

- `GET /api/v1/dashboard`
- `GET /api/v1/search?q=python`
- `GET /api/v1/occupations`
- `GET /api/v1/occupations/{id}`
- `GET /api/v1/skills`
- `GET /api/v1/skills/{id}`
- `GET /api/v1/trends/skills`
- `GET /api/v1/sources`
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

Les valeurs calculées exposent toujours `is_official: false`, leur version de
méthode et leurs composantes.
