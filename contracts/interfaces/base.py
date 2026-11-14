"""Shared transport primitives. No planning policy or calculation lives here."""
from typing import Annotated
from pydantic import BaseModel, ConfigDict, Field

Code = Annotated[str, Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,39}$')]
Month = Annotated[str, Field(pattern=r'^([1-9][0-9]{3}|0[1-9][0-9]{2}|00[1-9][0-9]|000[1-9])-(0[1-9]|1[0-2])$')]
DecimalValue = Annotated[str, Field(pattern=r'^[0-9]{1,14}(\.[0-9]{1,6})?$')]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')
