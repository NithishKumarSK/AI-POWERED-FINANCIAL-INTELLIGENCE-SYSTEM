"""AlphaVerity API -- FastAPI backend for the Stock Price Validation pipeline.

Run from the repo root:
    uvicorn backend.main:app --reload --port 8000

Docs at http://localhost:8000/docs once running.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import bootstrap_paths
bootstrap_paths.add_module_paths()

from dotenv import load_dotenv
load_dotenv(ROOT / ".env", override=True)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routers import me, pending_predictions, stock_predictions

app = FastAPI(title="AlphaVerity API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(me.router, prefix="/api/v1", tags=["me"])
app.include_router(stock_predictions.router, prefix="/api/v1", tags=["stock-predictions"])
app.include_router(pending_predictions.router, prefix="/api/v1", tags=["pending-predictions"])


@app.get("/api/v1/health")
def health() -> dict:
    return {"status": "ok"}
