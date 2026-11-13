"""House Clerk financial disclosures client — free, official, no key.

Mirrors tools/sec_edgar_client.py's pattern: structured {"status": ...}
returns, never raises, mandatory identifying User-Agent (the House Clerk
site has no documented rate-limit policy, but SEC's "always identify
yourself" convention is followed here too, out of the same courtesy).

Source: https://disclosures-clerk.house.gov/ — Periodic Transaction Reports
(PTRs) members of the House file under the STOCK Act within 30-45 days of a
personal/spouse/dependent-child stock trade. Endpoints and PDF font-glyph
quirk verified live this session (not assumed from docs):
  - Yearly index: https://disclosures-clerk.house.gov/public_disc/financial-pdfs/<YEAR>FD.zip
    (a ZIP containing <YEAR>FD.xml: one <Member> element per filing)
  - Individual PTR PDF: https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/<YEAR>/<DocID>.pdf

PDF text extraction uses PyMuPDF (fitz), not pdftotext/poppler -- poppler
isn't installed in this environment, and more importantly these PDFs embed a
subset font where BOLD label/header glyphs (not body text) are shifted by a
constant +546 Unicode codepoint offset from their real ASCII value (verified
live against a real 2026 filing this session: ord('e') in the raw extract
is 647, i.e. ord('e')+546). house_disclosures_client.fix_glyph_shift()
reverses this so downstream regex-based parsing (core/congress_trade_service.py)
sees normal text. This is specific to the House Clerk's current PDF
generation template and may need re-verification if they change it.
"""
from __future__ import annotations

import io
import zipfile
from typing import Any, Dict

import requests

INDEX_URL = "https://disclosures-clerk.house.gov/public_disc/financial-pdfs/{year}FD.zip"
PTR_URL = "https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/{year}/{doc_id}.pdf"

# Verified live this session (see module docstring) -- a fixed codepoint
# shift applied to lowercase glyphs in the PDF's bold/label font subset.
_GLYPH_SHIFT = 546
_GLYPH_SHIFT_LO = 0x251
_GLYPH_SHIFT_HI = 0x3d0


def fix_glyph_shift(text: str) -> str:
    """Reverse the House Clerk PDF template's bold-font glyph shift so
    label text ("Filing Status:", "Description:", etc.) reads normally.
    Body text (names, dates, dollar amounts, tickers) is unaffected either
    way -- it was never shifted -- so this is safe to apply unconditionally."""
    out = []
    for ch in text:
        o = ord(ch)
        if _GLYPH_SHIFT_LO <= o <= _GLYPH_SHIFT_HI:
            out.append(chr(o - _GLYPH_SHIFT))
        else:
            out.append(ch)
    return "".join(out)


def _ua() -> str:
    import os
    contact = os.getenv("SEC_EDGAR_CONTACT_EMAIL", "research-contact@example.com")
    return f"Stock-Prediction-Agent/1.0 ({contact})"


def get_ptr_index(year: int, timeout: int = 30) -> Dict[str, Any]:
    """Download and unzip one year's PTR/financial-disclosure index.

    Returns {"status": "SUCCESS", "xml_bytes": bytes} or
    {"status": "ERROR", "error_type": ..., "message": ...}. Never raises."""
    url = INDEX_URL.format(year=year)
    try:
        resp = requests.get(url, headers={"User-Agent": _ua()}, timeout=timeout)
        if resp.status_code != 200:
            return {"status": "ERROR", "error_type": f"HTTP_{resp.status_code}",
                     "message": f"House Clerk index returned HTTP {resp.status_code}"}
        with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
            names = [n for n in z.namelist() if n.lower().endswith(".xml")]
            if not names:
                return {"status": "ERROR", "error_type": "NO_XML",
                         "message": f"No XML inside {year}FD.zip (files: {z.namelist()})"}
            return {"status": "SUCCESS", "xml_bytes": z.read(names[0])}
    except requests.Timeout:
        return {"status": "ERROR", "error_type": "TIMEOUT", "message": "Request timed out"}
    except Exception as exc:
        return {"status": "ERROR", "error_type": type(exc).__name__, "message": str(exc)}


def get_ptr_pdf_text(year: int, doc_id: str, timeout: int = 30) -> Dict[str, Any]:
    """Download one PTR PDF and extract its (glyph-shift-corrected) text.

    Returns {"status": "SUCCESS", "text": str} or an ERROR dict. Never raises."""
    import fitz

    url = PTR_URL.format(year=year, doc_id=doc_id)
    try:
        resp = requests.get(url, headers={"User-Agent": _ua()}, timeout=timeout)
        if resp.status_code != 200:
            return {"status": "ERROR", "error_type": f"HTTP_{resp.status_code}",
                     "message": f"PTR PDF {doc_id} returned HTTP {resp.status_code}"}
        if not resp.content.startswith(b"%PDF"):
            return {"status": "ERROR", "error_type": "NOT_A_PDF",
                     "message": f"doc {doc_id} did not come back as a PDF"}
        doc = fitz.open(stream=resp.content, filetype="pdf")
        raw_text = "".join(page.get_text() for page in doc)
        return {"status": "SUCCESS", "text": fix_glyph_shift(raw_text)}
    except requests.Timeout:
        return {"status": "ERROR", "error_type": "TIMEOUT", "message": "Request timed out"}
    except Exception as exc:
        return {"status": "ERROR", "error_type": type(exc).__name__, "message": str(exc)}
