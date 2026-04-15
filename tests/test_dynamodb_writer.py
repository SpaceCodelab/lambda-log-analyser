"""
tests/test_dynamodb_writer.py
Unit tests for DynamoDBWriter.
boto3 calls are mocked — no AWS credentials needed.
"""

from unittest.mock import MagicMock, patch

import pytest

from dynamodb_writer import DynamoDBWriter
from log_parser import AnalysisSummary, ParsedEvent


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_table():
    return MagicMock()


@pytest.fixture
def writer(mock_table):
    with patch("dynamodb_writer.boto3.resource") as mock_resource:
        mock_resource.return_value.Table.return_value = mock_table
        w = DynamoDBWriter(table_name="test-table", region="us-east-1")
        w._table = mock_table
        return w


def _report_event(request_id="req-1", duration=100.0, memory=64.0, cold=False) -> ParsedEvent:
    return ParsedEvent(
        log_group="/aws/lambda/fn",
        log_stream="stream",
        timestamp_ms=1_710_000_000_000,
        message="REPORT ...",
        event_type="report",
        request_id=request_id,
        duration_ms=duration,
        billed_duration_ms=duration + 1,
        memory_size_mb=128.0,
        max_memory_used_mb=memory,
        is_cold_start=cold,
        init_duration_ms=200.0 if cold else None,
    )


def _error_event() -> ParsedEvent:
    return ParsedEvent(
        log_group="/aws/lambda/fn",
        log_stream="stream",
        timestamp_ms=1_710_000_001_000,
        message="[ERROR] boom",
        event_type="error",
        error_type="ValueError",
        error_message="invalid input",
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestEventToItem:
    def test_report_item_has_required_keys(self, writer):
        ev = _report_event()
        item = writer._event_to_item(ev)
        for key in ["pk", "sk", "log_group", "log_stream", "event_type", "ttl",
                    "duration_ms", "max_memory_used_mb", "is_cold_start"]:
            assert key in item, f"Missing key: {key}"

    def test_pk_format(self, writer):
        ev = _report_event()
        item = writer._event_to_item(ev)
        assert item["pk"] == "/aws/lambda/fn#stream"

    def test_sk_format(self, writer):
        ev = _report_event()
        item = writer._event_to_item(ev)
        assert item["sk"] == "1710000000000#report"

    def test_cold_start_flag(self, writer):
        ev = _report_event(cold=True)
        item = writer._event_to_item(ev)
        assert item["is_cold_start"] is True
        assert "init_duration_ms" in item

    def test_warm_start_no_init_key(self, writer):
        ev = _report_event(cold=False)
        item = writer._event_to_item(ev)
        assert "init_duration_ms" not in item

    def test_error_item_has_error_type(self, writer):
        ev = _error_event()
        item = writer._event_to_item(ev)
        assert item["event_type"] == "error"
        assert item["error_type"] == "ValueError"

    def test_error_message_truncated(self, writer):
        ev = _error_event()
        ev.error_message = "x" * 600
        item = writer._event_to_item(ev)
        assert len(item["error_message"]) <= 500

    def test_ttl_is_future(self, writer):
        import time
        ev = _report_event()
        item = writer._event_to_item(ev)
        assert item["ttl"] > int(time.time())


class TestWriteEvents:
    def test_calls_batch_writer(self, writer, mock_table):
        mock_ctx = MagicMock()
        mock_table.batch_writer.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_table.batch_writer.return_value.__exit__ = MagicMock(return_value=False)

        events = [_report_event("req-1"), _error_event()]
        count = writer.write_events(events)
        assert count == 2
        assert mock_ctx.put_item.call_count == 2

    def test_empty_events_returns_zero(self, writer, mock_table):
        mock_ctx = MagicMock()
        mock_table.batch_writer.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_table.batch_writer.return_value.__exit__ = MagicMock(return_value=False)
        count = writer.write_events([])
        assert count == 0


class TestWriteRunSummary:
    def test_puts_item_with_correct_pk(self, writer, mock_table):
        summary = AnalysisSummary(log_groups_scanned=["/aws/lambda/fn"])
        writer.write_run_summary(summary)
        mock_table.put_item.assert_called_once()
        call_kwargs = mock_table.put_item.call_args[1]
        assert call_kwargs["Item"]["pk"] == "RUN_SUMMARY"

    def test_summary_dict_embedded(self, writer, mock_table):
        summary = AnalysisSummary(log_groups_scanned=["/aws/lambda/fn"])
        summary.total_errors = 3
        writer.write_run_summary(summary)
        item = mock_table.put_item.call_args[1]["Item"]
        assert item["summary"]["total_errors"] == 3
