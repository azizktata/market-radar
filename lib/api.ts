const BASE = "http://localhost:8000";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init);
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${text}`);
  }
  return res.json() as Promise<T>;
}

export type SiteResult = {
  price: number | null;
  price_raw: string | null;
  availability: string | null;
  url: string | null;
  scraped_at: string | null;
};

export type Product = {
  id: number;
  reference: string;
  name: string | null;
  source: string;
  category: string | null;
  created_at: string;
  tunisianet: SiteResult | null;
  mytek: SiteResult | null;
  spacenet: SiteResult | null;
};

export type Session = {
  id: number;
  type: string;
  status: "running" | "done" | "error" | "stopped";
  total: number;
  done: number;
  started_at: string;
  finished_at: string | null;
};

export const api = {
  getProducts: () => req<Product[]>("/api/products"),

  addProduct: (reference: string, name?: string) =>
    req<Product>("/api/products", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reference, name }),
    }),

  addProductsBulk: (references: string[]) =>
    req<{ added: number }>("/api/products/bulk", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ references }),
    }),

  deleteProduct: (id: number) =>
    fetch(`${BASE}/api/products/${id}`, { method: "DELETE" }),

  startDiscover: (sites?: string[]) =>
    req<{ session_id: number }>("/api/discover", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sites: sites ?? ["tunisianet", "mytek", "spacenet"] }),
    }),

  startScrape: (productIds?: number[], resumeFromSession?: number, categories?: string[]) =>
    req<{ session_id: number }>("/api/scrape", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        product_ids: productIds ?? null,
        resume_from_session: resumeFromSession ?? null,
        categories: categories ?? null,
      }),
    }),

  getCategories: () => req<string[]>("/api/products/categories"),

  stopScrape: () =>
    req<{ ok: boolean }>("/api/scrape/stop", { method: "POST" }),

  getSession: (id: number) => req<Session>(`/api/sessions/${id}`),

  getLatestSession: () => req<Session | null>("/api/sessions/latest"),

  exportUrl: () => `${BASE}/api/export`,
};
