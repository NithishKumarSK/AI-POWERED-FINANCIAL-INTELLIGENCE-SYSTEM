import { useState, type FormEvent, type ReactNode } from 'react'
import { apiErrorMessage, validateStockPrediction } from '../lib/api'
import type { StockPredictionRequest, ValidationResult } from '../lib/types'
import { DecisionBadge, MatchBadge, StatusBadge } from '../components/Badge'

const todayStr = new Date().toISOString().slice(0, 10)
const defaultOrigin = (() => {
  const d = new Date()
  d.setMonth(d.getMonth() - 2)
  return d.toISOString().slice(0, 10)
})()
const defaultCtxStart = (() => {
  const d = new Date()
  d.setFullYear(d.getFullYear() - 1)
  return d.toISOString().slice(0, 10)
})()

const initialForm: StockPredictionRequest = {
  symbol: 'AAPL',
  historical_context_start_date: defaultCtxStart,
  prediction_origin_date: defaultOrigin,
  decision_horizon_days: 30,
  initial_capital: 50000,
  benchmark: 'SPY',
  validation_mode: 'horizon_days',
  price_basis: 'close',
}

function fmtPct(v: number | undefined | null): string {
  if (v === undefined || v === null) return '—'
  return `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`
}

function fmtMoney(v: number | undefined | null): string {
  if (v === undefined || v === null) return '—'
  return `$${v.toLocaleString(undefined, { maximumFractionDigits: 0 })}`
}

export function PredictPage() {
  const [form, setForm] = useState<StockPredictionRequest>(initialForm)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<ValidationResult | null>(null)

  const update = <K extends keyof StockPredictionRequest>(key: K, value: StockPredictionRequest[K]) => {
    setForm((f) => ({ ...f, [key]: value }))
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    setResult(null)
    try {
      const res = await validateStockPrediction(form)
      setResult(res)
    } catch (err) {
      setError(apiErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <h1 className="text-2xl font-semibold text-slate-900">Stock Price Validation</h1>
      <p className="mt-1 text-sm text-slate-500">
        AI predicts the window after prediction origin date using only data up to that date. The market
        later proves it right or wrong.
      </p>

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-5">
        <form onSubmit={handleSubmit} className="card space-y-4 p-6 lg:col-span-2">
          <Field label="Symbol">
            <input
              value={form.symbol}
              onChange={(e) => update('symbol', e.target.value.toUpperCase())}
              className="input"
              required
            />
          </Field>
          <Field label="Historical context start date">
            <input
              type="date"
              value={form.historical_context_start_date}
              onChange={(e) => update('historical_context_start_date', e.target.value)}
              className="input"
              required
            />
          </Field>
          <Field label="Prediction origin date">
            <input
              type="date"
              value={form.prediction_origin_date}
              onChange={(e) => update('prediction_origin_date', e.target.value)}
              max={todayStr}
              className="input"
              required
            />
          </Field>
          <Field label="Decision horizon (days)">
            <input
              type="number"
              min={1}
              value={form.decision_horizon_days}
              onChange={(e) => update('decision_horizon_days', Number(e.target.value))}
              className="input"
            />
          </Field>
          <Field label="Initial capital ($)">
            <input
              type="number"
              min={1000}
              step={1000}
              value={form.initial_capital}
              onChange={(e) => update('initial_capital', Number(e.target.value))}
              className="input"
            />
          </Field>
          <Field label="Benchmark">
            <input
              value={form.benchmark}
              onChange={(e) => update('benchmark', e.target.value.toUpperCase())}
              className="input"
            />
          </Field>
          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-md bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-blue-700 disabled:opacity-60"
          >
            {loading ? 'Running prediction…' : 'Run Prediction'}
          </button>
          {error && <p className="text-sm text-red-600">{error}</p>}
        </form>

        <div className="lg:col-span-3">
          {!result && !loading && (
            <div className="card flex h-full min-h-[280px] items-center justify-center p-8 text-center text-sm text-slate-400">
              Results will appear here once you run a prediction.
            </div>
          )}
          {loading && (
            <div className="card flex h-full min-h-[280px] flex-col items-center justify-center gap-3 p-8 text-center text-sm text-slate-500">
              <div className="h-8 w-8 animate-spin rounded-full border-2 border-slate-200 border-t-blue-600" />
              Fetching market data and running the AI prediction — real external API calls, usually
              30–90 seconds.
            </div>
          )}
          {result && <ResultPanel result={result} />}
        </div>
      </div>
    </div>
  )
}

function ResultPanel({ result }: { result: ValidationResult }) {
  if (result.status === 'FAILED') {
    return (
      <div className="card p-6">
        <StatusBadge status="FAILED" />
        <p className="mt-3 text-sm text-slate-700">{result.error || 'The run could not be completed.'}</p>
      </div>
    )
  }

  const ai = result.ai_prediction
  const av = result.actual_validation
  const cmp = result.comparison

  return (
    <div className="space-y-4">
      <div className="card flex items-center justify-between p-4">
        <div className="flex items-center gap-3">
          <StatusBadge status={result.status} />
          {result.saved && <span className="text-xs text-slate-400">{result.save_message}</span>}
        </div>
        {result.status === 'PENDING' && (
          <span className="text-xs text-amber-600">{av?.validation_available_after && `Resolves after ${av.validation_available_after}`}</span>
        )}
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="card p-5">
          <div className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-500">
            AI Prediction
          </div>
          <div className="flex items-center justify-between">
            <DecisionBadge decision={ai?.decision} />
            <span className="text-2xl font-semibold text-slate-900">{fmtPct(ai?.predicted_return_pct)}</span>
          </div>
          <dl className="mt-4 space-y-1.5 text-sm">
            <Row label="Target price" value={ai?.predicted_target_price !== undefined ? `$${ai?.predicted_target_price?.toFixed(2)}` : '—'} />
            <Row label="Final capital" value={fmtMoney(ai?.predicted_final_capital)} />
            <Row label="Confidence" value={ai?.confidence_score !== undefined ? `${ai?.confidence_score}/100` : '—'} />
          </dl>
        </div>

        <div className="card p-5">
          <div className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-500">
            {result.status === 'PENDING' ? 'Actual Outcome' : 'Actual Outcome (ground truth)'}
          </div>
          {result.status === 'PENDING' ? (
            <p className="text-sm text-slate-500">
              {av?.reason || 'Target date has not arrived yet — this prediction is pending.'}
            </p>
          ) : (
            <>
              <div className="flex items-center justify-between">
                <DecisionBadge decision={av?.actual_decision} />
                <span className="text-2xl font-semibold text-slate-900">{fmtPct(av?.actual_return_pct)}</span>
              </div>
              <dl className="mt-4 space-y-1.5 text-sm">
                <Row label="Target price" value={av?.target_price !== undefined ? `$${av?.target_price?.toFixed(2)}` : '—'} />
                <Row label="Final capital" value={fmtMoney(av?.actual_final_capital)} />
              </dl>
            </>
          )}
        </div>
      </div>

      {cmp && result.status === 'SUCCESS' && (
        <div className="card p-5">
          <div className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-500">Comparison</div>
          <div className="flex flex-wrap items-center gap-4 text-sm">
            <MatchBadge match={cmp.decision_match} />
            <span className="text-slate-500">
              Return error: <span className="font-medium text-slate-800">{fmtPct(cmp.return_error_pct)}</span>
            </span>
            <span className="text-slate-500">
              Capital error:{' '}
              <span className="font-medium text-slate-800">
                {cmp.capital_error !== undefined ? fmtMoney(cmp.capital_error) : '—'}
              </span>
            </span>
          </div>
        </div>
      )}
    </div>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between">
      <dt className="text-slate-500">{label}</dt>
      <dd className="font-medium text-slate-800">{value}</dd>
    </div>
  )
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-slate-600">{label}</span>
      {children}
    </label>
  )
}
