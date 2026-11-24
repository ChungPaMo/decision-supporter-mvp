---
name: 충파모
description: 제조 생산계획 의사결정 지원. 흰 작업면, 회색 메뉴, 파랑 하나.
colors:
  ink: "#191f28"
  ink-2: "#333d4b"
  text: "#4e5968"
  muted: "#5d6875"
  faint: "#6b7684"
  line: "#e5e8eb"
  line-2: "#f0f2f4"
  line-hover: "#c9ced6"
  wash: "#f7f8fa"
  bg: "#ffffff"
  side-bg: "#f7f8fa"
  accent: "#2563eb"
  accent-press: "#1d4ed8"
  accent-wash: "#eaf2ff"
  accent-ink: "#1d4ed8"
  ok: "#087a4e"
  ok-wash: "#e6f6ee"
  warn: "#9a5b00"
  warn-wash: "#fff3d6"
  warn-mark: "#f5a524"
  bad: "#d92d3a"
  bad-wash: "#ffecee"
  h0: "#f4f5f7"
  h3: "#ffedc2"
  h4: "#ffd6da"
  bar-neutral: "#b0b8c1"
typography:
  display:
    fontFamily: "Pretendard Variable, Pretendard, -apple-system, BlinkMacSystemFont, Segoe UI, Malgun Gothic, sans-serif"
    fontSize: "2.13rem"
    fontWeight: 700
    lineHeight: 1.22
    letterSpacing: "-0.035em"
  headline:
    fontFamily: "Pretendard Variable, Pretendard, -apple-system, BlinkMacSystemFont, Segoe UI, Malgun Gothic, sans-serif"
    fontSize: "1.73rem"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-0.035em"
    fontFeature: "tnum"
  headline-sm:
    fontFamily: "Pretendard Variable, Pretendard, -apple-system, BlinkMacSystemFont, Segoe UI, Malgun Gothic, sans-serif"
    fontSize: "1.47rem"
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: "-0.03em"
    fontFeature: "tnum"
  title:
    fontFamily: "Pretendard Variable, Pretendard, -apple-system, BlinkMacSystemFont, Segoe UI, Malgun Gothic, sans-serif"
    fontSize: "1.07rem"
    fontWeight: 700
    lineHeight: 1.5
    letterSpacing: "-0.02em"
  title-sm:
    fontFamily: "Pretendard Variable, Pretendard, -apple-system, BlinkMacSystemFont, Segoe UI, Malgun Gothic, sans-serif"
    fontSize: "1rem"
    fontWeight: 650
    lineHeight: 1.5
  body:
    fontFamily: "Pretendard Variable, Pretendard, -apple-system, BlinkMacSystemFont, Segoe UI, Malgun Gothic, sans-serif"
    fontSize: "0.93rem"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Pretendard Variable, Pretendard, -apple-system, BlinkMacSystemFont, Segoe UI, Malgun Gothic, sans-serif"
    fontSize: "0.87rem"
    fontWeight: 500
    lineHeight: 1.5
  label-sm:
    fontFamily: "Pretendard Variable, Pretendard, -apple-system, BlinkMacSystemFont, Segoe UI, Malgun Gothic, sans-serif"
    fontSize: "0.83rem"
    fontWeight: 500
    lineHeight: 1.5
  caption:
    fontFamily: "Pretendard Variable, Pretendard, -apple-system, BlinkMacSystemFont, Segoe UI, Malgun Gothic, sans-serif"
    fontSize: "0.8rem"
    fontWeight: 400
    lineHeight: 1.5
rounded:
  sm: "6px"
  inner: "7px"
  control: "8px"
  md: "10px"
  btn-lg: "12px"
  lg: "14px"
  pill: "999px"
spacing:
  s1: "4px"
  s2: "8px"
  s3: "12px"
  s4: "16px"
  s5: "24px"
  s6: "32px"
  s7: "48px"
components:
  button-default:
    backgroundColor: "{colors.line-2}"
    textColor: "{colors.ink-2}"
    rounded: "{rounded.control}"
    height: "36px"
    padding: "0 14px"
  button-default-hover:
    backgroundColor: "{colors.line}"
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.bg}"
    rounded: "{rounded.control}"
    height: "36px"
    padding: "0 14px"
  button-primary-hover:
    backgroundColor: "{colors.accent-press}"
  button-primary-lg:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.bg}"
    typography: "{typography.title-sm}"
    rounded: "{rounded.btn-lg}"
    height: "46px"
    padding: "0 20px"
  button-sm:
    backgroundColor: "{colors.line-2}"
    textColor: "{colors.ink-2}"
    typography: "{typography.label-sm}"
    rounded: "{rounded.inner}"
    height: "30px"
    padding: "0 10px"
  button-danger:
    backgroundColor: "transparent"
    textColor: "{colors.bad}"
    rounded: "{rounded.control}"
    height: "36px"
    padding: "0 14px"
  button-danger-hover:
    backgroundColor: "{colors.bad-wash}"
  nav-item:
    backgroundColor: "transparent"
    textColor: "{colors.text}"
    rounded: "{rounded.control}"
    height: "38px"
    padding: "0 10px"
  nav-item-active:
    backgroundColor: "#e9ecef"
    textColor: "{colors.ink}"
  chip:
    backgroundColor: "{colors.bg}"
    textColor: "{colors.text}"
    rounded: "{rounded.pill}"
    height: "32px"
    padding: "0 12px"
  chip-selected:
    backgroundColor: "{colors.accent-wash}"
    textColor: "{colors.accent-ink}"
  input:
    backgroundColor: "{colors.bg}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    height: "40px"
    padding: "0 12px"
  select:
    backgroundColor: "{colors.bg}"
    textColor: "{colors.ink-2}"
    rounded: "{rounded.control}"
    height: "32px"
    padding: "0 30px 0 8px"
  tag:
    backgroundColor: "{colors.line-2}"
    textColor: "{colors.text}"
    typography: "{typography.caption}"
    rounded: "{rounded.sm}"
    padding: "1px 7px"
  plan-card:
    backgroundColor: "{colors.bg}"
    textColor: "{colors.ink}"
    rounded: "{rounded.lg}"
    padding: "16px 24px"
  plan-card-selected:
    backgroundColor: "#fbfdff"
  heat-cell:
    backgroundColor: "{colors.h0}"
    textColor: "{colors.ink-2}"
    rounded: "{rounded.sm}"
    height: "48px"
    padding: "0 12px"
  heat-cell-tight:
    backgroundColor: "{colors.h3}"
    textColor: "#6b4200"
  heat-cell-over:
    backgroundColor: "{colors.h4}"
    textColor: "#a8222d"
---

# Design System: 충파모

<!-- impeccable:design-schema 1 -->

이 문서는 2026-11-25에 실제로 만들어진 화면(`src/styles/theme.css`와 다섯 화면)을 읽고 적은 기록입니다. 값은 위쪽 머리말(frontmatter)이 기준이고, 아래 글은 그 값을 어디에 왜 쓰는지 설명합니다. 색과 간격은 `theme.css`의 `:root`에 CSS 변수(`--ink`, `--accent`, `--s4` 등)로 들어 있으니 새 화면에서는 변수를 그대로 쓰면 됩니다.

## Overview

**Creative North Star: "익숙하고 세련된 제품 화면"**

충파모는 색다른 세계관을 입히지 않습니다. 요즘 잘 만든 웹 서비스(토스, Linear, Stripe 대시보드)의 문법을 그대로 따르고, 그 옆에 놓아도 어색하지 않은 완성도를 목표로 합니다. 화면은 흰 작업면과 한 단계 낮은 회색 메뉴 두 겹뿐이고, 색은 파랑 하나만 눈에 띄게 씁니다.

홈 맨 위에는 숫자 카드 줄이 아니라 문장 하나가 옵니다. "2월, 롤 절단기가 한도를 다 씁니다"처럼 지금 막히는 곳을 말하고, 막히는 곳이 없으면 다음에 할 일을 말합니다. 나머지 네 화면(자료 넣기, 수요 예측, 생산계획, 기록)은 조건을 고르는 입력 묶음이나 표에서 바로 시작합니다. 빨강과 주황은 막힌 칸과 빠듯한 칸을 가리킬 때만 나오므로, 화면에 따뜻한 색이 보이면 그곳이 봐야 할 곳입니다.

구획은 상자로 나누지 않습니다. 테두리 상자는 표, 입력 묶음, 계획 카드 셋, 파일을 놓는 칸에만 쓰고, 그래프와 부하 지도는 상자 없이 그대로 놓습니다. 나머지는 여백과 가는 선으로 나눕니다. 그림자는 기본적으로 없습니다.

**Key Characteristics:**
- 흰 작업면 + 회색 메뉴, 두 겹의 평평한 면
- 강조색은 파랑 하나. 주된 버튼, 포커스, 고른 것에 씀
- 빨강·주황은 막힌 곳과 빠듯한 곳에만
- 홈 첫 줄은 문장 (약 32px), 그 아래 주된 버튼 하나
- 테두리 상자는 표, 입력 묶음, 계획 카드, 파일 놓는 칸에만. 그래프와 부하 지도는 상자 없이
- Pretendard 한 가지 글꼴, 숫자는 고정폭 숫자
- 상태는 6px 색 점과 글자로 표시

## Colors

회색 계열이 화면 대부분을 차지하고, 파랑 하나와 상태색 셋(초록·주황·빨강)이 뜻이 있을 때만 나옵니다.

### Primary
- **파랑** (`accent`): 주된 버튼의 바탕, 포커스 테두리, 입력 커서, 고른 칩의 1.5px 테두리, 고른 계획 카드의 2px 테두리, 그래프의 예측선.
- **누른 파랑** (`accent-press`): 주된 버튼에 마우스를 올렸을 때.
- **옅은 파랑** (`accent-wash`): 고른 표 줄, 고른 목록 줄, 고른 칩의 바탕, 일반 안내(notice) 바탕, 파일을 끌어다 놓는 칸의 hover.
- **짙은 파랑 글자** (`accent-ink`): 옅은 파랑 바탕 위의 글자(고른 칩, 일반 안내). `accent-press`와 같은 값입니다.

### Secondary
상태색입니다. 꾸밈으로 쓰지 않습니다.
- **빨강** (`bad`, 바탕 `bad-wash`): 한도 초과, 실행 불가, 오류, 반려·삭제 같은 위험한 버튼의 글자. 홈 첫 문장에서 한도를 다 쓰는 설비 이름.
- **주황** (`warn` 글자, `warn-mark` 점·막대, 바탕 `warn-wash`): 빠듯함(90% 이상), 확인 필요. 글자에는 어두운 `warn`을, 점과 막대에는 밝은 `warn-mark`를 씁니다.
- **초록** (`ok`, 바탕 `ok-wash`): 실행 가능, 승인됨, 서버 정상, 끝난 단계.

### Neutral
- **먹색** (`ink`): 제목, 강조 숫자, 로고 네모, 지금 단계 번호, 그래프의 계획 생산량 선과 말풍선.
- **본문 진한 회색** (`ink-2`): 기본 글자, 표 본문.
- **문단 회색** (`text`): 문단, 메뉴 글자, 입력 이름표.
- **보조 회색** (`muted`): 설명, 표 머리글, 단위, 선택 상자의 꺾쇠.
- **가장 옅은 글자색** (`faint`): 아이콘, 곁들이는 코드, placeholder, 그래프 눈금 글자, 그래프의 실제 수요 선. 글자로 읽히는 가장 옅은 색이며 이보다 옅은 회색은 글자에 쓰지 않습니다.
- **선** (`line`, `line-2`): `line`은 상자 테두리와 구획선, `line-2`는 표 줄 사이 선과 기본 버튼 바탕.
- **hover 선** (`line-hover`): 입력 칸, 칩, 계획 카드에 마우스를 올렸을 때의 테두리, 파일 놓는 칸의 점선.
- **옅은 바탕** (`wash`, `side-bg`): 메뉴 바탕, 줄 hover, 그래프의 예측 구간.
- **흰색** (`bg`): 작업면.
- **부하 지도 단계** (`h0`, `h3`, `h4`): 세 단계입니다. 사용률 90% 미만은 모두 같은 회색(`h0`), 90~100%는 옅은 주황(`h3`), 한도 도달·초과(99.5% 이상)는 옅은 빨강(`h4`). `theme.css`의 `--h1`, `--h2`는 `--h0`과 같은 값으로 남아 있습니다.
- **중립 막대** (`bar-neutral`): 문제없는 막대(셀 안 막대, 사용량 막대)의 채움.

### Named Rules
**파랑 하나 규칙.** 파랑 채움 버튼은 한 화면에서 주된 일 하나에만 씁니다. 나머지 버튼은 회색 바탕이거나 바탕이 없습니다.

**따뜻한 색은 신호 규칙.** 빨강과 주황은 막힌 곳, 빠듯한 곳, 오류에만 씁니다. 정상인 값은 회색으로 둡니다. 부하 지도에서 90% 아래 칸이 모두 한 가지 회색인 것이 이 규칙입니다.

**고른 것은 두 가지 규칙.** 값을 고르면 파랑입니다(표 줄과 목록 줄은 옅은 파랑 바탕, 칩은 옅은 파랑 바탕에 1.5px 파랑 선과 짙은 파랑 글자, 계획 카드는 2px 파랑 선). 보는 자리를 고르면 무채색입니다(탭은 흰 칸, 메뉴는 진한 회색 바탕, 부하 지도 칸은 2px 먹색 테두리).

## Typography

**Display Font:** Pretendard Variable (대체: Pretendard, -apple-system, Segoe UI, Malgun Gothic)
**Body Font:** 같은 글꼴 하나만 씁니다.

**Character:** 한 가지 글꼴을 굵기와 크기로만 나눕니다. 큰 글자일수록 자간을 좁히고(-0.035em), 숫자는 자릿수가 맞도록 고정폭 숫자(`.num`, tnum)로 씁니다. 기준 글자 크기는 15px이고 아래 rem 값은 이 기준에 대한 값입니다. 글꼴은 `index.html`에서 jsDelivr의 Pretendard v1.3.9 dynamic subset으로 읽습니다.

### Hierarchy
- **Display** (700, 2.13rem ≈ 32px, 줄높이 1.22, 자간 -0.035em): 홈 맨 위 문장(`.lead h2`). 1080px 아래에서 1.73rem, 640px 아래에서 1.6rem.
- **Headline** (700, 1.73rem ≈ 26px, 줄높이 1.2, 자간 -0.035em, 고정폭 숫자): 계획 카드의 합계, 분류 개수 같은 큰 숫자.
- **Headline-sm** (700, 1.47rem ≈ 22px, 줄높이 1.25, 자간 -0.03em): 요약 줄의 숫자. 홈 세 안 목록의 숫자는 이보다 조금 작은 1.33rem입니다.
- **Title** (700, 1.07rem ≈ 16px, 자간 -0.02em): 구획 제목(h2).
- **Title-sm** (650, 1rem = 15px): 상단 막대의 화면 이름, 계획 카드 이름, 파일 놓는 칸의 제목, 큰 버튼 글자. 로고 이름은 같은 크기에 700.
- **Body** (400, 0.93rem ≈ 14px, 줄높이 1.5): 문단, 표 본문, 알림. 홈 맨 위 문장 아래 설명만 1.07rem / 줄높이 1.6 / 최대 62ch. 버튼 글자는 0.9rem / 600.
- **Label** (500, 0.87rem ≈ 13px): 설명, 상태 글자, 입력 이름표, 칩, 탭, 촘촘한 표.
- **Label-sm** (500, 0.83rem ≈ 12.5px): 표 머리글, 범례, 부하 지도 머리글, 작은 버튼, 그래프 말풍선.
- **Caption** (400, 0.8rem = 12px): 곁들이는 코드, 부하 지도 칸의 작은 글자, 진행 단계. 딱지는 같은 크기에 600. 그래프 눈금 글자는 SVG 안에서 12px로 고정합니다.

### Named Rules
**숫자 고정폭 규칙.** 표, 부하 지도, 큰 숫자는 모두 고정폭 숫자로 씁니다. 숫자 뒤 단위는 작게(0.87rem, 500, 보조 회색) 붙입니다.

**이름 먼저 규칙.** 제품·설비·자재는 이름을 굵게(600, 먹색) 쓰고 코드는 그 아래 0.8rem 옅은 글자로 곁들입니다.

**낱말 단위 줄바꿈.** 한국어 본문은 `word-break: keep-all`로 낱말 중간에서 끊지 않습니다. 맨 위 문장은 `text-wrap: balance`입니다.

## Layout

- **틀**: 왼쪽 메뉴(232px, 접으면 64px) + 작업면. 메뉴와 상단 막대(높이 60px)는 스크롤해도 붙어 있습니다.
- **작업면**: 좌우·위 여백 32px, 아래 72px, 최대 너비 1680px. 구획 사이 간격 32px.
- **상단 막대**: 메뉴 접기 버튼, 화면 이름, 진행 단계(자료 → 예측 → 계획), 오른쪽에 데이터셋 선택과 다시 읽기.
- **화면 순서**: 홈은 맨 위 문장과 주된 버튼 → 2단 구획(왼쪽에 설비·인력 사용률, 오른쪽에 세 안 목록) → 수요와 계획 그래프, 확인할 것. 나머지 화면은 조건을 고르는 입력 묶음 → (있으면) 요약 줄 → 구획 순서입니다.
- **요약 줄이 나오는 곳**: 수요 예측(세 값, 건너뛴 제품이나 경고가 있을 때만 네 번째 값)과 자료 넣기(승인하지 않은 파일이 남아 있는 동안만). 홈, 생산계획, 기록에는 없습니다.
- **2단**: 넓은 쪽과 좁은 쪽의 비율은 2:1(`c21`), 2.6:1(`c31`), 1:2(`c12`), 1:1(`c11`). 좁은 쪽은 최소 300px, 단 사이 간격 48px.
- **간격 단위**: 4, 8, 12, 16, 24, 32, 48px (`s1`~`s7`). 구획 안쪽은 12~16px, 구획 사이는 32px.
- **표**: 줄 높이 46px, 좌우 칸 여백 16px, 머리글은 붙어 있음. 좁은 자리의 촘촘한 표(`tight`)는 줄 높이 40px, 칸 여백 6px, 0.87rem, 줄바꿈 없음. 이름 칸이 남는 너비를 다 갖는 표(`fit`)는 긴 이름을 말줄임으로 자릅니다.

**화면 너비에 따른 변화**
- 1280px 아래: 진행 단계의 설명 글자를 숨기고 단 사이 간격을 32px로 줄입니다.
- 1080px 아래: 2:1 계열 2단이 한 줄로 쌓이고 맨 위 문장이 작아집니다.
- 900px 아래: 메뉴가 아이콘만 남은 64px 띠가 되고, 진행 단계를 숨기고, 좌우 여백이 16px이 됩니다. 계획 카드 셋과 1:1 2단이 한 줄로 쌓입니다.
- 640px 아래: 부하 지도와 자재 부족 지도가 칸 안의 작은 글자를 숨기고 좁아집니다. 큰 버튼 높이가 44px이 됩니다.

## Elevation & Depth

평평합니다. 깊이는 그림자가 아니라 면의 밝기(흰 작업면과 회색 메뉴)와 1px 선으로 만듭니다. 카드와 구획에는 그림자가 없고, 테두리가 필요한 곳은 안쪽 1px 선(`inset 0 0 0 1px`)으로 그립니다. 상단 막대는 반투명 흰색(90%)에 뒤 내용을 흐리게 비춰, 스크롤한 내용 위에 떠 있음을 알립니다.

### Shadow Vocabulary
그림자는 떠 있거나 손으로 잡는 것 세 곳에만 있습니다.
- **고른 탭** (`0 1px 2px rgba(25, 31, 40, 0.1)`): 탭 묶음 안에서 고른 흰 칸.
- **슬라이더 손잡이** (`0 0 0 1px rgba(25, 31, 40, 0.12), 0 2px 6px rgba(25, 31, 40, 0.18)`): 잡아 끄는 동그라미.
- **그래프 말풍선** (`0 8px 24px rgba(25, 31, 40, 0.18)`): 마우스를 올렸을 때 뜨는 먹색 말풍선.
- **입력 포커스** (3px 옅은 파랑 테, 파랑의 16%): 그림자가 아니라 포커스 표시입니다.

### Named Rules
**평평함이 기본 규칙.** 구획, 카드, 표, 버튼에는 그림자를 넣지 않습니다. 위 세 곳 말고 새 그림자가 필요해 보이면 먼저 선이나 바탕색으로 해결합니다.

## Shapes

모서리는 부드럽게 둥글지만 알약 모양은 칩에만 씁니다.
- **누르는 것** (8px): 버튼, 메뉴 항목, 입력 칸, 선택 상자, 아이콘 버튼, 로고 네모, 그래프 말풍선.
- **안쪽 작은 것** (7px): 작은 버튼, 탭 묶음 안의 칸.
- **큰 버튼** (12px): 높이 46px 버튼.
- **칸과 딱지** (6px): 부하 지도 칸, 딱지.
- **안내와 목록 줄** (10px): 안내 상자, 홈의 세 안 목록 줄.
- **상자** (14px): 표와 입력 묶음을 두르는 테두리 상자, 계획 카드, 파일을 끌어다 놓는 칸.
- **알약** (999px): 칩.
- **점과 막대**: 상태 점은 6px 동그라미, 막대는 4~10px 높이에 끝을 높이의 절반만큼 둥글립니다.

테두리는 모두 1px `line`입니다. 예외는 고른 칩(1.5px 파랑), 고른 계획 카드(2px 파랑), 고른 부하 지도 칸(2px 먹색), 파일을 끌어다 놓는 칸(1.5px 점선)입니다. 아이콘은 24칸 격자에 선 굵기 1.9의 둥근 끝 선 그림이고, 글자 크기를 따라갑니다.

## Components

### Buttons
차분하고 단단합니다. 높이 36px, 좌우 14px, 0.9rem / 600, 모서리 8px.
- **기본**: 옅은 회색 바탕(`line-2`)에 진한 글자. hover 때 `line`.
- **주된 버튼**: 파랑 바탕에 흰 글자. hover 때 `accent-press`.
- **큰 버튼**: 높이 46px, 좌우 20px, 1rem / 650, 모서리 12px. 화면의 주된 일에 씁니다. 다음으로 넘어가는 버튼은 글자 뒤에 화살표 아이콘이 붙습니다.
- **위험한 버튼**: 빨강 글자에 옅은 빨강 안쪽 선(`#f3c2c6`), hover 때 `bad-wash`.
- **작은 버튼**: 높이 30px, 0.83rem, 모서리 7px. 표 안에서 씁니다.
- **상태**: 누르면 98%로 살짝 줄어듭니다. 못 누를 때는 투명도 40%. 포커스는 2px 파랑 바깥선(간격 2px).

### Chips
- **모양**: 흰 바탕, 안쪽 1px 선, 알약 모양, 높이 32px, 0.87rem / 500.
- **고름**: 옅은 파랑 바탕에 1.5px 파랑 안쪽 선, 짙은 파랑 글자(600). 달을 고르는 것처럼 여러 개 중 하나를 고를 때 씁니다.
- **누를 수 없는 칩**: 높이 28px, `wash` 바탕, 선 없음.

### Tabs
옅은 회색 통(`line-2`, 모서리 9px, 안쪽 3px) 안에 높이 28px 칸이 나란히 있고, 고른 칸만 흰색에 옅은 그림자가 붙습니다.

### Status (점, 딱지)
- **상태 점**: 6px 색 점 + 0.87rem 글자. 상태를 말할 때의 기본입니다. 빨강과 주황은 글자도 같은 색.
- **딱지**: 0.8rem / 600, 모서리 6px. 기본은 회색 바탕(`line-2`)에 문단 회색 글자이고, 기록 화면의 종류(자료·예측·계획)처럼 분류 이름을 적을 때 이 회색을 씁니다. 색 딱지(옅은 색 바탕에 같은 계열 글자)는 개수를 셀 때만 씁니다.

### Cards / Containers
- **구획**: 제목 줄(제목 + 한 줄 설명) 아래 내용.
- **테두리 상자**: 표, 입력 묶음, 올린 파일 목록에. 1px `line`, 모서리 14px, 안쪽 16px 24px. 표를 담을 때는 안쪽 여백 없이 꽉 채웁니다.
- **상자 없는 내용**: 그래프, 부하 지도, 자재 부족 지도, 홈의 세 안 목록은 테두리와 안쪽 여백 없이 구획 제목 아래에 그대로 놓습니다.
- **요약 줄**: 카드가 아니라 위아래 1px 선 사이에 값이 나란히 놓인 한 줄. 이름표(0.87rem) → 숫자(1.47rem / 700) → 무엇에 견준 값인지(0.87rem).
- **계획 카드**: 세 안을 나란히 비교할 때. 안쪽 1px 선, 모서리 14px, 합계 숫자 1.73rem. 고르면 2px 파랑 선과 아주 옅은 파랑 바탕(`#fbfdff`).
- **목록 줄**: 홈의 세 안처럼 누르는 줄. 모서리 10px, hover 때 `wash`, 고르면 `accent-wash`.
- **안내 상자**: 옅은 색 바탕에 아이콘과 글. 일반(파랑), 주의(주황), 오류(빨강), 완료(초록).
- **빈 상태**: 가운데 정렬된 한 줄 설명과 필요하면 버튼 하나.

### Tables
- **줄**: 누를 수 있는 줄은 hover 때 `wash`, 고른 줄은 `accent-wash`. 합계 줄은 650 먹색에 위쪽 1px 선.
- **셀 안 막대**: 숫자 아래 4px 회색 막대로 크기를 견줍니다. 넘친 값만 빨강.
- **바뀐 값**: 조건을 바꾸기 전과 후를 "전→후"로 적습니다. 문제 건수가 늘면 뒤 숫자가 빨강, 줄면 초록이고, 그대로인 칸은 옅은 회색 보통 굵기로 물러납니다.

### Inputs / Fields
- **모양**: 이름표(0.87rem / 500)가 위, 그 아래 높이 40px 칸. 흰 바탕, 1px `line`, 모서리 8px.
- **hover**: 테두리가 `line-hover`로 진해집니다.
- **포커스**: 파랑 테두리와 3px 옅은 파랑 테.
- **오류**: 빨강 테두리.
- **선택 상자**: 브라우저 기본 화살표를 지우고 오른쪽 10px 자리에 12px 꺾쇠(보조 회색, 선 굵기 1.6)를 직접 그립니다. 오른쪽 여백 30px. 상단 막대의 것은 높이 32px.
- **슬라이더**: 4px 선 위에 20px 흰 손잡이.
- **파일 놓는 칸**: 1.5px 점선, `wash` 바탕, 모서리 14px. 파일을 올리거나 hover하면 파랑 점선과 옅은 파랑 바탕.

### Navigation
- **메뉴**: 회색 면(`side-bg`) 위에 높이 38px 항목. 아이콘 18px + 0.93rem / 500 글자. hover 때 `#eceef1`, 지금 화면은 `#e9ecef` 바탕에 먹색 글자(650)와 먹색 아이콘. 확인할 것이 있으면 오른쪽에 6px 빨강 점.
- **접기**: 64px 띠로 줄고 아이콘만 남습니다. 너비 변화는 0.2초.
- **서버 상태**: 메뉴 맨 아래, 7px 점(초록·주황·빨강)과 두 줄 글자.
- **진행 단계**: 상단 막대의 자료 → 예측 → 계획. 16px 동그라미 번호가 끝난 단계는 초록 바탕의 체크, 지금 단계는 먹색 채움.

### 부하 지도 (Signature)
설비·인력(줄) × 달(칸)의 사용률 표입니다. 상자 없이 놓습니다. 칸 높이 48px, 사이 간격 2px, 모서리 6px. 칸 안에는 사용률(650)과 "쓴 시간 / 한도"(0.8rem)가 들어갑니다. 색은 세 단계입니다: 90% 미만은 한 가지 회색(`h0`), 90~100%는 옅은 주황(`h3`), 99.5% 이상은 한도 도달·초과로 보고 옅은 빨강(`h4`). 자료가 없는 칸은 바탕 없이 1px 선만 둡니다. 누를 수 있는 칸은 hover 때 1.5px 회색 선, 고른 칸은 2px 먹색 선입니다. 아래나 제목 줄 오른쪽에 세 단계 범례(90% 미만 / 90~100% 빠듯 / 한도 도달·초과)를 붙입니다. 자재 부족 지도도 같은 틀이며 부족한 정도에 따라 옅은 주황에서 빨강까지 네 단계로 칠합니다.

### 그래프
직접 그린 SVG 선 그래프 하나입니다. 상자 없이 놓습니다. 선 굵기 2, 실제 수요는 회색(`faint` 값), 예측은 파랑 점선과 파랑 12% 범위, 계획 생산량은 먹색 선에 흰 점. 눈금선은 `line-2` 점선, 눈금 글자 12px `faint`. 예측 구간은 `wash` 바탕에 "예측"이라고 적습니다. 마우스를 올리면 먹색 말풍선이 뜹니다. 범례는 구획 제목 줄 오른쪽에 10px 색 네모와 0.83rem 글자로 붙입니다.

### 움직임
상태가 바뀔 때만 짧게 움직입니다. 색·바탕은 0.12~0.15초, 메뉴 접기는 0.2초(`cubic-bezier(0.22, 1, 0.36, 1)`). 처음 열릴 때의 등장 효과는 없습니다. 움직임 줄이기 설정을 켜면 모두 멈춥니다.

## Do's and Don'ts

### Do:
- **Do** 홈처럼 상황을 먼저 말해야 하는 화면은 맨 위에 문장 하나(2.13rem / 700)와 주된 버튼 하나를 둡니다. 문장은 지금 막히는 곳이나 다음에 할 일을 말합니다.
- **Do** 파랑 채움 버튼은 화면의 주된 일 하나에만 씁니다.
- **Do** 고른 값(줄, 칩, 카드)은 파랑으로, 보는 자리(탭, 메뉴, 부하 지도 칸)는 무채색으로 표시합니다.
- **Do** 정상인 값은 회색으로 두고, 빨강·주황은 한도 초과, 빠듯함, 오류에만 씁니다.
- **Do** 상태는 6px 색 점과 글자로 말하고, 색 딱지는 개수를 셀 때만 씁니다. 분류 이름은 회색 딱지로 적습니다.
- **Do** 숫자에는 고정폭 숫자를 쓰고, 무엇에 견준 값인지(한도 대비, 수요 대비)를 옆이나 아래에 적습니다.
- **Do** 제품·설비·자재는 이름을 먼저 쓰고 코드는 작게 곁들입니다.
- **Do** 색과 간격은 `theme.css`의 변수(`--ink`, `--accent`, `--s1`~`--s7`, `--r-sm`, `--r`, `--r-lg`)를 씁니다.
- **Do** 색만으로 뜻을 전하지 않습니다. 부하 지도의 칸에는 숫자가, 상태 점 옆에는 글자가 항상 같이 있습니다.

### Don't:
- **Don't** 구획마다 테두리 상자나 카드를 두르지 않습니다. 테두리 상자는 표, 입력 묶음, 계획 카드, 파일 놓는 칸에만 쓰고 그래프와 부하 지도에는 두르지 않습니다.
- **Don't** 카드, 구획, 버튼에 그림자를 넣지 않습니다. 그림자는 고른 탭, 슬라이더 손잡이, 그래프 말풍선에만 있습니다.
- **Don't** 두 번째 강조색을 들이지 않습니다. 파랑 말고는 상태색 셋뿐입니다.
- **Don't** `faint`보다 옅은 회색을 글자에 쓰지 않습니다.
- **Don't** 어두운 바탕 화면을 만들지 않습니다. 밝은 화면만 씁니다.
- **Don't** 달력, 현황판 같은 비유나 색다른 세계관을 입히지 않습니다.
- **Don't** 화면 머리에 숫자 카드 네 개를 늘어놓지 않습니다. 요약이 꼭 필요한 화면에만 선 사이의 한 줄로 둡니다.
- **Don't** 측정하지 않은 값을 그리거나 예측 범위를 확률처럼 보이게 하지 않습니다.
