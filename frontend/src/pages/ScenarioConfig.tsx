import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { apiErrorMessage, billsApi, documentsApi, scenariosApi } from '../api/client'
import type { BillOut, RoundingMode } from '../types'
import Layout from '../components/Layout'
import { formatMoney } from '../lib/format'

const ROUNDING_OPTIONS: { value: RoundingMode; label: string }[] = [
  { value: 'none', label: 'No rounding' },
  { value: 'nearest_1', label: 'Nearest ₹1' },
  { value: 'nearest_5', label: 'Nearest ₹5' },
  { value: 'nearest_10', label: 'Nearest ₹10' },
]

export default function ScenarioConfig() {
  const { documentId } = useParams<{ documentId: string }>()
  const navigate = useNavigate()
  const [bill, setBill] = useState<BillOut | null>(null)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [markupB, setMarkupB] = useState('10')
  const [markupC, setMarkupC] = useState('20')
  const [rounding, setRounding] = useState<RoundingMode>('none')

  useEffect(() => {
    async function load() {
      if (!documentId) return
      try {
        const doc = await documentsApi.get(documentId)
        if (!doc.bill_id) {
          navigate(`/documents/${documentId}/review`)
          return
        }
        const b = await billsApi.get(doc.bill_id)
        if (!b.confirmed) {
          navigate(`/documents/${documentId}/review`)
          return
        }
        setBill(b)
      } catch (err) {
        setError(apiErrorMessage(err, 'Could not load this bill.'))
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [documentId, navigate])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!bill) return
    setSubmitting(true)
    setError(null)
    try {
      await scenariosApi.create(bill.id, {
        scenario_b_markup_percent: Number(markupB),
        scenario_c_markup_percent: Number(markupC),
        rounding,
      })
      navigate(`/documents/${documentId}/results`)
    } catch (err) {
      setError(apiErrorMessage(err, 'Could not generate scenarios.'))
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return (
      <Layout>
        <p className="text-slate-400">Loading…</p>
      </Layout>
    )
  }

  if (!bill) {
    return (
      <Layout>
        <p className="text-red-600">{error}</p>
      </Layout>
    )
  }

  return (
    <Layout>
      <h1 className="mb-1 text-xl font-semibold">Configure scenarios</h1>
      <p className="mb-6 text-sm text-slate-500">
        Baseline total: <span className="font-medium text-slate-700">{formatMoney(bill.grand_total, bill.currency)}</span>
      </p>

      {error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
      )}

      <form onSubmit={handleSubmit} className="max-w-xl space-y-6 rounded-xl border border-slate-200 bg-white p-6">
        <div className="grid grid-cols-2 gap-4">
          <label className="block">
            <span className="text-sm font-medium text-slate-700">Scenario B markup (%)</span>
            <input
              type="number"
              min={0}
              step="0.01"
              required
              value={markupB}
              onChange={(e) => setMarkupB(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-400 focus:outline-none"
            />
          </label>
          <label className="block">
            <span className="text-sm font-medium text-slate-700">Scenario C markup (%)</span>
            <input
              type="number"
              min={0}
              step="0.01"
              required
              value={markupC}
              onChange={(e) => setMarkupC(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-400 focus:outline-none"
            />
          </label>
        </div>

        <label className="block">
          <span className="text-sm font-medium text-slate-700">Rounding policy</span>
          <select
            value={rounding}
            onChange={(e) => setRounding(e.target.value as RoundingMode)}
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-400 focus:outline-none"
          >
            {ROUNDING_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </label>

        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-800">
          Scenario B and C will be clearly labelled{' '}
          <strong>SIMULATED / INTERNAL ESTIMATE — NOT A VENDOR QUOTATION</strong>. They are internal estimates for
          budgeting and comparison only and do not represent genuine third-party quotations.
        </div>

        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-500 disabled:bg-slate-300"
        >
          {submitting ? 'Calculating…' : 'Generate scenarios →'}
        </button>
      </form>
    </Layout>
  )
}
