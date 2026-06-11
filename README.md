# PrivateMailAI

Privacy-first local AI email assistant. Every byte of email data stays on your machine.

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- Docker (for Ollama)

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Ollama

```bash
docker compose up -d
./scripts/setup.sh  # Pull required models
```

## Architecture

- **Backend**: FastAPI + SQLAlchemy (async) + Alembic
- **Frontend**: React + TypeScript + Vite + Tailwind + shadcn/ui
- **AI**: Ollama (local LLM inference)
- **Database**: SQLite (aiosqlite) + ChromaDB (vector store)
- **Privacy**: All data stays local. No cloud AI. No telemetry.
