"""Same-DB schema isolation. Never search a different dataset as a fallback."""
from contextlib import contextmanager
import re
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError,IntegrityError,OperationalError,InterfaceError
from app.errors import ApiError,ErrorCode
from contracts.interfaces.dataset import LEGACY_DATASET,DatasetDetail

from .dataset_schema_v1 import ROOT_TABLES, schema_for as _schema_for
from .dataset_schema_v3 import provision_schema


def check_id(value):
    if not re.fullmatch(r'[A-Z][A-Z0-9_-]{0,39}',value):
        raise ApiError(422,ErrorCode.DATASET_INVALID,'Invalid dataset identifier.')
    return value


def schema_for(value):
    check_id(value)
    return _schema_for(value)


def scope_error(exc):
    return ApiError(503 if isinstance(exc,(OperationalError,InterfaceError)) else 500,
                    ErrorCode.DB_UNAVAILABLE if isinstance(exc,(OperationalError,InterfaceError)) else ErrorCode.PERSISTENCE_ERROR,
                    'Dataset storage unavailable or inconsistent; no fallback was used.')


class ScopedConnection:
    def __init__(self,engine):self.engine=engine;self.options={}
    def execution_options(self,**options):self.options.update(options);return self
    def __enter__(self):
        self.c=self.engine.base.connect().execution_options(**self.options)
        try:
            self.c.exec_driver_sql(f'SET LOCAL search_path TO "{self.engine.schema}", pg_catalog')
            return self.c
        except BaseException:self.c.close();raise
    def __exit__(self,*args):self.c.close()


class DatasetEngine:
    def __init__(self,base,dataset_id,schema):
        if schema!=schema_for(dataset_id):raise ValueError('Dataset schema mapping mismatch')
        self.base=base;self.dataset_id=dataset_id;self.schema=schema
    def connect(self):return ScopedConnection(self)
    @contextmanager
    def begin(self):
        with self.base.begin() as c:
            c.exec_driver_sql(f'SET LOCAL search_path TO "{self.schema}", pg_catalog')
            yield c


def get_dataset_engine(dataset_id):
    from app.db import get_engine
    check_id(dataset_id)
    base=get_engine()
    try:
        with base.connect() as c:
            row=c.execute(text('SELECT dataset_id,schema_name,status FROM public.dataset WHERE dataset_id=:d'),{'d':dataset_id}).mappings().first()
        if row is None:raise ApiError(404,ErrorCode.DATASET_NOT_FOUND,'Dataset not found.')
        if row['status']!='ACTIVE':raise ApiError(409,ErrorCode.DATASET_INACTIVE,'Dataset is archived.')
        return DatasetEngine(base,dataset_id,row['schema_name'])
    except DBAPIError as exc:raise scope_error(exc) from None




class DatasetRepository:
    def __init__(self,database):self.database=database
    def list(self):
        with self.database.connect() as c:
            return [DatasetDetail.model_validate(r) for r in c.execute(text('SELECT dataset_id,dataset_name,description,source_type,status,created_at,created_by FROM public.dataset ORDER BY dataset_id')).mappings()]
    def get(self,id):
        check_id(id)
        return next((r for r in self.list() if r.dataset_id==id),None)
    def create(self,request):
        try:
            with self.database.begin() as c:
                c.execute(text('SELECT pg_advisory_xact_lock(880008)'))
                if c.execute(text('SELECT 1 FROM public.dataset WHERE dataset_id=:d'),{'d':request.dataset_id}).scalar():
                    raise ApiError(409,ErrorCode.DATASET_EXISTS,'Dataset ID already exists.')
                provision_schema(c,request.dataset_id)
                c.execute(text('''INSERT INTO public.dataset(dataset_id,dataset_name,description,source_type,schema_name)
                    VALUES(:dataset_id,:dataset_name,:description,:source_type,:schema)'''),{**request.model_dump(),'schema':schema_for(request.dataset_id)})
            return self.get(request.dataset_id)
        except IntegrityError:raise ApiError(409,ErrorCode.DATASET_EXISTS,'Dataset ID or schema already exists.') from None
