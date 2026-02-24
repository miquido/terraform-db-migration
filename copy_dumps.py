#!/usr/bin/env python3
"""
Lambda function to copy anonymized SQL dumps to external S3 bucket
Triggered by S3 events when anonymized dumps are created
"""

import boto3
import os
from urllib.parse import unquote_plus
from datetime import datetime

# Initialize S3 client
s3_client = boto3.client('s3')


def lambda_handler(event, context):
    """
    AWS Lambda handler triggered by S3 upload events for anonymized dumps

    Expected S3 event structure:
    {
      "Records": [{
        "s3": {
          "bucket": {"name": "source-bucket"},
          "object": {"key": "anonymized/dump_20260219_135951.sql"}
        }
      }]
    }

    Environment variables:
    - DESTINATION_BUCKET: Target S3 bucket name (on different AWS account)
    - DESTINATION_PREFIX: S3 prefix for copied dumps (optional, default: dumps/)
    """

    print("🚀 Lambda invoked - processing S3 event for dump copy")

    try:
        # Parse S3 event
        record = event['Records'][0]
        source_bucket = record['s3']['bucket']['name']
        source_key = unquote_plus(record['s3']['object']['key'])

        print(f"📦 Source: s3://{source_bucket}/{source_key}")

        # Get configuration from environment
        destination_bucket = os.environ.get('DESTINATION_BUCKET')
        if not destination_bucket:
            raise ValueError("DESTINATION_BUCKET environment variable is required")

        destination_prefix = os.environ.get('DESTINATION_PREFIX', 'dumps/')

        # Generate destination key
        filename = os.path.basename(source_key)
        destination_key = f"{destination_prefix}{filename}"

        print(f"📋 Destination: s3://{destination_bucket}/{destination_key}")

        # Get source object metadata
        source_metadata = s3_client.head_object(
            Bucket=source_bucket,
            Key=source_key
        )

        source_size_mb = source_metadata['ContentLength'] / (1024 * 1024)
        print(f"📊 File size: {source_size_mb:.2f} MB")

        # Copy object to destination bucket (cross-account)
        print(f"📤 Starting copy operation...")
        start_time = datetime.now()

        copy_source = {
            'Bucket': source_bucket,
            'Key': source_key
        }

        # Use copy_object for cross-account copy
        s3_client.copy_object(
            CopySource=copy_source,
            Bucket=destination_bucket,
            Key=destination_key,
            MetadataDirective='COPY',
            ServerSideEncryption='AES256'
        )

        duration = (datetime.now() - start_time).total_seconds()

        print(f"✅ Copy complete!")
        print(f"   Duration: {duration:.2f}s")
        print(f"   Speed: {source_size_mb/duration:.2f} MB/s")

        return {
            'statusCode': 200,
            'body': {
                'message': 'Dump copied successfully',
                'source': f"s3://{source_bucket}/{source_key}",
                'destination': f"s3://{destination_bucket}/{destination_key}",
                'size_mb': round(source_size_mb, 2),
                'duration_seconds': round(duration, 2)
            }
        }

    except Exception as e:
        error_message = f"❌ Error copying dump: {str(e)}"
        print(error_message)

        return {
            'statusCode': 500,
            'body': {
                'error': str(e),
                'message': 'Failed to copy dump'
            }
        }


if __name__ == "__main__":
    # Test locally with sample event
    test_event = {
        'Records': [{
            's3': {
                'bucket': {'name': 'test-source-bucket'},
                'object': {'key': 'anonymized/dump_20260219_135951.sql'}
            }
        }]
    }

    # Set test environment
    os.environ['DESTINATION_BUCKET'] = 'test-destination-bucket'
    os.environ['DESTINATION_PREFIX'] = 'dumps/'

    result = lambda_handler(test_event, None)
    print(f"\nResult: {result}")

