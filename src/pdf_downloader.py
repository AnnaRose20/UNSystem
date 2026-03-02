"""PDF Downloader Module

This module provides functionality to query the requested_links database
and download PDFs from URLs matching specified criteria (year, type, orgid).
"""

import os
import requests
import logging
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse
from sqlalchemy import create_engine, text
import pandas as pd

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PDFDownloader:
    """Download PDFs from URLs in the database and save to local folder."""
    
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
        self.session.timeout = 30
    
    def query_urls(self, orgid: str, year: int = None, doc_type: str = None) -> pd.DataFrame:
        """
        Query the database for URLs matching the criteria.
        
        Args:
            orgid: Organization ID (e.g., 'UNGA', 'UNSC')
            year: Optional year to filter by
            doc_type: Optional document type to filter by
        
        Returns:
            DataFrame with matching records (Link, Symbol, Year, Type, OrgID)
        """
        query = "SELECT Link, Symbol, Year, Type, OrgID FROM requested_links WHERE OrgID = :org"
        params = {"org": orgid}
        
        if year:
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
    
    def _extract_filename_from_url(self, url: str, symbol: str = None) -> str:
        """
        Extract or generate a filename from the URL.
        
        Args:
            url: The URL to extract filename from
            symbol: Optional symbol to use as fallback
        
        Returns:
            Safe filename with .pdf extension
        """
        # Try to extract from URL path
        parsed = urlparse(url)
        filename = os.path.basename(parsed.path)
        
        # If no filename in path, use symbol
        if not filename or "." not in filename:
            filename = (symbol or "document").replace("/", "_")
        
        # Ensure .pdf extension
        if not filename.lower().endswith(".pdf"):
            filename = filename.split(".")[0] + ".pdf"
        
        # Clean up unsafe characters
        filename = filename.replace(" ", "_").replace("/", "_")
        return filename
    
    def _create_folder_structure(self, orgid: str, year: int = None, doc_type: str = None) -> Path:
        """
        Create standardized folder structure for downloaded files.
        
        Format: data/downloads/{OrgID}/{Year}/{Type}/
        
        Returns:
            Path to the target directory
        """
        path = self.download_dir / orgid
        
        if year:
            path = path / str(year)
        
        if doc_type:
            path = path / doc_type.replace(" ", "_")
        
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    def download_pdf(self, url: str, target_path: Path, symbol: str = None) -> dict:
        """
        Download a single PDF from URL.
        
        Args:
            url: URL of the PDF
            target_path: Directory to save the PDF
            symbol: Optional document symbol for naming
        
        Returns:
            Dict with download status and file information
        """
        try:
            filename = self._extract_filename_from_url(url, symbol)
            filepath = target_path / filename
            
            # Skip if already downloaded
            if filepath.exists():
                return {
                    "status": "skipped",
                    "url": url,
                    "symbol": symbol,
                    "filepath": str(filepath),
                    "reason": "File already exists"
                }
            
            # Download the file
            logger.info(f"Downloading: {url}")
            response = self.session.get(url, stream=True, timeout=30)
            response.raise_for_status()
            
            # Check if content is actually a PDF
            content_type = response.headers.get("content-type", "").lower()
            if "application/pdf" not in content_type and response.content[:4] != b"%PDF":
                return {
                    "status": "failed",
                    "url": url,
                    "symbol": symbol,
                    "filepath": str(filepath),
                    "reason": "Not a PDF file"
                }
            
            # Save the file
            with open(filepath, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            file_size = filepath.stat().st_size / (1024 * 1024)  # Size in MB
            logger.info(f"Successfully saved: {filepath} ({file_size:.2f} MB)")
            
            return {
                "status": "success",
                "url": url,
                "symbol": symbol,
                "filepath": str(filepath),
                "size_mb": round(file_size, 2),
                "downloaded_at": datetime.now().isoformat()
            }
        
        except requests.RequestException as e:
            logger.error(f"Failed to download {url}: {e}")
            return {
                "status": "failed",
                "url": url,
                "symbol": symbol,
                "reason": str(e)
            }
        except Exception as e:
            logger.error(f"Unexpected error downloading {url}: {e}")
            return {
                "status": "failed",
                "url": url,
                "symbol": symbol,
                "reason": str(e)
            }
    
    def download_batch(self, orgid: str, year: int = None, doc_type: str = None) -> dict:
        """
        Download all PDFs matching the criteria.
        
        Args:
            orgid: Organization ID
            year: Optional year filter
            doc_type: Optional document type filter
        
        Returns:
            Summary dict with results and statistics
        """
        logger.info(f"Starting batch download: OrgID={orgid}, Year={year}, Type={doc_type}")
        
        # Query database
        df = self.query_urls(orgid, year, doc_type)
        
        if df.empty:
            return {
                "status": "no_data",
                "message": f"No URLs found for OrgID={orgid}, Year={year}, Type={doc_type}",
                "total": 0,
                "results": []
            }
        
        # Create folder structure
        target_path = self._create_folder_structure(orgid, year, doc_type)
        logger.info(f"Saving PDFs to: {target_path}")
        
        # Download each PDF
        results = []
        for _, row in df.iterrows():
            result = self.download_pdf(row["Link"], target_path, row.get("Symbol"))
            results.append(result)
        
        # Compile statistics
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
            "results": results
        }
        
        logger.info(f"Batch download completed: {successful} successful, {failed} failed, {skipped} skipped")
        return summary
