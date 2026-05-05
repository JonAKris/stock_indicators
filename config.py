"""
Configuration loader for the Stock Indicators ETL project.
Reads settings from environment variables (loaded from .env file).
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Network settings
    TIMEOUT: int = int(os.getenv("TIMEOUT", "180"))
    RETRIES: int = int(os.getenv("RETRIES", "3"))
    BACKOFF_FACTOR: float = float(os.getenv("BACKOFF_FACTOR", "0.3"))
    
    # EODData API
    API_KEY: str = os.environ["EOD_API_KEY"]
    API_BASE_URL: str = os.getenv("EOD_BASE_URL", "https://api.eoddata.com/")

    # PostgreSQL
    DB_HOST: str = os.getenv("DB_HOST", "msa1.sumo.computer")
    DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
    DB_NAME: str = os.getenv("DB_NAME", "stocks")
    DB_USER: str = os.getenv("DB_USER", "stockman")
    DB_PASS: str = os.environ["DB_PASS"]

    # Sync behaviour
    # Comma-separated list of exchange codes; empty/None means all exchanges
    EXCHANGES: list[str] = [
        e.strip().upper()
        for e in os.getenv("EXCHANGES", "").split(",")
        if e.strip()
    ]

    # Quote parameters
    QUOTE_INTERVAL: str = os.getenv("QUOTE_INTERVAL", "d")

    # Rate-limiting
    REQUEST_DELAY: float = float(os.getenv("REQUEST_DELAY", "0.25"))

    @property
    def dsn(self) -> str:
        return (
            f"host={self.DB_HOST} port={self.DB_PORT} "
            f"dbname={self.DB_NAME} user={self.DB_USER} "
            f"password={self.DB_PASS}"
        )
