#!/bin/bash
set -e

# --- Configuration ---
CONTAINER_NAME="rebalancer-bot"
CONFIG_FILE_PATH="/data/config.json"

# --- Input Validation ---
if [ -z "$1" ]; then
    echo "Usage: $0 <new_password>"
    echo "Error: Please provide a new password as the first argument."
    exit 1
fi
NEW_PASSWORD=$1

# --- Main Script ---
echo "Attempting to reset admin password for container '$CONTAINER_NAME'..."

# 1. Check if the container is running
if ! docker ps --filter "name=^/$CONTAINER_NAME$" --format "{{.Names}}" | grep -q "^$CONTAINER_NAME$"; then
    echo "Error: Container '$CONTAINER_NAME' is not running."
    echo "Please start the container with 'docker-compose up -d' before running this script."
    exit 1
fi

# 2. Execute the password reset script inside the container
echo "Container found. Executing password reset..."

# This is a Python one-liner that will be executed inside the container.
# It reads the config, hashes the new password, updates the config, and saves it.
docker exec "$CONTAINER_NAME" python -c "
import json
import bcrypt

config_path = '$CONFIG_FILE_PATH'
new_password = '$NEW_PASSWORD'

try:
    with open(config_path, 'r') as f:
        config = json.load(f)

    print('Hashing new password...')
    hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())

    # The hash is bytes, needs to be decoded for JSON serialization
    config['password_hash'] = hashed_password.decode('latin1')

    with open(config_path, 'w') as f:
        json.dump(config, f, indent=4)

    print('Password has been successfully updated in', config_path)

except FileNotFoundError:
    print('Error: Config file not found at', config_path)
    exit(1)
except Exception as e:
    print('An unexpected error occurred:', e)
    exit(1)
"

echo "Password reset script finished."
echo "You can now log in with the username 'admin' and your new password."
