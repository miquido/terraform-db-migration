import os
import pg8000.native
from datetime import datetime
import json

# Configuration from environment variables
PG_HOST = os.environ.get("PG_HOST", "localhost")
PG_DATABASE = os.environ.get("PG_DATABASE", "dbdev")
PG_USER = os.environ.get("PG_USER", "userdev")
PG_PORT = int(os.environ.get("PG_PORT", "9999"))
EXCLUDED_TABLES = os.environ.get("EXCLUDED_TABLES", "audit_logs,sessions").split(",")
OUTPUT_FILE = os.environ.get("OUTPUT_FILE", None)  # Optional: specify output filename


def format_value(val):
    """Format Python values to SQL literals"""
    if val is None:
        return "NULL"
    if isinstance(val, str):
        return "'" + val.replace("'", "''").replace("\\", "\\\\") + "'"
    if isinstance(val, bool):
        return "TRUE" if val else "FALSE"
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, dict) or isinstance(val, list):
        # Handle JSON/JSONB
        return "'" + json.dumps(val).replace("'", "''") + "'"
    if isinstance(val, bytes):
        # Handle bytea
        return "'\\x" + val.hex() + "'"
    if isinstance(val, datetime):
        return "'" + val.isoformat() + "'"
    # Fallback: convert to string
    return "'" + str(val).replace("'", "''") + "'"


def get_sequences_for_table(conn, schema, table):
    """Get all sequences used by a table (typically for SERIAL columns)"""
    sequences = []
    result = conn.run(f"""
        SELECT 
            a.attname as column_name,
            pg_get_serial_sequence('"{schema}"."{table}"', a.attname) as sequence_name
        FROM pg_attribute a
        JOIN pg_class c ON a.attrelid = c.oid
        JOIN pg_namespace n ON c.relnamespace = n.oid
        WHERE n.nspname = '{schema}' 
        AND c.relname = '{table}'
        AND a.attnum > 0
        AND NOT a.attisdropped
        AND pg_get_serial_sequence('"{schema}"."{table}"', a.attname) IS NOT NULL
    """)
    for row in result:
        sequences.append({
            'column': row[0],
            'sequence': row[1]
        })
    return sequences


def generate_dump():
    """Generate database dump without anonymization"""
    print(f"🔄 Starting database dump...")
    print(f"Host: {PG_HOST}")
    print(f"Database: {PG_DATABASE}")
    print(f"User: {PG_USER}")
    print(f"Excluded tables: {', '.join(EXCLUDED_TABLES)}")
    print()

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

    # Get all user schemas (excluding system schemas)
    schemas = [
        row[0] for row in conn.run(
            "SELECT schema_name FROM information_schema.schemata WHERE schema_name NOT IN ('pg_catalog', 'information_schema') ORDER BY schema_name"
        )
    ]

    sql_lines = []

    # 0. Disable foreign key checks for the session
    sql_lines.append("-- Disable foreign key checks and triggers\n")
    sql_lines.append("SET session_replication_role = 'replica';\n\n")

    # 1. TRUNCATE all tables (CASCADE handles foreign keys)
    sql_lines.append("-- Truncate all tables\n")
    all_tables = []
    for schema in schemas:
        tables = [
            row[0] for row in conn.run(
                f'SELECT tablename FROM pg_tables WHERE schemaname = \'{schema}\' ORDER BY tablename'
            )
        ]
        for table in tables:
            if table in EXCLUDED_TABLES:
                continue
            all_tables.append((schema, table))

    # TRUNCATE CASCADE clears data and handles foreign keys
    for schema, table in all_tables:
        sql_lines.append(f'TRUNCATE TABLE "{schema}"."{table}" CASCADE;\n')

    sql_lines.append("\n")

    # 2. INSERTs
    sql_lines.append("-- Insert data\n")
    sequences_to_fix = []

    total_rows = 0
    for idx, (schema, table) in enumerate(all_tables, 1):
        print(f"Processing [{idx}/{len(all_tables)}] {schema}.{table}...", end=" ", flush=True)

        # Get column names
        columns = [
            row[0] for row in conn.run(
                f'SELECT column_name FROM information_schema.columns WHERE table_schema = \'{schema}\' AND table_name = \'{table}\' ORDER BY ordinal_position'
            )
        ]

        # Get all rows (NO ANONYMIZATION)
        rows = conn.run(f'SELECT * FROM "{schema}"."{table}"')
        row_count = len(rows) if rows else 0
        total_rows += row_count
        print(f"{row_count} rows")

        if rows:
            for row in rows:
                values = ", ".join(format_value(v) for v in row)
                sql_lines.append(
                    f'INSERT INTO "{schema}"."{table}" ({", ".join(columns)}) VALUES ({values});\n'
                )

            # Check if table has sequences
            seqs = get_sequences_for_table(conn, schema, table)
            for seq_info in seqs:
                sequences_to_fix.append({
                    'schema': schema,
                    'table': table,
                    'column': seq_info['column'],
                    'sequence': seq_info['sequence']
                })

    sql_lines.append("\n")

    # 3. Fix sequences
    if sequences_to_fix:
        sql_lines.append("-- Reset sequences to max values\n")
        for seq in sequences_to_fix:
            sql_lines.append(
                f"SELECT setval('{seq['sequence']}', "
                f"COALESCE((SELECT MAX({seq['column']}) FROM \"{seq['schema']}\".\"{seq['table']}\"), 1), "
                f"true);\n"
            )
        sql_lines.append("\n")

    # 4. Re-enable foreign key checks
    sql_lines.append("-- Re-enable foreign key checks and triggers\n")
    sql_lines.append("SET session_replication_role = 'default';\n")

    # Prepare dump content
    dump_content = "".join(sql_lines)

    # Determine filename
    if OUTPUT_FILE:
        dump_filename = OUTPUT_FILE
    else:
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        dump_filename = f"dump_raw_{timestamp}.sql"

    # Save to local file
    with open(dump_filename, "w", encoding="utf-8") as f:
        f.write(dump_content)

    file_size = os.path.getsize(dump_filename) / (1024*1024)

    print()
    print(f"✅ Dump saved to {dump_filename}")
    print(f"📊 Statistics:")
    print(f"   - Schemas: {len(schemas)}")
    print(f"   - Tables: {len(all_tables)}")
    print(f"   - Total rows: {total_rows}")
    print(f"   - Sequences: {len(sequences_to_fix)}")
    print(f"   - File size: {file_size:.2f} MB")
    print(f"   - Anonymized: No (use anonymizer.py to anonymize)")

    return dump_filename, file_size


if __name__ == "__main__":
    generate_dump()

