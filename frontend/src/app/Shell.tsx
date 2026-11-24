import { Fragment, ReactNode, useEffect, useRef, useState } from 'react';
import { apiClient } from '../services/api';
import { useProductionStore } from '../store/productionStore';
import { go, Icon, PageId, PAGES } from './core';
import { Stage } from './data';

const SIDE_KEY = 'chungpamo.sidebar.collapsed';
type Health = { level: 'ok' | 'warn' | 'bad'; title: string; note: string };

// 서버와 DB 상태를 15초마다 스스로 확인한다. 화면마다 "서버 상태 다시 조회"를 누를 필요가 없다.
function useHealth(): [Health, () => void] {
  const [health, setHealth] = useState<Health>({ level: 'warn', title: '확인 중', note: '서버 상태를 읽는 중' });
  const alive = useRef(true);
  const check = async () => {
    try {
      const reply = await apiClient.health();
      if (!alive.current) return;
      if (reply.status === 'ok') setHealth({ level: 'ok', title: '정상 동작 중', note: '서버와 DB 연결됨' });
      else setHealth({ level: 'warn', title: 'DB 연결 안 됨', note: '서버는 켜져 있음' });
    } catch { if (alive.current) setHealth({ level: 'bad', title: '서버 연결 안 됨', note: '서버가 꺼져 있음' }); }
  };
  useEffect(() => {
    alive.current = true;
    void check();
    const timer = window.setInterval(() => void check(), 15000);
    return () => { alive.current = false; window.clearInterval(timer); };
  }, []);
  return [health, () => void check()];
}

export default function Shell({ page, flow, attention, children }: { page: PageId; flow: Stage[]; attention: boolean; children: ReactNode }) {
  const [collapsed, setCollapsed] = useState(() => { try { return localStorage.getItem(SIDE_KEY) === '1'; } catch { return false; } });
  const [health, recheck] = useHealth();
  const { datasetId, datasets, setDatasets, setDataset } = useProductionStore();
  const current = PAGES.find((p) => p.id === page)!;
  const toggle = () => setCollapsed((value) => { try { localStorage.setItem(SIDE_KEY, value ? '0' : '1'); } catch { /* 기억은 선택 사항 */ } return !value; });
  const loadDatasets = async () => { try { setDatasets(await apiClient.listDatasets()); } catch { setDatasets(null); } };
  useEffect(() => { void loadDatasets(); }, [health.level]);

  return <div className={`shell${collapsed ? ' collapsed' : ''}`}>
    <aside className="sidebar">
      <div className="brand"><b className="brandmark">충</b><div><strong>충파모</strong><small>생산계획 의사결정</small></div></div>
      <nav aria-label="주 메뉴">
        {PAGES.map((item) => <button key={item.id} type="button" className={`navitem${item.id === page ? ' active' : ''}`} aria-current={item.id === page ? 'page' : undefined}
          title={collapsed ? item.label : item.hint} aria-label={item.label} onClick={() => go(item.id)}>
          <Icon name={item.icon} /><span>{item.label}</span>{item.id === 'home' && attention && <i className="dot" aria-label="확인할 것이 있음" />}
        </button>)}
      </nav>
      <div className="sidefoot">
        <button type="button" className={`health ${health.level === 'ok' ? '' : health.level}`} onClick={recheck} title="눌러서 다시 확인" aria-label={`${health.title}. ${health.note}. 눌러서 다시 확인`}>
          <i /><span>{health.title}<small>{health.note}</small></span>
        </button>
      </div>
    </aside>
    <div className="workspace">
      <header className="topbar">
        <button type="button" className="iconbtn" onClick={toggle} aria-label={collapsed ? '메뉴 펴기' : '메뉴 접기'} aria-expanded={!collapsed} title={collapsed ? '메뉴 펴기' : '메뉴 접기'}><Icon name="menu" /></button>
        <h1>{current.label}</h1>
        <nav className="flow" aria-label="진행 단계">{flow.map((stage, i) => <Fragment key={stage.id}>{i > 0 && <span className="sep" />}
          <button type="button" className={stage.state} onClick={() => go(stage.id)} title={`${stage.label}: ${stage.note}`}>
            <b>{stage.state === 'done' ? '✓' : i + 1}</b><strong>{stage.label}</strong><span className="note">{stage.note}</span></button></Fragment>)}</nav>
        <div className="right">
          <select className="select" value={datasetId} onChange={(event) => setDataset(event.target.value)} aria-label="데이터셋">
            {(datasets ?? []).some((d) => d.dataset_id === datasetId) || <option value={datasetId}>{datasetId}</option>}
            {(datasets ?? []).map((d) => <option key={d.dataset_id} value={d.dataset_id}>{d.dataset_id}</option>)}
          </select>
          <button type="button" className="iconbtn" onClick={() => { recheck(); void loadDatasets(); }} aria-label="서버 상태와 데이터셋 목록 다시 읽기" title="다시 읽기"><Icon name="refresh" /></button>
        </div>
      </header>
      <main className="page">
        {health.level !== 'ok' && health.title !== '확인 중' && <div className={`notice ${health.level}`} role="alert"><Icon name="alert" /><span><b>{health.title}.</b> {health.level === 'bad' ? '서버를 켜면 자동으로 다시 연결됩니다.' : 'DB(Docker)를 켜면 자동으로 다시 연결됩니다. 엑셀 문서 종류 분류는 DB 없이도 됩니다.'}</span></div>}
        {children}
      </main>
    </div>
  </div>;
}
