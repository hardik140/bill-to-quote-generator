import { useMemo, useState } from 'react'
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table'
import type { BillItemOut } from '../types'
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
        align === 'right' ? 'text-right font-medium' : 'text-left'
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
        header: 'Product Name',
        cell: ({ row }) => (
          <EditableCell
            value={row.original.description}
            disabled={readOnly}
            onCommit={(v) => onFieldCommit(row.original.id, 'description', v)}
          />
        ),
      }),
      columnHelper.accessor('rate', {
        header: () => <span className="block text-right">Rate</span>,
        cell: ({ row }) => (
          <EditableCell
            value={row.original.rate}
            disabled={readOnly}
            align="right"
            onCommit={(v) => onFieldCommit(row.original.id, 'rate', v)}
          />
        ),
      }),
      columnHelper.display({
        id: 'actions',
        header: '',
        cell: ({ row }) =>
          readOnly ? null : (
            <div className="flex items-center justify-end gap-1 text-slate-400">
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
                <th key={h.id} className="px-3 py-2 first:pl-4 last:pr-4">
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
                <td key={cell.id} className="px-3 py-1 first:pl-4 last:pr-4">
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </td>
              ))}
            </tr>
          ))}
          {items.length === 0 && (
            <tr>
              <td colSpan={5} className="px-4 py-6 text-center text-slate-400">
                No line items yet. Use "Add item" to enter one manually.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}
