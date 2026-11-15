import { ReactNode } from 'react';
import Icon, { IconName } from '../scenario/icons';
import '../styles/scenario.css';

export interface NavItem { id: string; label: string; icon: IconName; name?: string }

export const NAV_ITEMS: NavItem[] = [
  { id: 'dashboard', label: '대시보드', icon: 'home' },
  { id: 'upload', label: '데이터 업로드', icon: 'upload' },
  { id: 'verify', label: '데이터 검증', icon: 'shield' },
  { id: 'forecast', label: '수요예측', icon: 'chart' },
  { id: 'plan', label: '생산계획', icon: 'calendar' },
  { id: 'whatif', label: '시나리오 분석', icon: 'box' },
];

interface ShellProps {
  mode: 'real' | 'scenario';
  nav: NavItem[];
  active: string;
  onNav: (id: string) => void;
  dataset: ReactNode;
  topEnd?: ReactNode;
  crumb: string[];
  notice?: ReactNode;
  footer?: ReactNode;
  children: ReactNode;
}

// 기획 시안의 공통 셸: 남색 사이드바 + 데이터셋 상단 바. 실제 업무 화면과 예시 시나리오가 함께 쓴다.
export default function Shell({ mode, nav, active, onNav, dataset, topEnd, crumb, notice, footer, children }: ShellProps) {
  return <div className="sc-shell">
    <div className="sc-side">
      <div className="sc-brand"><Icon name="logo" size={26} /><span>충파모</span></div>
      <nav aria-label="업무 메뉴"><ul>{nav.map((item) => <li key={item.id}>
        <button type="button" className={item.id === active ? 'active' : ''} aria-current={item.id === active ? 'page' : undefined}
          aria-label={item.name} onClick={() => onNav(item.id)}>
          <Icon name={item.icon} size={19} /><span>{item.label}</span>
        </button></li>)}</ul></nav>
      <div className="sc-mode" aria-label="화면 모드">
        <a href="#" aria-current={mode === 'real' ? 'true' : undefined}>실제 데이터</a>
        <a href="#scenario" aria-current={mode === 'scenario' ? 'true' : undefined}>예시 시나리오</a>
      </div>
      <p className="sc-photo-credit">배경 사진: <a href="https://commons.wikimedia.org/wiki/File:Burgos_BOBINAS.jpg" target="_blank" rel="noreferrer">FFC1966, CC BY-SA 4.0</a></p>
    </div>
    <div className="sc-frame">
      <header className="sc-top">
        {dataset}
        <div className="sc-top-icons">{topEnd}<Icon name="bell" size={20} /><Icon name="help" size={20} /><span className="sc-avatar"><Icon name="user" size={18} /></span></div>
      </header>
      {notice}
      <main className={`sc-main sc-main-${mode}`}>
        <nav className="sc-crumb" aria-label="위치"><Icon name="home" size={15} />
          {crumb.map((part, i) => <span key={part} className={i === crumb.length - 1 ? 'here' : ''}>{i > 0 && <Icon name="chevronRight" size={13} />}{part}</span>)}
        </nav>
        {children}
      </main>
      {footer}
    </div>
  </div>;
}
