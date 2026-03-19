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
  sous_categorie: string | null;
  marque: string | null;
  pvc: number | null;
  created_at: string;
  [siteKey: string]: SiteResult | null | number | string | null;
};

export type Site = {
  id: number;
  name: string;
  domain: string;
  scraper_key: string;
  price_selector: string;
  threshold: number;
  enabled: boolean;
  created_at: string;
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

  addProduct: (data: { reference: string; name?: string; category?: string; sous_categorie?: string; marque?: string; pvc?: number }) =>
    req<Product>("/api/products", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),

  importProducts: async (file: File): Promise<{ added: number; skipped: number }> => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${BASE}/api/products/import`, { method: "POST", body: form });
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`${res.status} ${text}`);
    }
    return res.json();
  },

  deleteProduct: (id: number) =>
    fetch(`${BASE}/api/products/${id}`, { method: "DELETE" }),

  clearProducts: () =>
    req<{ deleted: number }>("/api/products", { method: "DELETE" }),

  getSites: () => req<Site[]>("/api/sites"),

  addSite: (data: {
    name: string; domain: string;
    sample_url?: string;
    price_selector?: string;
    scraper_key?: string;
    threshold?: number; enabled?: boolean;
  }) =>
    req<Site & { detected: boolean; price_sample: string | null }>("/api/sites", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),

  updateSite: (id: number, data: Partial<Omit<Site, "id" | "created_at">> & { sample_url?: string }) =>
    req<Site>(`/api/sites/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),

  deleteSite: (id: number) =>
    fetch(`${BASE}/api/sites/${id}`, { method: "DELETE" }),

  detectSiteSelector: (url: string) =>
    req<{ selector: string | null; price_sample: string | null }>("/api/sites/detect", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
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
