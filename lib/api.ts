const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    credentials: "include",
  });
  if (res.status === 401) {
    if (window.location.pathname !== "/login") {
      window.location.href = "/login";
    }
    throw new Error("Session expirée");
  }
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${text}`);
  }
  return res.json() as Promise<T>;
}

export type Company = {
  id: number;
  name: string;
  created_at: string;
};

export type User = {
  id: number;
  email: string;
  name: string | null;
  role: "superadmin" | "user";
  companies: Company[];
};

export type LoginResponse = {
  user: User;
};

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
  login: (email: string, password: string) =>
    req<LoginResponse>("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    }),

  logout: () =>
    req<{ ok: boolean }>("/api/auth/logout", { method: "POST" }),

  getMe: () =>
    req<{ user: User }>("/api/auth/me"),

  getProducts: (companyId: number) =>
    req<Product[]>(`/api/products?company_id=${companyId}`),

  addProduct: (companyId: number, data: { reference: string; name?: string; category?: string; sous_categorie?: string; marque?: string; pvc?: number }) =>
    req<Product>(`/api/products?company_id=${companyId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),

  importProducts: async (companyId: number, file: File): Promise<{ added: number; skipped: number }> => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${BASE}/api/products/import?company_id=${companyId}`, {
      method: "POST",
      body: form,
      credentials: "include",
    });
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`${res.status} ${text}`);
    }
    return res.json();
  },

  deleteProduct: (companyId: number, id: number) =>
    fetch(`${BASE}/api/products/${id}?company_id=${companyId}`, {
      method: "DELETE",
      credentials: "include",
    }),

  clearProducts: (companyId: number) =>
    req<{ deleted: number }>(`/api/products?company_id=${companyId}`, { method: "DELETE" }),

  getSites: (companyId: number) =>
    req<Site[]>(`/api/sites?company_id=${companyId}`),

  addSite: (companyId: number, data: {
    name: string; domain: string;
    sample_url?: string;
    price_selector?: string;
    scraper_key?: string;
    threshold?: number; enabled?: boolean;
  }) =>
    req<Site & { detected: boolean; price_sample: string | null }>(`/api/sites?company_id=${companyId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),

  updateSite: (companyId: number, id: number, data: Partial<Omit<Site, "id" | "created_at">> & { sample_url?: string }) =>
    req<Site>(`/api/sites/${id}?company_id=${companyId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),

  deleteSite: (companyId: number, id: number) =>
    fetch(`${BASE}/api/sites/${id}?company_id=${companyId}`, {
      method: "DELETE",
      credentials: "include",
    }),

  detectSiteSelector: (url: string) =>
    req<{ selector: string | null; price_sample: string | null }>("/api/sites/detect", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    }),

  startScrape: (companyId: number, productIds?: number[], resumeFromSession?: number, categories?: string[]) =>
    req<{ session_id: number }>(`/api/scrape?company_id=${companyId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        product_ids: productIds ?? null,
        resume_from_session: resumeFromSession ?? null,
        categories: categories ?? null,
      }),
    }),

  getCategories: (companyId: number) =>
    req<string[]>(`/api/products/categories?company_id=${companyId}`),

  stopScrape: (companyId: number) =>
    req<{ ok: boolean }>(`/api/scrape/stop?company_id=${companyId}`, { method: "POST" }),

  getSession: (companyId: number, id: number) =>
    req<Session>(`/api/sessions/${id}?company_id=${companyId}`),

  getLatestSession: (companyId: number) =>
    req<Session | null>(`/api/sessions/latest?company_id=${companyId}`),

  exportUrl: (companyId: number) => `${BASE}/api/export?company_id=${companyId}`,

  // Admin endpoints
  adminGetUsers: () =>
    req<{ id: number; email: string; name: string | null; role: string; is_active: number; created_at: string }[]>("/api/admin/users"),

  adminCreateUser: (data: { email: string; name?: string; password: string }) =>
    req<any>("/api/admin/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),

  adminUpdateUser: (id: number, data: { email?: string; name?: string; password?: string; role?: string; is_active?: boolean }) =>
    req<any>(`/api/admin/users/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),

  adminDeleteUser: (id: number) =>
    fetch(`${BASE}/api/admin/users/${id}`, { method: "DELETE", credentials: "include" }),

  adminGetCompanies: () =>
    req<Company[]>("/api/admin/companies"),

  adminCreateCompany: (name: string) =>
    req<Company>("/api/admin/companies", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    }),

  adminUpdateCompany: (id: number, name: string) =>
    req<Company>(`/api/admin/companies/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    }),

  adminDeleteCompany: (id: number) =>
    fetch(`${BASE}/api/admin/companies/${id}`, { method: "DELETE", credentials: "include" }),

  adminGetCompanyUsers: (companyId: number) =>
    req<any[]>(`/api/admin/companies/${companyId}/users`),

  adminAssignUserToCompany: (companyId: number, userId: number) =>
    req<{ ok: boolean }>(`/api/admin/companies/${companyId}/users`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: userId }),
    }),

  adminRemoveUserFromCompany: (companyId: number, userId: number) =>
    fetch(`${BASE}/api/admin/companies/${companyId}/users/${userId}`, { method: "DELETE", credentials: "include" }),
};
