"""Coordinates are 1-based indexes in the original workbook."""
from typing import Annotated, Literal

from pydantic import Field, model_validator

from .base import StrictModel


Row = Annotated[int, Field(ge=1, le=100_000, strict=True)]
Column = Annotated[int, Field(ge=1, le=64, strict=True)]
Sha256 = Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]


class XlsxTableSelection(StrictModel):
    source_sha256: Sha256
    sheet: str = Field(min_length=1, max_length=31)
    header_row: Row
    data_start_row: Row
    data_end_row: Row
    first_col: Column
    last_col: Column

    @model_validator(mode='after')
    def ordered_bounds(self):
        if not self.header_row < self.data_start_row <= self.data_end_row or self.first_col > self.last_col:
            raise ValueError('Specify an ordered header, body rows and column interval')
        return self


class XlsxSheetLayout(StrictModel):
    name: str
    visibility: Literal['visible', 'hidden', 'veryHidden']
    max_row: int
    max_col: int


class XlsxLayoutCell(StrictModel):
    row: Row
    col: Column
    kind: Literal['text', 'number', 'date', 'bool', 'formula', 'error', 'merged', 'empty']
    value: str | None = Field(max_length=80)


class XlsxLayoutWindow(StrictModel):
    sheet: str
    first_row: Row
    last_row: Row
    first_col: Column
    last_col: Column
    hidden_columns: list[Column]
    merged_ranges: list[str]
    merges_truncated: bool
    cells: list[XlsxLayoutCell] = Field(max_length=1600)


class XlsxLayoutReply(StrictModel):
    source_sha256: Sha256
    filename: str
    sheets: list[XlsxSheetLayout] = Field(max_length=8)
    window: XlsxLayoutWindow | None = None
    persisted: Literal[False] = False
