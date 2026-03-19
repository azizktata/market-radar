"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

export function NavBar() {
  const pathname = usePathname();

  return (
    <nav className="border-b">
      <div className="mx-auto max-w-screen-xl px-6 h-14 py-2 flex items-center justify-between">
        <span className="font-bold text-lg tracking-tight">Market Radar</span>
        <div className="flex items-center gap-6 text-sm space-x-6">
          <div className="px-3">

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
            </div>
            <div>

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
            </div>
        </div>
      </div>
    </nav>
  );
}
