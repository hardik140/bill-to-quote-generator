import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiErrorMessage, documentsApi } from '../api/client'
import type { DocumentSummary } from '../types'
import { formatDateTime, formatMoney } from '../lib/format'

const ACCEPTED = ['.pdf', '.jpg', '.jpeg', '.png']

const STATUS_STYLES: Record<string, string> = {
  uploaded: 'bg-slate-100 text-slate-600',
  processing: 'bg-amber-100 text-amber-700',
  processed: 'bg-emerald-100 text-emerald-700',
  failed: 'bg-red-100 text-red-700',
  archived: 'bg-slate-100 text-slate-500',
}

export default function Dashboard() {
  const [documents, setDocuments] = useState<DocumentSummary[]>([])
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [dragActive, setDragActive] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const navigate = useNavigate()

  async function refresh() {
    setLoading(true)
    try {
      const docs = await documentsApi.list()
      setDocuments(docs)
    } catch (err) {
      setError(apiErrorMessage(err, 'Could not load recent documents.'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refresh()
  }, [])

  async function handleFile(file: File) {
    const ext = '.' + file.name.split('.').pop()?.toLowerCase()
    if (!ACCEPTED.includes(ext)) {
      setError(`Unsupported file type '${ext}'. Allowed: ${ACCEPTED.join(', ')}`)
      return
    }
    setError(null)
    setUploading(true)
    try {
      const uploaded = await documentsApi.upload(file)
      await documentsApi.extract(uploaded.document_id)
      navigate(`/documents/${uploaded.document_id}/review`)
    } catch (err) {
      setError(apiErrorMessage(err, 'Unable to confidently extract this document. Please review or enter the fields manually.'))
      await refresh()
    } finally {
      setUploading(false)
    }
  }

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return documents
    return documents.filter((d) =>
      [d.original_filename, d.vendor_name, d.invoice_number].some((v) => v?.toLowerCase().includes(q))
    )
  }, [documents, query])

  return (
    <div className="space-y-8">
      <section
        className={`rounded-xl border-2 border-dashed p-10 text-center transition-colors ${
          dragActive ? 'border-indigo-400 bg-indigo-50' : 'border-slate-300 bg-white'
        }`}
        onDragOver={(e) => {
          e.preventDefault()
          setDragActive(true)
        }}
        onDragLeave={() => setDragActive(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDragActive(false)
          const file = e.dataTransfer.files?.[0]
          if (file) handleFile(file)
        }}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept={ACCEPTED.join(',')}
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0]
            if (file) handleFile(file)
            e.target.value = ''
          }}
        />
        {uploading ? (
          <div className="space-y-2">
            <div className="mx-auto h-8 w-8 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent" />
            <p className="text-sm text-slate-500">Uploading and extracting locally… this can take up to 30 seconds.</p>
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-base font-medium text-slate-700">Drop a bill / invoice here, or</p>
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-500"
            >
              Choose a file
            </button>
            <p className="text-xs text-slate-400">PDF, JPG, or PNG · up to 20 MB · stays on this machine</p>
          </div>
        )}
      </section>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
      )}

      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-semibold">Recent documents</h2>
          <input
            type="search"
            placeholder="Search by filename, vendor, invoice no."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="w-72 rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-indigo-400 focus:outline-none"
          />
        </div>

        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-3">File</th>
                <th className="px-4 py-3">Vendor</th>
                <th className="px-4 py-3">Invoice No.</th>
                <th className="px-4 py-3">Uploaded</th>
                <th className="px-4 py-3 text-right">Baseline Total</th>
                <th className="px-4 py-3 text-center">Scenarios</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading && (
                <tr>
                  <td colSpan={8} className="px-4 py-6 text-center text-slate-400">
                    Loading…
                  </td>
                </tr>
              )}
              {!loading && filtered.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-4 py-6 text-center text-slate-400">
                    No documents yet. Upload a bill to get started.
                  </td>
                </tr>
              )}
              {filtered.map((doc) => (
                <tr key={doc.id} className="hover:bg-slate-50">
                  <td className="max-w-[220px] truncate px-4 py-3 font-medium text-slate-700">{doc.original_filename}</td>
                  <td className="px-4 py-3 text-slate-600">{doc.vendor_name ?? '-'}</td>
                  <td className="px-4 py-3 text-slate-600">{doc.invoice_number ?? '-'}</td>
                  <td className="px-4 py-3 text-slate-500">{formatDateTime(doc.uploaded_at)}</td>
                  <td className="px-4 py-3 text-right text-slate-700">
                    {doc.grand_total != null ? formatMoney(doc.grand_total) : '-'}
                  </td>
                  <td className="px-4 py-3 text-center text-slate-600">{doc.scenario_count}</td>
                  <td className="px-4 py-3">
                    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[doc.status] ?? 'bg-slate-100 text-slate-600'}`}>
                      {doc.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={() => navigate(`/documents/${doc.id}/review`)}
                      className="text-sm font-medium text-indigo-600 hover:text-indigo-500"
                    >
                      Open →
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
