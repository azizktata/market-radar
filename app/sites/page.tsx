"use client";

import { useCallback, useEffect, useState } from "react";
import { Pencil, Trash2, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api, type Site } from "@/lib/api";
import { useCompany } from "@/contexts/company-context";

type SiteFormData = {
  name: string;
  domain: string;
  sample_url: string;
  threshold: string;
  enabled: boolean;
};

const EMPTY_FORM: SiteFormData = {
  name: "",
  domain: "",
  sample_url: "",
  threshold: "0",
  enabled: true,
};

export default function SitesPage() {
  const { currentCompany, isLoading: companyLoading } = useCompany();
  const [sites, setSites] = useState<Site[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Site | null>(null);
  const [form, setForm] = useState<SiteFormData>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [detectionNote, setDetectionNote] = useState<string | null>(null);

  const loadSites = useCallback(async () => {
    if (!currentCompany) return;
    try {
      const data = await api.getSites(currentCompany.id);
      setSites(data);
      setError(null);
    } catch {
      setError("Impossible de charger les sites.");
    } finally {
      setLoading(false);
    }
  }, [currentCompany]);

  useEffect(() => {
    if (!currentCompany || companyLoading) return;
    loadSites();
  }, [currentCompany, companyLoading, loadSites]);

  function openAdd() {
    setEditing(null);
    setForm(EMPTY_FORM);
    setFormError(null);
    setDetectionNote(null);
    setModalOpen(true);
  }

  function openEdit(site: Site) {
    setEditing(site);
    setForm({
      name: site.name,
      domain: site.domain,
      sample_url: "",
      threshold: String(site.threshold),
      enabled: site.enabled,
    });
    setFormError(null);
    setDetectionNote(null);
    setModalOpen(true);
  }

  async function handleToggle(site: Site) {
    if (!currentCompany) return;
    try {
      const updated = await api.updateSite(currentCompany.id, site.id, { enabled: !site.enabled });
      setSites((prev) => prev.map((s) => (s.id === site.id ? updated : s)));
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "Erreur lors de la mise à jour.");
    }
  }

  async function handleDelete(site: Site) {
    if (!currentCompany) return;
    if (!window.confirm(`Supprimer le site «${site.name}» ?`)) return;
    try {
      await api.deleteSite(currentCompany.id, site.id);
      setSites((prev) => prev.filter((s) => s.id !== site.id));
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "Erreur lors de la suppression.");
    }
  }

  async function handleSave(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!currentCompany) return;
    setSaving(true);
    setFormError(null);
    setDetectionNote(null);

    const payload = {
      name: form.name.trim(),
      domain: form.domain.trim(),
      sample_url: form.sample_url.trim() || undefined,
      threshold: parseFloat(form.threshold) || 0,
      enabled: form.enabled,
    };

    try {
      if (editing) {
        const updated = await api.updateSite(currentCompany.id, editing.id, payload);
        setSites((prev) => prev.map((s) => (s.id === editing.id ? updated : s)));
        setModalOpen(false);
      } else {
        const created = await api.addSite(currentCompany.id, payload);
        setSites((prev) => [...prev, created]);
        if (created.detected) {
          setDetectionNote(
            `Sélecteur détecté : ${created.price_selector}${created.price_sample ? ` (prix trouvé : ${created.price_sample})` : ""}`
          );
        } else if (payload.sample_url) {
          setDetectionNote("Aucun sélecteur détecté automatiquement. Vous pourrez le configurer manuellement plus tard.");
        }
        if (!created.detected || !payload.sample_url) {
          setModalOpen(false);
        } else {
          setTimeout(() => setModalOpen(false), 2500);
        }
      }
    } catch (e: unknown) {
      setFormError(e instanceof Error ? e.message : "Erreur lors de la sauvegarde.");
    } finally {
      setSaving(false);
    }
  }

  if (companyLoading || !currentCompany) {
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
          <div>
            <h2 className="text-lg font-semibold">Gestion des sites</h2>
            <p className="text-xs text-muted-foreground mt-0.5">
              Sites de scraping — sélecteurs de prix détectés automatiquement.
            </p>
          </div>
          <Button size="sm" onClick={openAdd}>
            <Plus className="size-4 mr-1.5" />Ajouter un site
          </Button>
        </div>

        {error && (
          <div className="rounded-md bg-destructive/10 border border-destructive/30 px-4 py-3 text-sm text-destructive">
            {error}
          </div>
        )}

        {loading ? (
          <div className="py-20 text-center text-muted-foreground text-sm">Chargement…</div>
        ) : (
          <div className="rounded-md border overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/50">
                  <th className="px-4 py-3 text-left font-medium">Nom</th>
                  <th className="px-4 py-3 text-left font-medium">Domaine</th>
                  <th className="px-4 py-3 text-left font-medium">Sélecteur (auto)</th>
                  <th className="px-4 py-3 text-left font-medium">Seuil KO (%)</th>
                  <th className="px-4 py-3 text-center font-medium">Activé</th>
                  <th className="px-4 py-3 text-right font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {sites.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-4 py-10 text-center text-muted-foreground">
                      Aucun site configuré.
                    </td>
                  </tr>
                ) : (
                  sites.map((site) => (
                    <tr key={site.id} className="border-b last:border-0 hover:bg-muted/30 transition-colors">
                      <td className="px-4 py-3 font-medium">{site.name}</td>
                      <td className="px-4 py-3 text-muted-foreground">{site.domain}</td>
                      <td className="px-4 py-3">
                        {site.price_selector ? (
                          <span className="font-mono text-xs text-muted-foreground">{site.price_selector}</span>
                        ) : (
                          <span className="text-xs text-amber-600 dark:text-amber-400">Non détecté</span>
                        )}
                      </td>
                      <td className="px-4 py-3 tabular-nums">{site.threshold}%</td>
                      <td className="px-4 py-3 text-center">
                        <button
                          onClick={() => handleToggle(site)}
                          className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium transition-colors ${
                            site.enabled
                              ? "bg-green-100 text-green-800 hover:bg-green-200 dark:bg-green-900/40 dark:text-green-300"
                              : "bg-muted text-muted-foreground hover:bg-muted/80"
                          }`}
                        >
                          {site.enabled ? "Actif" : "Inactif"}
                        </button>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <div className="flex items-center justify-end gap-1">
                          <Button variant="ghost" size="icon-sm" onClick={() => openEdit(site)}>
                            <Pencil className="size-3.5" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            className="text-muted-foreground hover:text-destructive"
                            onClick={() => handleDelete(site)}
                          >
                            <Trash2 className="size-3.5" />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {modalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-full max-w-md rounded-lg bg-background border shadow-lg p-6 space-y-4">
            <h2 className="text-lg font-semibold">
              {editing ? "Modifier le site" : "Ajouter un site"}
            </h2>
            <form onSubmit={handleSave} className="space-y-3">
              <div className="space-y-1">
                <label className="text-sm font-medium">Nom <span className="text-destructive">*</span></label>
                <input
                  type="text"
                  className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-ring/50"
                  placeholder="ex: Mon Shop"
                  value={form.name}
                  onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                  required
                  autoFocus
                />
              </div>
              <div className="space-y-1">
                <label className="text-sm font-medium">Domaine <span className="text-destructive">*</span></label>
                <input
                  type="text"
                  className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-ring/50"
                  placeholder="ex: monshop.tn"
                  value={form.domain}
                  onChange={(e) => setForm((f) => ({ ...f, domain: e.target.value }))}
                  required
                />
              </div>
              <div className="space-y-1">
                <label className="text-sm font-medium">
                  URL d&apos;un produit{editing ? " (pour re-détecter)" : ""}
                </label>
                <input
                  type="url"
                  className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-ring/50"
                  placeholder="https://monshop.tn/produits/exemple"
                  value={form.sample_url}
                  onChange={(e) => setForm((f) => ({ ...f, sample_url: e.target.value }))}
                />
                <p className="text-xs text-muted-foreground">
                  Copiez l&apos;URL d&apos;une page produit — le sélecteur de prix sera détecté automatiquement.
                </p>
              </div>
              <div className="space-y-1">
                <label className="text-sm font-medium">Seuil KO (%)</label>
                <input
                  type="number"
                  step="0.1"
                  min="0"
                  className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-ring/50"
                  placeholder="0"
                  value={form.threshold}
                  onChange={(e) => setForm((f) => ({ ...f, threshold: e.target.value }))}
                />
                <p className="text-xs text-muted-foreground">
                  Statut KO si le prix du site dépasse PVC × (1 + seuil/100).
                </p>
              </div>
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="site-enabled"
                  checked={form.enabled}
                  onChange={(e) => setForm((f) => ({ ...f, enabled: e.target.checked }))}
                  className="rounded border-input"
                />
                <label htmlFor="site-enabled" className="text-sm">Activer ce site</label>
              </div>

              {detectionNote && (
                <div className={`rounded-md px-3 py-2 text-sm border ${
                  detectionNote.startsWith("Sélecteur détecté")
                    ? "bg-green-50 border-green-200 text-green-800 dark:bg-green-950/30 dark:border-green-800 dark:text-green-300"
                    : "bg-amber-50 border-amber-200 text-amber-800 dark:bg-amber-950/30 dark:border-amber-800 dark:text-amber-300"
                }`}>
                  {detectionNote}
                </div>
              )}

              {formError && (
                <div className="rounded-md bg-destructive/10 border border-destructive/30 px-3 py-2 text-sm text-destructive">
                  {formError}
                </div>
              )}

              <div className="flex justify-end gap-2 pt-1">
                <Button type="button" variant="outline" onClick={() => setModalOpen(false)} disabled={saving}>
                  Annuler
                </Button>
                <Button type="submit" disabled={saving}>
                  {saving
                    ? (form.sample_url ? "Détection…" : "Sauvegarde…")
                    : editing ? "Enregistrer" : "Ajouter"}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
