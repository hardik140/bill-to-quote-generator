import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { apiErrorMessage, billsApi, documentsApi } from '../api/client'
import type { BillItemOut, BillOut, DocumentDetail } from '../types'
import Layout from '../components/Layout'
import BillItemsTable from '../components/BillItemsTable'
import { formatMoney } from '../lib/format'

export default function ExtractionReview() {
  const { documentId } = useParams<{ documentId: string }>()
  const navigate = useNavigate()
  const [doc, setDoc] = useState<DocumentDetail | null>(null)
  const [bill, setBill] = useState<BillOut | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [confirming, setConfirming] = useState(false)

  const load = useCallback(async () => {
    if (!documentId) return
    setLoading(true)
    try {
      const d = await documentsApi.get(documentId)
      setDoc(d)
      if (d.bill_id) {
        const b = await billsApi.get(d.bill_id)
        setBill(b)
      }
    } catch (err) {
      setError(apiErrorMessage(err, 'Could not load this document.'))
    } finally {
      setLoading(false)
    }
  }, [documentId])

  useEffect(() => {
    load()
  }, [load])

  async function handleItemFieldCommit(itemId: string, field: keyof BillItemOut, value: string) {
    if (!bill) return
    setError(null)
    try {
      const payload = field === 'rate' ? { rate: Number(value) } : { [field]: value }
      const updated = await billsApi.updateItem(bill.id, itemId, payload)
      setBill((prev) =>
        prev ? { ...prev, items: prev.items.map((i) => (i.id === itemId ? updated : i)) } : prev
      )
      const fresh = await billsApi.get(bill.id)
      setBill(fresh)
    } catch (err) {
      setError(apiErrorMessage(err, 'That value was not accepted.'))
      load()
    }
  }

  async function handleDeleteItem(itemId: string) {
    if (!bill) return
    try {
      await billsApi.deleteItem(bill.id, itemId)
      const fresh = await billsApi.get(bill.id)
      setBill(fresh)
    } catch (err) {
      setError(apiErrorMessage(err, 'Could not delete that item.'))
    }
  }

  async function handleMoveItem(itemId: string, direction: -1 | 1) {
    if (!bill) return
    const ids = bill.items.map((i) => i.id)
    const idx = ids.indexOf(itemId)
    const swapWith = idx + direction
    if (swapWith < 0 || swapWith >= ids.length) return
    ;[ids[idx], ids[swapWith]] = [ids[swapWith], ids[idx]]
    try {
      await billsApi.reorderItems(bill.id, ids)
      const fresh = await billsApi.get(bill.id)
      setBill(fresh)
    } catch (err) {
      setError(apiErrorMessage(err, 'Could not reorder items.'))
    }
  }

  async function handleAddItem() {
    if (!bill) return
    try {
      await billsApi.addItem(bill.id, { description: 'New item', rate: 0 })
      const fresh = await billsApi.get(bill.id)
      setBill(fresh)
    } catch (err) {
      setError(apiErrorMessage(err, 'Could not add a new item.'))
    }
  }

  async function handleConfirm() {
    if (!bill) return
    setConfirming(true)
    setError(null)
    try {
      await billsApi.confirm(bill.id)
      navigate(`/documents/${documentId}/scenarios`)
    } catch (err) {
      setError(apiErrorMessage(err, 'Could not confirm this bill.'))
    } finally {
      setConfirming(false)
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

  const readOnly = !!bill?.confirmed

  return (
    <Layout>
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">{doc.original_filename}</h1>
          <p className="text-sm text-slate-500">
            {bill ? (bill.confirmed ? 'Confirmed' : 'Awaiting review') : 'Extraction in progress'}
          </p>
        </div>
        {bill?.confirmed && (
          <button
            onClick={() => navigate(`/documents/${documentId}/scenarios`)}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-500"
          >
            Continue to scenarios →
          </button>
        )}
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
      )}

      {bill && bill.extraction_status === 'needs_review' && !bill.confirmed && (
        <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          Some items need your review — low-confidence values are highlighted below, and the extracted total may
          differ from the sum of rates. Please verify against the source document before confirming.
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="rounded-xl border border-slate-200 bg-white p-2" style={{ minHeight: 480 }}>
          {doc.mime_type === 'application/pdf' ? (
            <iframe title="Original document" src={doc.preview_url} className="h-[480px] w-full rounded-lg" />
          ) : (
            <img src={doc.preview_url} alt="Original document" className="mx-auto max-h-[480px] rounded-lg object-contain" />
          )}
        </div>

        <div>
          {bill && (
            <div className="rounded-xl border border-slate-200 bg-white p-6">
              <div className="mb-4 flex items-center justify-between">
                <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Totals</h2>
                <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs text-slate-500">
                  SOURCE / BASELINE
                </span>
              </div>
              <div>
                <div className="text-xs text-slate-400">Total</div>
                <div className="text-2xl font-bold text-slate-800">{formatMoney(bill.grand_total, bill.currency)}</div>
              </div>
            </div>
          )}
        </div>
      </div>

      {bill && (
        <div className="mt-6 space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Product Line Items</h2>
            {!readOnly && (
              <button onClick={handleAddItem} className="text-sm font-medium text-indigo-600 hover:text-indigo-500">
                + Add item
              </button>
            )}
          </div>
          <BillItemsTable
            items={bill.items}
            readOnly={readOnly}
            currency={bill.currency}
            onFieldCommit={handleItemFieldCommit}
            onDelete={handleDeleteItem}
            onMove={handleMoveItem}
          />
          {!readOnly && (
            <div className="flex justify-end">
              <button
                onClick={handleConfirm}
                disabled={confirming || bill.items.length === 0}
                className="rounded-lg bg-emerald-600 px-5 py-2 text-sm font-semibold text-white hover:bg-emerald-500 disabled:cursor-not-allowed disabled:bg-slate-300"
              >
                {confirming ? 'Confirming…' : 'Confirm source data →'}
              </button>
            </div>
          )}
        </div>
      )}
    </Layout>
  )
}
