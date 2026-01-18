#!/bin/bash
echo "=== Starting Orchestrator API ==="
cd /app
exec python backend/run.py
