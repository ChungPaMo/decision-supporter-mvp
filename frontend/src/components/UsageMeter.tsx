export default function UsageMeter({ label, used, limit, unit, status }: {
  label: string; used: string | null; limit: string | null; unit: string | null; status: string;
}) {
  const values = used !== null && limit !== null && Number.isFinite(Number(used)) && Number.isFinite(Number(limit));
  const percent = values && Number(limit) > 0 ? Number(used) / Number(limit) * 100 : null;
  const overflow = percent !== null && percent > 100;
  return <article className={`resource-card ${overflow ? 'resource-over' : ''}`}>
    <h4>{label}</h4><strong>{percent === null ? '미산출' : `${percent.toFixed(1)}%`}</strong>
    <div className="usage-track" role="img" aria-label={`${label}: ${used ?? '미확인'} / ${limit ?? '미확인'} ${unit ?? ''}, ${status}`}>
      <span style={{ width: `${percent === null ? 0 : Math.min(100, Math.max(0, percent))}%` }} /><i /></div>
    <p>{used ?? '—'} / {limit ?? '—'} {unit ?? ''}</p><small>{status}{overflow ? ' · 표시 막대 상한 초과' : ''}</small>
  </article>;
}
