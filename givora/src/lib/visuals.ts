// =====================================================================
// L'IMAGE DE CHAQUE CARTE.
//
// Une carte de cadeau sans visuel se lit comme une liste de courses.
// Mais on ne peut pas afficher la photo d'un produit précis sans le flux
// produit d'un marchand (voir src/lib/products.ts) : nos entrées sont
// des CATÉGORIES de cadeau, pas des références.
//
// Donc on illustre honnêtement la catégorie : une tuile dégradée
// dérivée du nom de la catégorie, avec son pictogramme. C'est
// auto-hébergé (zéro requête, zéro licence, zéro lien mort) et ça reste
// vrai. Le jour où un flux produit est branché, la vraie photo remplace
// la tuile et le reste ne bouge pas.
// =====================================================================

const GLYPHS: Record<string, string> = {
  café: "☕", gourmet: "🧀", bebidas: "🍷", "bebidas-pro": "🍾",
  cozinha: "🍳", "cozinha-pro": "🥘", eletro: "⚡", casa: "🛋️",
  decoração: "🕯️", jardim: "🪴", móveis: "🪑",
  esporte: "🏃", "esporte-calçado": "👟", "ar-livre": "🏕️", "bem-estar": "🧘",
  tecnologia: "📱", áudio: "🎧", games: "🎮", foto: "📷", música: "🎸",
  livros: "📚", papelaria: "✏️", arte: "🎨", artesanato: "🧵",
  beleza: "🧴", moda: "🧣", acessórios: "⌚",
  pet: "🐾", viagem: "🧳", auto: "🚗", ferramentas: "🔧",
  infantil: "🧸", bebê: "🍼",
  "vale-presente": "🎁", assinatura: "🔄",
};

/** Teinte dérivée du nom : deux catégories différentes ne se ressemblent pas. */
function hueOf(category: string): number {
  let h = 0;
  for (let i = 0; i < category.length; i++) h = (h * 31 + category.charCodeAt(i)) % 360;
  return h;
}

export type Visual = { glyph: string; from: string; to: string };

export function visualFor(category: string, glyph?: string): Visual {
  const hue = hueOf(category);
  return {
    // Le pictogramme de l'article gagne sur celui de la catégorie.
    glyph: glyph ?? GLYPHS[category] ?? "🎁",
    // Saturation et luminosité fixes : les teintes varient, le niveau
    // reste constant, donc aucune tuile ne crie plus fort qu'une autre.
    from: `hsl(${hue} 62% 92%)`,
    to: `hsl(${(hue + 34) % 360} 58% 84%)`,
  };
}
