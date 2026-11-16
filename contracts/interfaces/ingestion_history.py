"""Persistence evidence is distinct from an approval or a stateless preview."""
from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import Field
from .base import StrictModel
from .dataset import DatasetId
from .ingestion import TransformReply


class TransformationSummary(StrictModel):
    contract_version: str = 'ingestion-history-0.1'
    transformation_id: UUID
    dataset_id: DatasetId
    batch_id: UUID
    batch_status: str
    created_at: datetime
    created_by: str
    engine_version: str
    input_digest: str = Field(pattern=r'^[a-f0-9]{64}$')
    result_digest: str = Field(pattern=r'^[a-f0-9]{64}$')
    policy_digest: str = Field(pattern=r'^[a-f0-9]{64}$')
    manifest_digest: str = Field(pattern=r'^[a-f0-9]{64}$')
    output_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    persisted: Literal[True] = True
    approval_required: Literal[True] = True
    auto_approve: Literal[False] = False


class TransformationDetail(TransformationSummary):
    preview: TransformReply


class TransformationPage(StrictModel):
    items: list[TransformationSummary]
    total: int
    limit: int
    offset: int
