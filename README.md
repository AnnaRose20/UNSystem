# UNO Document Intelligence Pipeline

This project implements a data pipeline for the United Nations system:
it crawls and generates links to publicly available documents published
by UN organs, normalises the output, stores it in a local database, and
exposes the resulting registry via a simple HTTP API.

The codebase began as a technical assignment; over time the focus has
shifted to providing reusable generator functions and a minimal FastAPI
server that can be extended for further analysis or consumption.

---

## High‑Level Architecture

1. **Seeds & crawlers** – a JSON file (`data/seeds/UNO_URLs_EXCARPT.json`)
   lists base URLs for every principal organ, programme, fund and
   specialised agency.  Scrapers such as `crawler_step3.py` can be
   pointed at those seeds to discover documents and metadata.

2. **Generator library** (`src/generators_api.py`) – contains one
   function per organisation that returns a `pandas.DataFrame` of
   symbols/URLs built according to known naming patterns.  Generators
   are pure Python and easy to extend; several rely on a simple helper
   for pattern‑based series, others perform lightweight web requests.

3. **Database layer** (`src/db/`) – uses SQLAlchemy with an SQLite
   backend.  Current schema includes an `org_node` table for the
   organisational hierarchy; the API writes requests to a
   `requested_links` table that records every URL delivered to callers.

4. **API server** (`src/api_export.py`) – FastAPI application exposing a
   single endpoint `/export/urls.xlsx`.  Callers supply an `org`
   parameter (e.g. `UNGA`, `UNICEF`) and optional year; the server
   invokes the appropriate generator, filters by year, returns an XLSX
   file, and writes the dataset to the database (with `OrgID` and a
   request timestamp).

5. **Utilities / loaders** – additional scripts such as
   `loadunfromjson.py` and `loaderfile.py` load documents into the
   database or perform other housekeeping tasks.

6. **Data storage** – primary persistence is SQLite (`uno.db`); the API
   also writes requests to `requested_urls.db` (by default) with
   filenames and timestamps.


## Repository structure

```
UNCrawl/
├─ data/seeds/UNO_URLs_EXCARPT.json   # base URL list (see below)
├─ src/
│  ├─ api_export.py                   # FastAPI application
│  ├─ generators_api.py              # URL generator library
│  ├─ crawler_step3.py               # sample scraper
│  ├─ loadunfromjson.py              # example loader
│  ├─ loaderfile.py                  # helper for loading files
│  └─ db/
│     ├─ __init__.py
│     ├─ session.py                  # SQLAlchemy setup
│     └─ model.py                    # ORM models (OrgNode)
└─ README.md                         # this documentation
```


## Setup instructions

1. **Clone the repository** and `cd` into it.

   ```powershell
   git clone <repo-url> d:\UNCrawl
   cd d:\UNCrawl
   ```

2. **Create / activate a Python virtual environment.**

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\activate   # Windows
   ```

3. **Install dependencies.**

   ```powershell
   pip install --upgrade pip
   pip install fastapi uvicorn pandas openpyxl sqlalchemy requests beautifulsoup4
   ```

   (Additional packages may be required for crawling or future
   features.)

4. **Initialise the database.**

   ```python
   python - <<'PY'
   from src.db.session import init_db
   init_db()
   PY
   ```

   This creates `uno.db` with the `org_node` table.

5. **Run the API server.**

   ```powershell
   uvicorn src.api_export:app --reload
   ```

   Visit http://127.0.0.1:8000/docs for automatic Swagger UI.

6. **Make a sample request.**

   ```powershell
   curl "http://127.0.0.1:8000/export/urls.xlsx?org=UNGA&year=2024" --output unga.xlsx
   ```

   The call returns an Excel file and also writes the rows to the
   database under `requested_links`.


## Base URL JSON format

The file `data/seeds/UNO_URLs_EXCARPT.json` contains three arrays with
objects of the form:

```json
{
  "Hauptorgane": [
    {"name":"UN-Generalversammlung","abkuerzung":"UNGA","url":"https://www.un.org/en/ga/"},
    …
  ],
  "Nebenorgane_Programme_Fonds": […],
  "Sonderorganisationen": […]
}
```

Generators and crawlers use the `url` values as starting points.


## Extending the system

* **Add a new generator.**  In `generators_api.py` add a function that
  returns a `pandas.DataFrame` with columns `Year`, `Type`, `Symbol`
  and `URL`.  Register it in the `ORG_GENERATORS` dictionary in
  `api_export.py` using the uppercase, hyphen‑stripped key you want the
  endpoint to accept.  See existing generators for examples (pattern
  based, custom, or scraping).

* **Crawl documents.**  Populate / extend `data/seeds` or write new
  scrapers in `crawler_step3.py`.  The seed file can be edited directly
  or generated programmatically from the org model.

* **Change persistence.**  The database URL is set in
  `src/db/session.py`.  Replace the SQLite connection string with a
  Postgres/MySQL DSN and install the appropriate driver.
  Remember to re-run `init_db()` after altering models.

* **Add new API endpoints** – extend `api_export.py` with additional
  routes (e.g. `/search/`, `/list/`) and use the generator library or
  database session as needed.


## Data model and schema

The only permanent ORM model at present is `OrgNode`:

```python
class OrgNode(Base):
    __tablename__ = "org_node"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    parent_id: Mapped[Optional[str]] = mapped_column(ForeignKey("org_node.id"))
```

This table can represent the hierarchy of the UN system (main organs,
subsidiary bodies, agencies, etc.).  Documents and requested links are
not currently modelled with ORM classes; they are handled via raw
`DataFrame.to_sql()` calls into `requested_links`.

The `requested_links` table schema produced by `to_sql` is:

```sql
CREATE TABLE requested_links (
    Year INTEGER,
    Type TEXT,
    Symbol TEXT,
    Link TEXT,
    OrgID TEXT,
    RequestedAt TIMESTAMP
);
```


## Example use cases

* **Generate a list of GA resolutions.**  hit
  `/export/urls.xlsx?org=UNGA&year=2024` and open the resulting file.

* **Track which organisations have been queried.**  inspect the
  `requested_links` table in `uno.db`.

* **Seed a scraper.**  iterate over `UNO_URLs_EXCARPT.json` items and
  feed each URL to your favourite crawling routine.


## AI and further development

The original assignment invited the use of AI for research or
augmentation.  Although the current codebase does not integrate any
models, you can easily layer in semantic search by storing document
text embeddings in a vector store and adding a `/search` endpoint, or
use GPT‑style models to summarise documents after download.

The structured generator functions and clear seed file make it
straightforward to hook in natural‑language routines later.


## Next steps / suggestions

* implement a more complete data model for documents (metadata,
  content, versioning, etc.) and add corresponding ORM models
* migrate the link database to PostgreSQL if you expect larger volumes
* add unit tests for generators and API endpoints
* build a simple dashboard or chatbot leveraging the generated list of
  URLs
* write a crawler that actually downloads document PDFs and stores them
  in `data/processed/`

Happy hacking! Feel free to modify or prune this README as the project
evolves.  The core idea—organisationally-aware URL generation + a
lightweight API—remains the same.  🎯