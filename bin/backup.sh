#!/bin/bash
set -e
# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color


# Get the script directory and change to project root
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
cd "$SCRIPT_DIR/.."

# Configuration (can be overridden by environment variables)
DUMPS_DIR="${DUMPS_DIR:-dumps}"
DB_NAME="${DB_NAME:-tasks_processing}"
DB_USER="${DB_USER:-postgres}"
MAX_BACKUPS="${MAX_BACKUPS:-5}"

if [[ $(command -v tar) == "" ]]; then
    echo "Error: 'tar' command not found. Please install it to proceed." >&2
    exit 1
fi

# Create dumps directory if it doesn't exist
mkdir -p "$DUMPS_DIR"

# Generate timestamp for backup filename
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
DUMP_FILE="$DUMPS_DIR/backup_${TIMESTAMP}.sql"
ARCHIVE_FILE="${DUMP_FILE}.tar.gz"

echo -e "${YELLOW}Creating database backup...${NC}"

# Perform pg_dump from the container
docker compose exec -T db pg_dump -U "$DB_USER" "$DB_NAME" > "$DUMP_FILE"

if [ ! -s "$DUMP_FILE" ]; then
    echo "Error: Dump file is empty" >&2
    rm -f "$DUMP_FILE"
    exit 1
fi

echo -e "${GREEN}Backup created: $DUMP_FILE${NC}"

# Compress the dump
echo -e "${YELLOW}Compressing backup...${NC}"
tar -czf "$ARCHIVE_FILE" -C "$DUMPS_DIR" "$(basename "$DUMP_FILE")"
rm "$DUMP_FILE"

echo -e "${GREEN}Compressed backup: $ARCHIVE_FILE${NC}"

# Remove old backups, keeping only the most recent ones
echo -e "${YELLOW}Cleaning up old backups...${NC}"
BACKUP_COUNT=$(ls -1 "$DUMPS_DIR"/backup_*.tar.gz 2>/dev/null | wc -l)

if [ "$BACKUP_COUNT" -gt "$MAX_BACKUPS" ]; then
    BACKUPS_TO_DELETE=$((BACKUP_COUNT - MAX_BACKUPS))
    ls -1t "$DUMPS_DIR"/backup_*.tar.gz | tail -n "$BACKUPS_TO_DELETE" | xargs rm -f
    echo -e "${YELLOW}Removed $BACKUPS_TO_DELETE old backup(s)${NC}"
fi

# Display current backups
echo ""
echo -e "${YELLOW}Current backups (most recent first):${NC}"
ls -lht "$DUMPS_DIR"/backup_*.tar.gz 2>/dev/null || echo -e "${YELLOW}No backups found${NC}"

echo ""
echo -e "${GREEN}Backup completed successfully!${NC}"
