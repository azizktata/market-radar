"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";

interface AddProductDialogProps {
  open: boolean;
  onClose: () => void;
  onAdd: (references: string[]) => Promise<void>;
}

export function AddProductDialog({ open, onClose, onAdd }: AddProductDialogProps) {
  const [value, setValue] = useState("");
  const [loading, setLoading] = useState(false);

  if (!open) return null;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const refs = value
      .split(/[\n,;]+/)
      .map((r) => r.trim())
      .filter(Boolean);
    if (!refs.length) return;
    setLoading(true);
    try {
      await onAdd(refs);
      setValue("");
      onClose();
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-md rounded-lg bg-background border shadow-lg p-6 space-y-4">
        <h2 className="text-lg font-semibold">Ajouter des références</h2>
        <p className="text-sm text-muted-foreground">
          Entrez une ou plusieurs références (une par ligne, ou séparées par virgule).
        </p>
        <form onSubmit={handleSubmit} className="space-y-4">
          <textarea
            className="w-full h-36 rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring/50 font-mono resize-none"
            placeholder={"WM-1234\nFR-5678\nLG-9012"}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            autoFocus
          />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={onClose} disabled={loading}>
              Annuler
            </Button>
            <Button type="submit" disabled={loading || !value.trim()}>
              {loading ? "Ajout..." : "Ajouter"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
