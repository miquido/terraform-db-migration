#!/bin/bash

# Database dump script for ECS task
# Creates PostgreSQL dump and uploads to S3

set -e

# Required environment variables:
# - PG_HOST: Database hostname
# - PG_DATABASE: Database name
# - PG_USER: Database user
# - PG_PASSWORD: Database password (set via PG_PASSWORD)
# - PG_PORT: Database port (default: 5432)
# - S3_BUCKET: S3 bucket name
# - S3_PREFIX: S3 prefix/folder (default: db-dumps/)
# - AWS_REGION: AWS region (default: eu-central-1)

# Configuration
PG_HOST="${PG_HOST:?PG_HOST is required}"
PG_DATABASE="${PG_DATABASE:?PG_DATABASE is required}"
PG_USER="${PG_USER:?PG_USER is required}"
PG_PORT="${PG_PORT:-5432}"
S3_BUCKET="${S3_BUCKET:?S3_BUCKET is required}"
S3_PREFIX="${S3_PREFIX:-db-dumps/}"
AWS_REGION="${AWS_REGION:-eu-central-1}"

# Generate timestamp and filename
TIMESTAMP=$(date -u +"%Y%m%d_%H%M%S")
DUMP_FILENAME="dump_${TIMESTAMP}.sql"
DUMP_PATH="/tmp/${DUMP_FILENAME}"

echo "========================================"
echo "Database Dump to S3"
echo "========================================"
echo "Timestamp: $TIMESTAMP"
echo "Host: $PG_HOST"
echo "Database: $PG_DATABASE"
echo "User: $PG_USER"
echo "Port: $PG_PORT"
echo "S3 Bucket: s3://${S3_BUCKET}/${S3_PREFIX}"
echo "AWS Region: $AWS_REGION"
echo "========================================"
echo ""

# Step 1: Create database dump
echo "📦 Step 1: Creating database dump..."
echo "Running pg_dump..."

export PGPASSWORD="${PG_PASSWORD}"

pg_dump \
  -h "$PG_HOST" \
  -p "$PG_PORT" \
  -U "$PG_USER" \
  -d "$PG_DATABASE" \
  --clean \
  --if-exists \
  --no-owner \
  --no-privileges \
  -f "$DUMP_PATH"

if [ $? -eq 0 ]; then
    FILE_SIZE=$(du -h "$DUMP_PATH" | cut -f1)
    echo "✅ Dump created successfully: $DUMP_PATH ($FILE_SIZE)"
else
    echo "❌ pg_dump failed!"
    exit 1
fi

echo ""

# Step 2: Upload to S3
echo "📤 Step 2: Uploading to S3..."
S3_KEY="${S3_PREFIX}${DUMP_FILENAME}"
S3_URI="s3://${S3_BUCKET}/${S3_KEY}"

aws s3 cp "$DUMP_PATH" "$S3_URI" \
  --region "$AWS_REGION" \
  --metadata "database=$PG_DATABASE,timestamp=$TIMESTAMP"

if [ $? -eq 0 ]; then
    echo "✅ Upload successful: $S3_URI"
else
    echo "❌ S3 upload failed!"
    exit 1
fi

echo ""

# Step 3: Cleanup
echo "🧹 Step 3: Cleaning up..."
rm -f "$DUMP_PATH"
echo "✅ Cleanup complete"

echo ""
echo "========================================"
echo "✅ Dump completed successfully!"
echo "========================================"
echo "File: $DUMP_FILENAME"
echo "Size: $FILE_SIZE"
echo "S3 Location: $S3_URI"
echo "========================================"

exit 0

