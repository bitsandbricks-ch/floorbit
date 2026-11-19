import { Group, Pagination, Paper, Table, Text, UnstyledButton } from '@mantine/core'
import { IconChevronDown, IconChevronUp, IconSelector } from '@tabler/icons-react'
import {
  flexRender, getCoreRowModel, getPaginationRowModel, getSortedRowModel, useReactTable,
  type ColumnDef, type PaginationState, type SortingState,
} from '@tanstack/react-table'
import { useMemo, useState, type CSSProperties, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import './DataTable.css'

/** Natural order for names and addresses (sw-2 before sw-10, 198.51.100.9 before .10). */
const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' })

/** One column of a DataTable: what it shows, and how it sorts when it sorts. */
export type DataColumn<T> = {
  id: string
  header: ReactNode
  cell: (row: T) => ReactNode
  /** The value to sort by; leave it out for a column that doesn't sort. */
  sort?: (row: T) => string | number | null | undefined
  /** CSS width, e.g. 44 or '20%'. */
  width?: number | string
  mono?: boolean
  /** Left out on a phone, where the table keeps only what names the row. */
  hideOnPhone?: boolean
}

export type DataTableProps<T> = {
  rows: T[]
  columns: DataColumn<T>[]
  rowKey: (row: T) => string
  /** The table's accessible name. */
  label: string
  /** Sorted by this column first. */
  defaultSort?: { id: string; desc?: boolean }
  /** Rows per page; 0 shows them all. */
  pageSize?: number
  /** Shown instead of the table when there are no rows. */
  empty?: ReactNode
  /** The line under the table, e.g. "12 devices"; it gets the row count. */
  count?: (n: number) => ReactNode
  rowStyle?: (row: T) => CSSProperties | undefined
  /** Keep the sort and page in the address (?sort=name&page=2), so a link or a reload shows the same view.
   *  Off where several tables share one page, such as a dashboard. */
  urlState?: boolean
  density?: 'default' | 'compact'
  /** Below this width the table scrolls sideways instead of squeezing. */
  minWidth?: number
  /** Drawn without the bordered box, for tables that already sit inside one. */
  bare?: boolean
  className?: string
}

/** The one table every page uses (#1015): sorting on the columns that can, paging, the empty state
 *  and the count. Search and filters sit above it on the page, and narrow `rows`. */
export function DataTable<T>(props: DataTableProps<T>) {
  const { rows, columns, rowKey, label, defaultSort, pageSize = 50, empty, count, rowStyle, urlState = true,
    density = 'default', minWidth, bare, className } = props
  const { t } = useTranslation()
  const [params, setParams] = useSearchParams()
  const initialSort: SortingState = defaultSort ? [{ id: defaultSort.id, desc: !!defaultSort.desc }] : []
  const [localSort, setLocalSort] = useState<SortingState>(initialSort)
  const [localPage, setLocalPage] = useState(0)

  // In the address: ?sort=name or ?sort=-name, and ?page=2 (counted from 1 for people).
  const sorting: SortingState = (() => {
    if (!urlState) return localSort
    const raw = params.get('sort')
    if (!raw) return initialSort
    const desc = raw.startsWith('-')
    return [{ id: desc ? raw.slice(1) : raw, desc }]
  })()
  const pageIndex = urlState ? Math.max(0, (Number(params.get('page')) || 1) - 1) : localPage

  const setUrl = (change: (p: URLSearchParams) => void) => setParams((p) => { const next = new URLSearchParams(p); change(next); return next }, { replace: true })
  const setSorting = (next: SortingState) => {
    if (!urlState) { setLocalSort(next); setLocalPage(0); return }
    setUrl((p) => {
      const s = next[0]
      const same = s && defaultSort && s.id === defaultSort.id && s.desc === !!defaultSort.desc
      if (!s || same) p.delete('sort'); else p.set('sort', `${s.desc ? '-' : ''}${s.id}`)
      p.delete('page')
    })
  }
  const setPage = (index: number) => {
    if (!urlState) { setLocalPage(index); return }
    setUrl((p) => { if (index > 0) p.set('page', String(index + 1)); else p.delete('page') })
  }

  const defs = useMemo<ColumnDef<T>[]>(() => columns.map((c) => ({
    id: c.id,
    accessorFn: c.sort ? (row: T) => c.sort?.(row) ?? '' : undefined,
    enableSorting: !!c.sort,
    sortingFn: (a, b, id) => {
      const x = a.getValue<string | number>(id), y = b.getValue<string | number>(id)
      return typeof x === 'number' && typeof y === 'number' ? x - y : collator.compare(String(x), String(y))
    },
    cell: ({ row }) => c.cell(row.original),
    header: () => c.header,
  })), [columns])

  const paged = pageSize > 0
  const pages = paged ? Math.max(1, Math.ceil(rows.length / pageSize)) : 1
  const pagination: PaginationState = { pageIndex: Math.min(pageIndex, pages - 1), pageSize: paged ? pageSize : Math.max(1, rows.length) }
  // The table's functions are only read while rendering here, so the compiler not memoizing this is fine.
  // eslint-disable-next-line react-hooks/incompatible-library
  const table = useReactTable({
    data: rows,
    columns: defs,
    state: { sorting, pagination },
    onSortingChange: (u) => setSorting(typeof u === 'function' ? u(sorting) : u),
    onPaginationChange: (u) => setPage((typeof u === 'function' ? u(pagination) : u).pageIndex),
    getRowId: (row) => rowKey(row),
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    enableSortingRemoval: false,
    autoResetPageIndex: false,
  })

  if (!rows.length) return <>{empty ?? <Text c="dimmed">{t('table.empty')}</Text>}</>

  const byId = new Map(columns.map((c) => [c.id, c]))
  const cellClass = (c?: DataColumn<T>) => [c?.hideOnPhone && 'fb-dt-phone-hide', c?.mono && 'fb-dt-mono'].filter(Boolean).join(' ') || undefined
  const body = (
    // On a phone the columns marked hideOnPhone go, so the rest fit without the wide minimum.
    <div className="fb-dt-scroll" style={minWidth ? ({ '--fb-dt-min': `${minWidth}px` } as CSSProperties) : undefined}>
      <Table highlightOnHover verticalSpacing={density === 'compact' ? 4 : 8} fz="sm" aria-label={label}
        className={['fb-dt', density === 'compact' && 'is-compact', className].filter(Boolean).join(' ')}>
        <Table.Thead>
          {table.getHeaderGroups().map((hg) => (
            <Table.Tr key={hg.id}>
              {hg.headers.map((h) => {
                const c = byId.get(h.column.id)
                const sorted = h.column.getIsSorted()
                return (
                  <Table.Th key={h.id} w={c?.width} className={cellClass(c)}
                    aria-sort={sorted ? (sorted === 'desc' ? 'descending' : 'ascending') : undefined}>
                    {h.column.getCanSort() ? (
                      <UnstyledButton className="fb-sort" onClick={() => setSorting([{ id: h.column.id, desc: sorted === 'asc' }])}>
                        {flexRender(h.column.columnDef.header, h.getContext())}
                        {sorted === 'asc' ? <IconChevronUp size={12} /> : sorted === 'desc' ? <IconChevronDown size={12} />
                          : <IconSelector size={12} className="fb-dt-sortable" aria-hidden />}
                      </UnstyledButton>
                    ) : flexRender(h.column.columnDef.header, h.getContext())}
                  </Table.Th>
                )
              })}
            </Table.Tr>
          ))}
        </Table.Thead>
        <Table.Tbody>
          {table.getRowModel().rows.map((row) => (
            <Table.Tr key={row.id} style={rowStyle?.(row.original)}>
              {row.getVisibleCells().map((cell) => (
                <Table.Td key={cell.id} className={cellClass(byId.get(cell.column.id))}>
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </Table.Td>
              ))}
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </div>
  )
  return (
    <>
      {bare ? body : <Paper withBorder className="fb-dt-box">{body}</Paper>}
      {(count || pages > 1) && (
        <Group justify="space-between" mt="sm">
          <Text size="sm" c="dimmed">{count?.(rows.length)}</Text>
          {pages > 1 && (
            <Pagination size="sm" total={pages} value={pagination.pageIndex + 1} onChange={(p) => setPage(p - 1)}
              getControlProps={(control) => ({ 'aria-label': t(`table.${control}`) })} />
          )}
        </Group>
      )}
    </>
  )
}
