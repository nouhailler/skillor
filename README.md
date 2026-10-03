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
docker compose exec api python -m app.cli sync eurostat
docker compose exec api python -m app.cli sync france_travail
```

Les imports sont enregistrés dans `import_jobs` et les réponses sources sont
conservées sous `data/raw/<source>/`.

L'import ESCO enrichit les métiers avec leurs libellés, descriptions et
synonymes multilingues, leur groupe ISCO, puis construit les relations vers les
compétences essentielles et optionnelles. Les fiches de compétences liées sont
récupérées par lots. `--max-relation-skills` permet de borner un import de test ;
la valeur par défaut est configurable avec `ESCO_MAX_RELATION_SKILLS`.

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
- `POST /api/v1/imports/{source}` (clé d'administration)

Les valeurs calculées exposent toujours `is_official: false`, leur version de
méthode et leurs composantes.
