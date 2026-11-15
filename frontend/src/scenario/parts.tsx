import { ReactNode } from 'react';
import Icon, { IconName } from './icons';

export type Tone = 'ok' | 'warn' | 'bad' | 'info' | 'violet' | 'muted' | 'solid';

export function Chip({ tone, icon, children }: { tone: Tone; icon?: IconName; children: ReactNode }) {
  return <span className={`sc-chip sc-tone-${tone}`}>{icon && <Icon name={icon} size={14} />}{children}</span>;
}

export function Card({ title, aside, children, className = '', label }: { title?: ReactNode; aside?: ReactNode; children: ReactNode; className?: string; label?: string }) {
  return <section className={`sc-card ${className}`} aria-label={label}>
    {(title || aside) && <div className="sc-card-head">{title && <h3>{title}</h3>}{aside}</div>}
    {children}
  </section>;
}

// 사용자가 직접 확인·결정해야 함을 알리는 경고 띠.
export function Caution({ title, children, compact }: { title: string; children?: ReactNode; compact?: boolean }) {
  return <div className={`sc-caution${compact ? ' compact' : ''}`} role="note">
    <Icon name="warn" size={compact ? 20 : 24} />
    <div><strong>{title}</strong>{children && <p>{children}</p>}</div>
  </div>;
}

export function Stepper({ steps, current }: { steps: string[]; current: number }) {
  return <ol className="sc-stepper" aria-label="등록 단계">{steps.map((label, i) => {
    const state = i + 1 === current ? 'current' : i + 1 < current ? 'done' : 'todo';
    return <li key={label} className={state} aria-current={state === 'current' ? 'step' : undefined}>
      <span className="sc-step-no">{i + 1}</span>{label}
    </li>;
  })}</ol>;
}

export function Kpi({ icon, label, sub, value, tone = 'info', aside }: { icon: IconName; label: string; sub?: string; value: string; tone?: Tone; aside?: ReactNode }) {
  return <div className="sc-kpi">
    <span className={`sc-kpi-icon sc-tone-${tone}`}><Icon name={icon} size={22} /></span>
    <div><span className="sc-kpi-label">{label}</span>{sub && <small>{sub}</small>}<strong>{value}</strong></div>
    {aside}
  </div>;
}

export function Facts({ rows }: { rows: Array<{ icon?: IconName; label: string; value: ReactNode }> }) {
  return <dl className="sc-facts">{rows.map((row) => <div key={row.label}>
    <dt>{row.icon && <Icon name={row.icon} size={16} />}{row.label}</dt><dd>{row.value}</dd>
  </div>)}</dl>;
}
