# Use official PostgreSQL image (contains pg_dump and psql)
FROM postgres:16

# Install AWS CLI for S3 upload
RUN apt-get update && \
    apt-get install -y awscli && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy scripts
COPY dump_and_upload.sh /usr/local/bin/
COPY restore_from_s3.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/dump_and_upload.sh /usr/local/bin/restore_from_s3.sh

# Default command: dump (can be overridden to "restore")
CMD ["/usr/local/bin/dump_and_upload.sh"]
