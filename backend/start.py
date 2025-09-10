"""
Quick start script for Genesis backend.
"""
import subprocess
import sys
import os

def main():
    """Start the FastAPI backend server."""
    # Ensure we're in the backend directory
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(backend_dir)
    
    # Start uvicorn
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "app.main:app",
        "--reload",
        "--host", "0.0.0.0",
        "--port", "8000"
    ]
    
    print("Starting Genesis Backend...")
    print(f"API will be available at: http://localhost:8000")
    print(f"API documentation at: http://localhost:8000/docs")
    print("\nPress Ctrl+C to stop the server")
    
    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        print("\nShutting down...")

if __name__ == "__main__":
    main()
