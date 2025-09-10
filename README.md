## Genesis - Quick Start

Run Genesis either via CLI or with the web app.

### 1) CLI (single terminal)

```powershell
# From project root
cd .

# Activate virtual environment (Windows PowerShell)
./.venv/Scripts/Activate.ps1

# First time only
pip install -r requirements.txt

# Start CLI
python .\main.py
```

Tips:
- Type to chat.
- `/upload <path>` adds a file to your message.
- `/help` shows commands. `/quit` exits.

### 2) Web App (backend + frontend)

Open two terminals.

Terminal A — Backend (FastAPI):
```powershell
cd .
./.venv/Scripts/Activate.ps1
pip install -r requirements.txt  # first time only
cd backend
python .\start.py  # starts FastAPI at http://localhost:8000
# (Alt) uvicorn app.main:app --reload --port 8000
```

Terminal B — Frontend (Next.js):
```powershell
cd ..\frontend
npm install                  # first time only
"NEXT_PUBLIC_API_BASE=http://localhost:8000" | Out-File -Encoding utf8 -Append .env.local
npm run dev                  # opens http://localhost:3000
```

### Notes
- Always activate the venv before Python commands: `./.venv/Scripts/Activate.ps1`.
- Local folders `inputs/`, `outputs/`, and `.staging_uploads/` stay on your machine (git-ignored).
- If you change the backend port, update `NEXT_PUBLIC_API_BASE` in `frontend/.env.local`.
