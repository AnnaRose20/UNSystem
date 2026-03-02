import json
from db.session import SessionLocal, init_db
from db.model import OrgNode


def insert_org(db, org_id, name, parent):
    obj = db.get(OrgNode, org_id)

    if not obj:
        obj = OrgNode(
            id=org_id,
            name=name,
            parent_id=parent
        )
        db.add(obj)


def load_un_structure(json_file: str):

    init_db()

    with open(json_file, encoding="utf-8") as f:
        data = json.load(f)

    with SessionLocal() as db:

        # --------------------
        # ROOT NODE
        # --------------------
        insert_org(db, "UN", "United Nations", None)

        # --------------------
        # Hauptorgane → parent UN
        # --------------------
        for item in data["Hauptorgane"]:
            insert_org(
                db,
                item["abkuerzung"],
                item["name"],
                "UN"
            )

        # --------------------
        # Nebenorgane → parent UNGA
        # --------------------
        for item in data["Nebenorgane_Programme_Fonds"]:
            insert_org(
                db,
                item["abkuerzung"],
                item["name"],
                "UNGA"
            )

        # --------------------
        # Sonderorganisationen → parent UN
        # --------------------
        for item in data["Sonderorganisationen"]:
            insert_org(
                db,
                item["abkuerzung"],
                item["name"],
                "UN"
            )

        db.commit()
        print("✅ Organization hierarchy inserted!")


if __name__ == "__main__":
    load_un_structure("data/seeds/seeds.json")