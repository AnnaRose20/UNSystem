import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from db.session import SessionLocal, init_db

def main():
    init_db()
    with SessionLocal() as db:
        print("DB initialized")

if __name__ == "__main__":
    main()