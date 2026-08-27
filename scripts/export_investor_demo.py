#!/usr/bin/env python3
"""Export the deterministic VLEP demo bundle consumed by GitHub Pages."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from vlep.research_mvp import export_demo_bundle


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("apps/investor-demo/public/demo-bundle.json"),
    )
    args = parser.parse_args()
    bundle = export_demo_bundle()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Exported {bundle['bundle_hash']} to {args.output}")


if __name__ == "__main__":
    main()
