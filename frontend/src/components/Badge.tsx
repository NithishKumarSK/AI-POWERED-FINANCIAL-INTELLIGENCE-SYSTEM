interface BadgeProps {
  decision?: string | null
}

export function DecisionBadge({ decision }: BadgeProps) {
  const d = (decision || '').toUpperCase()
  const cls =
    d === 'BUY' ? 'badge-buy' : d === 'SELL' ? 'badge-sell' : d === 'HOLD' ? 'badge-hold' : 'badge-neutral'
  return <span className={`badge ${cls}`}>{d || '—'}</span>
}

export function MatchBadge({ match }: { match?: boolean | null }) {
  if (match === undefined || match === null) {
    return <span className="badge badge-neutral">—</span>
  }
  return (
    <span className={`badge ${match ? 'badge-buy' : 'badge-sell'}`}>{match ? 'MATCH' : 'CONFLICT'}</span>
  )
}

export function StatusBadge({ status }: { status?: string | null }) {
  const s = (status || '').toUpperCase()
  const cls = s === 'SUCCESS' || s === 'VALIDATED' ? 'badge-buy' : s === 'PENDING' ? 'badge-hold' : 'badge-sell'
  return <span className={`badge ${cls}`}>{s || '—'}</span>
}
