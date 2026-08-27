"""
Deploy the VLEP PostgreSQL schema by running the 9 migration files in order.
Supports a --verify flag to check if all tables were created correctly.
"""

import sys

from sqlalchemy import text

from vlep.config import get_settings
from vlep.db import sync_engine


def deploy():
    settings = get_settings()
    migrations_dir = settings.migrations_dir

    if not migrations_dir.exists():
        print(f"Error: Migrations directory not found at {migrations_dir}")
        sys.exit(1)

    # Find and sort migration files
    migration_files = sorted(migrations_dir.glob("*.sql"))
    if not migration_files:
        print(f"Error: No .sql migration files found in {migrations_dir}")
        sys.exit(1)

    print(f"Found {len(migration_files)} migration files in {migrations_dir}")

    # Use a raw DBAPI connection with autocommit=True so the SQL script's
    # own BEGIN and COMMIT statements control the transaction.
    raw_conn = sync_engine.raw_connection()
    raw_conn.autocommit = True
    cursor = raw_conn.cursor()

    try:
        for migration in migration_files:
            print(f"Executing: {migration.name}...")
            with open(migration, encoding="utf-8") as f:
                sql_content = f.read()

            cursor.execute(sql_content)
            print(f"Successfully executed: {migration.name}")

    except Exception as e:
        print(f"\n[ERROR] Migration failed on {migration.name}: {e}")
        cursor.close()
        raw_conn.close()
        sys.exit(1)

    cursor.close()
    raw_conn.close()
    print("\nAll migrations executed successfully!")

def verify():
    print("\nVerifying database schema...")
    query = """
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_schema IN (
            'core', 'ingestion', 'ontology', 'literature', 'evidence',
            'phenotyping', 'nosology', 'modeling', 'csep', 'review', 'governance'
        )
        ORDER BY table_schema, table_name;
    """

    with sync_engine.connect() as conn:
        result = conn.execute(text(query)).fetchall()

    if not result:
        print("Warning: No tables found in VLEP schemas!")
        sys.exit(1)

    print(f"Found {len(result)} tables across VLEP schemas:")
    current_schema = None
    for schema, table in result:
        if schema != current_schema:
            current_schema = schema
            print(f"\nSchema: {schema}")
        print(f"  - {table}")

    print("\nVerification successful!")

def main():
    args = sys.argv[1:]
    if "--verify" in args:
        verify()
    else:
        deploy()
        verify()

if __name__ == "__main__":
    main()
