import sys
import os

# Add parent to path
sys.path.insert(0, "/app")

# Now import and run
from backend.main import app

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
