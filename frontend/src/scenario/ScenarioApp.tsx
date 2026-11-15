import { useEffect } from 'react';
import Shell, { NAV_ITEMS } from '../layouts/Shell';
import { DATASET, SCREENS } from './data';
import Icon from './icons';
import { screenFromHash, useScenario } from './store';
import Overview from './screens/Overview';
import { UploadScreen, MappingScreen, ValidationScreen } from './screens/DataScreens';
import { ForecastSetupScreen, ForecastResultScreen, ForecastMeaningScreen } from './screens/ForecastScreens';
import { PlanCompareScreen, WhatIfScreen, FinalReviewScreen } from './screens/PlanScreens';

const FIRST_SCREEN: Record<string, number> = { dashboard: 0, upload: 1, verify: 3, forecast: 4, plan: 7, whatif: 8 };
const VIEWS = [Overview, UploadScreen, MappingScreen, ValidationScreen, ForecastSetupScreen, ForecastResultScreen, ForecastMeaningScreen, PlanCompareScreen, WhatIfScreen, FinalReviewScreen];

export default function ScenarioApp() {
  const { screen, go } = useScenario();
  useEffect(() => {
    const sync = () => {
      const next = screenFromHash(window.location.hash);
      if (next != null) useScenario.setState({ screen: next });
    };
    sync();
    window.addEventListener('hashchange', sync);
    window.addEventListener('popstate', sync);
    return () => { window.removeEventListener('hashchange', sync); window.removeEventListener('popstate', sync); };
  }, []);
  const meta = screen ? SCREENS[screen - 1] : null;
  const View = VIEWS[screen] ?? Overview;

  return <Shell mode="scenario" nav={NAV_ITEMS} active={meta ? meta.nav : 'dashboard'} onNav={(id) => go(FIRST_SCREEN[id])}
    crumb={meta ? [...meta.crumb] : ['대시보드', '예시 시나리오 개요']}
    dataset={<div className="sc-dataset"><label htmlFor="scenario-dataset">데이터셋</label>
      <select id="scenario-dataset" value={DATASET} onChange={() => undefined}><option>{DATASET}</option></select>
      <span className="sc-draft-tag" title="기획서 예시 시나리오의 합성 데이터입니다. 서버에 저장되거나 계산되지 않습니다.">UX 시안 · 합성 데이터</span></div>}
    topEnd={<div className="sc-pager" aria-label="시안 화면 이동">
      <button type="button" disabled={screen === 0} onClick={() => go(screen - 1)} aria-label="이전 화면"><Icon name="arrowLeft" size={16} /></button>
      <span className="sc-screen-count" aria-label={meta ? `9개 화면 중 ${screen}번째` : '시나리오 개요'}>{meta ? `${screen} / 9` : '개요'}</span>
      <button type="button" disabled={screen === 9} onClick={() => go(screen + 1)} aria-label="다음 화면"><Icon name="arrowRight" size={16} /></button>
    </div>}>
    <View />
  </Shell>;
}
