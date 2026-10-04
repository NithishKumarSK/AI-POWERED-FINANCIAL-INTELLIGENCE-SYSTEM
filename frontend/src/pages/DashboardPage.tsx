import { useEffect, useState } from 'react'
import { apiErrorMessage, fetchPredictions, fetchSummary } from '../lib/api'
import type { AccuracySummary, LedgerRecord, Scope } from '../lib/types'
import { StatTile } from '../components/StatTile'
import { DecisionBadge, MatchBadge } from '../components/Badge'

function fmtPct(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined) return '—'
  return `${v.toFixed(digits)}%`
}

export function DashboardPage() {
  const [scope, setScope] = useState<Scope>('team')
  const [summary, setSummary] = useState<AccuracySummary | null>(null)
  const [records, setRecords] = useState<LedgerRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = async (nextScope: Scope) => {
    setLoading(true)
    setError('')
    try {
      const [s, r] = await Promise.all([fetchSummary(nextScope), fetchPredictions(nextScope, 50)])
      setSummary(s)
      setRecords(r.records)
    } catch (err) {
      setError(apiErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load(scope)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scope])

  return (
    <div>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Accuracy Dashboard</h1>
          <p className="mt-1 text-sm text-slate-500">
            Live from the shared team database — not a local file anyone's test runs get mixed into.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <ScopeToggle scope={scope} onChange={setScope} />
          <button
            onClick={() => load(scope)}
            className="rounded-md border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-600 hover:bg-slate-50"
          >
            Refresh
          </button>
        </div>
      </div>

      {error && <p className="mt-4 text-sm text-red-600">{error}</p>}

      <div className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-5">
        <StatTile label="Total Validated" value={summary ? String(summary.total) : '—'} />
        <StatTile label="Decision Match" value={fmtPct(summary?.decision_match_rate ?? null)} />
        <StatTile label="Direction Match" value={fmtPct(summary?.direction_match_rate ?? null)} />
        <StatTile
          label="Avg |Return Error|"
          value={summary?.avg_abs_return_error !== null && summary?.avg_abs_return_error !== undefined ? `${summary.avg_abs_return_error.toFixed(2)}pp` : '—'}
        />
        <StatTile
          label="Avg |Capital Error|"
          value={summary?.avg_abs_capital_error !== null && summary?.avg_abs_capital_error !== undefined ? `$${summary.avg_abs_capital_error.toLocaleString(undefined, { maximumFractionDigits: 0 })}` : '—'}
        />
      </div>

      <div className="card mt-6 overflow-hidden">
        <div className="border-b border-slate-200 px-5 py-3 text-sm font-semibold text-slate-700">
          Recent Runs {loading && <span className="font-normal text-slate-400">— loading…</span>}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
                <th className="px-5 py-2.5">Symbol</th>
                <th className="px-5 py-2.5">Target Date</th>
                <th className="px-5 py-2.5">AI Decision</th>
                <th className="px-5 py-2.5">Actual Decision</th>
                <th className="px-5 py-2.5">Match</th>
                <th className="px-5 py-2.5">Return Error</th>
              </tr>
            </thead>
            <tbody>
              {records.map((r, i) => (
                <tr key={`${r.run_id}-${i}`} className="border-b border-slate-100 last:border-0 hover:bg-slate-50">
                  <td className="px-5 py-2.5 font-medium text-slate-800">{r.stock_prediction_input?.symbol}</td>
                  <td className="px-5 py-2.5 text-slate-500">{r.stock_prediction_input?.target_date}</td>
                  <td className="px-5 py-2.5"><DecisionBadge decision={r.ai_prediction?.decision} /></td>
                  <td className="px-5 py-2.5"><DecisionBadge decision={r.actual_validation?.actual_decision} /></td>
                  <td className="px-5 py-2.5"><MatchBadge match={r.comparison?.decision_match} /></td>
                  <td className="px-5 py-2.5 text-slate-600">{fmtPct(r.comparison?.abs_return_error_pct ?? null, 2)}</td>
                </tr>
              ))}
              {!loading && records.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-5 py-10 text-center text-sm text-slate-400">
                    No validated records yet{scope === 'mine' ? ' for you' : ''}. Run a prediction to get started.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

function ScopeToggle({ scope, onChange }: { scope: Scope; onChange: (s: Scope) => void }) {
  return (
    <div className="flex overflow-hidden rounded-md border border-slate-200 bg-white text-xs font-medium">
      {(['team', 'mine'] as Scope[]).map((s) => (
        <button
          key={s}
          onClick={() => onChange(s)}
          className={`px-3 py-2 transition ${scope === s ? 'bg-blue-600 text-white' : 'text-slate-600 hover:bg-slate-50'}`}
        >
          {s === 'team' ? 'Everyone' : 'My Runs'}
        </button>
      ))}
    </div>
  )
}
