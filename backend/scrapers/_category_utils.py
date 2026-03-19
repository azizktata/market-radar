"""
Shared category normalization utilities for all scrapers.
"""
import unicodedata


def _strip(s: str) -> str:
    """Remove accents and lowercase."""
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower().strip()


# Mid-level section names that are too generic — skip, try next breadcrumb level
SECTION_LEVEL = {
    "electromenager",
    "lavage",
    "cuisson",
    "froid",
    "climatisation",
    "preparation culinaire",
    "chauffage et chauffe eau",
    "chauffage chauffe eau",
    "appareil de cuisson",
    "hygiene et soin maison",
    "rangement conservation",
    "rangement et conservation",
    "cuisine",
    "entretien du linge",
    "fontaine",
    "purification et humidification",
    "gros electro cuisine",
    "gros electro lavage",
    "gros electromenager lavage",
    "petit electro cuisine",
    "petit electromenager cuisine",
    "cafe et petit dejeuner",
    "pack electromenager",
    "pack petit electro",
}

# normalized (no accents, lowercase) → canonical display name
CANONICAL = {
    "refrigerateur": "Réfrigérateur",
    "refrigerateurs": "Réfrigérateur",
    "mini-refrigerateur": "Mini-Réfrigérateur",
    "mini refrigerateur": "Mini-Réfrigérateur",
    "congelateur": "Congélateur",
    "vitrine refrigeree": "Vitrine Réfrigérée",
    "armoire refrigeree": "Armoire Réfrigérée",
    "cave a vin": "Cave à Vin",
    "machine a laver": "Machine à Laver",
    "seche linge": "Sèche-Linge",
    "seche-linge": "Sèche-Linge",
    "lave vaisselle": "Lave-Vaisselle",
    "lave-vaisselle": "Lave-Vaisselle",
    "climatiseur": "Climatiseur",
    "ventilateur": "Ventilateur",
    "four encastrable": "Four Encastrable",
    "four pose libre": "Four Pose Libre",
    "table de cuisson": "Table de Cuisson",
    "hotte": "Hotte",
    "cuisiniere": "Cuisinière",
    "micro onde": "Micro-Onde",
    "micro-onde": "Micro-Onde",
    "aspirateur": "Aspirateur",
    "fer a repasser": "Fer à Repasser",
    "centrale vapeur": "Centrale Vapeur",
    "nettoyeur": "Nettoyeur Vapeur",
    "nettoyeur a haute pression": "Nettoyeur Haute Pression",
    "cafetiere": "Cafetière",
    "bouilloire": "Bouilloire",
    "mousseur a lait": "Mousseur à Lait",
    "presse agrumes": "Presse-Agrumes",
    "centrifugeuse": "Centrifugeuse",
    "moulin a cafe": "Moulin à Café",
    "capsule a cafe": "Capsule à Café",
    "grille-pain": "Grille-Pain",
    "grille pain": "Grille-Pain",
    "machine a the": "Machine à Thé",
    "friteuse": "Friteuse",
    "grille viande": "Grille-Viande",
    "barbecue": "Barbecue",
    "panini gaufrier": "Panini/Gaufrier",
    "crepiere electrique": "Crêpière Électrique",
    "four a pizza": "Four à Pizza",
    "cuiseur": "Cuiseur",
    "yaourtiere": "Yaourtière",
    "mixeur": "Mixeur",
    "blender": "Blender",
    "batteur": "Batteur",
    "hachoir": "Hachoir",
    "robot multifonction": "Robot Multifonction",
    "robot petrin": "Robot Pétrin",
    "machine a pain": "Machine à Pain",
    "balance cuisine": "Balance Cuisine",
    "chauffage electrique": "Chauffage Électrique",
    "chauffage a gaz": "Chauffage à Gaz",
    "chauffe bain": "Chauffe-Bain",
    "chaudiere": "Chaudière",
    "purificateur d air": "Purificateur d'Air",
    "humidificateur": "Humidificateur",
    "fontaine d eau fraiche": "Fontaine d'Eau",
    "fontaine fraiche": "Fontaine d'Eau",
    "fontaine a chocolat": "Fontaine à Chocolat",
    "machine sous vide": "Machine Sous-Vide",
}


def normalize_category(raw: str) -> str | None:
    """
    Returns the canonical category name for a raw breadcrumb text.
    Returns None if the text is a section-level (too generic) category.
    """
    if not raw:
        return None
    key = _strip(raw)
    if key in SECTION_LEVEL:
        return None
    if key in CANONICAL:
        return CANONICAL[key]
    # Unknown category but specific enough — return cleaned original
    return raw.strip()


def extract_category(crumb_items) -> str | None:
    """
    Extract and normalize a category from breadcrumb <li> items.

    Tries [-2] first. If that is section-level (returns None), falls back to [-3].
    This handles Mytek's inverted breadcrumb (specific before general) as well as
    the normal order used by Tunisianet and Spacenet.

    crumb_items: list of BeautifulSoup Tag objects or plain strings.
    """
    def _text(item) -> str:
        return item.get_text(strip=True) if hasattr(item, "get_text") else str(item).strip()

    for idx in [-2, -3]:
        if len(crumb_items) > abs(idx):
            result = normalize_category(_text(crumb_items[idx]))
            if result is not None:
                return result
    return None
