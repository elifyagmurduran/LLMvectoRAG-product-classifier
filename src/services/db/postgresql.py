"""PostgreSQL database connector (scaffold — not yet implemented)."""
from __future__ import annotations
import pandas as pd
from src.services.db.base import DatabaseConnector
from src.utils.logging import get_logger

logger = get_logger("pipeline.db.postgresql")


class PostgreSQLConnector(DatabaseConnector):
    """Connect to PostgreSQL via username/password authentication.

    To activate: implement the methods below, then register in factory.py:
        factory.register_db("postgresql", PostgreSQLConnector)

    Uses psycopg2 + SQLAlchemy. Embedding columns use the pgvector extension
    cast: :col::vector(1024). See docs/IMPL_GUIDE_DATABASE.md for full details.

    Args:
        host: PostgreSQL server hostname.
        port: Port number (default 5432).
        database: Database name.
        username: Database username.
        password: Database password.
        schema_name: Default schema.
        table: Default table name.
        primary_key: Primary key column name.
    """

    def __init__(self, host: str, port: int = 5432, database: str = "",
                 username: str = "", password: str = "",
                 schema_name: str = "public", table: str = "promo_bronze",
                 primary_key: str = "id", **kwargs):
        self._host = host
        self._port = port
        self._database = database
        self._username = username
        self._password = password
        self._schema = schema_name
        self._table = table
        self._pk = primary_key
        self._engine = None

    @property
    def full_table_name(self) -> str:
        return f"{self._schema}.{self._table}"

    def connect(self) -> None:
        raise NotImplementedError(
            "PostgreSQLConnector.connect is not yet implemented. "
            "See docs/IMPL_GUIDE_DATABASE.md for the implementation spec."
        )

    def disconnect(self) -> None:
        raise NotImplementedError(
            "PostgreSQLConnector.disconnect is not yet implemented. "
            "See docs/IMPL_GUIDE_DATABASE.md for the implementation spec."
        )

    def fetch_batch(self, query: str, params: dict | None = None,
                    batch_size: int = 256) -> pd.DataFrame:
        raise NotImplementedError(
            "PostgreSQLConnector.fetch_batch is not yet implemented. "
            "See docs/IMPL_GUIDE_DATABASE.md for the implementation spec."
        )

    def update_rows(self, table: str, updates: list[dict],
                    key_column: str = "id") -> int:
        raise NotImplementedError(
            "PostgreSQLConnector.update_rows is not yet implemented. "
            "See docs/IMPL_GUIDE_DATABASE.md for the implementation spec."
        )

    def execute(self, query: str, params: dict | None = None) -> None:
        raise NotImplementedError(
            "PostgreSQLConnector.execute is not yet implemented. "
            "See docs/IMPL_GUIDE_DATABASE.md for the implementation spec."
        )
