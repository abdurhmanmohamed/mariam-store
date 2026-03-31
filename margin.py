# margin.py — Raw SQL approach (no Flask context needed)

import os, sqlite3
from sqlalchemy import create_engine, text

# ==========================
# DATABASE CONNECTIONS
# ==========================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SQLITE_PATH = os.path.join(BASE_DIR, 'instance', 'mariam.db')

sqlite_conn = sqlite3.connect(SQLITE_PATH)
sqlite_conn.row_factory = sqlite3.Row  # allow column access by name

pg_engine = create_engine(
    "postgresql://postgres.faossrhfekblsmausrte:Romaire_marim@aws-1-eu-central-1.pooler.supabase.com:6543/postgres"
)

print(f"📂 SQLite path: {SQLITE_PATH}")
print(f"   File exists: {os.path.exists(SQLITE_PATH)}\n")


# ==========================
# PRE-MIGRATION: WIDEN/CREATE PG TABLES
# ==========================
def setup_pg():
    print("🔧 Setting up PostgreSQL schema...")
    with pg_engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS admin (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                number INTEGER NOT NULL,
                password TEXT NOT NULL
            );
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS itemdetails (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                price INTEGER NOT NULL,
                old_price INTEGER,
                discount_label TEXT,
                visability INTEGER NOT NULL DEFAULT 1
            );
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS itemcolor (
                id SERIAL PRIMARY KEY,
                color TEXT NOT NULL,
                item_id INTEGER REFERENCES itemdetails(id)
            );
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS itemimg (
                id SERIAL PRIMARY KEY,
                img TEXT NOT NULL,
                item_id INTEGER REFERENCES itemdetails(id)
            );
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS "order" (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                number INTEGER,
                adress TEXT NOT NULL,
                message TEXT,
                created_at TIMESTAMP,
                state TEXT DEFAULT 'order',
                total_price INTEGER
            );
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS cart (
                id SERIAL PRIMARY KEY,
                img TEXT,
                color TEXT,
                name TEXT NOT NULL,
                price INTEGER NOT NULL,
                amount INTEGER NOT NULL,
                size TEXT DEFAULT '',
                session_id TEXT,
                order_id INTEGER REFERENCES "order"(id)
            );
        """))
        # Widen any existing VARCHAR columns
        for stmt in [
            'ALTER TABLE itemdetails ALTER COLUMN description TYPE TEXT;',
            'ALTER TABLE "order" ALTER COLUMN adress TYPE TEXT;',
            'ALTER TABLE "order" ALTER COLUMN message TYPE TEXT;',
        ]:
            try:
                conn.execute(text(stmt))
            except Exception:
                pass  # already TEXT
    print("✅ Schema ready.\n")


# ==========================
# GENERIC MERGE FUNCTION (raw SQL)
# ==========================
def merge_table(table_name, skip_if_missing_col=None):
    print(f"🔄 Merging {table_name}...")
    cursor = sqlite_conn.execute(f'SELECT * FROM "{table_name}"')
    rows = cursor.fetchall()
    cols = [d[0] for d in cursor.description]

    inserted = updated = skipped = 0

    with pg_engine.begin() as conn:
        for row in rows:
            data = dict(zip(cols, row))

            # Ensure size has a default for cart
            if table_name == 'cart' and 'size' not in data:
                data['size'] = ''
            if table_name == 'cart' and data.get('size') is None:
                data['size'] = ''

            # Check if row already exists
            exists = conn.execute(
                text(f'SELECT id FROM "{table_name}" WHERE id = :id'),
                {"id": data["id"]}
            ).fetchone()

            col_names = list(data.keys())
            placeholders = ', '.join([f':{c}' for c in col_names])
            col_list = ', '.join([f'"{c}"' for c in col_names])
            update_set = ', '.join([f'"{c}" = :{c}' for c in col_names if c != 'id'])

            if exists:
                conn.execute(
                    text(f'UPDATE "{table_name}" SET {update_set} WHERE id = :id'),
                    data
                )
                updated += 1
            else:
                conn.execute(
                    text(f'INSERT INTO "{table_name}" ({col_list}) VALUES ({placeholders})'),
                    data
                )
                inserted += 1

    print(f"  ✅ {table_name}: {inserted} inserted, {updated} updated ({len(rows)} total)\n")


# ==========================
# RESET SEQUENCES
# ==========================
def reset_sequences():
    tables = ['admin', 'itemdetails', 'itemcolor', 'itemimg', 'order', 'cart']
    print("🔧 Resetting PostgreSQL sequences...")
    with pg_engine.begin() as conn:
        for t in tables:
            try:
                conn.execute(text(f"""
                    SELECT setval(
                        pg_get_serial_sequence('{t}', 'id'),
                        COALESCE((SELECT MAX(id) FROM "{t}"), 1)
                    );
                """))
                print(f"  ✅ Sequence reset for {t}")
            except Exception as e:
                print(f"  ⚠️ Could not reset sequence for {t}: {e}")


# ==========================
# RUN MIGRATION
# ==========================
try:
    setup_pg()
    merge_table("admin")
    merge_table("itemdetails")
    merge_table("itemcolor")
    merge_table("itemimg")
    merge_table("order")
    merge_table("cart")
    reset_sequences()
    print("\n🚀 MIGRATION COMPLETED SUCCESSFULLY")
except Exception as e:
    print(f"\n❌ ERROR: {e}")
finally:
    sqlite_conn.close()