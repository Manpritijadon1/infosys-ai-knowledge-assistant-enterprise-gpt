import os
import psycopg
from dotenv import load_dotenv

load_dotenv()

database_url = os.getenv("DATABASE_URL")

if not database_url:
    raise ValueError("DATABASE_URL not found in .env")

with psycopg.connect(database_url) as conn:
    with conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        cur.execute("""
            SELECT extversion
            FROM pg_extension
            WHERE extname = 'vector';
        """)
        print("pgvector version:", cur.fetchone()[0])

print("pgvector enabled successfully!")