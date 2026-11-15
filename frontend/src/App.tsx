import { useEffect, useState } from 'react';
import MainLayout from './layouts/MainLayout';
import ScenarioApp from './scenario/ScenarioApp';
import { screenFromHash } from './scenario/store';
import DashboardScreen from './screens/DashboardScreen';
import DataUploadScreen from './screens/DataUploadScreen';
import ForecastScreen from './screens/ForecastScreen';
import PlanningWorkspace from './screens/PlanningWorkspace';
import { useProductionStore } from './store/productionStore';
import './styles/app.css';
import './styles/operations.css';

export default function App() {
  useEffect(() => {
    const restoreRoute = () => {
      if (window.location.hash === '#forecast') useProductionStore.getState().setStep('forecast');
      else if (!window.location.hash) useProductionStore.getState().setStep('data');
    };
    window.addEventListener('hashchange', restoreRoute);
    return () => window.removeEventListener('hashchange', restoreRoute);
  }, []);
  const step = useProductionStore((state) => state.step);
  const datasetId = useProductionStore((state) => state.datasetId);
  // #scenario, #scenario/1~9 는 기획서 예시 시나리오(합성 데이터 UX 시안)로 분리해 보여준다.
  const [scenario, setScenario] = useState(() => screenFromHash(window.location.hash) != null);
  useEffect(() => {
    const sync = () => setScenario(screenFromHash(window.location.hash) != null);
    window.addEventListener('hashchange', sync);
    window.addEventListener('popstate', sync);
    return () => { window.removeEventListener('hashchange', sync); window.removeEventListener('popstate', sync); };
  }, []);

  if (scenario) return <ScenarioApp />;
  // key 에 데이터셋을 넣어, 데이터셋이 바뀌면 화면 상태(선택 UUID·이력·진행 중 요청)를 버리고 새로 조회한다.
  return (
    <MainLayout>
      {step === 'dashboard' && <DashboardScreen key={datasetId} />}
      {step === 'data' && <DataUploadScreen key={datasetId} />}
      {step === 'verify' && <DataUploadScreen key={`${datasetId}-verify`} view="verify" />}
      {step === 'forecast' && <ForecastScreen key={datasetId} />}
      {(['plans', 'diagnosis', 'mrp', 'whatif', 'approval'] as const).map(stage => step === stage && <PlanningWorkspace key={`${datasetId}-${stage}`} stage={stage} />)}
    </MainLayout>
  );
}
