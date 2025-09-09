#!/bin/bash
#
# Creates a compressed, timestamped backup of the application's SQLite database.
#
# This script performs the following actions:
#   1. Verifies that the source database file exists.
#   2. Creates a backup directory if it does not already exist.
#   3. Uses the SQLite .backup command for a safe, online backup.
#   4. Compresses the backup file using gzip.
#   5. Prunes old backups, keeping only the 10 most recent ones.
#
# Usage:
#   ./scripts/backup_db.sh
#
set -e

# --- Configuration ---
DATA_DIR="./data"
DB_FILE="$DATA_DIR/rebalancer.db"
BACKUP_DIR="$DATA_DIR/backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="$BACKUP_DIR/rebalancer_backup_$TIMESTAMP.db.gz"

# --- Main Script ---
echo "Starting database backup..."

# 1. Check if the database file exists.
if [ ! -f "$DB_FILE" ]; then
    echo "Error: Database file not found at $DB_FILE"
    exit 1
fi

# 2. Create the backup directory if it doesn't exist.
mkdir -p "$BACKUP_DIR"
echo "Backup directory is $BACKUP_DIR"

# 3. Create the compressed backup.
echo "Creating backup of $DB_FILE to $BACKUP_FILE"
# Use sqlite3 .backup command for a safe copy to a temporary file.
sqlite3 "$DB_FILE" ".backup '$BACKUP_DIR/rebalancer.db.tmp'"
# Compress the temporary file into the final gzipped backup file.
gzip -c "$BACKUP_DIR/rebalancer.db.tmp" > "$BACKUP_FILE"
# Remove the temporary uncompressed backup.
rm "$BACKUP_DIR/rebalancer.db.tmp"

# 4. Prune old backups, keeping the last 10.
echo "Pruning old backups..."
# List all .gz files by time, skip the first 10, and delete the rest.
ls -1t "$BACKUP_DIR"/*.gz | tail -n +11 | xargs -r rm

echo "Backup complete!"
echo "Backup saved to: $BACKUP_FILE"
