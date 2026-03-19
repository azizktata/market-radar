"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";

interface AddProductDialogProps {
  open: boolean;
  onClose: () => void;
  onAdd: (product: { reference: string; name?: string; category?: string; sous_categorie?: string; marque?: string; pvc?: number }) => Promise<void>;
}

export function AddProductDialog({ open, onClose, onAdd }: AddProductDialogProps) {
  const [reference, setReference] = useState("");
  const [name, setName] = useState("");
  const [category, setCategory] = useState("");
  const [sousCategorie, setSousCategorie] = useState("");
  const [marque, setMarque] = useState("");
  const [pvc, setPvc] = useState("");
  const [loading, setLoading] = useState(false);

  if (!open) return null;

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const ref = reference.trim();
    if (!ref) return;
    setLoading(true);
    try {
      await onAdd({
        reference: ref,
        name: name.trim() || undefined,
        category: category.trim() || undefined,
        sous_categorie: sousCategorie.trim() || undefined,
        marque: marque.trim() || undefined,
        pvc: pvc ? parseFloat(pvc) : undefined,
      });
      setReference("");
      setName("");
      setCategory("");
      setSousCategorie("");
      setMarque("");
      setPvc("");
      onClose();
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-md rounded-lg bg-background border shadow-lg p-6 space-y-4">
        <h2 className="text-lg font-semibold">Ajouter un produit</h2>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="space-y-1">
            <label className="text-sm font-medium">Référence <span className="text-destructive">*</span></label>
            <input
              type="text"
              className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-ring/50 font-mono"
              placeholder="ex: WM-1234"
              value={reference}
              onChange={(e) => setReference(e.target.value)}
              autoFocus
              required
            />
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium">Nom</label>
            <input
              type="text"
              className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-ring/50"
              placeholder="ex: Lave-linge Samsung 8kg"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium">Catégorie</label>
            <input
              type="text"
              className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-ring/50"
              placeholder="ex: Machine à Laver"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
            />
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium">Sous-catégorie</label>
            <input
              type="text"
              className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-ring/50"
              placeholder="ex: Lave-linge hublot"
              value={sousCategorie}
              onChange={(e) => setSousCategorie(e.target.value)}
            />
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium">Marque</label>
            <input
              type="text"
              className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-ring/50"
              placeholder="ex: Samsung"
              value={marque}
              onChange={(e) => setMarque(e.target.value)}
            />
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium">PVC (DT)</label>
            <input
              type="number"
              step="0.001"
              min="0"
              className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-ring/50"
              placeholder="ex: 1299.000"
              value={pvc}
              onChange={(e) => setPvc(e.target.value)}
            />
          </div>
          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="outline" onClick={onClose} disabled={loading}>
              Annuler
            </Button>
            <Button type="submit" disabled={loading || !reference.trim()}>
              {loading ? "Ajout…" : "Ajouter"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
