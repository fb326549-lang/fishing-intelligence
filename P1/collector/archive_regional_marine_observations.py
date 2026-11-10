#!/usr/bin/env python3
"""Append six-region CWA rolling 48-hour observations to immutable history."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from archive_cwa_tide_history import archive_regional_series


def archive(input_csv: str, history_dir: str, snapshot_id: str, collected_at: str) -> dict:
    """Append new region/time/value revisions without replacing prior observations."""
    return archive_regional_series(
        input_csv,
        history_dir,
        "regional_marine_observations_48h.jsonl",
        "O-B0075-001",
        "rolling_48_hour",
        snapshot_id,
        collected_at,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Six-region O-B0075-001 CSV.")
    parser.add_argument("--history-dir", required=True)
    parser.add_argument("--snapshot-id", required=True)
    parser.add_argument("--collected-at", default=datetime.now(timezone.utc).isoformat())
    args = parser.parse_args()
    result = archive(args.input, args.history_dir, args.snapshot_id, args.collected_at)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
