# PDF Download API Guide

This guide explains how to use the new PDF download functionality in the UNO URL Export API.

## Overview

Two new files have been added:
1. **`src/pdf_downloader.py`** - Core module for downloading PDFs from URLs in the database
2. **Enhanced `src/api_export.py`** - Two new API endpoints for PDF operations

## New API Endpoints

### 1. `/download/pdfs` - Download PDFs

Download all PDFs matching the specified criteria and save them locally.

**Endpoint:** `GET /download/pdfs`

**Query Parameters:**
- `org` (required): Organization ID (e.g., `UNGA`, `UNSC`, `UNICEF`)
- `year` (optional): Filter by specific year (e.g., `2023`)
- `type` (optional): Filter by document type (e.g., `Resolution`, `Report`)

**Example Requests:**

```bash
# Download all UNGA PDFs for year 2023
curl "http://localhost:8000/download/pdfs?org=UNGA&year=2023"

# Download all UNSC Resolutions
curl "http://localhost:8000/download/pdfs?org=UNSC&type=Resolution"

# Download all UNGA 2023 Resolutions
curl "http://localhost:8000/download/pdfs?org=UNGA&year=2023&type=Resolution"
```

**Response:** JSON object with download summary:
```json
{
  "status": "completed",
  "orgid": "UNGA",
  "year": 2023,
  "doc_type": "Resolution",
  "total": 50,
  "successful": 48,
  "failed": 2,
  "skipped": 0,
  "total_size_mb": 125.50,
  "output_directory": "data/downloads/UNGA/2023/Resolution",
  "results": [
    {
      "status": "success",
      "url": "https://docs.un.org/en/A/RES/78/1",
      "symbol": "A/RES/78/1",
      "filepath": "data/downloads/UNGA/2023/Resolution/A_RES_78_1.pdf",
      "size_mb": 2.34,
      "downloaded_at": "2026-03-03T10:30:45.123456"
    },
    ...
  ]
}
```

### 2. `/download/status` - Check Download Status

Check how many PDFs are available for download without actually downloading them.

**Endpoint:** `GET /download/status`

**Query Parameters:**
- `org` (required): Organization ID
- `year` (optional): Filter by specific year
- `type` (optional): Filter by document type

**Example Requests:**

```bash
# Check how many UNGA PDFs are available for 2023
curl "http://localhost:8000/download/status?org=UNGA&year=2023"

# Preview available Resolutions
curl "http://localhost:8000/download/status?org=UNGA&type=Resolution"
```

**Response:** JSON object with URL count and sample:
```json
{
  "status": "ok",
  "orgid": "UNGA",
  "year": 2023,
  "doc_type": null,
  "total_urls": 150,
  "sample_urls": [
    {
      "Symbol": "A/78/1",
      "Link": "https://docs.un.org/en/A/78/1",
      "Type": "Resolution",
      "Year": 2023
    },
    ...
  ]
}
```

## Folder Structure

Downloaded PDFs are organized as follows:

```
data/downloads/
├── UNGA/
│   ├── 2023/
│   │   ├── Resolution/
│   │   │   ├── A_RES_78_1.pdf
│   │   │   └── A_RES_78_2.pdf
│   │   └── Report/
│   │       └── A_78_100.pdf
│   └── 2022/
│       └── Resolution/
└── UNSC/
    ├── 2023/
    └── 2022/
```

Folder structure: `data/downloads/{OrgID}/{Year}/{DocumentType}/`

## Features

✅ **Smart Caching** - Already downloaded files are skipped automatically
✅ **Content Validation** - Verifies that downloaded files are actually PDFs
✅ **Error Handling** - Continues downloading even if some URLs fail
✅ **Progress Logging** - Logs each download with file size information
✅ **Organized Structure** - Auto-creates folder hierarchy for organization and filtering
✅ **Database Integration** - Queries the same database used by the export API

## Usage in Python Code

You can also use the PDF downloader directly in Python scripts:

```python
from src.pdf_downloader import PDFDownloader

# Initialize downloader
downloader = PDFDownloader(db_path="uno.db", download_dir="data/downloads")

# Download all UNGA 2023 Resolutions
result = downloader.download_batch(orgid="UNGA", year=2023, doc_type="Resolution")

print(f"Downloaded {result['successful']} files successfully")
print(f"Total size: {result['total_size_mb']} MB")
print(f"Saved to: {result['output_directory']}")

# Or check URLs before downloading
df = downloader.query_urls(orgid="UNGA", year=2023)
print(f"Found {len(df)} URLs")
```

## Requirements

Make sure the following packages are installed:
- `pandas` - Data manipulation
- `requests` - HTTP requests for downloading
- `sqlalchemy` - Database querying
- `fastapi` - API framework

Install with:
```bash
pip install pandas requests sqlalchemy fastapi
```

## Error Handling

The API provides helpful error messages:

- **404 No Data**: No URLs found matching the criteria
  ```json
  {
    "status": "no_data",
    "message": "No URLs found for OrgID=INVALID, Year=null, Type=null"
  }
  ```

- **Network Errors**: Logs and skips problematic URLs
  - Connection timeouts
  - Invalid URLs
  - Non-PDF content
  - Server errors (4xx, 5xx)

- **Partially Failed Batches**: Returns all results with individual status for each URL

## Configuration

Edit the downloader initialization in `api_export.py` to change defaults:

```python
downloader = PDFDownloader(
    db_path="uno.db",           # SQLite database path
    download_dir="data/downloads"  # Where to save PDFs
)
```

## Performance Tips

1. **Use Year/Type Filters** - Download only what you need
   ```bash
   curl "http://localhost:8000/download/pdfs?org=UNGA&year=2023&type=Resolution"
   ```

2. **Check Status First** - Preview available files
   ```bash
   curl "http://localhost:8000/download/status?org=UNGA&year=2023"
   ```

3. **Batch Multiple Years** - Run separate requests for each year if needed

4. **Monitor Network** - Large batch downloads may take time

## Troubleshooting

**Issue:** Files not downloading
- **Solution:** Ensure URLs in database are valid and accessible
- **Check:** Run `/download/status` to verify URLs exist

**Issue:** Wrong folder structure
- **Solution:** Check that `data/downloads` directory is writable
- **Check:** Verify folder permissions

**Issue:** Memory errors on large batches
- **Solution:** Download smaller subsets (specific year + type)
- **Check:** Use `/download/status` to see batch size first

## See Also

- [Main API Documentation](README.md)
- [Export URLs Endpoint](API_EXPORT.md)
