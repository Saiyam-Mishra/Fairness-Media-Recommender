"""
Extracts database schema in a concise format for LLM context.

Requirements:
    pip install psycopg2-binary python-dotenv

Usage:
    python extract_schema.py
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

def get_conn():
    return psycopg2.connect(
        host     = os.getenv("DB_HOST"),
        port     = int(os.getenv("DB_PORT", "5432")),
        dbname   = os.getenv("DB_NAME", "postgres"),
        user     = os.getenv("DB_USER", "postgres"),
        password = os.getenv("DB_PASSWORD"),
    )

def main():
    conn = get_conn()
    cur  = conn.cursor(cursor_factory=RealDictCursor)

    # Get all tables
    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        ORDER BY table_name;
    """)
    tables = [r["table_name"] for r in cur.fetchall()]

    lines = []

    for table in tables:
        # Columns
        cur.execute("""
            SELECT
                c.column_name,
                c.data_type,
                c.is_nullable,
                CASE WHEN pk.column_name IS NOT NULL THEN 'PK' ELSE '' END AS pk,
                CASE WHEN fk.column_name IS NOT NULL
                     THEN '-> ' || fk.foreign_table || '.' || fk.foreign_column
                     ELSE '' END AS fk
            FROM information_schema.columns c
            LEFT JOIN (
                SELECT kcu.column_name FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                    ON tc.constraint_name = kcu.constraint_name
                WHERE tc.constraint_type = 'PRIMARY KEY'
                  AND tc.table_schema = 'public' AND tc.table_name = %s
            ) pk ON pk.column_name = c.column_name
            LEFT JOIN (
                SELECT kcu.column_name, ccu.table_name AS foreign_table, ccu.column_name AS foreign_column
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                    ON tc.constraint_name = kcu.constraint_name
                JOIN information_schema.constraint_column_usage ccu
                    ON ccu.constraint_name = tc.constraint_name
                WHERE tc.constraint_type = 'FOREIGN KEY'
                  AND tc.table_schema = 'public' AND tc.table_name = %s
            ) fk ON fk.column_name = c.column_name
            WHERE c.table_schema = 'public' AND c.table_name = %s
            ORDER BY c.ordinal_position;
        """, (table, table, table))
        cols = cur.fetchall()

        # Row count
        cur.execute(f"SELECT COUNT(*) AS n FROM {table};")
        count = cur.fetchone()["n"]

        lines.append(f"\n{table} ({count} rows)")
        for c in cols:
            typ  = c["data_type"].replace("character varying","varchar").replace("timestamp with time zone","timestamptz")
            null = "" if c["is_nullable"] == "NO" else " nullable"
            pk   = f" [{c['pk']}]" if c["pk"] else ""
            fk   = f" {c['fk']}"   if c["fk"] else ""
            lines.append(f"  {c['column_name']}: {typ}{null}{pk}{fk}")

    schema_text = "\n".join(lines)

    with open("schema_for_llm.txt", "w") as f:
        f.write(schema_text)

    cur.close()
    conn.close()

    size = os.path.getsize("schema_for_llm.txt")
    print(f"✅ schema_for_llm.txt  ({size:,} bytes  ~{size//4:,} tokens)")
    print("\nPreview:")
    print("\n".join(lines[:30]))

if __name__ == "__main__":
    main()