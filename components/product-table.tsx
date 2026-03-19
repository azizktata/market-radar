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
  VisibilityState,
} from "@tanstack/react-table";
import { useState, useRef, useEffect } from "react";
import { createPortal } from "react-dom";
import { ArrowUpDown, ExternalLink, Trash2, Columns3 } from "lucide-react";
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

type SiteCol = { key: string; label: string; threshold: number };

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

function StatusBadge({ price, pvc, threshold }: { price: number | null; pvc: number | null; threshold: number }) {
  if (price == null || pvc == null) {
    return <span className="text-muted-foreground text-xs">—</span>;
  }
  const ok = price <= pvc * (1 + threshold / 100);
  return (
    <span className={cn("font-medium text-sm", ok ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400")}>
      {ok ? "OK" : "KO"}
    </span>
  );
}

function buildColumns(sites: SiteCol[], onDelete: (id: number) => void): ColumnDef<Product>[] {
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
    {
      accessorKey: "marque",
      header: "Marque",
      cell: ({ row }) => (
        <span className="text-sm">{(row.original.marque as string | null) ?? "—"}</span>
      ),
    },
    {
      accessorKey: "category",
      header: "Catégorie",
      cell: ({ row }) => (
        <span className="text-sm text-muted-foreground">{(row.original.category as string | null) ?? "—"}</span>
      ),
    },
    {
      accessorKey: "sous_categorie",
      header: "Sous-catégorie",
      cell: ({ row }) => (
        <span className="text-sm text-muted-foreground">{(row.original.sous_categorie as string | null) ?? "—"}</span>
      ),
    },
    {
      accessorKey: "pvc",
      header: "PVC",
      cell: ({ row }) => {
        const pvc = row.original.pvc as number | null;
        return pvc != null
          ? <span className="tabular-nums text-sm">{pvc.toLocaleString("fr-TN")} DT</span>
          : <span className="text-muted-foreground text-xs">—</span>;
      },
    },
  ];

  for (const { key, label, threshold } of sites) {
    cols.push({
      id: `${key}_prix`,
      header: ({ column }) => (
        <Button variant="ghost" size="sm" onClick={() => column.toggleSorting()}>
          Prix {label} <ArrowUpDown className="ml-1 size-3" />
        </Button>
      ),
      accessorFn: (row) => (row[key] as SiteResult | null)?.price ?? null,
      cell: ({ row }) => {
        const prices = sites
          .map((s) => (row.original[s.key] as SiteResult | null)?.price)
          .filter((p): p is number => p != null);
        const result = row.original[key] as SiteResult | null;
        const price = result?.price ?? null;
        const isCheapest = price != null && prices.length > 1 && price === Math.min(...prices);
        const isMostExp  = price != null && prices.length > 1 && price === Math.max(...prices);
        return (
          <PriceCell result={result} isCheapest={isCheapest} isMostExpensive={isMostExp} />
        );
      },
    });

    cols.push({
      id: `${key}_statut`,
      header: `Statut ${label}`,
      cell: ({ row }) => {
        const result = row.original[key] as SiteResult | null;
        const pvc = row.original.pvc as number | null;
        return <StatusBadge price={result?.price ?? null} pvc={pvc} threshold={threshold} />;
      },
    });

    cols.push({
      id: `${key}_url`,
      header: `URL ${label}`,
      cell: ({ row }) => {
        const url = (row.original[key] as SiteResult | null)?.url;
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
  sites: SiteCol[];
  onDelete: (id: number) => void;
  selectable?: boolean;
  onSelectionChange?: (ids: number[]) => void;
}

const PAGE_SIZE = 50;

const DEFAULT_HIDDEN: VisibilityState = {
  category: false,
  sous_categorie: false,
  marque: false,
};

function ColumnToggle({ table }: { table: ReturnType<typeof useReactTable<Product>> }) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState({ top: 0, right: 0 });
  const btnRef = useRef<HTMLDivElement>(null);
  const dropRef = useRef<HTMLDivElement>(null);

  function handleToggle() {
    if (!open && btnRef.current) {
      const rect = btnRef.current.getBoundingClientRect();
      setPos({ top: rect.bottom + 4, right: window.innerWidth - rect.right });
    }
    setOpen((o) => !o);
  }

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (
        dropRef.current && !dropRef.current.contains(e.target as Node) &&
        btnRef.current && !btnRef.current.contains(e.target as Node)
      ) setOpen(false);
    }
    if (open) document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, [open]);

  const toggleable = table.getAllLeafColumns().filter(
    (col) => !["select", "actions"].includes(col.id)
  );

  return (
    <>
      <div ref={btnRef}>
        <Button variant="outline" size="sm" onClick={handleToggle}>
          <Columns3 className="size-4 mr-1.5" />Colonnes
        </Button>
      </div>
      {open && typeof window !== "undefined" && createPortal(
        <div
          ref={dropRef}
          style={{ position: "fixed", top: pos.top, right: pos.right }}
          className="z-50 w-56 rounded-md border bg-background shadow-lg p-2 max-h-80 overflow-y-auto"
        >
          {toggleable.map((col) => (
            <label key={col.id} className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-muted cursor-pointer text-sm select-none">
              <input
                type="checkbox"
                checked={col.getIsVisible()}
                onChange={col.getToggleVisibilityHandler()}
                className="rounded border-input shrink-0"
              />
              {typeof col.columnDef.header === "string"
                ? col.columnDef.header
                : col.id.replace(/_/g, " ")}
            </label>
          ))}
        </div>,
        document.body
      )}
    </>
  );
}

export function ProductTable({ products, sites, onDelete, selectable, onSelectionChange }: ProductTableProps) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const [globalFilter, setGlobalFilter] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [columnVisibility, setColumnVisibility] = useState<VisibilityState>(DEFAULT_HIDDEN);
  const [pagination, setPagination] = useState({ pageIndex: 0, pageSize: PAGE_SIZE });
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});

  const categories = [...new Set(products.map((p) => p.category as string | null).filter((c): c is string => !!c))].sort();
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
        ...buildColumns(sites, onDelete),
      ]
    : buildColumns(sites, onDelete);

  const table = useReactTable({
    data,
    columns,
    state: { sorting, globalFilter, pagination, rowSelection, columnVisibility },
    onSortingChange: setSorting,
    onColumnVisibilityChange: setColumnVisibility,
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
        <div className="ml-auto flex items-center gap-2">
        <ColumnToggle table={table} />
        <label className="flex items-center gap-1.5 text-sm text-muted-foreground whitespace-nowrap">
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
                  Aucun produit. Utilisez &ldquo;Ajouter&rdquo; ou &ldquo;Importer Excel&rdquo;.
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
