"""
AI Financial Analyst System — Walk-Forward Prediction Validation

Primary entry point. Delegates entirely to stock_prediction_app.py.

Run (from the repo root):
    streamlit run core/streamlit_app.py
    streamlit run core/stock_prediction_app.py   (identical)

Legacy options app (archive only):
    streamlit run legacy/legacy_options_app.py
"""
from __future__ import annotations

import sys
import importlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import bootstrap_paths
bootstrap_paths.add_module_paths()

from dotenv import load_dotenv
load_dotenv(ROOT / ".env", override=True)

import stock_prediction_app as _spa
importlib.reload(_spa)

_spa.main()
