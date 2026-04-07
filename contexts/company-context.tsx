"use client";

import { createContext, useContext, useState, useEffect, ReactNode } from "react";
import { api, type User, type Company } from "@/lib/api";

type CompanyContextType = {
  user: User | null;
  companies: Company[];
  currentCompany: Company | null;
  setCurrentCompany: (company: Company) => void;
  isLoading: boolean;
  setUser: (user: User | null) => void;
  setCompanies: (companies: Company[]) => void;
  setIsLoading: (loading: boolean) => void;
  refreshUser: () => Promise<void>;
  initialized: boolean;
};

const CompanyContext = createContext<CompanyContextType | null>(null);

export function CompanyProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [currentCompany, setCurrentCompany] = useState<Company | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [initialized, setInitialized] = useState(false);

  const refreshUser = async () => {
    setIsLoading(true);
    try {
      const { user: u } = await api.getMe();
      setUser(u);
      setCompanies(u.companies || []);
      if (u.companies && u.companies.length > 0) {
        setCurrentCompany(u.companies[0]);
      }
    } catch {
      setUser(null);
      setCompanies([]);
      setCurrentCompany(null);
    } finally {
      setIsLoading(false);
      setInitialized(true);
    }
  };

  useEffect(() => {
    refreshUser();
  }, []);

  return (
    <CompanyContext.Provider value={{ 
      user, 
      companies, 
      currentCompany, 
      setCurrentCompany, 
      isLoading, 
      setUser,
      setCompanies,
      setIsLoading,
      refreshUser,
      initialized
    }}>
      {children}
    </CompanyContext.Provider>
  );
}

export function useCompany() {
  const context = useContext(CompanyContext);
  if (!context) {
    throw new Error("useCompany must be used within CompanyProvider");
  }
  return context;
}
