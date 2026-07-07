"""
AI Financial Analyst System — Walk-Forward Prediction Validation

Primary entry point. Delegates entirely to stock_prediction_app.py.

Run:
    streamlit run streamlit_app.py
    streamlit run stock_prediction_app.py   (identical)

Legacy options app (archive only):
    streamlit run legacy_options_app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(1, str(ROOT / "tools"))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env", override=True)

# Import the corrected app module — set_page_config runs at import time
from stock_prediction_app import main

main()
