# db-jango Backend

Django REST API for browsing, tagging, and classifying database metadata.

## Purpose

The backend stores a hierarchical representation of database objects (databases, schemas, tables, views, columns) in a local SQLite database and exposes them via a REST API. It supports:

- Browsing the entity tree (lazy-loaded per level)
- Full-text search across entity names
- Tagging entities with key/value pairs
- Computing semantic terms from entity names
- Classifying entities for PHI/PII sensitivity
- Running background tasks from the UI or CLI

## Design

### Data Model

All metadata is stored as **Entities** connected by **Relationships**:

```
DATABASE ─contains→ SCHEMA ─contains→ TABLE/VIEW ─contains→ COLUMN
```

Each entity has a fully-qualified name (`fqn`), e.g. `mydb.public.users.email`.

Supporting models:
- **Tag** — user-defined key/value labels on any entity
- **Term** — computed tokens extracted from entity names (business, language, sentinel types)
- **IdentifiableInfo** — PHI/PII scores per entity (0–100)
- **IdentifiableInfoBooster** — propagation records for child-to-parent and sibling scoring
- **TaskStatus** — tracks background command execution

### Database Location

SQLite database is stored at `~/.db-jango/sqlite3.db` (created automatically on first run).

### Configuration

Key settings in `config/settings.py`:
- `DATABASES` — SQLite in `~/.db-jango/`
- `REST_FRAMEWORK` — session auth, pagination at 100 items
- `CORS_ALLOWED_ORIGINS` — frontend dev server at `localhost:4200`

External config files (JSON-based, editable):
- `core/config/terms.json` — domain-specific term dictionaries
- `core/config/phi_classifier.json` — PHI/PII keyword patterns and weights

## Setup

```bash
cd backend
uv sync                              # install dependencies
uv run python manage.py migrate      # apply database migrations
uv run python manage.py createsuperuser  # create admin user
uv run python manage.py runserver    # start dev server on :8000
```

Required environment variables for Redshift commands:
```
PGHOST, PGPORT (default 5439), PGDATABASE, PGUSER, PGPASSWORD
```

## Migrations

Django migrations live in `catalog/migrations/`. The initial migration (`0001_initial.py`) creates:

- `Entity` — core metadata object with UUID primary key, FQN, name, type, JSON metadata
- `Relationship` — directed edges between entities (CONTAINS, BELONGS_TO)
- `Tag` — entity labels
- `Term` — computed tokens with scores and pass stage
- `IdentifiableInfo` — PHI/PII scores per entity
- `IdentifiableInfoBooster` — score propagation tracking
- `TaskStatus` — background task state machine (pending → running → completed/failed)

To create new migrations after model changes:
```bash
uv run python manage.py makemigrations
uv run python manage.py migrate
```

## Server

Start the development server:
```bash
uv run python manage.py runserver 0.0.0.0:8000
```

API endpoints (all under `/api/`):
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/schemas/` | GET | List all schema entities |
| `/api/entities/<fqn>/` | GET | Get entity detail by FQN |
| `/api/entities/<fqn>/children/` | GET | List child entities |
| `/api/search/?q=<term>` | GET | Search entities by name |
| `/api/tags/` | GET/POST | List or create tags |
| `/api/tasks/` | GET/POST | List tasks or trigger a new task |
| `/api/auth/login/` | POST | Session login |
| `/api/auth/logout/` | POST | Session logout |
| `/api/auth/user/` | GET | Current user info |

## Management Commands

All commands are run via `uv run python manage.py <command>`.

### `fetch_schema`

Full metadata fetch from Redshift — schemas, tables/views, and columns.

```bash
uv run python manage.py fetch_schema [--schema <pattern>] [--workers 4] [--force]
```

- Three-stage pipeline: schemas → tables/views → columns
- Multi-threaded with configurable worker count
- Idempotent (uses `update_or_create`); use `--force` to overwrite
- `--schema` filters by schema name substring

### `refresh_schemas`

Lightweight refresh of the schema list only (no tables or columns).

```bash
uv run python manage.py refresh_schemas [--schema <pattern>]
```

- Fast — only queries `information_schema.schemata`
- Creates/updates the database and schema entities
- Reports how many new schemas were discovered

### `compute_terms`

Tokenizes entity names into semantic terms using a multi-pass pipeline.

```bash
uv run python manage.py compute_terms [--schema <pattern>] [--recompute] [--workers 4]
```

- **Pass 1**: Tokenizes names (word splitting, dictionary matching)
- **Pass 2**: Classifies terms using parent/sibling context
- Processes schema-by-schema for incremental progress
- Skips already-processed entities unless `--recompute` is set

### `classify_phi`

Scores entities for PHI/PII sensitivity using a 5-pass pipeline.

```bash
uv run python manage.py classify_phi [--schema <pattern>] [--recompute] [--workers 4]
```

- **Pass 1**: Name pattern matching (regex-based)
- **Pass 2**: Term-based scoring adjustment
- **Pass 3**: Child-to-parent boost propagation
- **Pass 4**: Sibling-to-sibling boost propagation
- **Pass 5**: Score normalization (capped at 100)
- Skips already-classified entities unless `--recompute` is set

### `migrate_data_01`

One-time migration from the legacy `db-browser` SQLite database.

```bash
uv run python manage.py migrate_data_01 [--source ~/.db-browser/catalog.db] [--skip-existing]
```

- Migrates entities, relationships, tags, terms, identifiable info, and boosters
- Batch-processed with atomic transactions
- Safe to re-run (uses `ignore_conflicts`)
- Default source: `~/.db-browser/catalog.db`

## Project Structure

```
backend/
├── manage.py
├── pyproject.toml
├── config/
│   ├── settings.py          # Django settings
│   ├── urls.py              # Root URL routing
│   └── wsgi.py
├── catalog/
│   ├── models.py            # Entity, Relationship, Tag, Term, etc.
│   ├── views.py             # REST API views
│   ├── serializers.py       # DRF serializers
│   ├── urls.py              # API URL patterns
│   ├── admin.py
│   ├── migrations/
│   │   └── 0001_initial.py
│   └── management/commands/
│       ├── fetch_schema.py
│       ├── refresh_schemas.py
│       ├── compute_terms.py
│       ├── classify_phi.py
│       └── migrate_data_01.py
└── core/
    ├── terms.py             # Term tokenization and classification logic
    ├── phi_classifier.py    # PHI/PII scoring functions
    └── config/
        ├── terms.json       # Customizable term dictionaries
        └── phi_classifier.json  # PHI/PII patterns and weights
```
