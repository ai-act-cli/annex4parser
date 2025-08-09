"""Background scheduler service for Annex4Parser.

The module exposes an APScheduler-based runner that periodically updates
regulation sources and provides a lightweight health check endpoint.

Run it from the command line:

```
python -m annex4parser.scheduler \
    --db-url sqlite:///compliance.db \
    --config sources.yaml \
    --port 8000
```

Jobs are scheduled with sensible defaults:

* **ELI** sources every 6 hours – these are moderately changing
* **RSS** sources every hour – RSS feeds are more dynamic
* **HTML** sources every 24 hours – pages rarely update

Use the command line flags to override the database URL, path to
`sources.yaml` configuration file and the HTTP port.

The server exposes `/health` returning ``{"status": "ok"}`` and can be
monitored with ``curl http://localhost:8000/health``.
"""

import argparse
import asyncio
import logging
from aiohttp import web
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .models import Base
from .regulation_monitor_v2 import RegulationMonitorV2


async def run_scheduler(db_url: str, config_path: str | None, port: int) -> None:
    """Запустить APScheduler и health-endpoint."""
    engine = create_engine(db_url)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    monitor = RegulationMonitorV2(db=session, config_path=config_path)

    scheduler = AsyncIOScheduler()
    scheduler.add_job(monitor.update_eli_sources, "interval", hours=6)
    scheduler.add_job(monitor.update_rss_sources, "interval", hours=1)
    scheduler.add_job(monitor.update_html_sources, "interval", hours=24)
    scheduler.start()

    async def health(_: web.Request) -> web.Response:
        return web.json_response({"status": "ok"})

    app = web.Application()
    app.router.add_get("/health", health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    try:
        await asyncio.Event().wait()
    finally:
        scheduler.shutdown()
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Annex4Parser scheduler")
    parser.add_argument("--db-url", default="sqlite:///compliance.db")
    parser.add_argument("--config", default=None, help="Path to sources.yaml")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(message)s",
    )

    asyncio.run(run_scheduler(args.db_url, args.config, args.port))


if __name__ == "__main__":  # pragma: no cover
    main()
