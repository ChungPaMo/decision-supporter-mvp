import { useMemo } from 'react';
import Shell from './app/Shell';
import { Empty, Notice, useRoute } from './app/core';
import { alerts, EMPTY_OVERVIEW, loadOverview, stages, useLoad } from './app/data';
import ForecastPage from './pages/ForecastPage';
import HistoryPage from './pages/HistoryPage';
import HomePage from './pages/HomePage';
import IngestPage from './pages/IngestPage';
import PlanPage from './pages/PlanPage';
import { useProductionStore } from './store/productionStore';
import './styles/theme.css';

// 데이터셋이 바뀌면 key 로 화면을 통째로 다시 만들어, 이전 데이터셋의 선택과 진행 중인 요청을 버린다.
function Workspace() {
  const route = useRoute();
  const overview = useLoad(loadOverview, []);
  const data = overview.data ?? EMPTY_OVERVIEW;
  const flow = useMemo(() => stages(data), [data]);
  const attention = useMemo(() => alerts(data).some((a) => a.tone !== 'info'), [data]);
  const reload = () => void overview.reload();
  return <Shell page={route.page} flow={flow} attention={attention}>
    {overview.error && <Notice tone="bad">{overview.error}</Notice>}
    {route.page === 'home' && (overview.data ? <HomePage overview={data} onReload={reload} /> : <section className="panel"><Empty>{overview.loading ? '현황을 읽는 중…' : '현황을 읽지 못했습니다.'}</Empty></section>)}
    {route.page === 'ingest' && <IngestPage onChanged={reload} />}
    {route.page === 'forecast' && <ForecastPage focus={route.params.f} names={data.names} onChanged={reload} />}
    {route.page === 'plan' && <PlanPage key={route.params.f ?? 'plan'} focus={route.params.f} startMonth={route.params.t} startPlan={route.params.p} pick={route.params.r && route.params.k && route.params.m ? { id: route.params.r, kind: route.params.k, month: route.params.m } : undefined} names={data.names} onChanged={reload} />}
    {route.page === 'history' && <HistoryPage overview={data} kind={route.params.kind} focus={route.params.x} onReload={reload} />}
  </Shell>;
}

export default function App() {
  const datasetId = useProductionStore((state) => state.datasetId);
  return <Workspace key={datasetId} />;
}
