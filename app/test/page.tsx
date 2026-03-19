"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { RefreshCw, Square, Play, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ProductTable } from "@/components/product-table";
import { ProgressBar } from "@/components/progress-bar";
import { api, type Product, type Session } from "@/lib/api";

export default function TestPage() {
  const [allProducts, setAllProducts] = useState<Product[]>([]);
  const [offset, setOffset] = useState(0);
  const [count, setCount] = useState(10);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [stopping, setStopping] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const products = allProducts.slice(offset, offset + count);

  const loadProducts = useCallback(async () => {
    try {
      const all = await api.getProducts();
      setAllProducts(all);
      setError(null);
    } catch {
      setError("Impossible de joindre le backend (port 8000).");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadProducts(); }, [loadProducts]);

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

  async function handleScrape(resumeFrom?: number) {
    try {
      const ids = products.map((p) => p.id);
      const { session_id } = await api.startScrape(ids, resumeFrom);
      setSession(await api.getSession(session_id));
    } catch (e: any) {
      alert(e.message);
    }
  }

  async function handleStop() {
    setStopping(true);
    try { await api.stopScrape(); } catch (e: any) { alert(e.message); setStopping(false); }
  }

  const isRunning = session?.status === "running";
  const isStopped = session?.status === "stopped";

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b">
        <div className="mx-auto max-w-screen-xl px-6 py-4 flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-bold tracking-tight">Market Radar</h1>
              <span className="rounded-full bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300 px-2 py-0.5 text-xs font-medium">
                Test — {products.length} produit(s) (depuis #{offset})
              </span>
            </div>
            <div className="flex items-center gap-3 mt-1">
              <p className="text-xs text-muted-foreground">
                <a href="/" className="underline hover:text-foreground">← Page principale</a>
              </p>
              <label className="flex items-center gap-1 text-xs text-muted-foreground">
                Début
                <input
                  type="number"
                  min={0}
                  max={Math.max(0, allProducts.length - 1)}
                  value={offset}
                  onChange={(e) => setOffset(Math.max(0, Number(e.target.value)))}
                  className="w-16 h-7 rounded border border-input bg-background px-2 text-xs outline-none focus:ring-2 focus:ring-ring/50"
                />
              </label>
              <label className="flex items-center gap-1 text-xs text-muted-foreground">
                Nombre
                <input
                  type="number"
                  min={1}
                  max={200}
                  value={count}
                  onChange={(e) => setCount(Math.max(1, Number(e.target.value)))}
                  className="w-16 h-7 rounded border border-input bg-background px-2 text-xs outline-none focus:ring-2 focus:ring-ring/50"
                />
              </label>
              <span className="text-xs text-muted-foreground">
                ({allProducts.length} produits au total)
              </span>
            </div>
          </div>

          {isRunning ? (
            <Button size="sm" variant="destructive" onClick={handleStop} disabled={stopping}>
              <Square className="size-4 mr-1.5" />{stopping ? "Arrêt…" : "Arrêter"}
            </Button>
          ) : (
            <Button size="sm" onClick={() => handleScrape()} disabled={products.length === 0}>
              <RefreshCw className="size-4 mr-1.5" />Scraper ({products.length})
            </Button>
          )}
        </div>
      </header>

      <main className="mx-auto max-w-screen-xl px-6 py-6 space-y-4">
        {error && (
          <div className="rounded-md bg-destructive/10 border border-destructive/30 px-4 py-3 text-sm text-destructive">
            {error}
          </div>
        )}

        {session && (isRunning || session.status === "done") && (
          <ProgressBar session={session} />
        )}

        {isStopped && session && (
          <div className="rounded-md border border-amber-200 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/30 px-4 py-3 flex items-center justify-between gap-4">
            <p className="text-sm text-amber-800 dark:text-amber-300">
              Arrêté — {session.done} / {session.total} tâches complétées.
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
          <ProductTable products={products} onDelete={() => {}} />
        )}
      </main>
    </div>
  );
}
