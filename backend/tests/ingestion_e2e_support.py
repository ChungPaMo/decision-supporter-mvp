"""Official CHUNGPAMO-2027 source reuse and explicit memory-only persistence boundaries."""
from contextlib import contextmanager, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import runpy
from unittest.mock import patch

from fastapi import Depends
from fastapi.testclient import TestClient
from app.api import ingest_assistance
from app.api.batches import get_service
from app.api.datasets import dataset_context
from app.api.ingest_history import get_history_service
from app.batches import capacity
from app.batches.service import BatchService
from app.ingest.history import TransformationService
from app.main import app
from tests.test_ingestion_history import HistoryMemoryRepository, HistoryTx

ROOT = Path(__file__).resolve().parents[2]
DATASET = 'CHUNGPAMO-2027'
MANIFEST = ROOT / 'contracts/examples/ingestion_e2e_source_manifest.json'


def official_sources():
    """Read existing owner outputs first; generate only into an absent ignored directory."""
    preferred = ROOT / 'modules/planning_engine/synthetic/data'
    target = preferred if preferred.exists() else ROOT / '.artifacts/ingestion-e2e-dataset'
    if not target.exists():
        resolved = target.resolve()
        if not resolved.is_relative_to((ROOT / '.artifacts').resolve()):
            raise RuntimeError('Generator destination must be inside ignored artifacts')
        # The owner generator can replace OUT, so never call it for an existing directory.
        module = runpy.run_path(str(ROOT / 'modules/planning_engine/synthetic/generate.py'), run_name='api_e2e_official_generator')
        module['main'].__globals__['OUT'] = resolved
        with redirect_stdout(io.StringIO()):
            module['main']()
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    sources = {}
    for name, expected in manifest['files'].items():
        content = (target / name).read_bytes()
        if hashlib.sha256(content).hexdigest() != expected:
            raise AssertionError('Existing official source differs from pinned gold; do not overwrite: ' + name)
        sources[name] = content
    return target, manifest, sources


class ScenarioTx(HistoryTx):
    def __init__(self, repo):
        super().__init__(repo)
        self.c = self


class ScenarioRepository(HistoryMemoryRepository):
    def __init__(self, dataset_id=DATASET):
        super().__init__(dataset_id)
        self.state.products.clear()  # No arbitrary P1 seed: all facts must come from official uploads.
        self.state.capacity = {section: [] for section in capacity.MODELS}

    @contextmanager
    def transaction(self):
        with super().transaction():
            yield ScenarioTx(self)


@contextmanager
def memory_api():
    """Real API/DTO/validators; only persistence reads/writes are test doubles."""
    repositories = {dataset: ScenarioRepository(dataset) for dataset in (DATASET, 'TISSUE-LEGACY')}
    def scoped_batch(dataset_id: str = Depends(dataset_context)):
        return BatchService(repositories[dataset_id])
    def scoped_history(dataset_id: str = Depends(dataset_context)):
        return TransformationService(repositories[dataset_id])
    def approved_rows(tx, section):
        return tx.s.capacity[section]
    def capacity_commit(tx, batch_id, actor, records):
        # Retain production reference, unit, duplicate and routing checks.
        capacity.validate_rows(tx, tx.get_batch(batch_id).entity, [(row.section, row.payload) for row in records])
        tx.mark_approved(batch_id, actor, len(records))
        for row in records:
            tx.s.capacity[row.section].append({'payload': row.payload, 'batch_id': batch_id})
        return len(records)
    replacements = {get_service: scoped_batch, get_history_service: scoped_history}
    previous = {key: app.dependency_overrides.get(key) for key in replacements}
    app.dependency_overrides.update(replacements)
    try:
        # load_master calls its factory directly, so route dependency overrides alone are insufficient.
        with patch.object(ingest_assistance, 'get_service', scoped_batch), \
             patch.object(capacity, 'approved_rows', approved_rows), patch.object(capacity, 'commit', capacity_commit):
            with TestClient(app) as client:
                yield client, repositories
    finally:
        for key, value in previous.items():
            if value is None:
                app.dependency_overrides.pop(key, None)
            else:
                app.dependency_overrides[key] = value


def upload(client, name, content, entity, dataset=DATASET, **settings):
    return client.post('/batches', params={'dataset_id': dataset}, files={'file': (name, content)}, data={
        'entity': entity, 'source_type': 'SYNTHETIC', 'source_note': 'Lee CHUNGPAMO-2027 official generator; TEST-DOUBLE-ONLY',
        'created_by': 'INGEST-E2E', **settings})


def approve(client, batch, dataset=DATASET, **changes):
    return client.post('/batches/' + batch['batch_id'] + '/approve', params={'dataset_id': dataset}, json={
        'approved_by': 'E2E-REVIEWER', 'expected_result_digest': batch['result_digest'], **changes})
