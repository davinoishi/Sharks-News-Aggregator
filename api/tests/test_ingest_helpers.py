"""Tests for ingest text/feed helpers (brief 06)."""
import time
from datetime import timezone
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models import IngestMethod, Source, SourceCategory, SourceStatus
from app.tasks.ingest import (
    derive_title_from_description,
    ingest_api,
    ingest_html,
    is_schedule_stub,
    is_scoreboard_stub,
    parse_published_date,
    resolve_entry_url,
    sanitize_feed_xml,
    strip_html,
)

# --- strip_html --------------------------------------------------------------

def test_strip_html_removes_tags():
    assert strip_html("<b>Celebrini</b> scores") == "Celebrini scores"


def test_strip_html_unescapes_entities():
    assert strip_html("Sharks &amp; Kings") == "Sharks & Kings"


def test_strip_html_strips_whitespace():
    assert strip_html("  <i>hi</i>  ") == "hi"


def test_strip_html_passthrough_none_and_empty():
    assert strip_html(None) is None
    assert strip_html("") == ""


# --- derive_title_from_description -------------------------------------------

def test_derive_title_short_description_used_verbatim():
    # Bluesky profile RSS items have no <title>; tweets usually fit whole.
    assert derive_title_from_description(
        "Connor Bedard’s new contract with #Blackhawks: 5 years x $15 million."
    ) == "Connor Bedard’s new contract with #Blackhawks: 5 years x $15 million."


def test_derive_title_truncates_on_word_boundary():
    long = "word " * 60
    title = derive_title_from_description(long)
    assert title.endswith("…")
    assert len(title) <= 141
    assert not title[:-1].endswith(" ")


def test_derive_title_strips_html_and_whitespace():
    assert derive_title_from_description("  <b>Sharks</b>\n sign   goalie  ") == "Sharks sign goalie"


def test_derive_title_empty_inputs():
    assert derive_title_from_description(None) is None
    assert derive_title_from_description("") is None
    assert derive_title_from_description("<p> </p>") is None


# --- is_scoreboard_stub ------------------------------------------------------

def test_scoreboard_stub_matches_boxscore_live_score_title():
    assert is_scoreboard_stub(
        "Vegas Golden Knights vs. San Jose Sharks - Boxscore - Live Score - September 22, 2026"
    )


def test_scoreboard_stub_matches_marker_variants():
    assert is_scoreboard_stub("Sharks vs Kings Box Score")
    assert is_scoreboard_stub("Sharks - Golden Knights LiveScore today")
    assert is_scoreboard_stub("Watch Sharks vs Knights Live Stream free")
    assert is_scoreboard_stub("Sharks vs Knights H2H Stats and prediction")


def test_scoreboard_stub_matches_live_updates_play_by_play():
    # Auto-generated pages for games months away, surfaced by Google Alerts.
    assert is_scoreboard_stub(
        "Florida Panthers vs. San Jose Sharks Live Updates, Score, and Play-by-play - October 1, 2026"
    )
    assert is_scoreboard_stub(
        "Colorado Avalanche vs. San Jose Sharks Live Updates, Score, and Play-by-play - March 5, 2027"
    )
    assert is_scoreboard_stub("Sharks vs Kings play by play and stats")


def test_scoreboard_stub_matches_streaming_promos():
    # "Watch X vs Y" streaming-promo pages (Fubo, DirecTV, ...).
    assert is_scoreboard_stub("Watch Dallas Stars vs San Jose Sharks - Fubo")
    assert is_scoreboard_stub("Watch San Jose Sharks vs. Vegas Golden Knights: streaming info")
    assert is_scoreboard_stub("Sharks vs Stars: How to Watch, TV Channel, Start Time")
    assert is_scoreboard_stub("Where to watch Sharks-Kings tonight")


def test_scoreboard_stub_matches_thescore_matchup_widgets():
    # theScore/ESPN pipe-delimited "| NHL Matchup |" auto-pages.
    assert is_scoreboard_stub(
        "San Jose Sharks vs Detroit Red Wings | October 17, 2026 | NHL Matchup | theScore"
    )
    assert is_scoreboard_stub("Sharks vs Kings | Nov 3, 2026 | Matchup | theScore")


def test_scoreboard_stub_is_case_insensitive():
    assert is_scoreboard_stub("SHARKS VS KNIGHTS LIVE SCORE")


def test_scoreboard_stub_matches_bare_schedule_pages():
    # No marker words at all — the title is only teams, a date, and the
    # publisher. Structure is the only tell.
    assert is_scoreboard_stub("San Jose Sharks vs. Vegas Golden Knights - 2026-09-27 - TSN")
    assert is_scoreboard_stub("San Jose Sharks at Anaheim Ducks - October 17, 2026")
    assert is_scoreboard_stub("Sharks vs Kings | Nov 3, 2026 | Sportsnet")
    assert is_scoreboard_stub("NHL: San Jose Sharks vs Utah - 11/3/2026 - ESPN")
    assert is_scoreboard_stub("Sharks vs. Blues - Sat, Dec 5 - 7:00 PM PT")


def test_schedule_stub_requires_a_date_segment():
    # A matchup alone is how plenty of real headlines start.
    assert not is_schedule_stub("San Jose Sharks vs. Vegas Golden Knights")
    assert not is_schedule_stub("Sharks vs Kings - TSN")


def test_schedule_stub_ignores_titles_with_any_copy():
    # Any segment that isn't a matchup, a date, or a publisher means the page
    # has editorial content.
    assert not is_schedule_stub("Sharks vs. Golden Knights - September 27, 2026 - Preview and prediction")
    assert not is_schedule_stub("Sharks vs Kings - Nov 3, 2026 - Celebrini scores twice")
    assert not is_schedule_stub("Sharks vs. Ducks: what to watch - October 17, 2026")
    # A final score is copy, not fixture data.
    assert not is_schedule_stub("Sharks 4, Golden Knights 2 - 2026-09-27 - TSN")
    assert not is_schedule_stub(None)
    assert not is_schedule_stub("")


def test_scoreboard_stub_ignores_real_headlines():
    assert not is_scoreboard_stub("Celebrini scores twice as Sharks beat Golden Knights")
    assert not is_scoreboard_stub("Sharks announce 2026-27 preseason schedule")
    # Leading "Watch" without a matchup is real editorial content.
    assert not is_scoreboard_stub("Watch: Celebrini's between-the-legs goal stuns crowd")
    # A matchup without "watch"/markers is a real preview or recap.
    assert not is_scoreboard_stub("Sharks vs Stars: three takeaways from the shootout loss")
    # The bare word "matchup" in editorial prose must not trip the widget rule.
    assert not is_scoreboard_stub("Sharks-Wings matchup: three things to watch Friday")
    assert not is_scoreboard_stub(None)
    assert not is_scoreboard_stub("")


# --- sanitize_feed_xml -------------------------------------------------------

def test_sanitize_replaces_named_entities():
    out = sanitize_feed_xml(b"<title>A&nbsp;B&mdash;C</title>")
    assert b"&#160;" in out
    assert b"&#8212;" in out
    assert b"&nbsp;" not in out


def test_sanitize_removes_control_chars():
    out = sanitize_feed_xml(b"good\x00\x07text")
    assert out == b"goodtext"


def test_sanitize_keeps_tab_newline_cr():
    assert sanitize_feed_xml(b"a\tb\nc\r") == b"a\tb\nc\r"


def test_sanitize_handles_non_utf8():
    # latin-1 'é' (0xe9) should decode and re-encode as utf-8 without raising.
    out = sanitize_feed_xml(b"caf\xe9")
    assert out.decode("utf-8") == "café"


# --- resolve_entry_url -------------------------------------------------------

def _src(base_url="https://www.nhl.com/sharks/"):
    return SimpleNamespace(base_url=base_url)


def test_resolve_relative_uses_feed_channel_link():
    # The to-rss.xyz NHL.com proxy emits relative entry links; resolve them
    # against the feed's channel <link> (the real publisher host).
    feed = SimpleNamespace(feed={"link": "https://www.nhl.com/sharks/news/"})
    out = resolve_entry_url(
        "/sharks/news/sharks-re-sign-defenseman-nolan-allan", feed, _src()
    )
    assert out == "https://www.nhl.com/sharks/news/sharks-re-sign-defenseman-nolan-allan"


def test_resolve_relative_falls_back_to_source_base_url():
    feed = SimpleNamespace(feed={})
    out = resolve_entry_url("/sharks/news/foo", feed, _src())
    assert out == "https://www.nhl.com/sharks/news/foo"


def test_resolve_leaves_absolute_url_untouched():
    feed = SimpleNamespace(feed={"link": "https://www.nhl.com/sharks/news/"})
    url = "https://example.com/article"
    assert resolve_entry_url(url, feed, _src()) == url


def test_resolve_passthrough_none():
    feed = SimpleNamespace(feed={})
    assert resolve_entry_url(None, feed, _src()) is None


# --- parse_published_date ----------------------------------------------------

def test_parse_published_uses_published_parsed():
    st = time.struct_time((2026, 6, 1, 12, 0, 0, 0, 0, -1))
    entry = SimpleNamespace(published_parsed=st)
    dt = parse_published_date(entry)
    assert dt is not None and dt.year == 2026 and dt.month == 6 and dt.day == 1


def test_parse_published_falls_back_to_updated():
    st = time.struct_time((2026, 1, 2, 0, 0, 0, 0, 0, -1))
    entry = SimpleNamespace(published_parsed=None, updated_parsed=st)
    dt = parse_published_date(entry)
    assert dt is not None and dt.year == 2026 and dt.month == 1 and dt.day == 2


def test_parse_published_is_timezone_aware():
    # brief 07, C2: parsed dates are returned as timezone-aware UTC.
    st = time.struct_time((2026, 6, 1, 12, 0, 0, 0, 0, -1))
    dt = parse_published_date(SimpleNamespace(published_parsed=st))
    assert dt.tzinfo is not None and dt.utcoffset() == timezone.utc.utcoffset(None)


def test_parse_published_none_when_absent():
    assert parse_published_date(SimpleNamespace()) is None


# --- unimplemented ingest methods retire the source as unsupported (R2-F1) ----
#
# Earlier (brief 07, C3) these stubs forced fetch_error_count to the "broken"
# threshold, which produced false "broken source" alerts every cycle. R2-F1
# instead moves the source to SourceStatus.UNSUPPORTED so get_active_sources
# stops scheduling it, and leaves fetch_error_count untouched.

def _source_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[Source.__table__])
    return sessionmaker(bind=engine)()


def _make_source(db):
    src = Source(
        name="HTML scrape source",
        category=SourceCategory.OTHER,
        ingest_method=IngestMethod.HTML,
        base_url="https://example.com",
        status=SourceStatus.APPROVED,
        fetch_error_count=0,
    )
    db.add(src)
    db.commit()
    db.refresh(src)
    return src


def test_ingest_html_marks_source_unsupported():
    db = _source_session()
    try:
        src = _make_source(db)
        result = ingest_html(db, src)
        assert result["status"] == "unsupported"
        assert "not_implemented" in result["reason"]
        # Retired from scheduling, not flagged broken.
        assert src.status == SourceStatus.UNSUPPORTED
        assert src.fetch_error_count == 0
    finally:
        db.close()


def test_ingest_api_marks_source_unsupported():
    db = _source_session()
    try:
        src = _make_source(db)
        result = ingest_api(db, src)
        assert result["status"] == "unsupported"
        assert src.status == SourceStatus.UNSUPPORTED
        assert src.fetch_error_count == 0
    finally:
        db.close()
