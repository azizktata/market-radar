"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Download, RefreshCw, Search, Plus, Square, Play, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ProductTable } from "@/components/product-table";
import { AddProductDialog } from "@/components/add-product-dialog";
import { ProgressBar } from "@/components/progress-bar";
import { StatsCards } from "@/components/stats-cards";
import { api, type Product, type Session } from "@/lib/api";

export default function Home() {
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [stopping, setStopping] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [categories, setCategories] = useState<string[]>([]);
  const [selectedCategory, setSelectedCategory] = useState("");
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadProducts = useCallback(async () => {
    try {
      const data = await api.getProducts();
      setProducts(data);
      setError(null);
    } catch {
      setError("Impossible de joindre le backend. Vérifiez que uvicorn tourne sur le port 8000.");
    } finally {
      setLoading(false);
    }
  }, []);

  // On mount, recover any in-progress or stopped session
  useEffect(() => {
    loadProducts();
    api.getLatestSession().then((s) => { if (s) setSession(s); }).catch(() => {});
    api.getCategories().then(setCategories).catch(() => {});
  }, [loadProducts]);

  // Refresh categories when products reload
  useEffect(() => {
    if (products.length > 0) {
      api.getCategories().then(setCategories).catch(() => {});
    }
  }, [products]);

  // Poll running session
  useEffect(() => {
    if (!session || session.status !== "running") {
      if (pollRef.current) clearInterval(pollRef.current);
      if (session?.status === "done" || session?.status === "stopped") {
        setStopping(false);
        loadProducts();
      }
      return;
    }
    pollRef.current = setInterval(async () => {
      try {
        const updated = await api.getSession(session.id);
        setSession(updated);
      } catch { /* ignore */ }
    }, 2000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [session, loadProducts]);

  async function handleDiscover() {
    try {
      const { session_id } = await api.startDiscover();
      setSession(await api.getSession(session_id));
    } catch (e: any) { alert(e.message); }
  }

  async function handleScrape(resumeFrom?: number) {
    try {
      let session_id: number;
      if (selectedIds.length > 0) {
        ({ session_id } = await api.startScrape(selectedIds, resumeFrom));
      } else if (selectedCategory) {
        ({ session_id } = await api.startScrape(undefined, resumeFrom, [selectedCategory]));
      } else {
        ({ session_id } = await api.startScrape(undefined, resumeFrom));
      }
      setSession(await api.getSession(session_id));
    } catch (e: any) { alert(e.message); }
  }

  async function handleStop() {
    setStopping(true);
    try { await api.stopScrape(); } catch (e: any) { alert(e.message); setStopping(false); }
  }

  async function handleAdd(refs: string[]) {
    await api.addProductsBulk(refs);
    await loadProducts();
  }

  async function handleDelete(id: number) {
    await api.deleteProduct(id);
    setProducts((prev) => prev.filter((p) => p.id !== id));
  }

  const isRunning = session?.status === "running";
  const isStopped = session?.status === "stopped";

  const lastScrape = products
    .flatMap((p) => ["tunisianet", "mytek", "spacenet"].map((s) => (p as any)[s]?.scraped_at))
    .filter(Boolean).sort().at(-1);

  const scrapeLabel = selectedIds.length > 0
    ? `Scraper (${selectedIds.length})`
    : selectedCategory
    ? `Scraper — ${selectedCategory}`
    : "Scraper tout";

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b">
        <div className="mx-auto max-w-screen-xl px-6 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold tracking-tight">Market Radar</h1>
            <p className="text-xs text-muted-foreground mt-0.5">
              {products.length} produit(s)
              {lastScrape && <> · Dernière mise à jour : {new Date(lastScrape).toLocaleString("fr-TN")}</>}
            </p>
          </div>

          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={handleDiscover} disabled={isRunning}>
              <Search className="size-4 mr-1.5" />Découvrir
            </Button>
            <Button variant="outline" size="sm" onClick={() => setAddOpen(true)} disabled={isRunning}>
              <Plus className="size-4 mr-1.5" />Ajouter
            </Button>

            {categories.length > 0 && (
              <select
                value={selectedCategory}
                onChange={(e) => { setSelectedCategory(e.target.value); setSelectedIds([]); }}
                disabled={isRunning}
                className="h-9 rounded-md border border-input bg-background px-2 text-sm outline-none focus:ring-2 focus:ring-ring/50 disabled:opacity-50"
              >
                <option value="">Toutes catégories</option>
                {categories.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            )}

            {isRunning ? (
              <Button size="sm" variant="destructive" onClick={handleStop} disabled={stopping}>
                <Square className="size-4 mr-1.5" />
                {stopping ? "Arrêt…" : "Arrêter"}
              </Button>
            ) : (
              <Button size="sm" onClick={() => handleScrape()} disabled={products.length === 0}>
                <RefreshCw className="size-4 mr-1.5" />{scrapeLabel}
              </Button>
            )}

            <Button variant="outline" size="sm" onClick={() => window.location.href = api.exportUrl()} disabled={products.length === 0}>
              <Download className="size-4 mr-1.5" />Excel
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-screen-xl px-6 py-6 space-y-4">
        {error && (
          <div className="rounded-md bg-destructive/10 border border-destructive/30 px-4 py-3 text-sm text-destructive">
            {error}
          </div>
        )}

        {products.length > 0 && <StatsCards products={products} />}

        {session && (isRunning || session.status === "done") && (
          <ProgressBar session={session} />
        )}

        {isStopped && session && (
          <div className="rounded-md border border-amber-200 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/30 px-4 py-3 flex items-center justify-between gap-4">
            <p className="text-sm text-amber-800 dark:text-amber-300">
              Scraping arrêté — {session.done} / {session.total} tâches complétées.
            </p>
            <div className="flex gap-2">
              <Button size="sm" onClick={() => handleScrape(session.id)}>
                <Play className="size-4 mr-1.5" />Continuer
              </Button>
              <Button size="sm" variant="outline" onClick={() => handleScrape()}>
                <RotateCcw className="size-4 mr-1.5" />Recommencer
              </Button>
            </div>
          </div>
        )}

        {loading ? (
          <div className="py-20 text-center text-muted-foreground text-sm">Chargement…</div>
        ) : (
          <ProductTable
            products={products}
            onDelete={handleDelete}
            selectable
            onSelectionChange={(ids) => { setSelectedIds(ids); if (ids.length > 0) setSelectedCategory(""); }}
          />
        )}
      </main>

      <AddProductDialog open={addOpen} onClose={() => setAddOpen(false)} onAdd={handleAdd} />
    </div>
  );
}
