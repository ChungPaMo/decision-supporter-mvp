import { useEffect } from 'react';
import MainLayout from './layouts/MainLayout';
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

  return (
    <MainLayout>
      {step === 'data' && <DataUploadScreen />}
      {step === 'forecast' && <ForecastScreen />}
      {(['plans', 'diagnosis', 'mrp', 'whatif', 'approval'] as const).map(stage => step === stage && <PlanningWorkspace key={stage} stage={stage} />)}
    </MainLayout>
  );
}
