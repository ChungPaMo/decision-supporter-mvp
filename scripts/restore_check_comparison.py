"""Compare only the PostgreSQL array-cast rewrite observed in the 0009 archive."""
import re
from dataclasses import dataclass


COLUMNS = {
    'public.bom_header.ck_status_bomstatus': 'status',
    'public.bom_line.ck_component_type_componenttype': 'component_type',
    'public.forecast_run.forecast_run_status_check': 'status',
    'public.import_batch.ck_batch_entity': 'entity',
    'public.import_batch.ck_source_type_sourcetype': 'source_type',
    'public.import_batch.ck_status_batchstatus': 'status',
    'public.inventory.ck_item_type_itemtype': 'item_type',
    'public.product.ck_product_type_producttype': 'product_type',
    'public.sales_order.ck_order_status': 'status',
    'public.unit.ck_dimension_unitdimension': 'dimension',
}

_LITERAL = r"'([A-Za-z_][A-Za-z_0-9]*)'::character varying"
_ITEM_CAST = re.compile(rf"\({_LITERAL}\)::text")
_CHOICES = re.compile(r"CHECK \(\(\(([a-z_]+)\)::text = ANY \(ARRAY\[(.+)\]\)\)\)")


@dataclass(frozen=True)
class CheckAttributes:
    column_type: str
    collation: str
    nullable: bool
    validated: bool
    local: bool
    no_inherit: bool
    inheritance_count: int
    has_parent: bool


def equivalent_array_cast(name, original, restored, original_attributes, restored_attributes):
    """Require exactly the expected dump/restore rewrite and matching SQL attributes."""
    column = COLUMNS.get(name)
    if not column or original_attributes != restored_attributes:
        return False
    matched = _CHOICES.fullmatch(restored)
    if not matched or matched[1] != column:
        return False
    values = [_ITEM_CAST.fullmatch(item) for item in matched[2].split(', ')]
    if any(value is None for value in values):
        return False
    literals = ', '.join(f"'{value[1]}'::character varying" for value in values)
    return original == f"CHECK ((({column})::text = ANY ((ARRAY[{literals}])::text[])))"
