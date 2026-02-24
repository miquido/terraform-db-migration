#!/usr/bin/env python3
"""
Fast SQL dump anonymizer - handles COPY blocks with TAB separator
AWS Lambda handler for S3-triggered anonymization
"""

import re
import sys
import boto3
import os
from datetime import datetime
from typing import List, Optional, Dict, Callable
from urllib.parse import unquote_plus

# Initialize S3 client
s3_client = boto3.client('s3')

class DumpAnonymizer:
    def __init__(self, anonymization_rules: Dict[str, Dict[str, Callable]] = None):
        """
        Initialize anonymizer with custom rules

        Args:
            anonymization_rules: Dictionary mapping table names to column anonymization rules
                                Format: { 'table_name': { 'column_name': anonymization_function } }
        """
        # Use provided rules or empty dict
        self.anonymization_rules = anonymization_rules or {}

        self.current_table = None
        self.copy_columns = []
        self.column_indices = {}
        self.in_copy_block = False
        self.copy_line_number = 0  # Counter for lines within COPY block

    def parse_copy_header(self, line: str) -> tuple[Optional[str], List[str]]:
        """
        Parses: COPY "user".users_details (id, email, full_name) FROM stdin;
        Returns: ('users_details', ['id', 'email', 'full_name'])
        """
        match = re.match(r'COPY\s+(?:"?\w+"?\.)?(\w+)\s+\((.*?)\)\s+FROM\s+stdin;', line)
        if match:
            table, columns = match.groups()
            column_list = [col.strip() for col in columns.split(',')]
            return table, column_list
        return None, []

    def anonymize_copy_line(self, line: str) -> str:
        """
        Anonymizes COPY line with TAB separator:
        uuid\tOdette Bowers\tfadowex@mailinator.com\t...
        """
        if not self.current_table or self.current_table not in self.anonymization_rules:
            return line

        # Split by TAB
        values = line.rstrip('\n').split('\t')

        if len(values) != len(self.copy_columns):
            return line

        rules = self.anonymization_rules[self.current_table]

        # Anonymize values according to rules, passing line number
        for col_name, anonymize_func in rules.items():
            if col_name in self.column_indices:
                idx = self.column_indices[col_name]
                values[idx] = anonymize_func(values[idx], self.copy_line_number)

        return '\t'.join(values) + '\n'

    def process_line(self, line: str) -> str:
        """Processes single dump line"""

        # COPY block starts
        if line.startswith('COPY '):
            self.current_table, self.copy_columns = self.parse_copy_header(line)
            self.in_copy_block = True
            self.copy_line_number = 0  # Reset counter for new COPY block

            # Create column_name -> index map
            self.column_indices = {col: i for i, col in enumerate(self.copy_columns)}

            # Debug log
            if self.current_table in self.anonymization_rules:
                print(f"   📝 Found table '{self.current_table}' - will anonymize: {list(self.anonymization_rules[self.current_table].keys())}")

            return line

        # End of COPY block
        if line.strip() == '\\.':
            self.in_copy_block = False
            self.current_table = None
            self.copy_columns = []
            self.column_indices = {}
            self.copy_line_number = 0
            return line

        # We're in COPY block - anonymize
        if self.in_copy_block and self.current_table:
            self.copy_line_number += 1  # Increment line counter
            return self.anonymize_copy_line(line)

        return line

    def anonymize_file(self, input_file: str, output_file: str):
        """Processes entire SQL file"""
        print(f"🔒 Starting anonymization: {input_file} → {output_file}")
        start_time = datetime.now()

        lines_processed = 0
        lines_anonymized = 0

        with open(input_file, 'r', encoding='utf-8') as infile, \
             open(output_file, 'w', encoding='utf-8') as outfile:

            for line in infile:
                lines_processed += 1

                if lines_processed % 50000 == 0:
                    print(f"   Processed {lines_processed:,} lines...")

                original_line = line
                processed_line = self.process_line(line)

                if processed_line != original_line:
                    lines_anonymized += 1

                outfile.write(processed_line)

        duration = (datetime.now() - start_time).total_seconds()

        print(f"✅ Anonymization complete!")
        print(f"   Lines processed: {lines_processed:,}")
        print(f"   Lines anonymized: {lines_anonymized:,}")
        print(f"   Duration: {duration:.2f}s")
        print(f"   Speed: {lines_processed/duration:,.0f} lines/sec")

        return {
            'lines_processed': lines_processed,
            'lines_anonymized': lines_anonymized,
            'duration': duration
        }


def load_anonymization_rules(rules_file: str) -> Dict[str, Dict[str, Callable]]:
    """
    Load anonymization rules from a Python file

    Args:
        rules_file: Path to Python file containing ANONYMIZATION_RULES

    Returns:
        Dictionary with anonymization rules
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location("rules_module", rules_file)
    if spec is None or spec.loader is None:
        raise ValueError(f"Could not load rules from {rules_file}")

    rules_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rules_module)

    if not hasattr(rules_module, 'ANONYMIZATION_RULES'):
        raise ValueError(f"Rules file {rules_file} must contain ANONYMIZATION_RULES variable")

    return rules_module.ANONYMIZATION_RULES


def lambda_handler(event, context):
    """
    AWS Lambda handler triggered by S3 upload events

    Expected S3 event structure:
    {
      "Records": [{
        "s3": {
          "bucket": {"name": "my-bucket"},
          "object": {"key": "dumps/dump_20260218_135951.sql"}
        }
      }]
    }

    Environment variables:
    - OUTPUT_PREFIX: S3 prefix for anonymized dumps (default: anonymized/)
    """

    print("🚀 Lambda invoked - processing S3 event")

    try:
        # Parse S3 event
        record = event['Records'][0]
        bucket_name = record['s3']['bucket']['name']
        object_key = unquote_plus(record['s3']['object']['key'])

        print(f"📦 Source: s3://{bucket_name}/{object_key}")

        # Load anonymization rules from local file (packaged with Lambda)
        anonymization_rules = {}
        rules_file = '/var/task/anonymization_rules.py'

        if os.path.exists(rules_file):
            print(f"📋 Loading anonymization rules from {rules_file}")
            try:
                anonymization_rules = load_anonymization_rules(rules_file)
                print(f"   Loaded rules for tables: {list(anonymization_rules.keys())}")
            except Exception as e:
                print(f"⚠️  Failed to load rules: {e}")
        else:
            print("⚠️  No anonymization rules found, dump will be copied without anonymization")

        # Get output prefix from environment or use default
        output_prefix = os.environ.get('OUTPUT_PREFIX', 'anonymized/')

        # Generate output key
        filename = os.path.basename(object_key)
        output_key = f"{output_prefix}{filename}"

        # Use /tmp directory in Lambda
        input_path = f"/tmp/input_{filename}"
        output_path = f"/tmp/output_{filename}"

        print(f"⬇️  Downloading from S3...")
        s3_client.download_file(bucket_name, object_key, input_path)

        file_size_mb = os.path.getsize(input_path) / (1024 * 1024)
        print(f"   Downloaded: {file_size_mb:.2f} MB")

        # Anonymize
        print(f"🔒 Starting anonymization...")
        anonymizer = DumpAnonymizer(anonymization_rules)
        stats = anonymizer.anonymize_file(input_path, output_path)

        output_size_mb = os.path.getsize(output_path) / (1024 * 1024)
        print(f"   Output size: {output_size_mb:.2f} MB")

        # Upload anonymized dump
        print(f"⬆️  Uploading to s3://{bucket_name}/{output_key}")
        s3_client.upload_file(
            output_path,
            bucket_name,
            output_key,
            ExtraArgs={
                'Metadata': {
                    'source_key': object_key,
                    'anonymized': 'true',
                    'lines_processed': str(stats['lines_processed']),
                    'lines_anonymized': str(stats['lines_anonymized']),
                    'processing_time': str(stats['duration'])
                }
            }
        )

        print(f"✅ Upload complete!")

        # Cleanup
        os.remove(input_path)
        os.remove(output_path)
        print(f"🧹 Cleanup complete")

        return {
            'statusCode': 200,
            'body': {
                'message': 'Anonymization successful',
                'source': f"s3://{bucket_name}/{object_key}",
                'output': f"s3://{bucket_name}/{output_key}",
                'stats': stats
            }
        }

    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()

        return {
            'statusCode': 500,
            'body': {
                'error': str(e)
            }
        }


def main():
    """CLI mode for local testing"""
    if len(sys.argv) < 3:
        print("Usage: ./anonimize.py <input.sql> <output.sql> [rules.py]")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2]

    # Load rules if provided
    anonymization_rules = {}
    if len(sys.argv) > 3:
        rules_file = sys.argv[3]
        print(f"📋 Loading anonymization rules from {rules_file}")
        anonymization_rules = load_anonymization_rules(rules_file)
        print(f"   Loaded rules for tables: {list(anonymization_rules.keys())}")

    anonymizer = DumpAnonymizer(anonymization_rules)
    anonymizer.anonymize_file(input_file, output_file)

if __name__ == '__main__':
    main()
