#!/bin/bash
set -e

# Parse command line arguments
SKIP_BACKUP=false
while [[ $# -gt 0 ]]; do
    case $1 in
        --no-backup)
            SKIP_BACKUP=true
            shift
            ;;
        *)
            echo "Unknown option: $1" >&2
            echo "Usage: $0 [--no-backup]" >&2
            exit 1
            ;;
    esac
done

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
cd $SCRIPT_DIR/..

# Store current HEAD before fetching
OLD_HEAD=$(git rev-parse HEAD)

git fetch
git reset --hard origin/main

# Get new HEAD
NEW_HEAD=$(git rev-parse HEAD)

# Only run docker compose up if HEAD has changed
if [ "$OLD_HEAD" != "$NEW_HEAD" ]; then
    if [ "$SKIP_BACKUP" = false ]; then
        ./bin/backup.sh
    fi
    echo "HEAD has changed, running docker compose up..."
    docker compose pull
    docker compose up -d --build --remove-orphans
fi
