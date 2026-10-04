"""CLI entry point for the pending-predictions resolver (Phase 1 stopgap scheduler).

Run manually, or schedule via Windows Task Scheduler / cron, e.g. nightly
after US market close:

    python run_resolver.py

See db/resolver.py for the resolution algorithm and db/schema.sql +
C:\\Users\\nithi\\.claude\\plans\\glowing-rolling-globe.md for the design.
"""
from __future__ import annotations

import sys

from db.resolver import resolve_pending_predictions


def main() -> int:
    result = resolve_pending_predictions()
    print(
        f"Resolver run complete: {result['candidates']} candidate(s), "
        f"{result['resolved']} validated, {result['invalid']} invalid, "
        f"{result['skipped']} skipped (data not yet available)."
    )
    if result.get("error"):
        print("ERROR during resolver run:", result["error"], file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
