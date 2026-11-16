"""Preserved large-source regression expanded to the official dataset full API journey."""
from tests.test_ingestion_api_e2e import verify_official_journey


def test_over_80000_transactions_exactly_match_generated_monthly_gold():
    result = verify_official_journey()
    assert result['counts']['source_rows'] == 86_214
    assert result['counts']['monthly_demand_rows'] == 498
    assert result['gold_rows_equal'] and result['history_link_verified'] and result['source_bytes_unchanged']
