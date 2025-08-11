"""Command line entry point for annex4parser.

This module allows the regulation monitor to be run as a script
from the command line. It accepts a list of source URLs
and will print out a summary of detected changes. For example:

```sh
    python -m annex4parser \
        --source https://eur-lex.europa.eu/legal-content/EN/ALL/?uri=CELEX%3A32024R1689 \
    --source https://www.europarl.europa.eu/doceo/document/TA-9-2024-0138_EN.html
```

Under the hood it instantiates a :class:`RegulationMonitor` and
runs a single check. In a production deployment you might
schedule this script via cron or a background worker.
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import List

from .regulation_monitor import RegulationMonitor
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .models import Base


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Annex4Parser CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # ---- single update (V1) ----
    p1 = sub.add_parser("update-single", help="Fetch one regulation via URL")
    p1.add_argument(
        "--name",
        required=True,
        help="Human-readable name of the regulation, e.g. 'EU AI Act'",
    )
    p1.add_argument(
        "--version",
        required=True,
        help="Version identifier for the regulation, e.g. '2025.08.01'",
    )
    p1.add_argument(
        "--url",
        required=True,
        help="URL from which to fetch the regulation text",
    )
    p1.add_argument(
        "--db-url",
        default="sqlite:///compliance.db",
        help="SQLAlchemy database URL (default: sqlite:///compliance.db)",
    )
    p1.add_argument(
        "--cache-dir",
        type=str,
        default=None,
        help="Directory to store cached versions of sources (defaults to ~/.annex4parser/cache)",
    )
    p1.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    # ---- update-all (V2) ----
    p2 = sub.add_parser("update-all", help="Update from sources.yaml via RegulationMonitorV2")
    p2.add_argument("--db-url", default="sqlite:///compliance.db")
    p2.add_argument("--config", default=None, help="Path to sources.yaml (optional)")
    p2.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(message)s")

    # Create DB + tables
    engine = create_engine(args.db_url)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    try:
        if args.cmd == "update-single":
            monitor = RegulationMonitor(db=session, cache_dir=args.cache_dir)
            reg = monitor.update(name=args.name, version=args.version, url=args.url)
            print(f"Processed {reg.name} version {reg.version}.")
        elif args.cmd == "update-all":
            from .regulation_monitor_v2 import RegulationMonitorV2
            # Создаем таблицы если их нет
            monitor = RegulationMonitorV2(db=session, config_path=args.config)
            import asyncio
            stats = asyncio.run(monitor.update_all())
            print(f"Update-all done: {stats}")
    finally:
        session.close()
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
