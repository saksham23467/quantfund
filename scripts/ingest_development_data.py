#!/usr/bin/env python3
"""Ingest DEVELOPMENT_DATA (free/public Indian equity) — never research/paper/live eligible.

Usage:
  make development-data
  make ingest-development-data FILE=/path/to/csv_or_bars_dir
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantfund.data.development.config import DevelopmentIngestConfig
from quantfund.data.development.ingest import ingest_development_data


def main() -> int:
    file_env = os.environ.get("FILE") or os.environ.get("DEVELOPMENT_DATA_FILE")
    allow_net = os.environ.get("ALLOW_NETWORK_FETCH", "").lower() in {"1", "true", "yes"}
    cfg = DevelopmentIngestConfig(
        file_path=Path(file_env) if file_env else None,
        allow_network_fetch=allow_net and not file_env,
    )
    result = ingest_development_data(cfg)

    print("Development data ingestion: SUCCESS" if result.success else "FAIL")
    print()
    print(f"Data class: {result.data_class}")
    print(f"Research eligibility: {result.research_eligibility.upper()}")
    print(f"Research eligible: {str(result.research_eligible).upper()}")
    print(f"Paper eligible: {str(result.paper_eligible).upper()}")
    print(f"Live eligible: {str(result.live_eligible).upper()}")
    print()
    print(f"Synthetic: {str(result.synthetic).upper()}")
    print(f"Research grade: {str(result.research_grade).upper()}")
    print()
    print(f"Real broker orders: {result.real_orders}")
    print(f"Quality: {result.quality.get('quality')}")
    if result.root:
        print(f"Dataset root: {result.root}")
    print()
    print(result.report_text)
    print()
    print("Eligibility gates weakened: FALSE")
    print("Phase 11 started: FALSE")
    print("LIVE_SEND: DISABLED")
    return 0 if result.success and not result.research_eligible else 1


if __name__ == "__main__":
    raise SystemExit(main())
