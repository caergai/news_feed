#!/bin/bash
# Navigate to the script's directory
cd "$(dirname "$0")"
echo "Starting Accelerate News Server..."
python3 main.py daemon
