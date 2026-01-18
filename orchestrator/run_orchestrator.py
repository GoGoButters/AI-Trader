"""
Orchestrator Application Launcher
Properly loads the backend package with relative imports
"""

import sys
import os

# Debug: print current directory and files
print("=== DEBUG: Startup ===")
print(f"Current directory: {os.getcwd()}")
print(f"Files in /app: {os.listdir('/app')}")
print(f"config.yml exists: {os.path.exists('/app/config.yml')}")
if os.path.exists("/app/config.yml"):
    print(f"config.yml size: {os.path.getsize('/app/config.yml')} bytes")

sys.path.insert(0, "/app")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.main:app",  # Import as module
        host="0.0.0.0",
        port=8080,
        reload=False,
    )
