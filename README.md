# DB-Jango — Database Metadata Browser

A multiuser web application for browsing, searching, tagging, and classifying database schema metadata. Built with Django REST Framework (backend) and Vue 3 + Vite (frontend), backed by SQLite.

## Purpose

DB-Jango provides a collaborative interface for data governance teams to:

- **Browse** database schemas, tables, views, and columns in a hierarchical tree
- **Search** entities by name across the catalog
- **Tag** entities with custom key/value labels for classification
- **Compute terms** — extract semantic tokens from entity names using NLP (wordninja)
- **Classify PHI/PII** — score entities for Protected Health Information and Personally Identifiable Information using a 5-pass pipeline
- **Run background tasks** — trigger metadata fetching, term computation, and classification from the UI

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│              Vue 3 + Vite SPA (:4200)                   │
│  ┌──────────┐ ┌──────────┐ ┌────────┐ ┌─────────────┐  │
│  │   Tree   │ │  Search  │ │ Detail │ │ Task Runner │  │
│  └──────────┘ └──────────┘ └────────┘ └─────────────┘  │
└────────────────────────┬────────────────────────────────┘
                         │ HTTP (proxied /api)
┌────────────────────────▼────────────────────────────────┐
│              Django + DRF Backend (:8000)                │
│  ┌─────────────┐  ┌───────────────┐  ┌──────────────┐  │
│  │  REST API   │  │  ORM Models   │  │  Core Logic  │  │
│  │  (catalog/) │  │  (catalog/)   │  │  (core/)     │  │
│  └─────────────┘  └───────────────┘  └──────────────┘  │
│  ┌──────────────────────────────────────────────────┐   │
│  │  Management Commands (fetch/compute/classify)    │   │
│  └──────────────────────────────────────────────────┘   │
└────────────────────────┬────────────────────────────────┘
                         │
                ┌────────▼────────┐
                │  ~/.db-jango/   │
                │   sqlite3.db    │
                └─────────────────┘
```

## Project Structure

```
db-jango/
├── backend/
│   ├── pyproject.toml          # uv project + dependencies
│   ├── manage.py               # Django entrypoint
│   ├── config/                 # settings, urls, wsgi
│   ├── catalog/                # main Django app
│   │   ├── models.py           # Entity, Relationship, Tag, Term, PHI models
│   │   ├── serializers.py      # DRF serializers
│   │   ├── views.py            # API viewsets and views
│   │   ├── urls.py             # URL routing
│   │   ├── admin.py            # Django admin registration
│   │   └── management/commands/
│   │       ├── fetch_schema.py     # Fetch from Redshift
│   │       ├── compute_terms.py    # Term extraction pipeline
│   │       ├── classify_phi.py     # PHI/PII classification
│   │       └── migrate_data_01.py  # One-time migration from db-browser
│   └── core/                   # Reusable logic (no Django dependency)
│       ├── terms.py            # Term segmentation and scoring
│       └── phi_classifier.py   # PHI/PII pattern matching
├── frontend/
│   ├── package.json
│   ├── vite.config.js          # Vite config + dev proxy /api -> Django
│   ├── index.html
│   └── src/
│       ├── main.js             # Vue app entry + router setup
│       ├── App.vue             # Root component with nav
│       ├── style.css           # Global styles
│       ├── components/         # BrowseView, SearchBox, EntityDetail, TaskRunner, Login
│       └── services/
│           └── api.js          # HTTP calls to /api
└── README.md
```

## Getting Started

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- Node.js 16+ and npm (for frontend)

### Backend Setup

```bash
cd backend

# Install dependencies
uv sync

# Run migrations (creates ~/.db-jango/sqlite3.db)
uv run python manage.py migrate

# Create an admin user
uv run python manage.py createsuperuser

# Start the dev server
uv run python manage.py runserver
```

The API is available at http://localhost:8000/api/ and admin at http://localhost:8000/admin/.

### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start dev server (proxies /api to Django)
npm run dev
```

The UI is available at http://localhost:4200/.

### Migrating Data from db-browser

If you have an existing `~/.db-browser/catalog.db`, migrate it in one command:

```bash
cd backend
uv run python manage.py migrate_data_01
```

## Management Commands

| Command | Description |
|---------|-------------|
| `uv run python manage.py fetch_schema --schema <name>` | Fetch metadata from Redshift |
| `uv run python manage.py compute_terms --schema <name>` | Extract and classify terms |
| `uv run python manage.py classify_phi --schema <name>` | Run PHI/PII classification |
| `uv run python manage.py migrate_data_01` | One-time migration from db-browser |

All commands accept `--workers N` (default 4) and `--recompute` to force re-processing.

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/schemas/` | List all schemas |
| GET | `/api/schemas/{name}/children/` | Tables/views in a schema |
| GET | `/api/entities/{fqn}/` | Entity detail (with terms, tags, PHI) |
| GET | `/api/entities/{fqn}/children/` | Child entities |
| GET | `/api/entities/{fqn}/tags/` | Entity tags |
| POST | `/api/entities/{fqn}/tags/` | Add a tag |
| DELETE | `/api/entities/{fqn}/tags/{id}/` | Remove a tag |
| PUT | `/api/entities/{fqn}/description/` | Update description |
| GET | `/api/entities/{fqn}/terms/` | Entity terms |
| GET | `/api/entities/{fqn}/phi/` | PHI/PII scores + boosters |
| GET | `/api/search/?q=pattern` | Search tables/views by name |
| GET | `/api/tasks/` | List available/recent tasks |
| POST | `/api/tasks/` | Trigger a background task |
| GET | `/api/tasks/{id}/` | Poll task status |

## Data Model

- **Entity** — Database, Schema, Table, View, or Column (UUID PK, unique FQN)
- **Relationship** — Parent-child containment links between entities
- **Tag** — User-defined key/value labels on entities
- **Term** — Extracted semantic tokens with type (business/operations/language) and score
- **IdentifiableInfo** — PHI and PII scores per entity (0-100)
- **IdentifiableInfoBooster** — Score boost records from child/sibling propagation

## Database

SQLite stored at `~/.db-jango/sqlite3.db`. No external database server required.
