#!/usr/bin/env python3
"""Record the iptoasn artifact this nightly pulled, in data/generated/metadata.json.

last_checked moves on every run. last_downloaded and run_id move only when the
artifact fed the build, so during a producer outage the download date visibly
stops advancing. Why: docs/memory/log/2026-09-24-iptoasn-freshness.md
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utilities.metadata import record_iptoasn_fetch, utc_timestamp


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--downloaded-at",
        default=None,
        help="RFC3339 time the producer run built the artifact; pass only when the "
        "artifact fed the build",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="producer run id behind --downloaded-at",
    )
    parser.add_argument(
        "--consumed",
        default="false",
        help="true when the build consumed the artifact; anything else records "
        "only last_checked",
    )
    args = parser.parse_args()

    if (args.downloaded_at is None) != (args.run_id is None):
        parser.error("--downloaded-at and --run-id must be given together")

    # The branch lives here, not in the workflow, so no shell edit can swap it.
    if args.consumed.strip().lower() != "true":
        args.downloaded_at = None
        args.run_id = None

    try:
        record_iptoasn_fetch(
            checked_at=utc_timestamp(),
            downloaded_at=args.downloaded_at,
            run_id=args.run_id,
        )
    except ValueError as exc:
        print(f"::error::{exc}")
        return 1
    consumed = "and consumed" if args.downloaded_at else "not consumed"
    print(f"Recorded iptoasn fetch ({consumed}), run={args.run_id or 'unknown'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
