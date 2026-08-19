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
  const [deleting, setDeleting] = useState(false)
  const [documentToDelete, setDocumentToDelete] = useState<DocumentSummary | null>(null)
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

  async function handleDeleteConfirm() {
    if (!documentToDelete) return
    setDeleting(true)
    setError(null)
    try {
      await documentsApi.delete(documentToDelete.id)
      setDocuments((prev) => prev.filter((d) => d.id !== documentToDelete.id))
      setDocumentToDelete(null)
    } catch (err) {
      setError(apiErrorMessage(err, 'Could not delete this document.'))
    } finally {
      setDeleting(false)
    }
  }

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return documents
    return documents.filter((d) => d.original_filename.toLowerCase().includes(q))
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
            placeholder="Search by filename"
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
                <th className="px-4 py-3">Uploaded</th>
                <th className="px-4 py-3 text-right">Baseline Total</th>
                <th className="px-4 py-3 text-center">Scenarios</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading && (
                <tr>
                  <td colSpan={6} className="px-4 py-6 text-center text-slate-400">
                    Loading…
                  </td>
                </tr>
              )}
              {!loading && filtered.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-6 text-center text-slate-400">
                    No documents yet. Upload a bill to get started.
                  </td>
                </tr>
              )}
              {filtered.map((doc) => (
                <tr key={doc.id} className="hover:bg-slate-50">
                  <td className="max-w-[260px] truncate px-4 py-3 font-medium text-slate-700">{doc.original_filename}</td>
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
                    <div className="flex items-center justify-end gap-2">
                      <button
                        type="button"
                        onClick={() => navigate(`/documents/${doc.id}/review`)}
                        className="rounded-lg px-2.5 py-1 text-sm font-medium text-indigo-600 hover:bg-indigo-50 hover:text-indigo-700 transition-colors"
                      >
                        Open →
                      </button>
                      <button
                        type="button"
                        title="Delete document"
                        aria-label={`Delete ${doc.original_filename}`}
                        onClick={() => setDocumentToDelete(doc)}
                        className="rounded-lg p-1.5 text-slate-400 hover:bg-red-50 hover:text-red-600 transition-colors"
                      >
                        <svg
                          className="h-4 w-4"
                          fill="none"
                          viewBox="0 0 24 24"
                          strokeWidth="1.75"
                          stroke="currentColor"
                          aria-hidden="true"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0"
                          />
                        </svg>
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {documentToDelete && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4 backdrop-blur-xs"
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-dialog-title"
        >
          <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl space-y-4">
            <div className="flex items-start gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-red-100 text-red-600">
                <svg
                  className="h-5 w-5"
                  fill="none"
                  viewBox="0 0 24 24"
                  strokeWidth="2"
                  stroke="currentColor"
                  aria-hidden="true"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0"
                  />
                </svg>
              </div>
              <div className="space-y-1">
                <h3 id="delete-dialog-title" className="text-base font-semibold text-slate-900">
                  Delete document
                </h3>
                <p className="text-sm text-slate-500">
                  Are you sure you want to delete <span className="font-medium text-slate-700">{documentToDelete.original_filename}</span>?
                  This action cannot be undone and will permanently remove this document and any generated quotations.
                </p>
              </div>
            </div>

            <div className="flex justify-end gap-3 pt-2">
              <button
                type="button"
                disabled={deleting}
                onClick={() => setDocumentToDelete(null)}
                className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50 cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={deleting}
                onClick={handleDeleteConfirm}
                className="inline-flex items-center gap-2 rounded-lg bg-red-600 px-4 py-2 text-sm font-semibold text-white hover:bg-red-500 disabled:opacity-50 cursor-pointer"
              >
                {deleting && (
                  <div className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                )}
                {deleting ? 'Deleting…' : 'Delete document'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
