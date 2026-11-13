"""
scheduled_retraining.py -- to-do item #5: "Build a proper, scheduled
retraining pipeline." Before this, every refresh this session (ML model,
confidence calibration map, range-timing training set) was a manually-run
one-off script -- real staleness bugs were found and fixed from exactly that
(e.g. confidence_calibration_map.json sitting at a stale 138-record snapshot
while the live DB had grown to 572). This orchestrates the same three
free/local refreshes on a recurring cadence so staleness can't silently
creep back in.

Deliberately makes ZERO live Gemini API calls, in keeping with this
project's explicit token-budget caution -- safe to run on an unattended
schedule for that reason alone. Steps 1-5 are DB-only/deterministic; steps
6-7 make live (free, keyless) calls to SEC EDGAR and the House Clerk, which
is slower and network-dependent but still costs no API tokens.

Runs, in order, each as a subprocess so one step's failure/crash can never
take down the others:
  1. core/ml_training_runner.py            -- retrain ML segment models (DB-only,
                                               no --bulk). Already has its own
                                               save-gate (beat baseline by 3pp,
                                               >=20 holdout samples) and segment-
                                               preservation safeguards -- this
                                               orchestrator does not duplicate or
                                               weaken those; it just calls it.
  2. core/confidence_calibration_builder.py -- refit confidence->hit-rate map.
  3. scripts/adhoc/build_range_timing_training_set.py -- refresh KNN day-timing
                                               precedent pool.
  4. core/calibration_profile_builder.py --from-db -- refresh per-symbol
                                               calibration profiles from the
                                               live DB. Found and fixed this
                                               session: this file was stale
                                               (generated 2026-07-20 from a
                                               5-row CSV snapshot covering
                                               only SPY/TSLA) while the live
                                               DB had grown to 572 records
                                               across 10 symbols -- GOOGL and
                                               7 others had no profile at all.
  5. scripts/adhoc/llm_memorization_risk_check.py -- re-check for LLM
                                               memorization risk (to-do item
                                               #7). Gains real statistical
                                               power over time even though
                                               this script itself never
                                               changes: the genuinely-unseen
                                               (post-cutoff) bucket keeps
                                               growing as more predictions
                                               resolve, while the cutoff
                                               itself is fixed.
  6. scripts/adhoc/build_congress_trade_cache.py -- incremental scan of new
                                               House PTR filings (item #9
                                               alternative data).
  7. scripts/adhoc/build_institutional_holdings_cache.py -- refresh the 23
                                               well-known filers' 13F
                                               holdings (item #9 alternative
                                               data; 13F data moves at most
                                               quarterly, cheap to re-run).

Every step's stdout/stderr + exit code is appended to a timestamped log under
data/retraining_logs/ -- a step that fails is recorded plainly, never
swallowed, and does not stop the remaining steps from running. Exits non-zero
if any step failed, so a Task Scheduler/cron consumer can alert on it; the
log explains which step and why.

Usage:
    python scripts/scheduled_retraining.py
"""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "data" / "retraining_logs"

STEPS = [
    ("ml_training_runner",         [sys.executable, str(ROOT / "core" / "ml_training_runner.py")]),
    ("confidence_calibration_builder", [sys.executable, str(ROOT / "core" / "confidence_calibration_builder.py")]),
    ("range_timing_training_set",  [sys.executable, str(ROOT / "scripts" / "adhoc" / "build_range_timing_training_set.py")]),
    ("calibration_profile_builder", [sys.executable, str(ROOT / "core" / "calibration_profile_builder.py"), "--from-db"]),
    ("llm_memorization_risk_check", [sys.executable, str(ROOT / "scripts" / "adhoc" / "llm_memorization_risk_check.py")]),
    ("congress_trade_cache",        [sys.executable, str(ROOT / "scripts" / "adhoc" / "build_congress_trade_cache.py")]),
    ("institutional_holdings_cache", [sys.executable, str(ROOT / "scripts" / "adhoc" / "build_institutional_holdings_cache.py")]),
]


def main() -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    log_path = LOG_DIR / f"retrain_{ts}.log"

    results = []
    with open(log_path, "w", encoding="utf-8") as log:
        log.write(f"Scheduled retraining run -- started {ts}\n")
        log.write("=" * 78 + "\n")

        for name, cmd in STEPS:
            log.write(f"\n--- STEP: {name} ---\n")
            log.write(f"cmd: {' '.join(cmd)}\n")
            try:
                proc = subprocess.run(
                    cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=1800,
                )
                log.write(proc.stdout or "")
                if proc.stderr:
                    log.write("\n[stderr]\n" + proc.stderr)
                log.write(f"\n[exit code: {proc.returncode}]\n")
                results.append((name, proc.returncode == 0, proc.returncode))
            except subprocess.TimeoutExpired as exc:
                log.write(f"\n[TIMEOUT after {exc.timeout}s -- step killed]\n")
                results.append((name, False, "timeout"))
            except Exception as exc:
                log.write(f"\n[ORCHESTRATOR ERROR: {type(exc).__name__}: {exc}]\n")
                results.append((name, False, "orchestrator_error"))

        log.write("\n" + "=" * 78 + "\n")
        log.write("Summary:\n")
        any_failed = False
        for name, ok, code in results:
            status = "OK" if ok else f"FAILED (exit={code})"
            log.write(f"  {name}: {status}\n")
            any_failed = any_failed or not ok
        log.write(f"\nOverall: {'FAILURE -- see steps above' if any_failed else 'ALL STEPS OK'}\n")

    print(f"Scheduled retraining finished -- log written to {log_path}")
    for name, ok, code in results:
        print(f"  {name}: {'OK' if ok else f'FAILED (exit={code})'}")

    return 1 if any(not ok for _, ok, _ in results) else 0


if __name__ == "__main__":
    sys.exit(main())
