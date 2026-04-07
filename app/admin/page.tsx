"use client";

import { useEffect, useState } from "react";
import { Plus, Pencil, Trash2, Users, Building2, Link as LinkIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api, type Company } from "@/lib/api";
import { useCompany } from "@/contexts/company-context";

type UserRecord = {
  id: number;
  email: string;
  name: string | null;
  role: string;
  is_active: number;
  created_at: string;
};

type Tab = "users" | "companies" | "assignments";

export default function AdminPage() {
  const { user, isLoading: companyLoading } = useCompany();
  const [activeTab, setActiveTab] = useState<Tab>("users");
  const [users, setUsers] = useState<UserRecord[]>([]);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [companyUsers, setCompanyUsers] = useState<Record<number, UserRecord[]>>({});
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [modalType, setModalType] = useState<"user" | "company" | "assignment" | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<any>({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (companyLoading || user?.role !== "superadmin") return;
    loadData();
  }, [companyLoading, user]);

  useEffect(() => {
    if (activeTab === "assignments" && companies.length > 0) {
      companies.forEach((c) => loadCompanyUsers(c.id));
    }
  }, [activeTab, companies]);

  async function loadData() {
    try {
      const [usersData, companiesData] = await Promise.all([
        api.adminGetUsers(),
        api.adminGetCompanies(),
      ]);
      setUsers(usersData);
      setCompanies(companiesData);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }

  async function loadCompanyUsers(companyId: number) {
    try {
      const usersData = await api.adminGetCompanyUsers(companyId);
      setCompanyUsers((prev) => ({ ...prev, [companyId]: usersData }));
    } catch (e) {
      console.error(e);
    }
  }

  function openModal(type: "user" | "company" | "assignment", id?: number) {
    setModalType(type);
    setEditingId(id ?? null);
    if (type === "user") {
      const existing = id ? users.find((u) => u.id === id) : null;
      setForm(existing ? { email: existing.email, name: existing.name || "", password: "", role: existing.role, is_active: !!existing.is_active } : { email: "", name: "", password: "", role: "user", is_active: true });
    } else if (type === "company") {
      const existing = id ? companies.find((c) => c.id === id) : null;
      setForm(existing ? { name: existing.name } : { name: "" });
    } else if (type === "assignment") {
      setForm({ user_id: "" });
    }
    setModalOpen(true);
  }

  async function handleSave() {
    setSaving(true);
    try {
      if (modalType === "user") {
        if (editingId) {
          await api.adminUpdateUser(editingId, form);
        } else {
          await api.adminCreateUser(form);
        }
      } else if (modalType === "company") {
        if (editingId) {
          await api.adminUpdateCompany(editingId, form.name);
        } else {
          await api.adminCreateCompany(form.name);
        }
      } else if (modalType === "assignment" && editingId) {
        await api.adminAssignUserToCompany(editingId, parseInt(form.user_id));
        await loadCompanyUsers(editingId);
      }
      await loadData();
      setModalOpen(false);
    } catch (e) {
      alert(e instanceof Error ? e.message : "Erreur");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (!modalType || !editingId) return;
    if (!window.confirm("Confirmer la suppression ?")) return;
    try {
      if (modalType === "user") {
        await api.adminDeleteUser(editingId);
      } else if (modalType === "company") {
        await api.adminDeleteCompany(editingId);
      }
      await loadData();
      setModalOpen(false);
    } catch (e) {
      alert(e instanceof Error ? e.message : "Erreur");
    }
  }

  if (companyLoading || user?.role !== "superadmin") {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-muted-foreground text-sm">Chargement...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <div className="mx-auto max-w-screen-xl px-6 py-6 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Administration</h2>
        </div>

        <div className="flex gap-1 border-b">
          {[
            { id: "users" as Tab, label: "Utilisateurs", icon: Users },
            { id: "companies" as Tab, label: "Entreprises", icon: Building2 },
            { id: "assignments" as Tab, label: "Affectations", icon: LinkIcon },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-4 py-2 text-sm border-b-2 transition-colors ${
                activeTab === tab.id
                  ? "border-primary text-primary"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              }`}
            >
              <tab.icon className="size-4" />
              {tab.label}
            </button>
          ))}
        </div>

        {loading ? (
          <div className="py-20 text-center text-muted-foreground text-sm">Chargement…</div>
        ) : (
          <>
            {activeTab === "users" && (
              <div className="rounded-md border overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b bg-muted/50">
                      <th className="px-4 py-3 text-left font-medium">Email</th>
                      <th className="px-4 py-3 text-left font-medium">Nom</th>
                      <th className="px-4 py-3 text-left font-medium">Rôle</th>
                      <th className="px-4 py-3 text-center font-medium">Actif</th>
                      <th className="px-4 py-3 text-right font-medium">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {users.map((u) => (
                      <tr key={u.id} className="border-b hover:bg-muted/30">
                        <td className="px-4 py-3">{u.email}</td>
                        <td className="px-4 py-3">{u.name || "-"}</td>
                        <td className="px-4 py-3">{u.role}</td>
                        <td className="px-4 py-3 text-center">{u.is_active ? "Oui" : "Non"}</td>
                        <td className="px-4 py-3 text-right">
                          <div className="flex items-center justify-end gap-1">
                            <Button variant="ghost" size="icon-sm" onClick={() => openModal("user", u.id)}>
                              <Pencil className="size-3.5" />
                            </Button>
                            <Button variant="ghost" size="icon-sm" className="text-muted-foreground hover:text-destructive" onClick={() => { setModalType("user"); setEditingId(u.id); handleDelete(); }}>
                              <Trash2 className="size-3.5" />
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div className="p-4 border-t">
                  <Button size="sm" onClick={() => openModal("user")}>
                    <Plus className="size-4 mr-1.5" />Ajouter un utilisateur
                  </Button>
                </div>
              </div>
            )}

            {activeTab === "companies" && (
              <div className="rounded-md border overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b bg-muted/50">
                      <th className="px-4 py-3 text-left font-medium">Nom</th>
                      <th className="px-4 py-3 text-left font-medium">Créée le</th>
                      <th className="px-4 py-3 text-right font-medium">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {companies.map((c) => (
                      <tr key={c.id} className="border-b hover:bg-muted/30">
                        <td className="px-4 py-3">{c.name}</td>
                        <td className="px-4 py-3">{new Date(c.created_at).toLocaleDateString("fr-TN")}</td>
                        <td className="px-4 py-3 text-right">
                          <div className="flex items-center justify-end gap-1">
                            <Button variant="ghost" size="icon-sm" onClick={() => openModal("company", c.id)}>
                              <Pencil className="size-3.5" />
                            </Button>
                            <Button variant="ghost" size="icon-sm" className="text-muted-foreground hover:text-destructive" onClick={() => { setModalType("company"); setEditingId(c.id); handleDelete(); }}>
                              <Trash2 className="size-3.5" />
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div className="p-4 border-t">
                  <Button size="sm" onClick={() => openModal("company")}>
                    <Plus className="size-4 mr-1.5" />Ajouter une entreprise
                  </Button>
                </div>
              </div>
            )}

            {activeTab === "assignments" && (
              <div className="space-y-4">
                {companies.map((c) => (
                  <div key={c.id} className="rounded-md border p-4">
                    <div className="flex items-center justify-between mb-3">
                      <h3 className="font-medium">{c.name}</h3>
                      <Button size="sm" variant="outline" onClick={() => openModal("assignment", c.id)}>
                        <Plus className="size-4 mr-1.5" />Ajouter un utilisateur
                      </Button>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {companyUsers[c.id]?.length > 0 ? (
                        companyUsers[c.id].map((u) => (
                          <div key={u.id} className="flex items-center gap-2 bg-muted px-3 py-1 rounded-full text-sm">
                            <span>{u.email}</span>
                            <button
                              onClick={async () => {
                                try {
                                  await api.adminRemoveUserFromCompany(c.id, u.id);
                                  loadCompanyUsers(c.id);
                                } catch (e) {
                                  alert(e instanceof Error ? e.message : "Erreur");
                                }
                              }}
                              className="text-muted-foreground hover:text-destructive"
                            >
                              <Trash2 className="size-3.5" />
                            </button>
                          </div>
                        ))
                      ) : (
                        <span className="text-muted-foreground text-sm">Aucun utilisateur</span>
                      )}
                    </div>
                    {(!companyUsers[c.id] || companyUsers[c.id].length === 0) && (
                      <div className="text-xs text-muted-foreground mt-2">
                        <button
                          onClick={() => loadCompanyUsers(c.id)}
                          className="text-primary hover:underline"
                        >
                          Charger les utilisateurs
                        </button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>

      {modalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-full max-w-md rounded-lg bg-background border shadow-lg p-6 space-y-4">
            <h2 className="text-lg font-semibold">
              {modalType === "user" ? (editingId ? "Modifier l'utilisateur" : "Ajouter un utilisateur") :
               modalType === "company" ? (editingId ? "Modifier l'entreprise" : "Ajouter une entreprise") :
               "Affecter un utilisateur"}
            </h2>
            <div className="space-y-3">
              {modalType === "user" && (
                <>
                  <div className="space-y-1">
                    <label className="text-sm font-medium">Email</label>
                    <input
                      type="email"
                      className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
                      value={form.email || ""}
                      onChange={(e) => setForm({ ...form, email: e.target.value })}
                      required
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="text-sm font-medium">Nom</label>
                    <input
                      type="text"
                      className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
                      value={form.name || ""}
                      onChange={(e) => setForm({ ...form, name: e.target.value })}
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="text-sm font-medium">Mot de passe {editingId ? "(laisser vide pour ne pas modifier)" : ""}</label>
                    <input
                      type="password"
                      className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
                      value={form.password || ""}
                      onChange={(e) => setForm({ ...form, password: e.target.value })}
                      required={!editingId}
                    />
                  </div>
                  <div className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      id="is-active"
                      checked={form.is_active ?? true}
                      onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
                    />
                    <label htmlFor="is-active" className="text-sm">Compte actif</label>
                  </div>
                </>
              )}
              {modalType === "company" && (
                <div className="space-y-1">
                  <label className="text-sm font-medium">Nom</label>
                  <input
                    type="text"
                    className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
                    value={form.name || ""}
                    onChange={(e) => setForm({ ...form, name: e.target.value })}
                    required
                  />
                </div>
              )}
              {modalType === "assignment" && (
                <div className="space-y-1">
                  <label className="text-sm font-medium">Utilisateur</label>
                  <select
                    className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
                    value={form.user_id || ""}
                    onChange={(e) => setForm({ ...form, user_id: e.target.value })}
                  >
                    <option value="">Sélectionner...</option>
                    {users.filter((u) => !companyUsers[editingId!]?.some((cu) => cu.id === u.id)).map((u) => (
                      <option key={u.id} value={u.id}>{u.email}</option>
                    ))}
                  </select>
                </div>
              )}
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setModalOpen(false)} disabled={saving}>
                Annuler
              </Button>
              <Button onClick={handleSave} disabled={saving}>
                {saving ? "Sauvegarde..." : "Enregistrer"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
