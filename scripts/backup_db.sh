#!/bin/bash
set -e

# --- Configuration ---
DATA_DIR="./data"
DB_FILE="$DATA_DIR/rebalancer.db"
BACKUP_DIR="$DATA_DIR/backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="$BACKUP_DIR/rebalancer_backup_$TIMESTAMP.db.gz"

# --- Main Script ---
echo "Starting database backup..."

# 1. Check if the database file exists
if [ ! -f "$DB_FILE" ]; then
    echo "Error: Database file not found at $DB_FILE"
    exit 1
fi

# 2. Create the backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"

# 3. Create the compressed backup
echo "Creating backup of $DB_FILE to $BACKUP_FILE"
# Use sqlite3 .backup command for a safe copy, then compress
sqlite3 "$DB_FILE" ".backup '$BACKUP_DIR/rebalancer.db.tmp'"
gzip -c "$BACKUP_DIR/rebalancer.db.tmp" > "$BACKUP_FILE"
rm "$BACKUP_DIR/rebalancer.db.tmp"

# 4. Prune old backups (optional, keep last 10)
echo "Pruning old backups (keeping the last 10)..."
ls -1t "$BACKUP_DIR"/*.gz | tail -n +11 | xargs -r rm

echo "Backup complete!"
echo "Backup saved to: $BACKUP_FILE"
