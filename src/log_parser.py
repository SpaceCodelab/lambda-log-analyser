"""
log_parser.py
Parses raw CloudWatch log messages from AWS Lambda invocations.

Extracts:
  - Errors and exceptions (message, type, traceback snippet)
  - Invocation duration (ms)
  - Billed duration (ms)
  - Max memory used (MB)
  - Memory size (MB)
  - Cold start detection
  - Request ID

Lambda produces structured REPORT lines like:
    REPORT RequestId: abc-123  Duration: 312.45 ms  Billed Duration: 313 ms
           Memory Size: 512 MB  Max Memory Used: 128 MB  Init Duration: 234.56 ms
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ── Compiled regex patterns ────────────────────────────────────────────────────

_REPORT_PATTERN = re.compile(
    r"REPORT RequestId:\s*(?P<request_id>[\w-]+)"
    r".*?Duration:\s*(?P<duration>[\d.]+)\s*ms"
    r".*?Billed Duration:\s*(?P<billed_duration>[\d.]+)\s*ms"
    r".*?Memory Size:\s*(?P<memory_size>[\d.]+)\s*MB"
    r".*?Max Memory Used:\s*(?P<max_memory_used>[\d.]+)\s*MB"
    r"(?:.*?Init Duration:\s*(?P<init_duration>[\d.]+)\s*ms)?",
    re.DOTALL,
)

_START_PATTERN = re.compile(
    r"START RequestId:\s*(?P<request_id>[\w-]+)"
    r"\s+Version:\s*(?P<version>\S+)"
)

_END_PATTERN = re.compile(r"END RequestId:\s*(?P<request_id>[\w-]+)")

_ERROR_PATTERNS: list[re.Pattern] = [
    re.compile(r"\[ERROR\]", re.IGNORECASE),
    re.compile(r"\bERROR\b"),
    re.compile(r"Traceback \(most recent call last\)"),
    re.compile(r"Exception:"),
    re.compile(r"Error:"),
    re.compile(r"FATAL", re.IGNORECASE),
    re.compile(r"Unhandled exception", re.IGNORECASE),
    re.compile(r"Task timed out"),
    re.compile(r"Runtime.ExitError"),
    re.compile(r"OutOfMemoryError", re.IGNORECASE),
]

_EXCEPTION_TYPE_PATTERN = re.compile(
    r"(?P<exc_type>[A-Za-z][A-Za-z0-9_]*(?:Error|Exception|Fault|Warning))"
    r"(?::\s*(?P<exc_message>.+))?"
)


# ── Data classes ───────────────────────────────────────────────────────────────


@dataclass
class ParsedEvent:
    """Represents a single parsed log event ready for storage."""

    log_group: str
    log_stream: str
    timestamp_ms: int
    message: str
    event_type: str  # "error" | "report" | "start" | "end" | "other"

    # REPORT fields (populated only for event_type == "report")
    request_id: Optional[str] = None
    duration_ms: Optional[float] = None
    billed_duration_ms: Optional[float] = None
    memory_size_mb: Optional[float] = None
    max_memory_used_mb: Optional[float] = None
    init_duration_ms: Optional[float] = None  # present only on cold starts
    is_cold_start: bool = False

    # Error fields (populated only for event_type == "error")
    error_type: Optional[str] = None
    error_message: Optional[str] = None

    @property
    def iso_timestamp(self) -> str:
        dt = datetime.fromtimestamp(self.timestamp_ms / 1000, tz=timezone.utc)
        return dt.isoformat()


@dataclass
class AnalysisSummary:
    """Aggregated statistics for a single analyser run."""

    log_groups_scanned: list[str] = field(default_factory=list)
    total_events_processed: int = 0
    total_errors: int = 0
    total_invocations: int = 0
    cold_starts: int = 0

    durations_ms: list[float] = field(default_factory=list)
    billed_durations_ms: list[float] = field(default_factory=list)
    memory_used_mb: list[float] = field(default_factory=list)
    memory_sizes_mb: list[float] = field(default_factory=list)
    error_events: list[ParsedEvent] = field(default_factory=list)

    estimated_cost: float = 0.0

    @property
    def avg_duration_ms(self) -> Optional[float]:
        return round(sum(self.durations_ms) / len(self.durations_ms), 2) if self.durations_ms else None

    @property
    def min_duration_ms(self) -> Optional[float]:
        return round(min(self.durations_ms), 2) if self.durations_ms else None

    @property
    def max_duration_ms(self) -> Optional[float]:
        return round(max(self.durations_ms), 2) if self.durations_ms else None

    @property
    def p95_duration_ms(self) -> Optional[float]:
        if not self.durations_ms:
            return None
        sorted_d = sorted(self.durations_ms)
        idx = max(0, int(len(sorted_d) * 0.95) - 1)
        return round(sorted_d[idx], 2)

    @property
    def p99_duration_ms(self) -> Optional[float]:
        if not self.durations_ms:
            return None
        sorted_d = sorted(self.durations_ms)
        idx = max(0, int(len(sorted_d) * 0.99) - 1)
        return round(sorted_d[idx], 2)

    @property
    def avg_memory_mb(self) -> Optional[float]:
        return round(sum(self.memory_used_mb) / len(self.memory_used_mb), 2) if self.memory_used_mb else None

    @property
    def min_memory_mb(self) -> Optional[float]:
        return round(min(self.memory_used_mb), 2) if self.memory_used_mb else None

    @property
    def max_memory_mb(self) -> Optional[float]:
        return round(max(self.memory_used_mb), 2) if self.memory_used_mb else None

    @property
    def memory_efficiency_pct(self) -> Optional[float]:
        if self.memory_used_mb and self.memory_sizes_mb:
            avg_used = sum(self.memory_used_mb) / len(self.memory_used_mb)
            avg_total = sum(self.memory_sizes_mb) / len(self.memory_sizes_mb)
            return round((avg_used / avg_total) * 100, 2) if avg_total > 0 else None
        return None

    @property
    def avg_billed_duration_ms(self) -> Optional[float]:
        return round(sum(self.billed_durations_ms) / len(self.billed_durations_ms), 2) if self.billed_durations_ms else None

    @property
    def total_billed_duration_ms(self) -> float:
        return sum(self.billed_durations_ms)

    @property
    def total_billed_duration_seconds(self) -> float:
        return self.total_billed_duration_ms / 1000

    @property
    def error_rate(self) -> float:
        if self.total_events_processed > 0:
            return round((self.total_errors / self.total_events_processed) * 100, 2)
        return 0.0

    @property
    def cold_start_rate(self) -> float:
        if self.total_invocations > 0:
            return round((self.cold_starts / self.total_invocations) * 100, 2)
        return 0.0

    def to_dict(self) -> dict:
        return {
            "log_groups_scanned": self.log_groups_scanned,
            "total_events_processed": self.total_events_processed,
            "total_errors": self.total_errors,
            "total_invocations": self.total_invocations,
            "cold_starts": self.cold_starts,
            "avg_duration_ms": self.avg_duration_ms,
            "min_duration_ms": self.min_duration_ms,
            "max_duration_ms": self.max_duration_ms,
            "p95_duration_ms": self.p95_duration_ms,
            "p99_duration_ms": self.p99_duration_ms,
            "avg_billed_duration_ms": self.avg_billed_duration_ms,
            "total_billed_duration_ms": self.total_billed_duration_ms,
            "avg_memory_mb": self.avg_memory_mb,
            "min_memory_mb": self.min_memory_mb,
            "max_memory_mb": self.max_memory_mb,
            "memory_efficiency_pct": self.memory_efficiency_pct,
            "error_rate": self.error_rate,
            "cold_start_rate": self.cold_start_rate,
            "estimated_cost": self.estimated_cost,
        }


# ── Parser ─────────────────────────────────────────────────────────────────────


class LogParser:
    """
    Stateless parser.  Feed it raw event dicts from LogFetcher and it
    returns ParsedEvent objects + maintains a running AnalysisSummary.
    """

    def parse_event(self, raw: dict) -> ParsedEvent:
        """Parse a single raw event dict into a ParsedEvent."""
        message: str = raw.get("message", "").strip()

        if message.startswith("REPORT "):
            return self._parse_report(raw, message)

        if self._is_error(message):
            return self._parse_error(raw, message)

        if message.startswith("START "):
            event_type = "start"
        elif message.startswith("END "):
            event_type = "end"
        else:
            event_type = "other"

        return ParsedEvent(
            log_group=raw["log_group"],
            log_stream=raw["log_stream"],
            timestamp_ms=raw["timestamp"],
            message=message,
            event_type=event_type,
        )

    def build_summary(
        self,
        events: list[ParsedEvent],
        log_groups: list[str],
    ) -> AnalysisSummary:
        """Aggregate a list of ParsedEvents into an AnalysisSummary."""
        summary = AnalysisSummary(log_groups_scanned=log_groups)
        summary.total_events_processed = len(events)

        for ev in events:
            if ev.event_type == "report":
                summary.total_invocations += 1
                if ev.duration_ms is not None:
                    summary.durations_ms.append(ev.duration_ms)
                if ev.billed_duration_ms is not None:
                    summary.billed_durations_ms.append(ev.billed_duration_ms)
                if ev.max_memory_used_mb is not None:
                    summary.memory_used_mb.append(ev.max_memory_used_mb)
                if ev.memory_size_mb is not None:
                    summary.memory_sizes_mb.append(ev.memory_size_mb)
                if ev.is_cold_start:
                    summary.cold_starts += 1
            elif ev.event_type == "error":
                summary.total_errors += 1
                summary.error_events.append(ev)

        return summary

    # ── Private helpers ────────────────────────────────────────────

    def _parse_report(self, raw: dict, message: str) -> ParsedEvent:
        match = _REPORT_PATTERN.search(message)
        if not match:
            logger.debug("REPORT line did not match pattern: %.80s", message)
            return ParsedEvent(
                log_group=raw["log_group"],
                log_stream=raw["log_stream"],
                timestamp_ms=raw["timestamp"],
                message=message,
                event_type="other",
            )

        groups = match.groupdict()
        init_duration = (
            float(groups["init_duration"]) if groups.get("init_duration") else None
        )
        return ParsedEvent(
            log_group=raw["log_group"],
            log_stream=raw["log_stream"],
            timestamp_ms=raw["timestamp"],
            message=message,
            event_type="report",
            request_id=groups["request_id"],
            duration_ms=float(groups["duration"]),
            billed_duration_ms=float(groups["billed_duration"]),
            memory_size_mb=float(groups["memory_size"]),
            max_memory_used_mb=float(groups["max_memory_used"]),
            init_duration_ms=init_duration,
            is_cold_start=init_duration is not None,
        )

    def _parse_error(self, raw: dict, message: str) -> ParsedEvent:
        error_type: Optional[str] = None
        error_message: Optional[str] = None

        exc_match = _EXCEPTION_TYPE_PATTERN.search(message)
        if exc_match:
            error_type = exc_match.group("exc_type")
            error_message = exc_match.group("exc_message")

        # Truncate very long error messages for storage
        truncated_message = message[:2000] if len(message) > 2000 else message

        return ParsedEvent(
            log_group=raw["log_group"],
            log_stream=raw["log_stream"],
            timestamp_ms=raw["timestamp"],
            message=truncated_message,
            event_type="error",
            error_type=error_type,
            error_message=error_message,
        )

    @staticmethod
    def _is_error(message: str) -> bool:
        return any(pattern.search(message) for pattern in _ERROR_PATTERNS)
