"""Compare the 55 baseline skipped DB cases with actual JUnit execution evidence.

No database access. Evidence stays ignored; only the generated Markdown is published.
"""
import argparse
import ast
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', default='.artifacts/db_regression_baseline.xml')
    parser.add_argument('--result', default='.artifacts/db_regression_final.xml')
    args = parser.parse_args()
    baseline = ET.parse(ROOT / args.baseline)
    final = ET.parse(ROOT / args.result)
    skipped = [case for case in baseline.iter('testcase') if case.find('skipped') is not None]
    assert len(skipped) == 55, 'Expected exactly the original 55 DB cases'
    actual = {(case.get('classname'), case.get('name')): case for case in final.iter('testcase')}
    groups = {
        'test_db_rules': ('R', 'unit, import_batch, batch_source_file, product, material, BOM, inventory, monthly_demand, demand_forecast, approved-input view'),
        'test_sql_repository': ('C', 'import_batch/source file, approved product/material/BOM/inventory/demand and SQL repository queries'),
        'test_forecast_runs': ('C', 'approved input batches, forecast_run, forecast_run_input, demand_forecast, input/version/digest snapshots'),
        'test_health': ('Q', 'health SELECT/current_database'),
        'test_postgres_integration': ('C', 'Alembic schema and API upload/mapping/approval/master queries'),
    }
    lines = [
        '# 기존 DB 테스트 55개 개별 감사', '',
        '2026-11-15. 기준 `bbf70b5e66f7c61b3b43ac87a034b61b684198e0`의 비DB 실행 JUnit과 이번 실제 DB 실행 JUnit을 대조했다. **55/55 passed, failed 0, skipped 0**.', '',
        '생성: `python scripts/audit_db_tests.py`. 입력은 Git 제외 `.artifacts/db_regression_baseline.xml`, `.artifacts/db_regression_final.xml`이다. 호스트명·로컬 경로가 포함된 원본 JUnit은 업로드하지 않는다.', '',
        '## 모든 행에 적용되는 실행 조건과 위험', '',
        '- 기존 skip: `test_engine` fixture의 `--no-db` 분기. 이 모드에서는 DB 접속 자체를 차단한다. 승인 토큰/대상이 잘못되면 이제 실패하며 skip으로 숨기지 않는다.',
        '- 환경 E: PostgreSQL 16.6, `127.0.0.1:55433/chungpamo_regression`, `chungpamo_regression_runner`, 별도 비밀번호·sentinel·현재 작업의 초기화 승인. Docker 프로젝트/컨테이너/볼륨/네트워크도 검사한다.',
        '- 공통 DDL: 세션 fixture가 **이 DB 안에서만** public/CP 테스트 데이터셋/과거 검증 스키마 DROP 및 재생성, public Alembic 0001→0008 적용을 수행한다. 이 DDL은 테스트별 rollback으로 되돌아가지 않는다.',
        '- 따라서 아래 Q(조회)와 R(rollback)도 개발 DB에서는 안전하지 않다. 모든 행의 개발 DB 실행 위험은 **금지**, 격리 회귀 DB 실행 가능 여부는 **가능·실행 완료**다.',
        '- R: 본문은 conn 트랜잭션/저장점에서 실행 후 rollback. C: 실제 commit/다중 연결 및 TRUNCATE CASCADE 정리, 전체 rollback 아님. Q: 본문 조회만. H: 과거 스키마 DDL/버전 왕복, commit, 전체 rollback 아님.',
        '- 객체 열은 각 테스트 모듈에서 사용하는 객체 범위다. 트리거·FK·view의 종속 객체 및 공통 세션 DDL도 포함해서 해석한다.', '',
        '## 개별 실행 결과', '',
        '| # | 파일·함수(매개변수 포함) | 기존 skip / 필요 환경 | 객체 범위 | 변경·rollback | 개발 위험 / 격리 실행 | 실제 결과 |',
        '| --- | --- | --- | --- | --- | --- | --- |',
    ]
    for number, case in enumerate(skipped, 1):
        key = (case.get('classname'), case.get('name'))
        result = actual.get(key)
        assert result is not None, f'Missing case: {key}'
        assert all(result.find(tag) is None for tag in ('failure', 'error', 'skipped')), f'Not passed: {key}'
        path = Path(*case.get('classname').split('.')).with_suffix('.py')
        name = case.get('name')
        function = name.split('[', 1)[0]
        tree = ast.parse((ROOT / path).read_text(encoding='utf-8-sig'))
        node = next(n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == function)
        mode, objects = groups[path.stem]
        if function == 'test_rows_cannot_be_added_or_changed_after_the_approving_transaction_commits':
            mode = 'C: commit + guarded TRUNCATE'
        if function == 'test_empty_test_db_migrates_down_to_0001_and_up_sequentially':
            mode = 'H: regression_history_0001, 0005→0001→0002→0003→0004→0005'
        if function == 'test_0005_preserves_legacy_results_and_allows_new_run':
            mode = 'H+C: regression_history_0005, 0005↔0004; current API 0008'
        location = f'[{path.as_posix()}]({"../"+path.as_posix()}) `{name}` (L{node.lineno})'
        lines.append(f'| {number} | {location} | --no-db / E | {objects} | {mode} | 금지 / 가능 | PASS |')
    lines += ['', '추가 DB 테스트 4개는 [주 검증 보고서](DB_REGRESSION_E2E_VERIFICATION.md)에 별도 기록하며 원래 55개 통계에 섞지 않는다.']
    body = '\n'.join(lines)
    (ROOT / 'docs/DB_REGRESSION_TEST_AUDIT.md').write_text(body + '\n', encoding='utf-8')
    print('55 original DB cases individually matched: 55 passed, 0 failed, 0 skipped.')


if __name__ == '__main__':
    main()
