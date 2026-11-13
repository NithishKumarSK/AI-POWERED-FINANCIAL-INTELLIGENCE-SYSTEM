"""
Data Quality Checker, adapted from claude-trading-skills' `data-quality-
checker` skill (vendor/claude-trading-skills/skills/data-quality-checker/
SKILL.md, references/instrument_notation_standard.md,
references/common_data_errors.md). MIT License, Copyright (c) 2026
TraderMonty.

Validates market-analysis Markdown text for common data-quality
mistakes: price-scale confusion (ETF vs. futures vs. index), date/
weekday mismatches, allocation totals, and bp/% unit mixing. Pure
text-processing, standard library only -- no API key, no network.

SCOPE REDUCTION, disclosed: the source skill is explicitly bilingual
(English + Japanese, full-width character normalization, Japanese
section headings like "配分"/"ウェイト"). This port is English-only --
porting correct Japanese tokenization/normalization without any way to
test it against real Japanese documents would risk a confidently-wrong
result, which is worse than an honestly-narrower tool. The instrument-
notation check (full ticker-naming-convention linting beyond the digit-
count price-scale check) is also not ported -- the digit-count table
from the source skill's own reference doc is the part that's
mechanically checkable without a style-guide judgment call.

Advisory mode, per the source skill's Key Principle 1: every finding is
a WARNING/INFO/ERROR for human review, never a blocker.
"""
from __future__ import annotations

import calendar
import datetime as _dt
import re
from typing import Any, Dict, List, Optional

# (min_digits, max_digits) before the decimal point, per the source
# skill's references/instrument_notation_standard.md digit-count table.
DIGIT_RANGES: Dict[str, Any] = {
    "GLD": (2, 3), "GC": (3, 4),
    "SPY": (2, 3), "SPX": (4, 5),
    "VIX": (1, 2),
    "TLT": (2, 3),
    "SLV": (2, 2), "SI": (2, 2),
    "USO": (2, 2), "CL": (2, 3),
}

_PRICE_PATTERN = re.compile(
    r"\b(" + "|".join(DIGIT_RANGES.keys()) + r")\b\s*[:\s]\s*\$?([\d,]+(?:\.\d+)?)"
)

_WEEKDAY_DATE_PATTERN = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
    r"(\d{1,2}),?\s+(\d{4})\s*\((Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\)"
)

_PERCENT_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*%")
_ALLOCATION_HEADING_PATTERN = re.compile(r"^#{1,6}\s*.*\b(allocation|weight)s?\b", re.IGNORECASE)
_ANY_HEADING_PATTERN = re.compile(r"^#{1,6}\s")
_BP_PATTERN = re.compile(r"\b\d+(?:\.\d+)?\s*bps?\b", re.IGNORECASE)


def _finding(severity: str, category: str, message: str, line_number: Optional[int] = None,
             context: Optional[str] = None) -> Dict[str, Any]:
    return {"severity": severity, "category": category, "message": message,
            "line_number": line_number, "context": context}


def check_price_scale(text: str) -> List[Dict[str, Any]]:
    findings = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for match in _PRICE_PATTERN.finditer(line):
            ticker = match.group(1)
            raw_num = match.group(2).replace(",", "")
            integer_part = raw_num.split(".")[0].lstrip("0") or "0"
            digit_count = len(integer_part)
            min_digits, max_digits = DIGIT_RANGES[ticker]
            if not (min_digits <= digit_count <= max_digits):
                findings.append(_finding(
                    "WARNING", "price_scale",
                    f"{ticker}: ${raw_num} has {digit_count} digit(s) "
                    f"(expected {min_digits}-{max_digits} digits)",
                    lineno, match.group(0),
                ))
    return findings


def check_dates(text: str, as_of: Optional[str] = None) -> List[Dict[str, Any]]:
    """`as_of` is accepted for interface parity with the source skill but
    unused here -- this check only matches dates that already spell out
    an explicit year AND a claimed weekday in parentheses (e.g. "January
    1, 2026 (Monday)"), so there is no year-inference ambiguity to
    resolve. The source skill's separate year-inference heuristic (for
    dates with no year at all) is not ported -- see module docstring.
    """
    findings = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for match in _WEEKDAY_DATE_PATTERN.finditer(line):
            month_name, day_str, year_str, claimed_weekday = match.groups()
            try:
                month = list(calendar.month_name).index(month_name)
                actual_date = _dt.date(int(year_str), month, int(day_str))
            except ValueError:
                continue
            actual_weekday = calendar.day_name[actual_date.weekday()]
            if actual_weekday != claimed_weekday:
                findings.append(_finding(
                    "ERROR", "dates",
                    f"Date-weekday mismatch: {month_name} {day_str}, {year_str} "
                    f"({claimed_weekday}) -- actual weekday is {actual_weekday}",
                    lineno, match.group(0),
                ))
    return findings


def check_allocations(text: str, tolerance_pct: float = 0.5) -> List[Dict[str, Any]]:
    """Section-aware: only sums percentages inside a heading whose text
    mentions 'allocation' or 'weight' (Key Principle 2 -- narrowed to
    English headings per the scope reduction above), up to the next
    heading of any level.
    """
    lines = text.splitlines()
    findings = []
    i = 0
    while i < len(lines):
        if _ALLOCATION_HEADING_PATTERN.match(lines[i]):
            start_line = i + 2  # 0-indexed heading at i -> 1-indexed first content line is i+2
            j = i + 1
            section_lines = []
            while j < len(lines) and not _ANY_HEADING_PATTERN.match(lines[j]):
                section_lines.append(lines[j])
                j += 1
            section_text = "\n".join(section_lines)
            pcts = [float(m.group(1)) for m in _PERCENT_PATTERN.finditer(section_text)]
            if pcts:
                total = sum(pcts)
                if abs(total - 100.0) > tolerance_pct:
                    findings.append(_finding(
                        "WARNING", "allocations",
                        f"Allocation total: {total:.1f}% (expected ~100%)",
                        start_line, section_text.strip()[:200],
                    ))
            i = j
        else:
            i += 1
    return findings


def check_units(text: str) -> List[Dict[str, Any]]:
    """INFO-only: a line mixing basis-point and percent notation for the
    same kind of figure may be intentional (e.g. "raised rates 25bps to
    5.25%") but is worth a human glance, per Key Principle 1's INFO tier.
    """
    findings = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if _BP_PATTERN.search(line) and _PERCENT_PATTERN.search(line):
            findings.append(_finding(
                "INFO", "units",
                "Line mixes basis-point and percent notation -- confirm units are not conflated",
                lineno, line.strip()[:200],
            ))
    return findings


_CHECK_FUNCTIONS = {
    "price_scale": check_price_scale,
    "dates": check_dates,
    "allocations": check_allocations,
    "units": check_units,
}


def run_all_checks(
    text: str,
    as_of: Optional[str] = None,
    checks: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Run the requested checks (default: all) and return findings sorted by line number."""
    selected = checks or list(_CHECK_FUNCTIONS.keys())
    findings: List[Dict[str, Any]] = []
    for name in selected:
        fn = _CHECK_FUNCTIONS.get(name)
        if fn is None:
            continue
        if name == "dates":
            findings.extend(fn(text, as_of))
        else:
            findings.extend(fn(text))
    findings.sort(key=lambda f: (f["line_number"] is None, f["line_number"] or 0))
    return findings
