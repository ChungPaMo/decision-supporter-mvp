from typing import Annotated
from fastapi import APIRouter,Depends,Query
from sqlalchemy.exc import DBAPIError
from app.config import get_settings
from app.errors import ApiError,ErrorCode,ERROR_RESPONSES
from app.datasets import DatasetRepository,scope_error,check_id
from contracts.interfaces.dataset import DatasetCreate,DatasetDetail,LEGACY_DATASET

router=APIRouter(prefix='/datasets',tags=['datasets'],responses=ERROR_RESPONSES)


def dataset_context(dataset_id:str=Query(LEGACY_DATASET,description='Data scope only, not an authorization grant. Omitted = TISSUE-LEGACY, never all.')):
    return check_id(dataset_id)


def get_repository():
    if get_settings().persistence!='postgres':raise ApiError(501,ErrorCode.PERSISTENCE_DISABLED,'Dataset persistence is disabled.')
    from app.db import get_engine
    return DatasetRepository(get_engine())


Repo=Annotated[DatasetRepository,Depends(get_repository)]


def call(fn):
    try:return fn()
    except DBAPIError as exc:raise scope_error(exc) from None


@router.get('',response_model=list[DatasetDetail])
def list_datasets(repo:Repo):return call(repo.list)


@router.post('',response_model=DatasetDetail,status_code=201)
def create_dataset(body:DatasetCreate,repo:Repo):return call(lambda:repo.create(body))


@router.get('/{dataset_id}',response_model=DatasetDetail)
def detail_dataset(dataset_id:str,repo:Repo):
    result=call(lambda:repo.get(dataset_id))
    if result is None:raise ApiError(404,ErrorCode.DATASET_NOT_FOUND,'Dataset not found.')
    return result
