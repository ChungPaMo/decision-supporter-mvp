"""Dataset identifiers are data scope, never authentication grants."""
from datetime import datetime
from typing import Annotated,Literal
from pydantic import Field
from .base import StrictModel

LEGACY_DATASET='TISSUE-LEGACY'
DatasetId=Annotated[str,Field(pattern=r'^[A-Z][A-Z0-9_-]{0,39}$')]


class DatasetCreate(StrictModel):
    dataset_id: DatasetId
    dataset_name: str = Field(min_length=1,max_length=200)
    description: str = Field(min_length=1,max_length=2000)
    source_type: Literal['SYNTHETIC'] = 'SYNTHETIC'


class DatasetDetail(DatasetCreate):
    status: Literal['ACTIVE','ARCHIVED']
    created_at: datetime
    created_by: str | None
