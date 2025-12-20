#!/bin/bash
set -e

echo "Running update..."
python3 update.py

echo "Starting bot..."
python3 -m bot
