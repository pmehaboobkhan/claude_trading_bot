# Proposed update — `prompts/routines/end_of_day.md`

**Author:** Claude (assistant)
**Date:** 2026-05-14
**Status:** DRAFT — awaiting human PR review
**Reason:** `logs/routine_runs/` accumulates 1-2 files per routine run. After ~30 days the directory has 800+ files and slows every grep walk, every context load, and every tool that lists it. `lib/archive.py` + `scripts/archive_routine_logs.py` (landed 2026-05-14) provide deterministic, idempotent archival to `logs/routine_runs/archive/<year>/<month>/`. This change wires the script into the EOD routine so it runs nightly.

## What this changes

- A new **Step 0** at the start of `prompts/routines/end_of_day.md` runs the archive script.
- Failure is **non-fatal**: archive errors get logged to `routine_audit.notes` but don't halt EOD. The script's worst case is no-op + nonzero exit; the journal/circuit-breaker/positions logic must not depend on it.
- No-op today (2026-05-14) because nothing in the directory is older than 30 days yet. The first real archival pass will happen ~2026-06-09 when 2026-05-09 logs cross the 30-day boundary.

## Proposed insertion at the top of "Steps" in `prompts/routines/end_of_day.md`

> Insert as a new Step 0 before the current Step 1. All subsequent step numbers shift by +1.

```markdown
0. **Routine-log archive (housekeeping, non-fatal):**
   ```bash
   python3 scripts/archive_routine_logs.py --keep-days 30 || \
     echo "[archive] non-fatal: archive script exited non-zero — continuing"
   ```
   Idempotent. Moves any `logs/routine_runs/<YYYY-MM-DD>_*.md` older than 30 days
   into `logs/routine_runs/archive/<year>/<month>/`. Files within the 30-day
   window are untouched. A non-zero exit is recorded in the routine audit notes
   but does NOT halt EOD — the journal and trade reconciliation logic must run
   regardless of archival success.
```

## Why a top-of-routine step

- The archive run is purely local I/O on tracked files; it should be over in < 1 s and never depend on broker/data availability.
- Running first means subsequent steps (which read journals and per-symbol files) see the cleaner directory.
- A failure here cannot corrupt trade state. Worst case is the directory keeps growing for a day; tomorrow's EOD retries.

## No config or test changes

The implementation is already tested (`tests/test_archive.py`, 12 tests, all green). The script is purely a wrapper. This update only touches the locked routine prompt — every locked-prompt change requires a human PR per CLAUDE.md.

## Verification once merged

```bash
# Confirm script is callable from EOD's working directory
python3 scripts/archive_routine_logs.py --dry-run

# A few days after merge, confirm archive subdir exists and files migrated
ls logs/routine_runs/archive/2026/05/ | head -5
```
