import { useMemo, useState } from 'react'
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table'
import type { BillItemOut } from '../types'
import { formatMoney } from '../lib/format'
import ConfidenceDot from './ConfidenceDot'

interface Props {
  items: BillItemOut[]
  readOnly: boolean
  currency: string
  onFieldCommit: (itemId: string, field: keyof BillItemOut, value: string) => void
  onDelete: (itemId: string) => void
  onMove: (itemId: string, direction: -1 | 1) => void
}

const columnHelper = createColumnHelper<BillItemOut>()

function EditableCell({
  value,
  disabled,
  align = 'left',
  onCommit,
}: {
  value: string | number
  disabled: boolean
  align?: 'left' | 'right'
  onCommit: (v: string) => void
}) {
  const [draft, setDraft] = useState(String(value))

  return (
    <input
      value={draft}
      disabled={disabled}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={() => {
        if (draft !== String(value)) onCommit(draft)
      }}
      className={`w-full rounded border border-transparent bg-transparent px-1.5 py-1 text-sm hover:border-slate-200 focus:border-indigo-400 focus:bg-white focus:outline-none disabled:text-slate-400 ${
        align === 'right' ? 'text-right' : 'text-left'
      }`}
    />
  )
}

export default function BillItemsTable({ items, readOnly, currency, onFieldCommit, onDelete, onMove }: Props) {
  const columns = useMemo(
    () => [
      columnHelper.display({
        id: 'flag',
        header: '',
        cell: ({ row }) => <ConfidenceDot lowConfidence={row.original.low_confidence} verified={row.original.user_verified} />,
      }),
      columnHelper.accessor('serial_no', {
        header: '#',
        cell: (info) => <span className="text-slate-400">{info.getValue()}</span>,
      }),
      columnHelper.accessor('description', {
        header: 'Description',
        cell: ({ row }) => (
          <EditableCell
            value={row.original.description}
            disabled={readOnly}
            onCommit={(v) => onFieldCommit(row.original.id, 'description', v)}
          />
        ),
      }),
      columnHelper.accessor('hsn_sac', {
        header: 'HSN/SAC',
        cell: ({ row }) => (
          <EditableCell
            value={row.original.hsn_sac ?? ''}
            disabled={readOnly}
            onCommit={(v) => onFieldCommit(row.original.id, 'hsn_sac', v)}
          />
        ),
      }),
      columnHelper.accessor('quantity', {
        header: 'Qty',
        cell: ({ row }) => (
          <EditableCell
            value={row.original.quantity}
            disabled={readOnly}
            align="right"
            onCommit={(v) => onFieldCommit(row.original.id, 'quantity', v)}
          />
        ),
      }),
      columnHelper.accessor('unit', {
        header: 'Unit',
        cell: ({ row }) => (
          <EditableCell
            value={row.original.unit ?? ''}
            disabled={readOnly}
            onCommit={(v) => onFieldCommit(row.original.id, 'unit', v)}
          />
        ),
      }),
      columnHelper.accessor('taxable_rate', {
        header: 'Rate',
        cell: ({ row }) => (
          <EditableCell
            value={row.original.taxable_rate}
            disabled={readOnly}
            align="right"
            onCommit={(v) => onFieldCommit(row.original.id, 'taxable_rate', v)}
          />
        ),
      }),
      columnHelper.accessor('gst_rate', {
        header: 'GST %',
        cell: ({ row }) => (
          <EditableCell
            value={row.original.gst_rate}
            disabled={readOnly}
            align="right"
            onCommit={(v) => onFieldCommit(row.original.id, 'gst_rate', v)}
          />
        ),
      }),
      columnHelper.accessor('line_amount', {
        header: 'Amount',
        cell: (info) => <span className="block text-right text-slate-600">{formatMoney(info.getValue(), currency)}</span>,
      }),
      columnHelper.accessor('tax_amount', {
        header: 'Tax',
        cell: (info) => <span className="block text-right text-slate-600">{formatMoney(info.getValue(), currency)}</span>,
      }),
      columnHelper.accessor('total_amount', {
        header: 'Total',
        cell: (info) => <span className="block text-right font-medium text-slate-800">{formatMoney(info.getValue(), currency)}</span>,
      }),
      columnHelper.display({
        id: 'actions',
        header: '',
        cell: ({ row }) =>
          readOnly ? null : (
            <div className="flex items-center gap-1 text-slate-400">
              <button title="Move up" onClick={() => onMove(row.original.id, -1)} className="hover:text-slate-700">
                ↑
              </button>
              <button title="Move down" onClick={() => onMove(row.original.id, 1)} className="hover:text-slate-700">
                ↓
              </button>
              <button title="Delete item" onClick={() => onDelete(row.original.id)} className="ml-1 hover:text-red-600">
                ✕
              </button>
            </div>
          ),
      }),
    ],
    [readOnly, currency, onFieldCommit, onDelete, onMove]
  )

  const table = useReactTable({ data: items, columns, getCoreRowModel: getCoreRowModel() })

  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
      <table className="w-full text-sm">
        <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id}>
              {hg.headers.map((h) => (
                <th key={h.id} className="px-2 py-2 first:pl-4 last:pr-4">
                  {flexRender(h.column.columnDef.header, h.getContext())}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody className="divide-y divide-slate-100">
          {table.getRowModel().rows.map((row) => (
            <tr key={row.id} className={row.original.low_confidence && !row.original.user_verified ? 'bg-amber-50/60' : undefined}>
              {row.getVisibleCells().map((cell) => (
                <td key={cell.id} className="px-2 py-1 first:pl-4 last:pr-4">
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </td>
              ))}
            </tr>
          ))}
          {items.length === 0 && (
            <tr>
              <td colSpan={11} className="px-4 py-6 text-center text-slate-400">
                No line items yet. Use "Add item" below to enter one manually.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}
