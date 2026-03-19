"use client";

import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";

interface ImportExcelDialogProps {
  open: boolean;
  onClose: () => void;
  onImported: () => void;
}

export function ImportExcelDialog({ open, onClose, onImported }: ImportExcelDialogProps) {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{ added: number; skipped: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  if (!open) return null;

  function handleClose() {
    setFile(null);
    setResult(null);
    setError(null);
    onClose();
  }

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!file) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await api.importProducts(file);
      setResult(res);
      onImported();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Erreur lors de l'import.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-md rounded-lg bg-background border shadow-lg p-6 space-y-4">
        <h2 className="text-lg font-semibold">Importer depuis Excel</h2>
        <p className="text-sm text-muted-foreground">
          Le fichier doit contenir une colonne <span className="font-mono text-xs bg-muted px-1 rounded">Référence</span> (obligatoire) et optionnellement{" "}
          <span className="font-mono text-xs bg-muted px-1 rounded">Nom</span>,{" "}
          <span className="font-mono text-xs bg-muted px-1 rounded">Catégorie</span>,{" "}
          <span className="font-mono text-xs bg-muted px-1 rounded">PVC</span>.
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div
            className="flex flex-col items-center justify-center gap-2 rounded-md border-2 border-dashed border-input px-4 py-6 cursor-pointer hover:border-ring/50 transition-colors"
            onClick={() => inputRef.current?.click()}
          >
            <input
              ref={inputRef}
              type="file"
              accept=".xlsx,.xls"
              className="hidden"
              onChange={(e) => { setFile(e.target.files?.[0] ?? null); setResult(null); setError(null); }}
            />
            {file ? (
              <p className="text-sm font-medium">{file.name}</p>
            ) : (
              <p className="text-sm text-muted-foreground">Cliquer pour sélectionner un fichier .xlsx</p>
            )}
          </div>

          {result && (
            <div className="rounded-md bg-green-50 border border-green-200 dark:bg-green-950/30 dark:border-green-800 px-3 py-2 text-sm text-green-800 dark:text-green-300">
              {result.added} produit(s) ajouté(s), {result.skipped} ignoré(s) (doublons).
            </div>
          )}

          {error && (
            <div className="rounded-md bg-destructive/10 border border-destructive/30 px-3 py-2 text-sm text-destructive">
              {error}
            </div>
          )}

          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={handleClose} disabled={loading}>
              {result ? "Fermer" : "Annuler"}
            </Button>
            {!result && (
              <Button type="submit" disabled={loading || !file}>
                {loading ? "Import…" : "Importer"}
              </Button>
            )}
          </div>
        </form>
      </div>
    </div>
  );
}
