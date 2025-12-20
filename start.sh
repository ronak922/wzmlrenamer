#!/usr/bin/env bash
set -e

# Run update script first
python3 update.py

# Start the bot module
exec python3 -m bot
