"use client";

import {
  ColumnDef,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  useReactTable,
  SortingState,
  RowSelectionState,
} from "@tanstack/react-table";
import { useState } from "react";
import { ArrowUpDown, ExternalLink, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { Product, SiteResult } from "@/lib/api";

const SITES: Array<{ key: keyof Pick<Product, "tunisianet" | "mytek" | "spacenet">; label: string }> = [
  { key: "tunisianet", label: "Tunisianet" },
  { key: "mytek",      label: "Mytek" },
  { key: "spacenet",   label: "Spacenet" },
];

function AvailBadge({ value }: { value: string | null }) {
  if (!value) return <span className="text-muted-foreground text-xs">—</span>;
  const lower = value.toLowerCase();
  const color = lower.includes("disponible") || lower.includes("en stock")
    ? "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300"
    : lower.includes("puis") || lower.includes("rupt") || lower.includes("hors stock")
    ? "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300"
    : "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300";
  return (
    <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap", color)}>
      {value}
    </span>
  );
}

function PriceCell({
  result,
  isCheapest,
  isMostExpensive,
}: {
  result: SiteResult | null;
  isCheapest: boolean;
  isMostExpensive: boolean;
}) {
  if (!result?.price_raw) return <span className="text-muted-foreground text-xs">—</span>;
  return (
    <span
      className={cn(
        "font-medium tabular-nums text-sm",
        isCheapest && "text-green-600 dark:text-green-400",
        isMostExpensive && "text-red-600 dark:text-red-400"
      )}
    >
      {result.price_raw}
    </span>
  );
}

function buildColumns(onDelete: (id: number) => void): ColumnDef<Product>[] {
  const cols: ColumnDef<Product>[] = [
    {
      accessorKey: "reference",
      header: ({ column }) => (
        <Button variant="ghost" size="sm" onClick={() => column.toggleSorting()}>
          Référence <ArrowUpDown className="ml-1 size-3" />
        </Button>
      ),
      cell: ({ row }) => (
        <span className="font-mono text-sm font-semibold">{row.original.reference}</span>
      ),
    },
    {
      accessorKey: "name",
      header: "Nom",
      cell: ({ row }) => (
        <span
          title={row.original.name ?? undefined}
          className="text-sm text-muted-foreground max-w-56 truncate block cursor-default"
        >
          {row.original.name ?? "—"}
        </span>
      ),
    },
  ];

  for (const { key, label } of SITES) {
    cols.push({
      id: `${key}_prix`,
      header: ({ column }) => (
        <Button variant="ghost" size="sm" onClick={() => column.toggleSorting()}>
          Prix {label} <ArrowUpDown className="ml-1 size-3" />
        </Button>
      ),
      accessorFn: (row) => row[key]?.price ?? null,
      cell: ({ row }) => {
        const prices = SITES.map((s) => row.original[s.key]?.price).filter(
          (p): p is number => p != null
        );
        const price = row.original[key]?.price ?? null;
        const isCheapest = price != null && prices.length > 1 && price === Math.min(...prices);
        const isMostExp  = price != null && prices.length > 1 && price === Math.max(...prices);
        return (
          <PriceCell result={row.original[key]} isCheapest={isCheapest} isMostExpensive={isMostExp} />
        );
      },
    });

    cols.push({
      id: `${key}_statut`,
      header: `Statut ${label}`,
      cell: ({ row }) => <AvailBadge value={row.original[key]?.availability ?? null} />,
    });

    cols.push({
      id: `${key}_url`,
      header: `URL ${label}`,
      cell: ({ row }) => {
        const url = row.original[key]?.url;
        if (!url) return <span className="text-muted-foreground text-xs">—</span>;
        return (
          <a href={url} target="_blank" rel="noopener noreferrer" className="text-primary hover:text-primary/80">
            <ExternalLink className="size-4" />
          </a>
        );
      },
    });
  }

  cols.push({
    id: "actions",
    header: "",
    cell: ({ row }) => (
      <Button
        variant="ghost"
        size="icon-sm"
        className="text-muted-foreground hover:text-destructive"
        onClick={() => onDelete(row.original.id)}
      >
        <Trash2 className="size-3.5" />
      </Button>
    ),
  });

  return cols;
}

interface ProductTableProps {
  products: Product[];
  onDelete: (id: number) => void;
  selectable?: boolean;
  onSelectionChange?: (ids: number[]) => void;
}

const PAGE_SIZE = 50;

export function ProductTable({ products, onDelete, selectable, onSelectionChange }: ProductTableProps) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const [globalFilter, setGlobalFilter] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [pagination, setPagination] = useState({ pageIndex: 0, pageSize: PAGE_SIZE });
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});

  const categories = [...new Set(products.map((p) => p.category).filter((c): c is string => !!c))].sort();
  const data = categoryFilter ? products.filter((p) => p.category === categoryFilter) : products;

  const columns: ColumnDef<Product>[] = selectable
    ? [
        {
          id: "select",
          header: ({ table }) => (
            <input
              type="checkbox"
              checked={table.getIsAllPageRowsSelected()}
              ref={(el) => { if (el) el.indeterminate = table.getIsSomePageRowsSelected(); }}
              onChange={table.getToggleAllPageRowsSelectedHandler()}
              className="rounded border-input"
            />
          ),
          cell: ({ row }) => (
            <input
              type="checkbox"
              checked={row.getIsSelected()}
              onChange={row.getToggleSelectedHandler()}
              className="rounded border-input"
            />
          ),
          size: 36,
        },
        ...buildColumns(onDelete),
      ]
    : buildColumns(onDelete);

  const table = useReactTable({
    data,
    columns,
    state: { sorting, globalFilter, pagination, rowSelection },
    onSortingChange: setSorting,
    onGlobalFilterChange: (v) => { setPagination((p) => ({ ...p, pageIndex: 0 })); setGlobalFilter(v); },
    onPaginationChange: setPagination,
    onRowSelectionChange: (updater) => {
      setRowSelection((prev) => {
        const next = typeof updater === "function" ? updater(prev) : updater;
        if (onSelectionChange) {
          const selectedIds = Object.keys(next)
            .filter((k) => next[k])
            .map((k) => data[Number(k)]?.id)
            .filter((id): id is number => id != null);
          onSelectionChange(selectedIds);
        }
        return next;
      });
    },
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    autoResetPageIndex: false,
    enableRowSelection: selectable ?? false,
  });

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3 flex-wrap">
        <input
          placeholder="Filtrer par référence ou nom..."
          value={globalFilter}
          onChange={(e) => setGlobalFilter(e.target.value)}
          className="h-9 w-full max-w-sm rounded-md border border-input bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-ring/50"
        />
        {categories.length > 0 && (
          <select
            value={categoryFilter}
            onChange={(e) => { setCategoryFilter(e.target.value); setRowSelection({}); setPagination((p) => ({ ...p, pageIndex: 0 })); }}
            className="h-9 rounded-md border border-input bg-background px-2 text-sm outline-none focus:ring-2 focus:ring-ring/50"
          >
            <option value="">Toutes catégories</option>
            {categories.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        )}
        <label className="flex items-center gap-1.5 text-sm text-muted-foreground whitespace-nowrap ml-auto">
          Afficher
          <select
            value={table.getState().pagination.pageSize}
            onChange={(e) => {
              table.setPageSize(Number(e.target.value));
              table.setPageIndex(0);
            }}
            className="h-9 rounded-md border border-input bg-background px-2 text-sm outline-none focus:ring-2 focus:ring-ring/50"
          >
            {[25, 50, 100, 200].map((n) => (
              <option key={n} value={n}>{n}</option>
            ))}
            <option value={9999}>Tout</option>
          </select>
          lignes
        </label>
      </div>

      <div className="rounded-md border">
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((hg) => (
              <TableRow key={hg.id}>
                {hg.headers.map((header) => (
                  <TableHead key={header.id}>
                    {header.isPlaceholder
                      ? null
                      : flexRender(header.column.columnDef.header, header.getContext())}
                  </TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {table.getRowModel().rows.length ? (
              table.getRowModel().rows.map((row) => (
                <TableRow key={row.id}>
                  {row.getVisibleCells().map((cell) => (
                    <TableCell key={cell.id}>
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </TableCell>
                  ))}
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell colSpan={columns.length} className="text-center py-10 text-muted-foreground">
                  Aucun produit. Utilisez &ldquo;Découvrir&rdquo; ou &ldquo;Ajouter une référence&rdquo;.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>{table.getFilteredRowModel().rows.length} produit(s)</span>

        {table.getPageCount() > 1 && (
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="xs"
              onClick={() => table.previousPage()}
              disabled={!table.getCanPreviousPage()}
            >
              ‹ Précédent
            </Button>
            <span className="tabular-nums">
              Page {table.getState().pagination.pageIndex + 1} / {table.getPageCount()}
            </span>
            <Button
              variant="outline"
              size="xs"
              onClick={() => table.nextPage()}
              disabled={!table.getCanNextPage()}
            >
              Suivant ›
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
