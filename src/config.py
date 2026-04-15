"""
config.py
Centralised configuration loaded from environment variables.
"""

import os


class Config:
    # ── AWS Region ────────────────────────────────────────────────
    AWS_REGION: str = os.environ.get("AWS_REGION", "us-east-1")

    # ── CloudWatch Logs ───────────────────────────────────────────
    LOG_GROUP_NAMES: list[str] = [
        name.strip()
        for name in os.environ.get("LOG_GROUP_NAMES", "").split(",")
        if name.strip()
    ]

    LOOKBACK_MINUTES: int = int(os.environ.get("LOOKBACK_MINUTES", "15"))

    # ── DynamoDB ──────────────────────────────────────────────────
    DYNAMODB_TABLE_NAME: str = os.environ.get(
        "DYNAMODB_TABLE_NAME", "lambda-log-analysis"
    )
    DYNAMODB_TTL_DAYS: int = int(os.environ.get("DYNAMODB_TTL_DAYS", "30"))

    # ── Logging ───────────────────────────────────────────────────
    LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO").upper()

    def validate(self) -> None:
        """Raise ValueError early if required config is missing."""
        if not self.LOG_GROUP_NAMES:
            raise ValueError("LOG_GROUP_NAMES env var must contain at least one log group.")
        if not self.DYNAMODB_TABLE_NAME:
            raise ValueError("DYNAMODB_TABLE_NAME env var is required.")


config = Config()
