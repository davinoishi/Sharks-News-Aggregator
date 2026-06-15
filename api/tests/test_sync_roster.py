"""Tests for CapWages roster-sync hardening (R2-F2).

The scrape keys off literal HTML markers, so a site redesign or partial parse
can silently yield a tiny roster — and remove_departed_players would then delete
every real player entity. These tests pin the size/shrink guard and the
abort-before-delete behavior.
"""
from unittest import mock

from app.tasks import sync_roster
from app.tasks.sync_roster import (
    MAX_EXPECTED_ROSTER,
    MIN_EXPECTED_ROSTER,
    validate_roster_size,
)

# --- validate_roster_size (pure) --------------------------------------------

def test_validate_accepts_plausible_roster():
    ok, _ = validate_roster_size(55, prev_count=0)
    assert ok


def test_validate_rejects_too_small():
    ok, reason = validate_roster_size(MIN_EXPECTED_ROSTER - 1, prev_count=0)
    assert not ok
    assert "too small" in reason


def test_validate_rejects_empty():
    ok, reason = validate_roster_size(0, prev_count=50)
    assert not ok
    assert "too small" in reason


def test_validate_rejects_too_large():
    ok, reason = validate_roster_size(MAX_EXPECTED_ROSTER + 1, prev_count=0)
    assert not ok
    assert "too large" in reason


def test_validate_rejects_sharp_shrink():
    # 60 -> 30 is a 50% drop, well past the 30% threshold.
    ok, reason = validate_roster_size(30, prev_count=60)
    assert not ok
    assert "shrank" in reason


def test_validate_allows_modest_shrink_within_threshold():
    # 60 -> 45 is a 25% drop (within the 30% allowance) and above the floor.
    ok, _ = validate_roster_size(45, prev_count=60)
    assert ok


def test_validate_ignores_shrink_when_no_baseline():
    # prev_count == 0 means "no prior successful sync" — only the band applies.
    ok, _ = validate_roster_size(25, prev_count=0)
    assert ok


# --- task abort-before-delete -----------------------------------------------

def _run_task_with(parsed_players, prev_count):
    """Run sync_sharks_roster with the network + DB boundaries mocked out.

    Returns (result, mocks) so callers can assert on what was / wasn't called.
    """
    db = mock.MagicMock()
    with mock.patch.object(sync_roster, "SessionLocal", return_value=db), \
            mock.patch.object(sync_roster, "fetch_capwages_roster", return_value=parsed_players), \
            mock.patch.object(sync_roster, "get_site_metric", return_value=prev_count), \
            mock.patch.object(sync_roster, "set_site_metric") as set_metric, \
            mock.patch.object(sync_roster, "send_alert") as send_alert, \
            mock.patch.object(sync_roster, "process_players", return_value={"a", "b"}) as process, \
            mock.patch.object(sync_roster, "remove_departed_players", return_value=0) as remove:
        result = sync_roster.sync_sharks_roster.run()
    return result, {
        "set_metric": set_metric,
        "send_alert": send_alert,
        "process": process,
        "remove": remove,
    }


def test_task_aborts_without_deleting_on_tiny_roster():
    # A 2-player parse (markers present, structure changed) must not drive removal.
    result, m = _run_task_with(["One Player", "Two Player"], prev_count=60)
    assert result["status"] == "aborted"
    m["remove"].assert_not_called()
    m["process"].assert_not_called()
    m["set_metric"].assert_not_called()
    m["send_alert"].assert_called_once()


def test_task_alerts_and_errors_when_fetch_fails():
    result, m = _run_task_with(None, prev_count=60)
    assert result["status"] == "error"
    m["remove"].assert_not_called()
    m["send_alert"].assert_called_once()


def test_task_syncs_and_updates_baseline_on_healthy_roster():
    players = [f"Player {i}" for i in range(55)]
    result, m = _run_task_with(players, prev_count=54)
    assert result["status"] == "success"
    m["remove"].assert_called_once()
    m["set_metric"].assert_called_once()
    m["send_alert"].assert_not_called()
