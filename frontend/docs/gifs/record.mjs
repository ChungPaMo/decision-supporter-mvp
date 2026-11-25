// README용 움직이는 화면을 녹화한다. 실제 화면을 열어 누르는 모습을 찍고, 커서·클릭 표시·자막을 덧입힌다.
import { chromium } from '@playwright/test';
import { mkdirSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';

const VIDEO = resolve('.gif-tmp');
rmSync(VIDEO, { recursive: true, force: true });
mkdirSync(VIDEO, { recursive: true });
const uploadDir = resolve('../.artifacts/ingestion-e2e-dataset/upload');
const files = readdirSync(uploadDir).filter((f) => f.endsWith('.csv')).map((f) => join(uploadDir, f));
const SIZE = { width: 1280, height: 720 };
const browser = await chromium.launch({ channel: 'msedge' });

// 커서, 클릭 표시, 자막을 화면 위에 얹는다 (녹화용, 앱 코드와 무관).
const overlay = () => {
  localStorage.setItem('chungpamo.dataset.v1', 'CHUNGPAMO-2027');
  const mount = () => {
    if (document.getElementById('demo-cursor')) return;
    const style = document.createElement('style');
    style.textContent = `
      #demo-cursor { position: fixed; left: 0; top: 0; width: 22px; height: 22px; margin: -3px 0 0 -3px; z-index: 99999; pointer-events: none; transition: transform 0.04s linear }
      #demo-cursor svg { display: block; filter: drop-shadow(0 1px 2px rgba(0,0,0,.35)) }
      .demo-ripple { position: fixed; width: 14px; height: 14px; margin: -7px 0 0 -7px; border-radius: 50%; border: 3px solid #2563eb; background: rgba(37,99,235,.25); z-index: 99998; pointer-events: none; animation: demo-ripple .6s ease-out forwards }
      @keyframes demo-ripple { to { transform: scale(4.2); opacity: 0 } }
      #demo-cap { position: fixed; left: 50%; bottom: 22px; transform: translateX(-50%); max-width: 86%; z-index: 99997; pointer-events: none; background: rgba(25,31,40,.94); color: #fff; font: 600 19px/1.4 "Pretendard Variable", "Malgun Gothic", sans-serif; padding: 11px 20px; border-radius: 12px; box-shadow: 0 8px 24px rgba(0,0,0,.25); text-align: center; opacity: 0; transition: opacity .25s }
      #demo-cap.on { opacity: 1 }
      #demo-cap small { display: block; font-weight: 500; font-size: 14px; color: #b9c2cd; margin-top: 2px }`;
    document.head.appendChild(style);
    const cursor = document.createElement('div');
    cursor.id = 'demo-cursor';
    cursor.innerHTML = '<svg width="22" height="22" viewBox="0 0 24 24"><path d="M4 2l15 9.5-6.6 1.3 3.9 7.4-2.7 1.4-3.9-7.4L4 18.6z" fill="#191f28" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/></svg>';
    document.body.appendChild(cursor);
    const cap = document.createElement('div');
    cap.id = 'demo-cap';
    document.body.appendChild(cap);
    window.addEventListener('mousemove', (e) => { cursor.style.transform = `translate(${e.clientX}px, ${e.clientY}px)`; }, true);
    window.addEventListener('mousedown', (e) => { const r = document.createElement('div'); r.className = 'demo-ripple'; r.style.left = `${e.clientX}px`; r.style.top = `${e.clientY}px`; document.body.appendChild(r); setTimeout(() => r.remove(), 700); }, true);
  };
  if (document.body) mount(); else document.addEventListener('DOMContentLoaded', mount);
};

async function scene(name, run) {
  const context = await browser.newContext({ viewport: SIZE });
  await context.addInitScript(overlay);
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  const wait = (ms) => page.waitForTimeout(ms);
  // 화면을 연속으로 찍어 둔다 (나중에 ffmpeg로 이어 붙인다). 찍은 시각을 함께 적어 실제 속도대로 재생되게 한다.
  const dir = join(VIDEO, name); mkdirSync(dir, { recursive: true });
  const stamps = []; let recording = false, loop = Promise.resolve();
  const startRecording = () => { recording = true; loop = (async () => { while (recording) { const file = join(dir, `f${String(stamps.length).padStart(5, '0')}.jpg`); const at = Date.now(); try { await page.screenshot({ path: file, type: 'jpeg', quality: 72 }); stamps.push([file, at]); } catch { break; } } })(); };
  let mouse = { x: 640, y: 360 };
  const glide = async (x, y) => { const from = { ...mouse }, steps = 22; for (let i = 1; i <= steps; i += 1) { const k = i / steps, e = 1 - Math.pow(1 - k, 3); await page.mouse.move(from.x + (x - from.x) * e, from.y + (y - from.y) * e); await wait(16); } mouse = { x, y }; };
  const say = async (text, sub = '') => { await page.evaluate(([t, s]) => { const c = document.getElementById('demo-cap'); if (!c) return; c.innerHTML = t + (s ? `<small>${s}</small>` : ''); c.classList.add('on'); }, [text, sub]); await wait(350); };
  const hush = () => page.evaluate(() => document.getElementById('demo-cap')?.classList.remove('on'));
  const moveTo = async (locator, dx = 0, dy = 0) => { await locator.scrollIntoViewIfNeeded(); await wait(250); const box = await locator.boundingBox(); if (!box) throw new Error('no box'); await glide(box.x + box.width / 2 + dx, box.y + box.height / 2 + dy); await wait(280); };
  const click = async (locator, after = 900) => { await moveTo(locator); await page.mouse.down(); await wait(90); await page.mouse.up(); await wait(after); };
  const open = async (hash, ms = 3200) => { await page.goto(`http://127.0.0.1:5173/#${hash}`); await page.waitForLoadState('networkidle'); await page.mouse.move(640, 360); mouse = { x: 640, y: 360 }; await wait(ms); if (!recording) startRecording(); };
  const tools = { page, wait, say, hush, moveTo, click, open, glide };
  await run(tools);
  await wait(900);
  recording = false; await loop;
  await context.close();
  // ffmpeg concat 목록: 각 장면을 다음 장면을 찍기까지의 시간만큼 보여 준다.
  const slash = (file) => file.split('\\').join('/');
  const lines = stamps.map(([file, at], i) => [`file '${slash(file)}'`, `duration ${(((stamps[i + 1]?.[1] ?? at + 900) - at) / 1000).toFixed(3)}`].join('\n'));
  writeFileSync(join(VIDEO, `${name}.txt`), [...lines, `file '${slash(stamps[stamps.length - 1][0])}'`, ''].join('\n'));
  console.log(name, 'frames', stamps.length, 'seconds', ((stamps[stamps.length - 1][1] - stamps[0][1]) / 1000).toFixed(1));
  console.log(name, errors.length ? `errors: ${errors.join(' | ')}` : 'recorded');
}

// 1) 자료 넣기: 올리기 → 분류하기 → 종류별 개수 → 줄을 눌러 검증 결과 보기
await scene('01-ingest', async ({ page, wait, say, moveTo, click, open }) => {
  await open('ingest', 2600);
  await say('① 엑셀·CSV 파일을 여기에 놓습니다', '파일 9개를 한꺼번에 올립니다');
  await moveTo(page.locator('.drop'));
  await wait(600);
  await page.locator('input[type=file]').setInputFiles(files);
  await wait(1500);
  await say('② 올리기만 하면 목록에 쌓입니다', '아직 분류하지 않았습니다');
  await wait(1700);
  await say('③ "분류하기"를 누르면 파일 분류기가 종류를 알아봅니다');
  await click(page.getByRole('button', { name: /분류하기/ }), 400);
  await page.waitForFunction(() => /분류해 아래 등록 순서에 넣었습니다/.test(document.body.innerText), null, { timeout: 120000 });
  await say('④ 무슨 자료가 몇 개인지 나옵니다', '설비·생산능력 3개, 나머지는 1개씩');
  await moveTo(page.locator('.tally'));
  await wait(2400);
  await say('⑤ 종류에 맞는 줄에 알아서 놓입니다', '제품과 자재가 먼저 승인돼야 합니다');
  await moveTo(page.locator('.steps'));
  await wait(1800);
  await say('⑥ 줄을 누르면 오른쪽에 검증 결과가 나옵니다', '읽은 행, 문제없는 행, 오류·경고');
  await click(page.locator('.tbl tbody tr').nth(8), 1600);
  await click(page.locator('.tbl tbody tr').nth(2), 2000);
});

// 2) 수요 예측: 제품 줄을 눌러 그래프 바꾸기 → 이 예측으로 계획 세우기
await scene('02-forecast', async ({ page, wait, say, moveTo, click, open, glide }) => {
  await open('forecast', 3400);
  await say('① 승인된 월별 수요로 다음 석 달을 예측합니다', '회색 선이 실제 수요, 파란 점선이 예측');
  await moveTo(page.locator('.chart'));
  await wait(2200);
  await say('② 제품 줄을 누르면 그래프가 그 제품으로 바뀝니다');
  await click(page.locator('.tbl.fit tbody tr').nth(1), 1700);
  await click(page.locator('.tbl.fit tbody tr').nth(4), 1700);
  await click(page.locator('.tbl.fit tbody tr').nth(7), 1900);
  await say('③ "전체 보기"로 돌아옵니다');
  await click(page.getByRole('button', { name: '전체 보기' }), 1700);
  await say('④ 그래프에 마우스를 올리면 달마다 값이 나옵니다');
  const chart = await page.locator('.chart').boundingBox();
  await glide(chart.x + chart.width * 0.55, chart.y + chart.height * 0.5);
  await wait(900);
  await glide(chart.x + chart.width * 0.93, chart.y + chart.height * 0.45);
  await wait(1500);
  await say('⑤ "이 예측으로 계획 세우기"를 누르면 생산계획으로 넘어갑니다');
  await click(page.getByRole('button', { name: /이 예측으로 계획 세우기/ }), 4500);
});

// 3) 생산계획: 홈에서 막힌 곳 확인 → 잔업 한도 바꾸기 → 다시 계산 → 전후 비교
await scene('03-plan', async ({ page, wait, say, moveTo, click, open }) => {
  await open('home', 3400);
  await say('① 홈의 첫 문장이 지금 막히는 곳을 알려 줍니다', '테두리 친 빨간 칸이 그곳입니다');
  await moveTo(page.locator('.heat .cl.sel'));
  await wait(2200);
  await say('② 안을 누르면 표가 그 안으로 바뀝니다');
  await click(page.locator('.rows button', { hasText: '안정형' }), 1500);
  await click(page.locator('.rows button', { hasText: '기준형' }), 1500);
  await say('③ 큰 버튼을 누르면 그 칸이 열린 채로 생산계획이 뜹니다');
  await click(page.locator('.lead .btn.primary'), 6000);
  await say('④ 칸의 정규 시간과 지금 잔업 한도가 보입니다', '정규 430시간 + 잔업 한도 40시간');
  await moveTo(page.locator('.notice').last());
  await wait(2400);
  await say('⑤ 잔업 한도를 80시간으로 바꿉니다');
  await click(page.getByRole('button', { name: /이 칸의 잔업 한도를/ }), 1300);
  await say('⑥ "이 조건으로 다시 계산"을 누르면 계획 엔진이 다시 계산합니다');
  await click(page.getByRole('button', { name: /이 조건으로 다시 계산/ }), 6500);
  await say('⑦ 전체 한도가 470시간에서 510시간으로 늘었습니다', '숫자와 칸 색이 바뀝니다');
  await moveTo(page.locator('.notice').last());
  await wait(2600);
  await say('⑧ "원래 계획"과 "바꾼 결과"를 오가며 견줍니다');
  await click(page.getByRole('button', { name: '원래 계획' }), 1700);
  await click(page.getByRole('button', { name: '바꾼 결과' }), 2000);
});

// 4) 화면 이동: 메뉴, 진행 표시, 메뉴 접기, 탭, 뒤로가기
await scene('04-navigation', async ({ page, wait, say, moveTo, click, open }) => {
  await open('home', 3000);
  await say('① 왼쪽 메뉴로 다섯 화면을 오갑니다');
  await click(page.locator('.navitem', { hasText: '자료 넣기' }), 1700);
  await click(page.locator('.navitem', { hasText: '수요 예측' }), 2200);
  await click(page.locator('.navitem', { hasText: '생산계획' }), 3600);
  await say('② 탭을 누르면 한 번에 하나만 보여 줍니다', '설비·인력 부하 / 제품별 생산량 / 자재 부족');
  const tabs = page.getByRole('group', { name: '자세히 볼 것' });
  await click(tabs.getByRole('button', { name: '제품별 생산량' }), 1900);
  await click(tabs.getByRole('button', { name: /자재 부족/ }), 2200);
  await say('③ 메뉴는 접을 수 있습니다');
  await click(page.locator('.topbar .iconbtn').first(), 1500);
  await click(page.locator('.topbar .iconbtn').first(), 1300);
  await say('④ 맨 위의 진행 표시를 눌러도 그 단계로 갑니다', '자료 → 예측 → 계획');
  await click(page.locator('.flow button').first(), 2000);
  await say('⑤ 뒤로가기를 누르면 이전 화면으로 돌아갑니다');
  await page.goBack(); await wait(2600);
  await click(page.locator('.navitem', { hasText: '기록' }), 2400);
});

await browser.close();
console.log('videos in', VIDEO);
