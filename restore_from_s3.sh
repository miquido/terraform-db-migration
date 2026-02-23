#!/bin/bash

# Restore PostgreSQL dump from S3
# Downloads dump from S3 and restores it using psql

set -e

# Required environment variables:
# - PG_HOST: Database hostname
# - PG_DATABASE: Database name
# - PG_USER: Database user
# - PGPASSWORD: Database password
# - PG_PORT: Database port (default: 5432)
# - S3_BUCKET: S3 bucket name
# - S3_KEY: S3 object key (path to dump file)
# - AWS_REGION: AWS region (default: eu-central-1)

# Configuration
PG_HOST="${PG_HOST:?PG_HOST is required}"
PG_DATABASE="${PG_DATABASE:?PG_DATABASE is required}"
PG_USER="${PG_USER:?PG_USER is required}"
PG_PORT="${PG_PORT:-5432}"
S3_BUCKET="${S3_BUCKET:?S3_BUCKET is required}"
S3_KEY="${S3_KEY:?S3_KEY is required}"
AWS_REGION="${AWS_REGION:-eu-central-1}"

# Generate filename from S3 key
FILENAME=$(basename "$S3_KEY")
DUMP_PATH="/tmp/${FILENAME}"

echo "========================================"
echo "Restore Database from S3"
echo "========================================"
echo "S3 Source: s3://${S3_BUCKET}/${S3_KEY}"
echo "Target Host: $PG_HOST"
echo "Target Database: $PG_DATABASE"
echo "Target User: $PG_USER"
echo "Target Port: $PG_PORT"
echo "AWS Region: $AWS_REGION"
echo "========================================"
echo ""

# Step 1: Download dump from S3
echo "📥 Step 1: Downloading dump from S3..."
aws s3 cp "s3://${S3_BUCKET}/${S3_KEY}" "$DUMP_PATH" --region "$AWS_REGION"

if [ $? -eq 0 ]; then
    FILE_SIZE=$(du -h "$DUMP_PATH" | cut -f1)
    echo "✅ Download complete: $DUMP_PATH ($FILE_SIZE)"
else
    echo "❌ S3 download failed!"
    exit 1
fi

echo ""

# Step 2: Restore using psql
echo "🔄 Step 2: Restoring database..."
echo "Running psql..."

export PGPASSWORD="${PG_PASSWORD}"

START_TIME=$(date +%s)

psql \
  -h "$PG_HOST" \
  -p "$PG_PORT" \
  -U "$PG_USER" \
  -d "$PG_DATABASE" \
  -f "$DUMP_PATH" \
  -q \
  --echo-errors \
  -v ON_ERROR_STOP=0

EXIT_CODE=$?
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

echo ""

if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ Restore completed successfully in ${DURATION}s"
elif [ $EXIT_CODE -eq 3 ]; then
    echo "⚠️  Restore completed with some errors in ${DURATION}s (often OK)"
else
    echo "❌ Restore failed with exit code $EXIT_CODE"
    rm -f "$DUMP_PATH"
    exit $EXIT_CODE
fi

echo ""

# Step 3: Cleanup
echo "🧹 Step 3: Cleaning up..."
rm -f "$DUMP_PATH"
echo "✅ Cleanup complete"

echo ""
echo "========================================"
echo "✅ Restore process completed!"
echo "========================================"
echo "Source: s3://${S3_BUCKET}/${S3_KEY}"
echo "Target: $PG_DATABASE@$PG_HOST"
echo "Duration: ${DURATION}s"
echo "========================================"

exit 0

