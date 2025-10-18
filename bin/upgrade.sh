#!/bin/bash
set -e

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
    echo "HEAD has changed, running docker compose up..."
    docker compose up -d --build --remove-orphans
fi
