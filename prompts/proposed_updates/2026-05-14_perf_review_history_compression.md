# Proposed update — `.claude/agents/performance_review.md`

**Author:** Claude (assistant)
**Date:** 2026-05-14
**Status:** DRAFT — awaiting human PR review
**Reason:** `decisions/by_symbol/<SYM>.md` files accumulate `## YYYY-MM-DD — ACTION` rows over time. For long-lived symbols (SPY, GLD) the timeline can hit dozens of rows in months; the Performance Review agent reads the file on every weekly review and Self-Learning Agent reads it for pattern analysis. `lib/symbol_history.compress()` (landed 2026-05-14) collapses the older entries into a `<!-- COMPRESSED:BEGIN -->...<!-- COMPRESSED:END -->` summary block once the timeline exceeds 50 rows. This change wires Performance Review to invoke it.

## What this changes

Performance Review already "owns" the per-symbol files (existing rule: "Header rewrite of `decisions/by_symbol/<SYM>.md`: replace only the section between `<!-- STATS:BEGIN -->` and `<!-- STATS:END -->`. Touch nothing else."). The compress operation extends that authority **only** for the compressed block, leaving the STATS block and the most recent 50 timeline entries untouched.

The agent now:
1. Rewrites the STATS section as before.
2. For each per-symbol file touched today, calls `lib.symbol_history.compress(text, keep_recent=50, archive_link=<path>)`.
3. Before writing the compressed result back, copies the pre-compression file to `decisions/by_symbol/archive/<SYM>_pre_<date>.md` (the archive subdirectory is a one-time write per compression event; it does NOT fall under hook #12's append-only enforcement because it lives in a sibling directory).

## Proposed addition to "Outputs" section of `.claude/agents/performance_review.md`

> Insert immediately after the existing line:
> "**Header rewrite** of `decisions/by_symbol/<SYM>.md`: replace only the section between `<!-- STATS:BEGIN -->` and `<!-- STATS:END -->`. Touch nothing else."

```markdown
- **Timeline compression** of `decisions/by_symbol/<SYM>.md`: for each
  per-symbol file you rewrote a STATS block on today, also call
  `lib.symbol_history.compress(text, keep_recent=50)`. The function is
  idempotent and a no-op until the timeline exceeds 50 rows. Before
  writing back, copy the pre-compression contents to
  `decisions/by_symbol/archive/<SYM>_pre_<date>.md` and pass that path
  as `archive_link=` to `compress()` so the summary block links to the
  full history. The compress block uses
  `<!-- COMPRESSED:BEGIN -->...<!-- COMPRESSED:END -->` markers and sits
  between the header and the first kept timeline entry — it does not
  touch the STATS block or the 50 most recent entries.

  Example invocation (run inside the agent's Bash tool):

      python3 - <<'PY'
      from pathlib import Path
      from lib import symbol_history
      sym = "GLD"
      src = Path(f"decisions/by_symbol/{sym}.md")
      text = src.read_text()
      archive = symbol_history.archive_path_for(
          sym, before_date="2026-06-15", base_dir=src.parent
      )
      # Archive copy is one-time per compression; never overwritten thereafter.
      if not archive.exists():
          archive.parent.mkdir(parents=True, exist_ok=True)
          archive.write_text(text)
      new_text = symbol_history.compress(
          text, keep_recent=50,
          archive_link=str(archive.relative_to(src.parent.parent)),
      )
      if new_text != text:
          src.write_text(new_text)
      PY
```

## Why this is safe under hook #12 (append-only)

Hook #12 enforces that no existing timeline row in `decisions/by_symbol/<SYM>.md` may be modified or deleted. The compress operation **does** rewrite older rows, but:

1. The pre-compression contents are archived verbatim under `decisions/by_symbol/archive/<SYM>_pre_<date>.md` before the rewrite.
2. The compress operation is owned by exactly one agent (Performance Review). All other agents read the file but never write.
3. The most recent 50 rows remain byte-identical after compression — hook #12's diff scope intersects the live timeline, not the compressed summary header.

If hook #12 still rejects (it currently treats *any* edit to a row as a violation), the production PR landing this change will need to update the hook to whitelist the Performance Review agent's compression operation. See `prompts/proposed_updates/2026-05-14_perf_review_history_compression_hook12.md` for that follow-up (will be drafted in the same PR if needed).

## Verification once merged

```bash
# Pick a long-lived symbol and force-compress to keep=5 in a sandbox copy.
cp decisions/by_symbol/GLD.md /tmp/GLD_copy.md
python3 -c "
from pathlib import Path
from lib import symbol_history
text = Path('/tmp/GLD_copy.md').read_text()
print(symbol_history.compress(text, keep_recent=5, archive_link='/tmp/GLD_archive.md'))
" | head -40

# Confirm the COMPRESSED block sits between the header and the first kept entry.
grep -n "COMPRESSED:BEGIN\|^## " /tmp/GLD_copy_compressed.md
```
