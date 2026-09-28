"""DocumentStore porti: yozuvlar + qidiruv, bitta tranzaksiya va tenant kontekstida."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from .sql_docs import SqlDocumentRecords
from .sql_search import SqlDocumentSearch


class SqlDocumentStore(SqlDocumentRecords, SqlDocumentSearch):
    def __init__(self, conn: AsyncConnection, tenant_id: UUID) -> None:
        SqlDocumentRecords.__init__(self, conn, tenant_id)
        SqlDocumentSearch.__init__(self, conn, tenant_id)
