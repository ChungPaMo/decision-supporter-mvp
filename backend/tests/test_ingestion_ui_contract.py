"""Keep the handoff's routes and request examples tied to real OpenAPI/DTOs."""
import json
from pathlib import Path
import re
import pytest
from app.main import app
from app.batches.schemas import ApproveRequest, RevalidateRequest
from contracts.interfaces.ingestion import SalesTransformPolicy

DOC = Path(__file__).resolve().parents[2] / 'docs/INGESTION_UI_API_HANDOFF.md'


def test_handoff_http_routes_exist_in_actual_openapi():
    source = DOC.read_text(encoding='utf-8')
    paths = app.openapi()['paths']
    routes = re.findall(r'`(GET|POST) (/[^` ?]+)', source)
    assert len(routes) >= 15
    for method, path in routes:
        assert path in paths and method.lower() in paths[path], (method, path)


@pytest.mark.parametrize('model', [SalesTransformPolicy, RevalidateRequest, ApproveRequest])
def test_handoff_request_examples_validate_against_current_models(model):
    source = DOC.read_text(encoding='utf-8')
    match = re.search(r'<!-- contract:' + model.__name__ + r' -->\s*```json\s*(.*?)\s*```', source, re.S)
    assert match, model.__name__
    body = json.loads(match.group(1))
    assert set(body) <= set(model.model_fields)
    model.model_validate(body)
