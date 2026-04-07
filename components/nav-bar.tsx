"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { cn } from "@/lib/utils";
import { useCompany } from "@/contexts/company-context";
import { api } from "@/lib/api";

export function NavBar() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, companies, currentCompany, setCurrentCompany, setUser, setCompanies } = useCompany();

  async function handleLogout() {
    try {
      await api.logout();
    } catch {
      // ignore
    }
    setUser(null);
    setCompanies([]);
    setCurrentCompany(null);
    router.push("/login");
  }

  function handleCompanyChange(company: typeof companies[0]) {
    setCurrentCompany(company);
    router.push("/");
  }

  if (pathname === "/login") return null;

  return (
    <nav className="border-b">
      <div className="mx-auto max-w-screen-xl px-6 py-2">
        <div className="flex items-center justify-between h-10">
          <div className="flex items-center gap-4">
            <span className="font-bold text-lg tracking-tight">Market Radar</span>
            
            {companies.length > 0 && (
              <div className="flex items-center gap-1 border-l pl-4 ml-2">
                {companies.map((company) => (
                  <button
                    key={company.id}
                    onClick={() => handleCompanyChange(company)}
                    className={cn(
                      "px-3 py-1 text-sm rounded-md transition-colors",
                      currentCompany?.id === company.id
                        ? "bg-primary text-primary-foreground"
                        : "text-muted-foreground hover:text-foreground hover:bg-muted"
                    )}
                  >
                    {company.name}
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="flex items-center gap-4 text-sm">
            <div className="flex items-center gap-4">
              <Link
                href="/"
                className={cn(
                  "transition-colors",
                  pathname === "/"
                    ? "font-medium text-foreground"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                Produits
              </Link>
              <Link
                href="/sites"
                className={cn(
                  "transition-colors",
                  pathname === "/sites"
                    ? "font-medium text-foreground"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                Sites
              </Link>
              {user?.role === "superadmin" && (
                <Link
                  href="/admin"
                  className={cn(
                    "transition-colors",
                    pathname === "/admin"
                      ? "font-medium text-foreground"
                      : "text-muted-foreground hover:text-foreground"
                  )}
                >
                  Admin
                </Link>
              )}
            </div>

            <button
              onClick={handleLogout}
              className="text-muted-foreground hover:text-foreground transition-colors"
            >
              Déconnexion
            </button>
          </div>
        </div>
      </div>
    </nav>
  );
}
