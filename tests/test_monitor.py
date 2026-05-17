import asyncio
import json
import signal
import time
from datetime import timezone

import pytest

from loopsentry.monitor import LoopSentry


def read_events(path):
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def test_start_requires_running_loop(tmp_path):
    sentry = LoopSentry(base_dir=str(tmp_path), threshold=0.01)

    with pytest.raises(RuntimeError, match="requires an active asyncio event loop"):
        sentry.start()

    assert sentry.running is False
    assert getattr(sentry, "thread", None) is None


def test_start_stop_start_reuses_same_instance_and_log_file(tmp_path):
    async def scenario():
        sentry = LoopSentry(base_dir=str(tmp_path), threshold=0.01)

        sentry.start()
        await asyncio.sleep(0.03)
        first_path = sentry.log_file
        sentry.stop()

        assert sentry._stop_event.is_set()
        assert sentry._file_handle.closed is True

        sentry.start()
        await asyncio.sleep(0.03)

        assert sentry.running is True
        assert sentry._stop_event.is_set() is False
        assert sentry._file_handle.closed is False
        assert sentry.log_file == first_path
        assert sentry.thread.is_alive() is True

        before = len(read_events(first_path))
        sentry._write_event("manual_probe", {"ok": True}, duration=1.23)
        after = len(read_events(first_path))
        sentry.stop()

        assert after == before + 1

    asyncio.run(scenario())


def test_write_event_reopens_closed_file_and_logs_warning(tmp_path):
    async def scenario():
        sentry = LoopSentry(base_dir=str(tmp_path), threshold=0.01)
        sentry.start()
        sentry._file_handle.close()

        sentry._write_event("manual_probe", {"value": 1}, duration=0.5)
        sentry.stop()

        events = read_events(sentry.log_file)
        assert sentry._file_handle.closed is True
        assert any(event["type"] == "loopsentry_warning" for event in events)
        assert any(event["type"] == "manual_probe" for event in events)

    asyncio.run(scenario())


def test_start_does_not_override_signal_handlers(tmp_path):
    original_sigint = signal.getsignal(signal.SIGINT)
    original_sigterm = signal.getsignal(signal.SIGTERM)

    def app_sigint(signum, frame):
        return None

    def app_sigterm(signum, frame):
        return None

    signal.signal(signal.SIGINT, app_sigint)
    signal.signal(signal.SIGTERM, app_sigterm)

    async def scenario():
        sentry = LoopSentry(base_dir=str(tmp_path), threshold=0.01)
        sentry.start()
        await asyncio.sleep(0.02)
        sentry.stop()

    try:
        asyncio.run(scenario())
        assert signal.getsignal(signal.SIGINT) is app_sigint
        assert signal.getsignal(signal.SIGTERM) is app_sigterm
    finally:
        signal.signal(signal.SIGINT, original_sigint)
        signal.signal(signal.SIGTERM, original_sigterm)


def test_block_detection_writes_utc_timestamps(tmp_path):
    async def scenario():
        sentry = LoopSentry(base_dir=str(tmp_path), threshold=0.01)
        sentry.start()
        time.sleep(0.03)
        await asyncio.sleep(0.03)
        sentry.stop()
        return read_events(sentry.log_file)

    events = asyncio.run(scenario())

    assert any(event["type"] == "block_started" for event in events)
    assert any(event["type"] == "block_resolved" for event in events)

    for event in events:
        parsed = time_from_iso(event["timestamp"])
        assert parsed.tzinfo == timezone.utc


def test_async_bottleneck_event_is_recorded(tmp_path):
    async def slow_task():
        await asyncio.sleep(0.03)

    async def scenario():
        sentry = LoopSentry(
            base_dir=str(tmp_path),
            threshold=0.01,
            async_threshold=0.01,
            detect_async_bottlenecks=True,
        )
        sentry.start()
        task = asyncio.create_task(slow_task(), name="slow-task")
        await task
        await asyncio.sleep(0.02)
        sentry.stop()
        return read_events(sentry.log_file)

    events = asyncio.run(scenario())

    async_events = [event for event in events if event["type"] == "async_bottleneck"]
    assert async_events
    assert async_events[0]["task_name"] == "slow-task"
    assert async_events[0]["duration_current"] > 0.01


def time_from_iso(value):
    return __import__("datetime").datetime.fromisoformat(value)
