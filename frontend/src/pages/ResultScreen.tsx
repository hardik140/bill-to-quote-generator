import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { apiErrorMessage, billsApi, documentsApi, scenariosApi } from '../api/client'
import type { DocumentDetail, ScenarioOut } from '../types'
import Layout from '../components/Layout'
import { formatMoney } from '../lib/format'

export default function ResultScreen() {
  const { documentId } = useParams<{ documentId: string }>()
  const navigate = useNavigate()
  const [doc, setDoc] = useState<DocumentDetail | null>(null)
  const [scenarios, setScenarios] = useState<ScenarioOut[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [generating, setGenerating] = useState<string | null>(null)
  const [pdfPaths, setPdfPaths] = useState<Record<string, string>>({})

  const load = useCallback(async () => {
    if (!documentId) return
    setLoading(true)
    try {
      const d = await documentsApi.get(documentId)
      setDoc(d)
      if (!d.bill_id) {
        navigate(`/documents/${documentId}/review`)
        return
      }
      const list = await billsApi.listScenarios(d.bill_id)
      if (list.length === 0) {
        navigate(`/documents/${documentId}/scenarios`)
        return
      }
      setScenarios(list)

      const files = await documentsApi.files(documentId)
      const map: Record<string, string> = {}
      for (const f of files) map[f.scenario_id] = f.storage_path
      setPdfPaths(map)
    } catch (err) {
      setError(apiErrorMessage(err, 'Could not load scenarios.'))
    } finally {
      setLoading(false)
    }
  }, [documentId, navigate])

  useEffect(() => {
    load()
  }, [load])

  async function handleGeneratePdf(scenarioId: string) {
    setGenerating(scenarioId)
    setError(null)
    try {
      const result = await scenariosApi.generatePdf(scenarioId)
      setPdfPaths((prev) => ({ ...prev, [scenarioId]: result.storage_path }))
    } catch (err) {
      setError(apiErrorMessage(err, 'Could not generate the PDF.'))
    } finally {
      setGenerating(null)
    }
  }

  if (loading) {
    return (
      <Layout>
        <p className="text-slate-400">Loading…</p>
      </Layout>
    )
  }

  if (!doc) {
    return (
      <Layout>
        <p className="text-red-600">{error ?? 'Document not found.'}</p>
      </Layout>
    )
  }

  return (
    <Layout>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Scenario results</h1>
          <p className="text-sm text-slate-500">{doc.original_filename}</p>
        </div>
        <button
          onClick={() => navigate(`/documents/${documentId}/scenarios`)}
          className="text-sm font-medium text-indigo-600 hover:text-indigo-500"
        >
          ← Reconfigure scenarios
        </button>
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
      )}

      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-3">Scenario</th>
              <th className="px-4 py-3">Markup</th>
              <th className="px-4 py-3 text-right">Total</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {scenarios.map((s) => {
              const isSimulated = s.scenario_type === 'SIMULATED'
              const pdfPath = pdfPaths[s.id]
              return (
                <tr key={s.id}>
                  <td className="px-4 py-3 font-medium text-slate-700">{s.label}</td>
                  <td className="px-4 py-3 text-slate-600">{isSimulated ? `${s.markup_percent}%` : '-'}</td>
                  <td className="px-4 py-3 text-right font-semibold text-slate-800">{formatMoney(s.grand_total)}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                        isSimulated ? 'bg-amber-100 text-amber-700' : 'bg-emerald-100 text-emerald-700'
                      }`}
                    >
                      {isSimulated ? 'Simulated' : 'Source'}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-end gap-3">
                      {pdfPath ? (
                        <a
                          href={`/files/generated/${s.bill_id}/${pdfPath.split(/[\\/]/).pop()}`}
                          target="_blank"
                          rel="noreferrer"
                          className="text-sm font-medium text-indigo-600 hover:text-indigo-500"
                        >
                          Preview PDF
                        </a>
                      ) : (
                        <span className="text-xs text-slate-400">Not generated yet</span>
                      )}
                      <button
                        onClick={() => handleGeneratePdf(s.id)}
                        disabled={generating === s.id}
                        className="rounded-lg bg-slate-800 px-3 py-1.5 text-xs font-semibold text-white hover:bg-slate-700 disabled:bg-slate-300"
                      >
                        {generating === s.id ? 'Generating…' : pdfPath ? 'Regenerate PDF' : 'Generate PDF'}
                      </button>
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {Object.keys(pdfPaths).length > 0 && (
        <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-xs text-slate-500">
          <div className="mb-1 font-medium text-slate-600">Files saved locally to:</div>
          {Object.values(pdfPaths)
            .filter((p, i, arr) => arr.indexOf(p) === i)
            .map((p) => (
              <div key={p} className="font-mono">
                {p}
              </div>
            ))}
        </div>
      )}
    </Layout>
  )
}
