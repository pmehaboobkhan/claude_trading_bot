"""Validate config files against their JSON Schemas.

Usage:
    python tests/run_schema_validation.py                       # validate all known configs
    python tests/run_schema_validation.py path/to/file.yaml     # validate one file
    python tests/run_schema_validation.py path/to/file.json     # validate one file (decisions)

Returns non-zero exit if any validation fails. Designed to be invoked from hooks.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"

# (file path under repo root, schema filename)
CONFIG_FILES = [
    ("config/watchlist.yaml", "watchlist.schema.json"),
    ("config/risk_limits.yaml", "risk_limits.schema.json"),
    ("config/strategy_rules.yaml", "strategy_rules.schema.json"),
    ("config/approved_modes.yaml", "approved_modes.schema.json"),
    ("config/routine_schedule.yaml", "routine_schedule.schema.json"),
]


def _load(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        return json.loads(text)
    return yaml.safe_load(text)


def _schema_for(file_path: Path) -> Path | None:
    name = file_path.name
    if name.endswith(".yaml"):
        return SCHEMA_DIR / f"{file_path.stem}.schema.json"
    # decisions/<date>/<HHMM>_<SYM>.json -> trade_decision.schema.json
    if file_path.suffix == ".json" and "decisions" in file_path.parts:
        return SCHEMA_DIR / "trade_decision.schema.json"
    return None


def validate(file_path: Path, schema_path: Path) -> list[str]:
    if not file_path.exists():
        return [f"missing file: {file_path}"]
    if not schema_path.exists():
        return [f"missing schema: {schema_path}"]
    try:
        data = _load(file_path)
    except (yaml.YAMLError, json.JSONDecodeError) as exc:
        return [f"parse error in {file_path}: {exc}"]
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    errors = []
    for err in sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path)):
        loc = ".".join(str(p) for p in err.absolute_path) or "<root>"
        errors.append(f"{file_path}: {loc}: {err.message}")
    return errors


def main(argv: list[str]) -> int:
    if len(argv) > 1:
        file_path = Path(argv[1]).resolve()
        try:
            file_path = file_path.relative_to(REPO_ROOT)
        except ValueError:
            pass
        schema = _schema_for(Path(file_path))
        if schema is None:
            print(f"no schema known for {file_path}", file=sys.stderr)
            return 0  # not our problem
        errors = validate(REPO_ROOT / file_path, schema)
    else:
        errors = []
        for rel, schema_name in CONFIG_FILES:
            errors.extend(validate(REPO_ROOT / rel, SCHEMA_DIR / schema_name))

    if errors:
        for e in errors:
            print(f"SCHEMA FAIL: {e}", file=sys.stderr)
        return 1
    print("schema validation OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
