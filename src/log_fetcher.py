"""
log_fetcher.py
Fetches recent log events from one or more CloudWatch Log Groups using boto3.
Handles pagination automatically.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Generator

import boto3
from botocore.exceptions import ClientError

from config import config

logger = logging.getLogger(__name__)


class LogFetcher:
    """
    Pulls log events from CloudWatch Logs for a configurable look-back window.
    Iterates over every log stream in each requested log group.
    """

    def __init__(self, region: str = config.AWS_REGION) -> None:
        self._client = boto3.client("logs", region_name=region)

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

        streams = list(self._list_streams(log_group_name, start_ms))
        logger.info("Found %d active stream(s) in '%s'", len(streams), log_group_name)

        for stream_name in streams:
            yield from self._fetch_stream_events(
                log_group_name, stream_name, start_ms, end_ms
            )

    def fetch_all_groups(
        self,
        log_group_names: list[str] | None = None,
        lookback_minutes: int = config.LOOKBACK_MINUTES,
    ) -> Generator[dict, None, None]:
        """Convenience wrapper — iterate over multiple log groups."""
        groups = log_group_names or config.LOG_GROUP_NAMES
        for group in groups:
            try:
                yield from self.fetch_events(group, lookback_minutes)
            except ClientError as exc:
                logger.error(
                    "Failed to fetch logs from '%s': %s", group, exc, exc_info=True
                )

    # ── Private helpers ───────────────────────────────────────────

    @staticmethod
    def _time_window(lookback_minutes: int) -> tuple[int, int]:
        now = datetime.now(timezone.utc)
        start = now - timedelta(minutes=lookback_minutes)
        return int(start.timestamp() * 1000), int(now.timestamp() * 1000)

    def _list_streams(
        self, log_group_name: str, start_ms: int
    ) -> Generator[str, None, None]:
        """Yield stream names that have had activity since *start_ms*."""
        paginator = self._client.get_paginator("describe_log_streams")
        pages = paginator.paginate(
            logGroupName=log_group_name,
            orderBy="LastEventTime",
            descending=True,
        )
        try:
            for page in pages:
                for stream in page.get("logStreams", []):
                    last_event = stream.get("lastEventTimestamp", 0)
                    if last_event < start_ms:
                        # Streams are ordered descending — stop early
                        return
                    yield stream["logStreamName"]
        except ClientError as exc:
            logger.error(
                "Could not list streams for '%s': %s", log_group_name, exc
            )

    def _fetch_stream_events(
        self,
        log_group_name: str,
        stream_name: str,
        start_ms: int,
        end_ms: int,
    ) -> Generator[dict, None, None]:
        """Yield all events from a single log stream within the time window."""
        kwargs: dict = {
            "logGroupName": log_group_name,
            "logStreamName": stream_name,
            "startTime": start_ms,
            "endTime": end_ms,
            "startFromHead": True,
        }
        while True:
            try:
                response = self._client.get_log_events(**kwargs)
            except ClientError as exc:
                logger.warning(
                    "Error reading stream '%s/%s': %s",
                    log_group_name,
                    stream_name,
                    exc,
                )
                break

            for event in response.get("events", []):
                yield {
                    "log_group": log_group_name,
                    "log_stream": stream_name,
                    "timestamp": event["timestamp"],
                    "message": event.get("message", ""),
                }

            # CloudWatch uses forward/backward tokens for pagination
            next_token = response.get("nextForwardToken")
            prev_token = kwargs.get("nextToken")
            if next_token == prev_token:
                # No more pages
                break
            kwargs["nextToken"] = next_token
