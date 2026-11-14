# File classifier · 이훤

`src/file_classifier.classify(ClassificationInput) -> ClassificationOutput`을 구현한다. 현재는 NotImplementedError이며 임의 entity/점수를 만들지 않는다. 수동 유형 선택은 기존 업로드 화면에서 가능하다.

입력은 파일 정보·SHA256·시트명·컬럼·허용한 최대 20개 샘플 행이다. 원본 파일 전체, 로컬 경로, DB 연결은 받지 않는다. 후보 점수·추천·근거·HOLD·버전을 반환하며 사용자 승인과는 별개다.

CSV 시트명은 null, format은 csv/xlsx/null이다. /classifications(JSON)와 /classifications/file(multipart)는 같은 classify 함수를 사용한다. AVAILABLE=True는 구현 상태 메타데이터에 반영된다. 상세 수용 기준은 [TEAM_HANDOFF](../../docs/TEAM_HANDOFF.md)를 따른다.

```powershell
./.venv/Scripts/python.exe -m pytest modules/file_classifier -q
```

공유 DTO는 contracts/interfaces/modules.py다. 공통 API·DB 저장·승인 gate를 이 모듈에서 수정하지 않는다. 경계 변경은 김대영에게 계약 변경을 요청한다.
