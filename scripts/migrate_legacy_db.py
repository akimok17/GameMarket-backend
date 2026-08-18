from app.core.database import engine
from app.core.migrations import migrate_legacy_schema


if __name__ == "__main__":
    changed = migrate_legacy_schema(engine)
    if changed:
        print("Added missing columns:")
        for item in changed:
            print(" -", item)
    else:
        print("Legacy schema is already compatible (or DB is not PostgreSQL).")
