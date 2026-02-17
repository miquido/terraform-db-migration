import os
import pg8000.native
import sys

# Configuration from environment variables
PG_HOST = os.environ.get("PG_HOST", "localhost")
PG_DATABASE = os.environ.get("PG_DATABASE", "dbdev")
PG_USER = os.environ.get("PG_USER", "userdev")
PG_PORT = int(os.environ.get("PG_PORT", "9999"))


def restore_dump(dump_file):
    """Restore SQL dump to PostgreSQL database"""
    print(f"🔄 Starting database restore...")
    print(f"Host: {PG_HOST}")
    print(f"Database: {PG_DATABASE}")
    print(f"User: {PG_USER}")
    print(f"Dump file: {dump_file}")
    print()

    if not os.path.exists(dump_file):
        print(f"❌ Error: File {dump_file} not found!")
        sys.exit(1)

    # Connect to PostgreSQL
    password = os.environ["PG_PASSWORD"]
    conn = pg8000.native.Connection(
        host=PG_HOST,
        database=PG_DATABASE,
        user=PG_USER,
        password=password,
        port=PG_PORT,
        ssl_context=True
    )

    # Read SQL dump
    print("📖 Reading SQL dump...")
    with open(dump_file, 'r', encoding='utf-8') as f:
        sql_content = f.read()

    file_size = os.path.getsize(dump_file) / (1024*1024)
    print(f"   File size: {file_size:.2f} MB")
    print()

    # Split into statements (simple split by semicolon)
    statements = [stmt.strip() for stmt in sql_content.split(';') if stmt.strip()]

    print(f"⚡ Executing {len(statements)} SQL statements...")

    executed = 0
    errors = 0

    for idx, stmt in enumerate(statements, 1):
        try:
            # Show progress every 100 statements
            if idx % 100 == 0:
                print(f"Progress: {idx}/{len(statements)} statements ({executed} ok, {errors} errors)", end='\r', flush=True)

            # Skip comments and empty lines
            if stmt.startswith('--') or not stmt.strip():
                continue

            conn.run(stmt)
            executed += 1

        except Exception as e:
            errors += 1
            # Only print first few errors to avoid spam
            if errors <= 5:
                print(f"\n⚠️  Error in statement {idx}: {str(e)[:100]}")
                if errors == 5:
                    print("   (suppressing further errors...)")

    conn.close()

    print()
    print()
    print(f"✅ Restore complete!")
    print(f"📊 Statistics:")
    print(f"   - Total statements: {len(statements)}")
    print(f"   - Executed: {executed}")
    print(f"   - Errors: {errors}")
    print(f"   - Success rate: {(executed/(executed+errors)*100):.1f}%" if (executed+errors) > 0 else "N/A")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python restore.py <dump_file.sql>")
        print("Example: python restore.py dump_anon_20260217.sql")
        print()
        print("Environment variables required:")
        print("  PG_PASSWORD - Database password")
        print("  PG_HOST     - Database host (default: localhost)")
        print("  PG_DATABASE - Database name (default: dbdev)")
        print("  PG_USER     - Database user (default: userdev)")
        print("  PG_PORT     - Database port (default: 9999)")
        sys.exit(1)

    dump_file = sys.argv[1]
    restore_dump(dump_file)

