# Use official PostgreSQL image (contains pg_dump)
FROM postgres:16

# Install AWS CLI for S3 upload
RUN apt-get update && \
    apt-get install -y awscli && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy the dump script
COPY dump_and_upload.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/dump_and_upload.sh

# Set entrypoint
ENTRYPOINT ["/usr/local/bin/dump_and_upload.sh"]
