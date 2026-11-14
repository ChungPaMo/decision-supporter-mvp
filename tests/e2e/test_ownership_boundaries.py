"""Enforce import boundaries and one forecast implementation without using any DB."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_production_modules_do_not_depend_on_backend_ui_or_database():
    folders = [ROOT / 'modules/file_classifier/src', ROOT / 'modules/planning_engine/engine/forecast']
    for folder in folders:
        for path in folder.rglob('*.py'):
            imports = []
            for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
                if isinstance(node, ast.Import): imports.extend(alias.name for alias in node.names)
                if isinstance(node, ast.ImportFrom) and node.module: imports.append(node.module)
            assert not {name.split('.')[0] for name in imports} & {'app', 'sqlalchemy', 'psycopg', 'frontend'}, path


def test_single_forecast_implementation_and_unchanged_migrations():
    assert not (ROOT / 'engine').exists()
    assert (ROOT / 'modules/planning_engine/engine/forecast/service.py').is_file()
    import engine.forecast
    assert Path(engine.forecast.__file__).resolve().is_relative_to(ROOT / 'modules/planning_engine')
    assert sorted(p.name[:4] for p in (ROOT / 'backend/migrations/versions').glob('*.py')) == ['0001', '0002', '0003', '0004', '0005']
