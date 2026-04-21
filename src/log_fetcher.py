"""
log_fetcher.py
Fetches recent log events from one or more CloudWatch Log Groups using boto3.
Handles pagination automatically.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Generator, Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from config import config

logger = logging.getLogger(__name__)


class LogFetcher:
    """
    Pulls log events from CloudWatch Logs for a configurable look-back window.
    Iterates over every log stream in each requested log group.
    """

    def __init__(
        self,
        region: str = config.AWS_REGION,
        session: Optional[boto3.session.Session] = None,
    ) -> None:
        self._client = (session or boto3.session.Session()).client(
            "logs", region_name=region
        )
        self.last_errors: list[str] = []

    # ── Public API ────────────────────────────────────────────────

    def fetch_events(
        self,
        log_group_name: str,
        lookback_minutes: int = config.LOOKBACK_MINUTES,
    ) -> Generator[dict, None, None]:
        """
        Yield every log event dict from *log_group_name* in the look-back window.

        Each yielded dict has the shape:
            {
                "log_group":   str,
                "log_stream":  str,
                "timestamp":   int   (epoch ms),
                "message":     str,
            }
        """
        start_ms, end_ms = self._time_window(lookback_minutes)
        logger.info(
            "Fetching logs from '%s' | window=%d min", log_group_name, lookback_minutes
        )

        yield from self._filter_group_events(log_group_name, start_ms, end_ms)

    def fetch_all_groups(
        self,
        log_group_names: list[str] | None = None,
        lookback_minutes: int = config.LOOKBACK_MINUTES,
    ) -> Generator[dict, None, None]:
        """Convenience wrapper — iterate over multiple log groups."""
        groups = log_group_names or config.LOG_GROUP_NAMES
        self.last_errors = []
        for group in groups:
            try:
                yield from self.fetch_events(group, lookback_minutes)
            except (ClientError, BotoCoreError) as exc:
                message = f"{group}: {exc}"
                self.last_errors.append(message)
                logger.error("Failed to fetch logs from '%s': %s", group, exc, exc_info=True)

    # ── Private helpers ───────────────────────────────────────────

    @staticmethod
    def _time_window(lookback_minutes: int) -> tuple[int, int]:
        now = datetime.now(timezone.utc)
        start = now - timedelta(minutes=lookback_minutes)
        return int(start.timestamp() * 1000), int(now.timestamp() * 1000)

    def _filter_group_events(
        self,
        log_group_name: str,
        start_ms: int,
        end_ms: int,
    ) -> Generator[dict, None, None]:
        """Yield all events from a log group within the time window."""
        kwargs: dict = {
            "logGroupName": log_group_name,
            "startTime": start_ms,
            "endTime": end_ms,
            "interleaved": True,
        }
        while True:
            try:
                response = self._client.filter_log_events(**kwargs)
            except ClientError as exc:
                logger.warning("Error reading group '%s': %s", log_group_name, exc)
                raise

            for event in response.get("events", []):
                yield {
                    "log_group": log_group_name,
                    "log_stream": event.get("logStreamName", ""),
                    "timestamp": event["timestamp"],
                    "message": event.get("message", ""),
                }

            next_token = response.get("nextToken")
            prev_token = kwargs.get("nextToken")
            if not next_token or next_token == prev_token:
                break
            kwargs["nextToken"] = next_token
