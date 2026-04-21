from unittest.mock import Mock

from log_fetcher import LogFetcher


def test_filter_group_events_omits_none_next_token():
    client = Mock()
    client.filter_log_events.side_effect = [
        {
            "events": [
                {
                    "logStreamName": "stream-a",
                    "timestamp": 1_710_000_000_000,
                    "message": "first",
                }
            ],
            "nextToken": "token-1",
        },
        {
            "events": [
                {
                    "logStreamName": "stream-b",
                    "timestamp": 1_710_000_000_001,
                    "message": "second",
                }
            ]
        },
    ]

    fetcher = LogFetcher.__new__(LogFetcher)
    fetcher._client = client
    fetcher.last_errors = []

    events = list(fetcher._filter_group_events("/aws/lambda/test", 1000, 2000))

    assert [event["message"] for event in events] == ["first", "second"]
    assert client.filter_log_events.call_count == 2

    first_call = client.filter_log_events.call_args_list[0].kwargs
    second_call = client.filter_log_events.call_args_list[1].kwargs

    assert "nextToken" not in first_call
    assert second_call["nextToken"] == "token-1"
