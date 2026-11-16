"""PostgreSQL adapter. Every table and batch reference uses the selected dataset schema."""
import json
from sqlalchemy import text
from app.batches.sql_repository import SqlBatchRepository, SqlBatchTx


class SqlTransformationTx(SqlBatchTx):
    def lock_input(self, input_digest):
        # Key includes dataset through input_digest; locks live only for this transaction.
        self.c.execute(text('SELECT pg_advisory_xact_lock(:key)'),
                       {'key': int(input_digest[:16], 16) - (1 << 63)})

    def find_transformation(self, input_digest):
        row = self.c.execute(text('SELECT * FROM ingestion_transformation WHERE input_digest=:d'),
                             {'d': input_digest}).mappings().first()
        return dict(row) if row else None

    def get_transformation(self, transformation_id):
        row = self.c.execute(text('SELECT * FROM ingestion_transformation WHERE transformation_id=:id'),
                             {'id': transformation_id}).mappings().first()
        return dict(row) if row else None

    def list_transformations(self, limit, offset):
        total = self.c.execute(text('SELECT count(*) FROM ingestion_transformation')).scalar_one()
        rows = self.c.execute(text('''SELECT t.transformation_id,t.dataset_id,t.batch_id,t.created_at,
            t.input_digest,t.result_digest,t.policy_digest,t.output_sha256,t.manifest_digest,
            t.manifest->>'created_by' AS created_by,t.manifest->>'engine_version' AS engine_version,b.status AS batch_status
            FROM ingestion_transformation t JOIN import_batch b ON b.batch_id=t.batch_id
            ORDER BY t.created_at DESC,t.transformation_id DESC LIMIT :l OFFSET :o'''),
                              {'l': limit, 'o': offset}).mappings().all()
        return [dict(row) for row in rows], total

    def transformation_sources(self, transformation_id):
        rows = self.c.execute(text('SELECT filename,content FROM ingestion_transform_source WHERE transformation_id=:id ORDER BY source_index'),
                              {'id': transformation_id}).all()
        return [(row.filename, bytes(row.content)) for row in rows]

    def insert_transformation(self, record, files):
        self.c.execute(text('''INSERT INTO ingestion_transformation
            (transformation_id,dataset_id,batch_id,created_at,input_digest,result_digest,policy_digest,output_sha256,manifest_digest,manifest)
            VALUES(:transformation_id,:dataset_id,:batch_id,:created_at,:input_digest,:result_digest,:policy_digest,:output_sha256,:manifest_digest,CAST(:manifest AS jsonb))'''),
            {**record, 'manifest': json.dumps(record['manifest'], ensure_ascii=False)})
        for source, (_, content) in zip(record['manifest']['result']['sources'], files):
            self.c.execute(text('''INSERT INTO ingestion_transform_source
                (transformation_id,source_index,filename,sha256,content,size_bytes)
                VALUES(:id,:i,:name,:sha,:content,:size)'''),
                {'id': record['transformation_id'], 'i': source['source_index'], 'name': source['filename'],
                 'sha': source['sha256'], 'content': content, 'size': len(content)})


class SqlTransformationRepository(SqlBatchRepository):
    def transaction(self):
        from contextlib import contextmanager
        @contextmanager
        def transaction():
            # Parent adapter owns commit/rollback and sanitized DB exception mapping.
            with super(SqlTransformationRepository, self).transaction() as tx:
                yield SqlTransformationTx(tx.c)
        return transaction()
