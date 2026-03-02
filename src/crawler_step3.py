from __future__ import annotations

import re
import requests
from typing import Any


def fetch_record_json(recid: int) -> list[dict[str, Any]]:
    url = f"https://digitallibrary.un.org/record/{recid}?of=recjson"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.json()


def extract_symbol_from_filename(file_name: str) -> str | None:
    """
    Convert A_80_34-EN.pdf -> A/80/34
    """
    base = file_name.split("-")[0]  # A_80_34
    base = base.replace(".pdf", "")
    if re.match(r"^[AES]_\d+_\d+$", base):
        return base.replace("_", "/")
    return None


def owning_org_from_symbol(symbol: str) -> str:
    if symbol.startswith("A/"):
        return "UNGA"
    elif symbol.startswith("S/"):
        return "UNSC"
    elif symbol.startswith("E/"):
        return "ECOSOC"
    return "UNKNOWN"


def extract_language(file_name: str) -> str | None:
    m = re.search(r"-([A-Z]{2})\.(pdf|docx?|txt)$", file_name, re.IGNORECASE)
    return m.group(1).upper() if m else None


def infer_doc_type(title: str | None) -> str:
    if not title:
        return "unknown"
    t = title.lower()
    if t.startswith("report"):
        return "report"
    if "resolution" in t:
        return "resolution"
    if "letter" in t:
        return "letter"
    return "unknown"


def main():
    recid = 4102708  # change this to test other records

    data = fetch_record_json(recid)
    record = data[0]

    record_id = record["recid"]
    title = record.get("title", {}).get("title")

    files = record.get("files", [])
    if not files:
        print("No files found.")
        return

    # Extract canonical symbol from first file
    canonical_id = None
    for f in files:
        symbol = extract_symbol_from_filename(f["full_name"])
        if symbol:
            canonical_id = symbol     
            break

    if not canonical_id:
        canonical_id = f"digitallibrary:{record_id}"

    owning_org = owning_org_from_symbol(canonical_id)
    doc_type = infer_doc_type(title)

    print("==== RECORD ====")
    print("record_id:", record_id)
    print("canonical_id:", canonical_id)
    print("owning_org:", owning_org)
    print("title:", title)
    print("doc_type:", doc_type)

    print("\n==== FILES ====")

    for f in files:
        file_name = f["full_name"]
        language = extract_language(file_name)
        version = f.get("version")
        source_url = f.get("url")
        size = f.get("size")

        # Content type from metadata
        magic = f.get("magic", [])
        content_type = None
        for item in magic:
            if "application/pdf" in item:
                content_type = "application/pdf"
                break

        print("\nfile:", file_name)
        print("  language:", language)
        print("  version:", version)
        print("  source_url:", source_url)
        print("  size:", size)
        print("  content_type:", content_type)


if __name__ == "__main__":
    main()