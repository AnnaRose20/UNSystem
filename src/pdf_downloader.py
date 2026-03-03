"""
PDF Downloader Module

This module provides functionality to query the requested_links database and download PDFs
from UN document viewer pages (e.g., https://docs.un.org/en/A/RES/79/110) by first extracting
the embedded PDF URL (iframe / pdf links) and then downloading the PDF.

Filters: year, type, orgid (OrgID) from requested_links table.
"""

from __future__ import annotations

import os
import logging
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse, urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup
from sqlalchemy import create_engine, text

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PDFDownloader:
    """Download PDFs from UN document pages stored in the database and save to local folder."""

    def __init__(self, db_path: str = "uno.db", download_dir: str = "data/downloads"):
        """
        Initialize the PDF Downloader.

        Args:
            db_path: Path to the SQLite database
            download_dir: Base directory to save downloaded PDFs
        """
        self.db_path = db_path
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)

        self.engine = create_engine(f"sqlite:///{db_path}")

        self.session = requests.Session()
        # Set headers once (UN sites often block default python UA)
        self.session.headers.update({"User-Agent": "Mozilla/5.0"})

    def query_urls(self, orgid: str, year: int | None = None, doc_type: str | None = None) -> pd.DataFrame:
        """
        Query the database for URLs matching the criteria.

        Returns:
            DataFrame with matching records (Link, Symbol, Year, Type, OrgID)
        """
        query = "SELECT Link, Symbol, Year, Type, OrgID FROM requested_links WHERE OrgID = :org"
        params: dict[str, object] = {"org": orgid}

        if year is not None:
            query += " AND Year = :year"
            params["year"] = year

        if doc_type:
            query += " AND Type = :type"
            params["type"] = doc_type

        try:
            with self.engine.connect() as conn:
                df = pd.read_sql(text(query), conn, params=params)
            logger.info(f"Found {len(df)} URLs for OrgID={orgid}, Year={year}, Type={doc_type}")
            return df
        except Exception as e:
            logger.error(f"Database query failed: {e}")
            return pd.DataFrame()

    # -----------------------------
    # New logic: HTML -> embedded PDF
    # -----------------------------
    def _extract_embedded_pdf_url(self, page_url: str) -> str | None:
        """
        Given a UN docs HTML page URL, find the embedded PDF URL.
        Strategy:
          1) iframe src
          2) any <a href> containing '.pdf'
        """
        resp = self.session.get(page_url, timeout=30)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # 1) iframe
        iframe = soup.find("iframe")
        if iframe and iframe.get("src"):
            return urljoin(page_url, iframe["src"])

        # 2) fallback: look for .pdf links
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if ".pdf" in href.lower():
                return urljoin(page_url, href)

        return None

    def _extract_filename_from_url(self, url: str, symbol: str | None = None) -> str:
        """
        Extract or generate a filename from the URL.

        If URL path has no filename, fallback to symbol.
        Ensures .pdf extension and cleans unsafe chars.
        """
        parsed = urlparse(url)
        filename = os.path.basename(parsed.path)

        if not filename or "." not in filename:
            filename = (symbol or "document").replace("/", "_")

        if not filename.lower().endswith(".pdf"):
            filename = filename.split(".")[0] + ".pdf"

        filename = filename.replace(" ", "_").replace("/", "_")
        return filename

    def _create_folder_structure(self, orgid: str, year: int | None = None, doc_type: str | None = None) -> Path:
        """
        Create standardized folder structure for downloaded files.

        Format: data/downloads/{OrgID}/{Year}/{Type}/
        """
        path = self.download_dir / orgid
        if year is not None:
            path = path / str(year)
        if doc_type:
            path = path / doc_type.replace(" ", "_")
        path.mkdir(parents=True, exist_ok=True)
        return path

    def download_pdf(self, page_url: str, target_path: Path, symbol: str | None = None) -> dict:
        """
        Download a single PDF from a UN docs HTML page URL by extracting the embedded PDF link first.

        Args:
            page_url: URL of the HTML page (e.g. https://docs.un.org/en/A/RES/79/110)
            target_path: Directory to save the PDF
            symbol: Optional document symbol for naming

        Returns:
            Dict with download status and file information
        """
        try:
            logger.info(f"Resolving embedded PDF from page: {page_url}")
            pdf_url = self._extract_embedded_pdf_url(page_url)

            if not pdf_url:
                return {
                    "status": "failed",
                    "url": page_url,
                    "symbol": symbol,
                    "reason": "Could not find embedded PDF link (no iframe/pdf anchor found)",
                }

            filename = self._extract_filename_from_url(pdf_url, symbol)
            filepath = target_path / filename

            # Skip if already downloaded
            if filepath.exists():
                return {
                    "status": "skipped",
                    "url": page_url,
                    "pdf_url": pdf_url,
                    "symbol": symbol,
                    "filepath": str(filepath),
                    "reason": "File already exists",
                }

            logger.info(f"Downloading PDF: {pdf_url}")
            pdf_resp = self.session.get(pdf_url, stream=True, timeout=30)
            pdf_resp.raise_for_status()

            # Ensure it's actually a PDF
            content_type = (pdf_resp.headers.get("Content-Type") or "").lower()
            if "pdf" not in content_type and pdf_resp.raw.read(4) != b"%PDF":
                # If we read from raw, we should not proceed writing partial; fail fast.
                return {
                    "status": "failed",
                    "url": page_url,
                    "pdf_url": pdf_url,
                    "symbol": symbol,
                    "filepath": str(filepath),
                    "reason": f"Resolved file is not a PDF (Content-Type={content_type})",
                }

            # If we read 4 bytes from raw above, stream is advanced. So: avoid that approach for writing.
            # Instead: do a safer check using iter_content peek without consuming raw.
            # Re-request only when needed.
            if "pdf" not in content_type:
                pdf_resp.close()
                pdf_resp = self.session.get(pdf_url, stream=True, timeout=30)
                pdf_resp.raise_for_status()
                first_chunk = next(pdf_resp.iter_content(chunk_size=8), b"")
                if not first_chunk.startswith(b"%PDF"):
                    return {
                        "status": "failed",
                        "url": page_url,
                        "pdf_url": pdf_url,
                        "symbol": symbol,
                        "filepath": str(filepath),
                        "reason": "Resolved file does not look like a PDF (%PDF missing)",
                    }
                # write first_chunk + rest
                with open(filepath, "wb") as f:
                    f.write(first_chunk)
                    for chunk in pdf_resp.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
            else:
                with open(filepath, "wb") as f:
                    for chunk in pdf_resp.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)

            file_size = filepath.stat().st_size / (1024 * 1024)
            logger.info(f"Saved: {filepath} ({file_size:.2f} MB)")

            return {
                "status": "success",
                "url": page_url,
                "pdf_url": pdf_url,
                "symbol": symbol,
                "filepath": str(filepath),
                "size_mb": round(file_size, 2),
                "downloaded_at": datetime.now().isoformat(),
            }

        except requests.RequestException as e:
            logger.error(f"Request failed for {page_url}: {e}")
            return {"status": "failed", "url": page_url, "symbol": symbol, "reason": str(e)}
        except Exception as e:
            logger.error(f"Unexpected error downloading {page_url}: {e}")
            return {"status": "failed", "url": page_url, "symbol": symbol, "reason": str(e)}

    def download_batch(self, orgid: str, year: int | None = None, doc_type: str | None = None) -> dict:
        """
        Download all PDFs matching the criteria from requested_links table.

        Args:
            orgid: Organization ID
            year: Optional year filter
            doc_type: Optional document type filter

        Returns:
            Summary dict with results and statistics
        """
        logger.info(f"Starting batch download: OrgID={orgid}, Year={year}, Type={doc_type}")

        df = self.query_urls(orgid, year, doc_type)
        if df.empty:
            return {
                "status": "no_data",
                "message": f"No URLs found for OrgID={orgid}, Year={year}, Type={doc_type}",
                "total": 0,
                "results": [],
            }

        target_path = self._create_folder_structure(orgid, year, doc_type)
        logger.info(f"Saving PDFs to: {target_path}")

        results: list[dict] = []
        for _, row in df.iterrows():
            # row["Link"] can be HTML page URL (docs.un.org) or direct PDF; we handle both:
            page_url = row["Link"]
            symbol = row.get("Symbol")
            result = self.download_pdf(page_url, target_path, symbol)
            results.append(result)

        successful = sum(1 for r in results if r["status"] == "success")
        failed = sum(1 for r in results if r["status"] == "failed")
        skipped = sum(1 for r in results if r["status"] == "skipped")
        total_size = sum(r.get("size_mb", 0) for r in results if r["status"] == "success")

        summary = {
            "status": "completed",
            "orgid": orgid,
            "year": year,
            "doc_type": doc_type,
            "total": len(results),
            "successful": successful,
            "failed": failed,
            "skipped": skipped,
            "total_size_mb": round(total_size, 2),
            "output_directory": str(target_path),
            "results": results,
        }

        logger.info(f"Batch download completed: {successful} successful, {failed} failed, {skipped} skipped")
        return summary


# Example manual run
if __name__ == "__main__":
    dl = PDFDownloader(db_path="uno.db", download_dir="data/downloads")

    # Single test (like your example)
    single = dl.download_pdf(
        "https://docs.un.org/en/A/RES/79/110",
        target_path=dl._create_folder_structure("UNGA", 2025, "RESOLUTION"),
        symbol="A/RES/79/110",
    )
    print(single)

    # Batch example:
    # summary = dl.download_batch(orgid="UNGA", year=2025, doc_type="RESOLUTION")
    # print(summary)