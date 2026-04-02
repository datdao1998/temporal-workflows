"""Create database and tables for the PDF extraction service.

Usage:
    python create_tables.py
    python create_tables.py --host localhost --port 5432 --user postgres --password postgres --db-name pdf_extraction
"""

import argparse
import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from src.db.models import Base


async def create_database(host: str, port: int, user: str, password: str, db_name: str) -> None:
    # Connect to the default 'postgres' database to create our target database
    admin_url = f"postgresql+asyncpg://{user}:{password}@{host}:{port}/postgres"
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")

    async with engine.connect() as conn:
        # Check if database already exists
        result = await conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": db_name},
        )
        if result.scalar():
            print(f"Database '{db_name}' already exists.")
        else:
            await conn.execute(text(f'CREATE DATABASE "{db_name}"'))
            print(f"Database '{db_name}' created.")

    await engine.dispose()


async def create_tables(host: str, port: int, user: str, password: str, db_name: str) -> None:
    db_url = f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db_name}"
    engine = create_async_engine(db_url, echo=True)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await engine.dispose()
    print("Tables created successfully.")


async def main(args):
    await create_database(args.host, args.port, args.user, args.password, args.db_name)
    await create_tables(args.host, args.port, args.user, args.password, args.db_name)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create PDF extraction database and tables")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=5432)
    parser.add_argument("--user", default="postgres")
    parser.add_argument("--password", default="postgres")
    parser.add_argument("--db-name", default="pdf_extraction")
    args = parser.parse_args()
    asyncio.run(main(args))
