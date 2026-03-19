import { useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import type { Product } from "@/lib/api";

const SITES: Array<{ key: keyof Pick<Product, "tunisianet" | "mytek" | "spacenet">; label: string }> = [
  { key: "tunisianet", label: "Tunisianet" },
  { key: "mytek",      label: "Mytek" },
  { key: "spacenet",   label: "Spacenet" },
];

interface StatsCardsProps {
  products: Product[];
}

export function StatsCards({ products }: StatsCardsProps) {
  const [visible, setVisible] = useState(true);

  const total = products.length;
  const scraped = products.filter((p) =>
    SITES.some((s) => p[s.key]?.price != null || p[s.key]?.availability != null)
  ).length;

  const siteCounts = SITES.map((s) => ({
    label: s.label,
    count: products.filter((p) => p[s.key]?.price != null).length,
  }));

  const catMap = new Map<string, number>();
  for (const p of products) {
    const cat = p.category ?? "Autres";
    catMap.set(cat, (catMap.get(cat) ?? 0) + 1);
  }
  const catEntries = [...catMap.entries()].sort((a, b) => b[1] - a[1]);
  const MAX_CATS = 8;
  const topCats = catEntries.slice(0, MAX_CATS);
  const otherCount = catEntries.slice(MAX_CATS).reduce((s, [, n]) => s + n, 0);

  return (
    <div className="space-y-2">
      <button
        onClick={() => setVisible((v) => !v)}
        className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
      >
        {visible ? <ChevronUp className="size-3.5" /> : <ChevronDown className="size-3.5" />}
        {visible ? "Masquer les statistiques" : "Afficher les statistiques"}
      </button>

      {visible && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {/* Total */}
          <div className="rounded-md border px-4 py-3">
            <p className="text-xs text-muted-foreground">Total produits</p>
            <p className="text-2xl font-bold tabular-nums mt-1">{total}</p>
          </div>

          {/* Coverage */}
          <div className="rounded-md border px-4 py-3">
            <p className="text-xs text-muted-foreground">Scrapés</p>
            <p className="text-2xl font-bold tabular-nums mt-1">
              {scraped}
              <span className="text-sm font-normal text-muted-foreground ml-1">/ {total}</span>
            </p>
            {total > 0 && (
              <div className="mt-2 h-1.5 rounded-full bg-muted overflow-hidden">
                <div
                  className="h-full rounded-full bg-primary"
                  style={{ width: `${Math.round((scraped / total) * 100)}%` }}
                />
              </div>
            )}
          </div>

          {/* Per site */}
          <div className="rounded-md border px-4 py-3">
            <p className="text-xs text-muted-foreground mb-2">Par site</p>
            <div className="space-y-1">
              {siteCounts.map(({ label, count }) => (
                <div key={label} className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">{label}</span>
                  <span className="font-semibold tabular-nums">{count}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Per category */}
          <div className="rounded-md border px-4 py-3">
            <p className="text-xs text-muted-foreground mb-2">Par catégorie</p>
            <div className="space-y-1">
              {topCats.map(([cat, count]) => (
                <div key={cat} className="flex items-center justify-between text-sm gap-2">
                  <span className="text-muted-foreground truncate" title={cat}>{cat}</span>
                  <span className="font-semibold tabular-nums shrink-0">{count}</span>
                </div>
              ))}
              {otherCount > 0 && (
                <div className="flex items-center justify-between text-sm gap-2">
                  <span className="text-muted-foreground italic">Autres</span>
                  <span className="font-semibold tabular-nums shrink-0">{otherCount}</span>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
