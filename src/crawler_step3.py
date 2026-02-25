import os
import re
import time
import hashlib
import sqlite3
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

import re
from urllib.parse import urlparse

# UN doc symbol patterns (extend as needed)
SYMBOL_RULES = [
    # resolutions
    ("resolution", r"\bA/RES/\d+/\d+\b"),
    ("resolution", r"\bS/RES/\d+\s*\(\d{4}\)\b"),

    # meeting records
    ("meeting_record", r"\bS/PV\.\d+\b"),
    ("meeting_record", r"\bA/\d+/PV\.\d+\b"),

    # presidential statements
    ("pres_statement", r"\bS/PRST/\d{4}/\d+\b"),

    # draft resolutions
    ("draft_resolution", r"\bA/\d+/L\.\d+\b"),
    ("draft_resolution", r"\bS/\d{4}/L\.\d+\b"),

    # reports (keep last!)
    ("report", r"\bS/\d{4}/\d+\b"),
    ("report", r"\bA/\d+/\d+\b"),

    # agenda
    ("agenda", r"\bA/\d+/1\b"),
]

def extract_symbol_and_category_from_text(text: str):
    if not text:
        return None, None
    for cat, pat in SYMBOL_RULES:
        m = re.search(pat, text)
        if m:
            return m.group(0), cat
    return None, None

def extract_symbol_and_category_from_url(url: str):
    return extract_symbol_and_category_from_text(url)

def domain(url: str) -> str:
    return urlparse(url).netloc.lower()

# Fallback category when there is no UN symbol (common for agencies/programmes)
def fallback_category(org_id: str, url: str) -> str:
    u = url.lower()
    d = domain(url)

    # UN main organs (often have symbols, but fallback anyway)
    if org_id in {"UNGA","UNSC","ECOSOC","UN Secretariat","ICJ","Trusteeship Council"}:
        if "press" in u or "statement" in u:
            return "statement"
        return "report"

    # Programmes/Funds + Specialized agencies: mostly "publications/reports"
    if any(x in u for x in ["publication", "publications", "report", "reports", "document", "documents", "library"]):
        return "publication"
    if any(x in u for x in ["news", "press", "media"]):
        return "press_release"

    return "publication"

from pypdf import PdfReader

def extract_symbol_and_category_from_pdf(file_path: str):
    try:
        reader = PdfReader(file_path)
        txt = (reader.pages[0].extract_text() or "")[:2500]
        return extract_symbol_and_category_from_text(txt)
    except Exception:
        return None, None

DB_PATH = "uno.db"
RAW_DIR = Path("data/raw")
RAW_DIR.mkdir(parents=True, exist_ok=True)

USER_AGENT = "UN-Doc-Crawler/0.1 (+educational project)"
TIMEOUT = 25
SLEEP_SECONDS = 1.0

# Keep it minimal: just PDFs (you can add .docx, .doc, etc. later)
DOC_EXTENSIONS = (".pdf",)

# limit how much we download per seed
MAX_DOCS_PER_SOURCE = 5

def ensure_tables(conn: sqlite3.Connection) -> None:
    """Ensure the required SQLite tables and indexes exist.

    This will run every startup and create the `raw_fetch` table if missing,
    along with helpful indexes. The connection should already be opened.
    """
    conn.execute("PRAGMA foreign_keys = ON;")

    conn.execute("""
    CREATE TABLE IF NOT EXISTS raw_fetch (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        org_id TEXT NOT NULL,
        source_id INTEGER,
        url TEXT NOT NULL,
        fetched_at TEXT DEFAULT (datetime('now')),
        http_status INTEGER,
        content_type TEXT,
        sha256 TEXT,
        file_path TEXT,
        error TEXT
    );
    """)

    # Helpful index
    conn.execute("CREATE INDEX IF NOT EXISTS idx_raw_fetch_org_id ON raw_fetch(org_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_raw_fetch_sha ON raw_fetch(sha256);")


def domain_of(url: str) -> str:
    """Return the network location (hostname) portion of ``url`` in lowercase.
    Used for comparing hosts when filtering links against an allowed domain."""
    
    return urlparse(url).netloc.lower()


def allowed(url: str, allowed_domain: str | None) -> bool:
    """Determine whether ``url`` lies within ``allowed_domain``.

    If ``allowed_domain`` is ``None`` all URLs are permitted. Subdomains of the
    allowed domain are also accepted.
    """
    if not allowed_domain:
        return True
    d = domain_of(url)
    allowed_domain = allowed_domain.lower().strip()
    # allow subdomains too
    return d == allowed_domain or d.endswith("." + allowed_domain)


def is_document_url(url: str) -> bool:
    """Return ``True`` if ``url`` appears to point to a document of interest.

    It strips fragments and query strings before checking the file extension
    against ``DOC_EXTENSIONS`` (currently only ``.pdf``).
    """
    u = url.split("#", 1)[0].split("?", 1)[0].lower()
    return u.endswith(DOC_EXTENSIONS)


def extract_links(html: str, base_url: str) -> list[str]:
    """Parse ``html`` and return a deduplicated list of absolute links.

    Anchors without ``href`` or with empty values are skipped.  Relative URLs
    are resolved against ``base_url``.
    """
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href:
            continue
        abs_url = urljoin(base_url, href)
        links.append(abs_url)
    # de-dup, keep order
    seen = set()
    out = []
    for u in links:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def sha256_bytes(data: bytes) -> str:
    """Compute the SHA‑256 hex digest of ``data``.
sssss
    Used to deduplicate downloaded files by content.
    """
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


def safe_ext_from_content_type(ct: str | None) -> str:
    """Return a sensible file extension based on the ``Content-Type`` header.

    Falls back to ``.bin`` when the header is missing or unrecognized.  Only
    ``pdf`` is handled explicitly for now.
    """
    if not ct:
        return ".bin"
    ct = ct.lower()
    if "pdf" in ct:
        return ".pdf"
    return ".bin"


def download_file(session: requests.Session, url: str) -> tuple[int, str | None, bytes]:
    """Fetch ``url`` using ``session`` and return (status, content-type, bytes).

    The ``User-Agent`` header and timeout are applied; the caller handles
    streaming or error logic.  Currently the entire body is read into memory.
    """
    r = session.get(url, timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}, stream=True)
    status = r.status_code
    ct = r.headers.get("Content-Type")
    data = r.content  # fine for “minimal”; for big files later use streaming-to-disk
    return status, ct, data


def crawl_one_source(conn: sqlite3.Connection, source_row: dict) -> None:
    """Process a single crawl source row and store results in the database.

    Fetches the seed page, extracts links, filters for approved documents, and
    downloads up to ``MAX_DOCS_PER_SOURCE`` files, recording successes or
    failures in ``raw_fetch``.
    """
    org_id = source_row["org_id"]
    source_id = source_row["id"]
    seed_url = source_row["seed_url"]
    allowed_domain = source_row["allowed_domain"]

    print(f"\n=== Crawling org_id={org_id} seed={seed_url}")

    with requests.Session() as s:
        s.headers.update({"User-Agent": USER_AGENT})

        try:
            resp = s.get(seed_url, timeout=TIMEOUT)
            resp.raise_for_status()
            html = resp.text
        except Exception as e:
            conn.execute(
                "INSERT INTO raw_fetch(org_id, source_id, url, http_status, error) VALUES (?,?,?,?,?)",
                (org_id, source_id, seed_url, None, f"seed_fetch_error: {e}"),
            )
            conn.commit()
            print(f"  !! Seed fetch failed: {e}")
            return

        links = extract_links(html, seed_url)

        # Filter by domain + document extension
        doc_links = []
        for u in links:
            if allowed(u, allowed_domain) and is_document_url(u):
                doc_links.append(u)

        if not doc_links:
            print("  (No document links found on seed page)")
            return

        downloaded = 0
        for doc_url in doc_links:
            if downloaded >= MAX_DOCS_PER_SOURCE:
                break

            time.sleep(SLEEP_SECONDS)

            try:
                status, ct, data = download_file(s, doc_url)
                if status >= 400:
                    raise RuntimeError(f"HTTP {status}")

                digest = sha256_bytes(data)
                ext = Path(urlparse(doc_url).path).suffix.lower() or safe_ext_from_content_type(ct)
                file_path = RAW_DIR / f"{digest}{ext}"

                if not file_path.exists():
                    file_path.write_bytes(data)
                
                                # 1) try URL-based detection
                doc_symbol, doc_category = extract_symbol_and_category_from_url(doc_url)
                detected_from = "url"

                # 2) if not found, try PDF-based detection
                if (not doc_symbol or not doc_category) and str(file_path).lower().endswith(".pdf"):
                    s2, c2 = extract_symbol_and_category_from_pdf(str(file_path))
                    if s2 or c2:
                        doc_symbol = doc_symbol or s2
                        doc_category = doc_category or c2
                        detected_from = "pdf"

                # 3) fallback for non-symbol org sites
                if not doc_category:
                    doc_category = fallback_category(org_id, doc_url)
                    detected_from = detected_from if detected_from in ("url","pdf") else "fallback"

                conn.execute(
                    """
                    INSERT INTO raw_fetch(
                        org_id, source_id, url, http_status, content_type, sha256, file_path,
                        doc_symbol, doc_category, detected_from
                    )
                    VALUES (?,?,?,?,?,?,?,?,?,?)
                    """,
                    (org_id, source_id, doc_url, status, ct, digest, str(file_path),
                    doc_symbol, doc_category, detected_from),
                )
                conn.commit()

                print(file_path.name)
                downloaded += 1
                print(f"  ✓ {downloaded}/{MAX_DOCS_PER_SOURCE} saved {file_path.name}")

            except Exception as e:
                conn.execute(
                    "INSERT INTO raw_fetch(org_id, source_id, url, http_status, error) VALUES (?,?,?,?,?)",
                    (org_id, source_id, doc_url, None, f"download_error: {e}"),
                )
                conn.commit()
                print(f"  !! failed {doc_url} ({e})")



def main() -> None:
    """Entry point for the crawler script.

    Opens the database, ensures tables exist, reads active crawl sources, and
    invokes ``crawl_one_source`` for each one.
    """
    if not Path(DB_PATH).exists():
        raise FileNotFoundError(f"SQLite DB not found: {DB_PATH} (run init_db/create tables first)")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        ensure_tables(conn)

        # Read crawl sources
        rows = conn.execute(
            """SELECT id, org_id, seed_url, allowed_domain
               FROM crawl_source
               WHERE active = 1
               ORDER BY id ASC"""
        ).fetchall()

        if not rows:
            print("No active crawl_source rows found.")
            return

        for r in rows:
            crawl_one_source(conn, dict(r))

        

        print("\nDone. Check:")
        print(" - data/raw/ for downloaded files")
        print(" - raw_fetch table for metadata/errors")

    finally:
        conn.close()



if __name__ == "__main__":
    main()