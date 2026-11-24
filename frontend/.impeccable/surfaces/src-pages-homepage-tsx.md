---
version: 1
slug: "src-pages-homepage-tsx"
primary_target: "src/pages/HomePage.tsx"
related_targets: ["src/styles/theme.css","src/app/Shell.tsx"]
---

# 홈 (그리고 같은 틀을 쓰는 네 화면)

Scope: 앱 전체의 틀과 홈 화면. 자료 넣기, 수요 예측, 생산계획, 기록이 같은 문법을 따른다.
Mode: Operate.

Audience and job: 제조 기업의 생산·계획 담당자가 매달 데스크톱에서 다음 석 달의 생산계획을 고른다. 공모전 심사위원에게 큰 화면으로 시연한다.
Task: 화면을 열자마자 어디가 막히는지 알고, 조건을 바꿔 다시 계산하러 간다.
Content: 서버에서 읽은 실제 계획 결과 (설비·인력 사용률, 세 안, 수요와 예측).
Constraints: 한국어, 밝은 화면, 화면에 요소를 많이 올리지 않는다, 서버 값만 보여 준다.
User said: 지금까지의 화면은 "한 화면에 너무 많고", "촌스럽고 어설펐다". 원하는 것은 "요즘 서비스 같은 세련됨". 기준 서비스는 토스, Linear, Stripe 대시보드.

## Direction contract

THESIS: 화면의 첫 문장이 계획의 병목을 말한다 ("2월, 롤 절단기가 한도를 다 씁니다"). 숫자 카드 네 개를 늘어놓는 대시보드 머리를 쓰지 않는다.

OWN-WORLD: 흰 작업면과 한 단계 낮은 회색 메뉴. 강조색은 파랑 하나이며 주된 버튼과 선택에만 쓴다. 빨강과 주황은 막힌 칸과 빠듯한 칸에만 나온다. 테두리 상자는 표와 입력 묶음에만, 나머지는 여백과 가는 선. Pretendard 한 가지 글꼴, 표 숫자는 고정폭 숫자.

STORY: 사용자는 어디가 막히는지 읽고, 어느 안이 실행 가능한지 보고, 잔업을 넣어 다시 계산하러 간다.

FIRST VIEWPORT: 왼쪽 232px 회색 메뉴. 작업면 맨 위 왼쪽에 병목 문장(약 32px)과 한 줄 설명, 그 아래 파랑 버튼 "잔업을 넣어 다시 계산". 이어서 왼쪽에 설비·인력 사용률 표(빠듯한 순), 오른쪽에 세 안 목록.

FORM: 분야의 표준 제품 화면을 그대로, 완성도 높게. 사용자가 두 번 다시 뽑은 뒤 "요즘 서비스 같은 세련됨"을 골라 표준 쪽으로 정했다. seed:c26ff5b1ea9bd49a

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
