"""
tests/test_log_parser.py
Unit tests for the LogParser and data classes.
No AWS credentials or network access required.
"""

import pytest
from log_parser import AnalysisSummary, LogParser, ParsedEvent


@pytest.fixture
def parser():
    return LogParser()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _raw(message: str) -> dict:
    return {
        "log_group": "/aws/lambda/test-fn",
        "log_stream": "2024/01/01/[$LATEST]abc123",
        "timestamp": 1_710_000_000_000,
        "message": message,
    }


REPORT_LINE = (
    "REPORT RequestId: abc-123-def\t"
    "Duration: 312.45 ms\t"
    "Billed Duration: 313 ms\t"
    "Memory Size: 512 MB\t"
    "Max Memory Used: 128 MB\t"
    "Init Duration: 234.56 ms\n"
)

REPORT_LINE_NO_INIT = (
    "REPORT RequestId: xyz-789\t"
    "Duration: 56.00 ms\t"
    "Billed Duration: 57 ms\t"
    "Memory Size: 256 MB\t"
    "Max Memory Used: 64 MB\n"
)


# ── REPORT parsing ────────────────────────────────────────────────────────────

class TestParseReport:
    def test_basic_fields(self, parser):
        ev = parser.parse_event(_raw(REPORT_LINE))
        assert ev.event_type == "report"
        assert ev.request_id == "abc-123-def"
        assert ev.duration_ms == pytest.approx(312.45)
        assert ev.billed_duration_ms == pytest.approx(313.0)
        assert ev.memory_size_mb == pytest.approx(512.0)
        assert ev.max_memory_used_mb == pytest.approx(128.0)

    def test_cold_start_detected(self, parser):
        ev = parser.parse_event(_raw(REPORT_LINE))
        assert ev.is_cold_start is True
        assert ev.init_duration_ms == pytest.approx(234.56)

    def test_warm_start(self, parser):
        ev = parser.parse_event(_raw(REPORT_LINE_NO_INIT))
        assert ev.is_cold_start is False
        assert ev.init_duration_ms is None

    def test_iso_timestamp_format(self, parser):
        ev = parser.parse_event(_raw(REPORT_LINE))
        assert "T" in ev.iso_timestamp
        assert "+00:00" in ev.iso_timestamp


# ── Error parsing ─────────────────────────────────────────────────────────────

class TestParseError:
    @pytest.mark.parametrize("msg", [
        "[ERROR] Something went wrong",
        "ERROR: division by zero",
        "Traceback (most recent call last):\n  File foo.py",
        "Task timed out after 15.00 seconds",
        "Runtime.ExitError Process exited before completing",
        "Unhandled exception in handler",
    ])
    def test_error_detection(self, parser, msg):
        ev = parser.parse_event(_raw(msg))
        assert ev.event_type == "error"

    def test_exception_type_extracted(self, parser):
        ev = parser.parse_event(_raw("ValueError: invalid literal for int()"))
        assert ev.error_type == "ValueError"
        assert "invalid literal" in (ev.error_message or "")

    def test_long_message_truncated(self, parser):
        long_msg = "[ERROR] " + "x" * 3000
        ev = parser.parse_event(_raw(long_msg))
        assert len(ev.message) <= 2000


# ── Other event types ─────────────────────────────────────────────────────────

class TestParseOther:
    def test_start_event(self, parser):
        ev = parser.parse_event(_raw("START RequestId: abc Version: $LATEST"))
        assert ev.event_type == "start"

    def test_end_event(self, parser):
        ev = parser.parse_event(_raw("END RequestId: abc"))
        assert ev.event_type == "end"

    def test_generic_info_log(self, parser):
        ev = parser.parse_event(_raw("INFO Processing batch of 100 items"))
        assert ev.event_type == "other"


# ── AnalysisSummary ───────────────────────────────────────────────────────────

class TestAnalysisSummary:
    def _make_report_event(self, duration, memory, cold=False) -> ParsedEvent:
        return ParsedEvent(
            log_group="/aws/lambda/fn",
            log_stream="stream",
            timestamp_ms=1_710_000_000_000,
            message="REPORT ...",
            event_type="report",
            duration_ms=duration,
            max_memory_used_mb=memory,
            is_cold_start=cold,
        )

    def _make_error_event(self) -> ParsedEvent:
        return ParsedEvent(
            log_group="/aws/lambda/fn",
            log_stream="stream",
            timestamp_ms=1_710_000_000_000,
            message="[ERROR] boom",
            event_type="error",
        )

    def test_avg_duration(self):
        summary = AnalysisSummary()
        summary.durations_ms = [100.0, 200.0, 300.0]
        assert summary.avg_duration_ms == pytest.approx(200.0)

    def test_p95_duration(self):
        summary = AnalysisSummary()
        summary.durations_ms = list(range(1, 101))   # 1..100
        assert summary.p95_duration_ms == 95

    def test_empty_summary_returns_none(self):
        summary = AnalysisSummary()
        assert summary.avg_duration_ms is None
        assert summary.max_duration_ms is None
        assert summary.p95_duration_ms is None

    def test_build_summary_counts(self):
        parser = LogParser()
        events = [
            self._make_report_event(100, 64, cold=True),
            self._make_report_event(200, 128, cold=False),
            self._make_error_event(),
        ]
        summary = parser.build_summary(events, ["/aws/lambda/fn"])
        assert summary.total_invocations == 2
        assert summary.total_errors == 1
        assert summary.cold_starts == 1
        assert summary.avg_duration_ms == pytest.approx(150.0)

    def test_to_dict_keys(self):
        summary = AnalysisSummary()
        d = summary.to_dict()
        for key in [
            "total_errors", "total_invocations", "cold_starts",
            "avg_duration_ms", "max_duration_ms", "p95_duration_ms",
        ]:
            assert key in d
