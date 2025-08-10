#!/usr/bin/env python3
"""Tests for APScheduler-based scheduler service."""

import asyncio
import logging
import socket

import aiohttp
import pytest

from annex4parser import scheduler


class DummyScheduler:
    """Record scheduled jobs without running them."""

    def __init__(self):
        self.jobs = []
        self.started = False
        self.shutdown_called = False

    def add_job(self, func, trigger, **kwargs):
        self.jobs.append((func, trigger, kwargs))

    def start(self):
        self.started = True

    def shutdown(self):
        self.shutdown_called = True


class DummyMonitor:
    """Simple monitor stub capturing init parameters."""

    def __init__(self, db, config_path):
        self.db = db
        self.config_path = config_path

    async def update_eli_sources(self):
        return {"type": "eli_sparql"}

    async def update_rss_sources(self):
        return {"type": "rss"}

    async def update_html_sources(self):
        return {"type": "html"}


@pytest.mark.asyncio
async def test_run_scheduler_schedules_jobs_and_health(monkeypatch):
    """Scheduler registers jobs with expected intervals and serves health."""
    # Capture DB URL passed to create_engine
    engine_urls = []
    real_create_engine = scheduler.create_engine

    def capture_create_engine(url):
        engine_urls.append(url)
        return real_create_engine(url)

    monkeypatch.setattr(scheduler, "create_engine", capture_create_engine)

    # Replace monitor and scheduler with stubs
    monkeypatch.setattr(scheduler, "RegulationMonitorV2", DummyMonitor)

    sched_instances = []

    def fake_scheduler():
        instance = DummyScheduler()
        sched_instances.append(instance)
        return instance

    monkeypatch.setattr(scheduler, "AsyncIOScheduler", fake_scheduler)

    # Get free port for HTTP server
    sock = socket.socket()
    sock.bind(("localhost", 0))
    port = sock.getsockname()[1]
    sock.close()

    task = asyncio.create_task(
        scheduler.run_scheduler("sqlite:///:memory:", "test.yaml", port)
    )

    # Wait for server to start
    async with aiohttp.ClientSession() as session:
        for _ in range(10):
            try:
                async with session.get(f"http://localhost:{port}/health") as resp:
                    assert resp.status == 200
                    assert await resp.json() == {"status": "ok"}
                    break
            except Exception:
                await asyncio.sleep(0.1)
        else:  # pragma: no cover - loop didn't break
            pytest.fail("health endpoint not responding")

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # Assertions on captured objects
    assert engine_urls == ["sqlite:///:memory:"]
    monitor = sched_instances[0].jobs[0][0].__self__
    assert isinstance(monitor, DummyMonitor)
    assert monitor.config_path == "test.yaml"

    sched = sched_instances[0]
    assert sched.started and sched.shutdown_called
    jobs = {(job[0].__name__, job[2]["hours"]) for job in sched.jobs}
    assert jobs == {
        ("update_eli_sources", 6),
        ("update_rss_sources", 1),
        ("update_html_sources", 24),
    }


def test_main_default_arguments(monkeypatch):
    """Main uses default args when none provided."""
    called = {}

    async def fake_run_scheduler(db_url, config, port):
        called["db_url"] = db_url
        called["config"] = config
        called["port"] = port

    monkeypatch.setattr(scheduler, "run_scheduler", fake_run_scheduler)

    log_config = {}

    def fake_basicConfig(level, format):
        log_config["level"] = level

    monkeypatch.setattr(logging, "basicConfig", fake_basicConfig)

    monkeypatch.setattr("sys.argv", ["scheduler"])
    scheduler.main()

    assert called == {
        "db_url": "sqlite:///compliance.db",
        "config": None,
        "port": 8000,
    }
    assert log_config["level"] == logging.INFO


def test_main_custom_arguments(monkeypatch):
    """Main passes CLI overrides and verbose logging."""
    called = {}

    async def fake_run_scheduler(db_url, config, port):
        called["db_url"] = db_url
        called["config"] = config
        called["port"] = port

    monkeypatch.setattr(scheduler, "run_scheduler", fake_run_scheduler)

    log_config = {}

    def fake_basicConfig(level, format):
        log_config["level"] = level

    monkeypatch.setattr(logging, "basicConfig", fake_basicConfig)

    monkeypatch.setattr(
        "sys.argv",
        [
            "scheduler",
            "--db-url",
            "sqlite:///test.db",
            "--config",
            "sources.yaml",
            "--port",
            "9001",
            "--verbose",
        ],
    )
    scheduler.main()

    assert called == {
        "db_url": "sqlite:///test.db",
        "config": "sources.yaml",
        "port": 9001,
    }
    assert log_config["level"] == logging.DEBUG
