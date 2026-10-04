import { useEffect, useState } from 'react'
import { apiErrorMessage, fetchPending, resolvePending } from '../lib/api'
import type { PendingRecord, ResolverResult, Scope } from '../lib/types'
import { DecisionBadge } from '../components/Badge'

function daysUntil(dateStr: string): number {
  const target = new Date(dateStr)
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return Math.round((target.getTime() - today.getTime()) / 86_400_000)
}

export function PendingPage() {
  const [scope, setScope] = useState<Scope>('team')
  const [records, setRecords] = useState<PendingRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [resolving, setResolving] = useState(false)
  const [error, setError] = useState('')
  const [resolverResult, setResolverResult] = useState<ResolverResult | null>(null)

  const load = async (nextScope: Scope) => {
    setLoading(true)
    setError('')
    try {
      const r = await fetchPending(nextScope)
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

  const handleResolve = async () => {
    setResolving(true)
    setResolverResult(null)
    try {
      const res = await resolvePending()
      setResolverResult(res)
      await load(scope)
    } catch (err) {
      setError(apiErrorMessage(err))
    } finally {
      setResolving(false)
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Pending Predictions</h1>
          <p className="mt-1 text-sm text-slate-500">
            Predictions whose target date hasn't arrived yet. Once it does, resolving checks the real
            outcome and moves the record into the accuracy ledger.
          </p>
        </div>
        <button
          onClick={handleResolve}
          disabled={resolving}
          className="rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-blue-700 disabled:opacity-60"
        >
          {resolving ? 'Resolving…' : 'Resolve Due Predictions'}
        </button>
      </div>

      {resolverResult && (
        <div className="card mt-4 p-4 text-sm">
          {resolverResult.error ? (
            <span className="text-red-600">Resolver error: {resolverResult.error}</span>
          ) : (
            <span className="text-slate-700">
              Checked <strong>{resolverResult.candidates}</strong> due prediction(s) —{' '}
              <strong className="text-emerald-600">{resolverResult.resolved} validated</strong>,{' '}
              <strong className="text-amber-600">{resolverResult.invalid} invalid</strong>,{' '}
              <strong>{resolverResult.skipped} still waiting on market data</strong>.
            </span>
          )}
        </div>
      )}

      {error && <p className="mt-4 text-sm text-red-600">{error}</p>}

      <div className="mt-6 flex justify-end">
        <div className="flex overflow-hidden rounded-md border border-slate-200 bg-white text-xs font-medium">
          {(['team', 'mine'] as Scope[]).map((s) => (
            <button
              key={s}
              onClick={() => setScope(s)}
              className={`px-3 py-2 transition ${scope === s ? 'bg-blue-600 text-white' : 'text-slate-600 hover:bg-slate-50'}`}
            >
              {s === 'team' ? 'Everyone' : 'My Pending'}
            </button>
          ))}
        </div>
      </div>

      <div className="card mt-3 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
                <th className="px-5 py-2.5">Symbol</th>
                <th className="px-5 py-2.5">Origin Date</th>
                <th className="px-5 py-2.5">Target Date</th>
                <th className="px-5 py-2.5">Resolves In</th>
                <th className="px-5 py-2.5">AI Decision</th>
                <th className="px-5 py-2.5">Predicted Return</th>
              </tr>
            </thead>
            <tbody>
              {records.map((r, i) => {
                const d = daysUntil(r.target_date)
                return (
                  <tr key={`${r.symbol}-${i}`} className="border-b border-slate-100 last:border-0 hover:bg-slate-50">
                    <td className="px-5 py-2.5 font-medium text-slate-800">{r.symbol}</td>
                    <td className="px-5 py-2.5 text-slate-500">{r.prediction_origin_date}</td>
                    <td className="px-5 py-2.5 text-slate-500">{r.target_date}</td>
                    <td className="px-5 py-2.5">
                      <span className={d <= 0 ? 'font-medium text-amber-600' : 'text-slate-600'}>
                        {d <= 0 ? 'Due now' : `${d} day${d === 1 ? '' : 's'}`}
                      </span>
                    </td>
                    <td className="px-5 py-2.5"><DecisionBadge decision={r.ai_decision} /></td>
                    <td className="px-5 py-2.5 text-slate-600">
                      {r.predicted_return_pct !== undefined ? `${r.predicted_return_pct >= 0 ? '+' : ''}${r.predicted_return_pct.toFixed(2)}%` : '—'}
                    </td>
                  </tr>
                )
              })}
              {!loading && records.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-5 py-10 text-center text-sm text-slate-400">
                    Nothing pending{scope === 'mine' ? ' for you' : ''} right now.
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
