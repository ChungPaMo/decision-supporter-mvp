"""Generator output against real API validators with isolated memory persistence.
No generated dataset is committed, no SQL connection is made, no owner file edited.
"""
from pathlib import Path
import runpy
import pytest
from scripts.verify_synthetic_contracts import verify,FILES
from app.ingest.pipeline import run_preview

ROOT=Path(__file__).resolve().parents[2]


@pytest.fixture(scope='module')
def report(tmp_path_factory):
    target=tmp_path_factory.mktemp('cp-paper-synthetic')/'generated'
    module=runpy.run_path(str(ROOT/'modules/planning_engine/synthetic/generate.py'),run_name='isolated_generator_test')
    main=module['main']
    # Redirect only this test invocation's output to a private temporary directory.
    main.__globals__['OUT']=target
    main()
    return verify(target)


@pytest.mark.parametrize('filename,entity',FILES)
def test_nine_upload_contracts_in_explicit_memory_api(report,filename,entity):
    item=next(r for r in report['normal'] if r['file']==filename)
    assert item['entity']==entity
    assert item['utf8_bom'] and len(item['sha256'])==64
    assert item['status']=='READY_FOR_APPROVAL' and item['errors']==0 and item['holds']==[]
    assert item['double_status']=='APPROVED' and item['double_approval_http']==200
    assert item['duplicate_http']==409


@pytest.mark.parametrize('filename,code',[
    ('bom_unknown_material.csv','MATERIAL_NOT_REGISTERED'),('demand_missing_qty.csv','QTY_MISSING'),
    ('inventory_negative_qty.csv','QTY_NEGATIVE'),('products_unknown_unit.csv','UNIT_UNKNOWN')])
def test_true_error_fixtures_blocked(report,filename,code):
    item=next(r for r in report['errors'] if r['file']==filename)
    assert item['status']=='HAS_ERRORS' and item['blocking_errors']>0
    assert any(i['code']==code and i['location']['row']>=2 for i in item['issues'])


def test_generator_error_expectations_do_not_redefine_existing_contract(report):
    byname={r['file']:r for r in report['errors']}
    month=byname['demand_bad_period_format.csv']
    duplicate=byname['demand_duplicate_period.csv']
    # YYYY/MM is an accepted ingest spelling. Equal duplicate demand is deduplicated with a warning.
    assert month['status']=='READY_FOR_APPROVAL' and month['blocking_errors']==0
    assert duplicate['status']=='READY_FOR_APPROVAL'
    assert any(i['code']=='DUPLICATE_ROW_IDENTICAL' for i in duplicate['issues'])
    assert report['dirty_sales']['status']=='MAPPING_HOLD'


def test_truly_invalid_month_and_conflicting_duplicate_still_block():
    for rows,code in [('P1,2026-13,1,EA\n','PERIOD_INVALID'),
                      ('P1,2026-12,1,EA\nP1,2026-12,2,EA\n','DUPLICATE_KEY_CONFLICT')]:
        result=run_preview('error.csv',('product_id,period,demand_qty,unit\n'+rows).encode(),'monthly_demand')
        assert result.status=='HAS_ERRORS'
        assert any(i.code==code for s in result.sheets for i in s.issues)


def test_capacity_routing_semantics_remain_separate(report):
    d=report['capacity_dto']
    assert (d['resources'],d['limits'],d['budgets'],d['steps'])==(6,3,18,27)
    assert len(d['shared_saw_products'])==9 and d['concurrent_labor_steps']==9
    assert d['periods']==['2027-01','2027-02','2027-03']
    assert d['inventory_dates']==['2026-12-31']
    assert report['counts_in_memory']=={'products':9,'materials':9,'boms':9,'inventory':18,'demand':498}
