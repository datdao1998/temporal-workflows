"""Test PostgreSQL connection and verify the jobs table exists with correct schema.

Usage:
    python tests/test_db_connection.py
    python tests/test_db_connection.py --host localhost --port 5432 --user postgres --password postgres --db-name pdf_extraction
"""

import argparse
import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def test_connection(host: str, port: int, user: str, password: str, db_name: str):
    db_url = f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db_name}"
    engine = create_async_engine(db_url)

    try:
        async with engine.connect() as conn:
            # 1. Test connection
            result = await conn.execute(text("SELECT 1"))
            print(f"[OK] Connected to {db_name} at {host}:{port}")

            # 2. Check jobs table exists
            result = await conn.execute(text(
                "SELECT EXISTS ("
                "  SELECT 1 FROM information_schema.tables "
                "  WHERE table_name = 'jobs'"
                ")"
            ))
            table_exists = result.scalar()
            if table_exists:
                print("[OK] Table 'jobs' exists")
            else:
                print("[FAIL] Table 'jobs' does not exist")
                return

            # 3. Verify columns
            result = await conn.execute(text(
                "SELECT column_name, data_type, is_nullable "
                "FROM information_schema.columns "
                "WHERE table_name = 'jobs' "
                "ORDER BY ordinal_position"
            ))
            columns = result.fetchall()

            expected = {
                "id": "character varying",
                "status": "character varying",
                "file_path": "text",
                "result": "json",
                "error": "text",
                "created_at": "timestamp without time zone",
                "updated_at": "timestamp without time zone",
            }

            print(f"\n{'Column':<15} {'Type':<35} {'Nullable':<10} {'Status'}")
            print("-" * 75)
            for col_name, data_type, nullable in columns:
                if col_name in expected:
                    type_ok = expected[col_name] in data_type
                    status = "OK" if type_ok else f"EXPECTED {expected[col_name]}"
                    print(f"{col_name:<15} {data_type:<35} {nullable:<10} {status}")
                else:
                    print(f"{col_name:<15} {data_type:<35} {nullable:<10} UNEXPECTED")

            found_cols = {col[0] for col in columns}
            missing = set(expected.keys()) - found_cols
            if missing:
                print(f"\n[FAIL] Missing columns: {missing}")
            else:
                print(f"\n[OK] All {len(expected)} expected columns present")

            # 4. Check index
            result = await conn.execute(text(
                "SELECT indexname FROM pg_indexes WHERE tablename = 'jobs'"
            ))
            indexes = [row[0] for row in result.fetchall()]
            if "idx_jobs_status" in indexes:
                print("[OK] Index 'idx_jobs_status' exists")
            else:
                print(f"[FAIL] Index 'idx_jobs_status' not found. Found: {indexes}")

            # 5. Row count
            result = await conn.execute(text("SELECT COUNT(*) FROM jobs"))
            count = result.scalar()
            print(f"\n[INFO] Current row count: {count}")

    except Exception as e:
        print(f"[FAIL] {e}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test PostgreSQL jobs table")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=5432)
    parser.add_argument("--user", default="postgres")
    parser.add_argument("--password", default="postgres")
    parser.add_argument("--db-name", default="pdf_extraction")
    args = parser.parse_args()
    asyncio.run(test_connection(args.host, args.port, args.user, args.password, args.db_name))
