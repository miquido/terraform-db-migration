import re
import sys
import os

# Configuration
ANONYMIZATION_RULES = {
    'email': lambda val, row_id: f"user_{row_id}@example.com",
    'phone': lambda val, row_id: "+48000000000",
    'first_name': lambda val, row_id: f"User",
    'last_name': lambda val, row_id: f"{row_id}",
    'name': lambda val, row_id: f"User {row_id}",
    'address': lambda val, row_id: "Anonymous Street 123",
    'street': lambda val, row_id: "Anonymous Street",
    'city': lambda val, row_id: "Warsaw",
    'postal_code': lambda val, row_id: "00-000",
}


def extract_insert_parts(line):
    """Extract table name, columns, and values from INSERT statement"""
    # Pattern: INSERT INTO "schema"."table" (col1, col2, ...) VALUES (val1, val2, ...);
    match = re.match(
        r'INSERT INTO "([^"]+)"\.\"([^"]+)\" \(([^)]+)\) VALUES \((.+)\);',
        line.strip()
    )
    if not match:
        return None

    schema = match.group(1)
    table = match.group(2)
    columns_str = match.group(3)
    values_str = match.group(4)

    # Parse column names
    columns = [col.strip().strip('"') for col in columns_str.split(',')]

    return {
        'schema': schema,
        'table': table,
        'columns': columns,
        'values_str': values_str,
    }


def parse_values(values_str):
    """Parse SQL values into list - simple parser for common types"""
    values = []
    current = ""
    in_string = False
    escape_next = False

    for char in values_str:
        if escape_next:
            current += char
            escape_next = False
            continue

        if char == '\\':
            escape_next = True
            current += char
            continue

        if char == "'" and not escape_next:
            in_string = not in_string
            current += char
            continue

        if char == ',' and not in_string:
            values.append(current.strip())
            current = ""
            continue

        current += char

    if current:
        values.append(current.strip())

    return values


def anonymize_value(column_name, value, row_id):
    """Anonymize a single value based on column name"""
    # Check if column should be anonymized
    if column_name not in ANONYMIZATION_RULES:
        return value

    # Don't anonymize NULL values
    if value == 'NULL':
        return value

    # Extract the actual string value (remove quotes)
    if value.startswith("'") and value.endswith("'"):
        # Get anonymized value
        anon_func = ANONYMIZATION_RULES[column_name]
        anon_val = anon_func(value, row_id)
        return f"'{anon_val}'"

    return value


def anonymize_insert(line):
    """Anonymize a single INSERT statement"""
    parts = extract_insert_parts(line)
    if not parts:
        return line

    values = parse_values(parts['values_str'])

    # Try to find ID column for consistent anonymization
    row_id = "unknown"
    if 'id' in parts['columns']:
        id_idx = parts['columns'].index('id')
        if id_idx < len(values):
            row_id = values[id_idx]

    # Anonymize each value based on column name
    anonymized_values = []
    for col, val in zip(parts['columns'], values):
        anon_val = anonymize_value(col, val, row_id)
        anonymized_values.append(anon_val)

    # Reconstruct INSERT statement
    columns_str = ", ".join(parts['columns'])
    values_str = ", ".join(anonymized_values)

    return f'INSERT INTO "{parts["schema"]}"."{parts["table"]}" ({columns_str}) VALUES ({values_str});\n'


def anonymize_dump(input_file, output_file):
    """Anonymize entire SQL dump file"""
    print(f"🔒 Starting anonymization...")
    print(f"Input: {input_file}")
    print(f"Output: {output_file}")
    print()

    total_lines = 0
    anonymized_lines = 0

    with open(input_file, 'r', encoding='utf-8') as infile:
        with open(output_file, 'w', encoding='utf-8') as outfile:
            for line in infile:
                total_lines += 1

                if line.strip().startswith('INSERT INTO'):
                    anonymized_line = anonymize_insert(line)
                    outfile.write(anonymized_line)
                    anonymized_lines += 1

                    if anonymized_lines % 1000 == 0:
                        print(f"Anonymized {anonymized_lines} INSERT statements...", end='\r', flush=True)
                else:
                    outfile.write(line)

    input_size = os.path.getsize(input_file) / (1024*1024)
    output_size = os.path.getsize(output_file) / (1024*1024)

    print()
    print(f"✅ Anonymization complete!")
    print(f"📊 Statistics:")
    print(f"   - Total lines: {total_lines}")
    print(f"   - Anonymized INSERTs: {anonymized_lines}")
    print(f"   - Input size: {input_size:.2f} MB")
    print(f"   - Output size: {output_size:.2f} MB")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python anonymizer.py <input_dump.sql> [output_dump.sql]")
        print("Example: python anonymizer.py dump_raw_20260217.sql dump_anon_20260217.sql")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else input_file.replace('.sql', '_anonymized.sql')

    if not os.path.exists(input_file):
        print(f"❌ Error: File {input_file} not found!")
        sys.exit(1)

    anonymize_dump(input_file, output_file)

