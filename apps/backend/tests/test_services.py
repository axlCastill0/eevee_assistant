"""Service health tests.

The central claim being tested: a service that stops checking in is reported
down. That is what lets the dashboard show "voice is down" when the voice
pipeline cannot speak for itself.

Run with:  python -m pytest apps/backend/tests -q
"""
import pytest

import services


@pytest.fixture(autouse=True)
def clean_registry():
    """Each test starts with nobody having checked in."""
    services._registry._last_seen.clear()
    yield
    services._registry._last_seen.clear()


@pytest.fixture
def frozen_clock(monkeypatch):
    """Control services' monotonic clock so staleness is testable instantly."""
    class Clock:
        now = 1000.0

        def advance(self, seconds):
            self.now += seconds

    clock = Clock()
    monkeypatch.setattr(services.time, "monotonic", lambda: clock.now)
    return clock


# ---------------------------------------------------------------------------
# summarize()
# ---------------------------------------------------------------------------

def test_never_checked_in_is_down():
    """A service that has never beaten is down, not 'unknown'.

    If it had not started, it is not running — reporting 'unknown' would hide
    a failed boot.
    """
    speech, ok = services.summarize()
    assert ok is False
    assert speech == "voice is down."


def test_everything_good_after_heartbeat():
    services.record_heartbeat("voice")
    speech, ok = services.summarize()
    assert ok is True
    assert speech == "Everything good."


def test_goes_down_when_heartbeats_stop(frozen_clock):
    services.record_heartbeat("voice")
    assert services.summarize() == ("Everything good.", True)

    # Still fresh just before the threshold.
    frozen_clock.advance(services.STALE_AFTER_S - 1)
    assert services.summarize()[1] is True

    # Stale just after it.
    frozen_clock.advance(2)
    speech, ok = services.summarize()
    assert ok is False
    assert speech == "voice is down."


def test_recovers_when_heartbeats_resume(frozen_clock):
    services.record_heartbeat("voice")
    frozen_clock.advance(services.STALE_AFTER_S + 10)
    assert services.summarize()[1] is False

    services.record_heartbeat("voice")
    assert services.summarize() == ("Everything good.", True)


# ---------------------------------------------------------------------------
# Multi-service phrasing. Only `voice` exists today, so these drive
# HEARTBEAT_SERVICES directly to lock the grammar in before more are added.
# ---------------------------------------------------------------------------

def _speech_with_services(monkeypatch, names):
    monkeypatch.setattr(services, "HEARTBEAT_SERVICES", set(names))
    return services.summarize()[0]


def test_two_down_uses_and(monkeypatch):
    assert _speech_with_services(monkeypatch, ["voice", "zigbee"]) == \
        "voice and zigbee are down."


def test_three_down_uses_oxford_list(monkeypatch):
    assert _speech_with_services(monkeypatch, ["aaa", "bbb", "ccc"]) == \
        "aaa, bbb, and ccc are down."


def test_partial_outage_names_only_the_down_one(monkeypatch):
    monkeypatch.setattr(services, "HEARTBEAT_SERVICES", {"voice", "zigbee"})
    services.record_heartbeat("voice")
    speech, ok = services.summarize()
    assert ok is False
    assert speech == "zigbee is down."


# ---------------------------------------------------------------------------
# health()
# ---------------------------------------------------------------------------

def test_backend_always_healthy():
    """If this code is executing, the backend is up by definition."""
    backend = next(s for s in services.health() if s.name == "backend")
    assert backend.healthy is True
    assert backend.last_seen_s_ago == 0.0


def test_health_includes_every_known_service():
    names = {s.name for s in services.health()}
    assert names == {"backend"} | services.HEARTBEAT_SERVICES


def test_detail_reports_silence_duration(frozen_clock):
    services.record_heartbeat("voice")
    frozen_clock.advance(100)
    voice = next(s for s in services.health() if s.name == "voice")
    assert voice.healthy is False
    assert voice.detail == "no heartbeat for 100s"
    assert voice.last_seen_s_ago == pytest.approx(100.0)


def test_never_seen_has_no_timestamp():
    voice = next(s for s in services.health() if s.name == "voice")
    assert voice.last_seen_s_ago is None
    assert voice.detail == "never checked in"


def test_unhealthy_filters():
    services.record_heartbeat("voice")
    assert services.unhealthy() == []


def test_clock_is_monotonic_not_wallclock(frozen_clock):
    """Staleness must survive an NTP step.

    A Pi without an RTC can jump its wall clock by hours on boot; using
    time.time() here would make a live service look long dead.
    """
    services.record_heartbeat("voice")
    # Only the monotonic clock is patched; a wall-clock implementation would
    # not see this advance at all and the test below would fail.
    frozen_clock.advance(services.STALE_AFTER_S + 1)
    assert services.summarize()[1] is False
