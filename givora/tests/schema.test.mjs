// Test des règles produit du moteur IA, sur des sorties modèle simulées.
// Le schéma Zod garantit la forme ; ces règles garantissent le produit.
// Lancer : node --experimental-strip-types tests/schema.test.mjs
import assert from "node:assert/strict";
import { checkRules, withinBudget, RecommendationSchema } from "../src/lib/recommend/schema.ts";

const good = [
  { title: "Prensa francesa", reason: "Como ela toma café todo dia, isso entra na rotina da manhã.",
    category: "cozinha", search_query: "prensa francesa 350ml", price_range: "R$ 70 - R$ 120", marketplace: "amazon_br" },
  { title: "Kit de suculentas", reason: "Você contou que ela cuida das plantas no domingo, e isso cabe na varanda.",
    category: "jardim", search_query: "kit mini suculentas", price_range: "R$ 60 - R$ 110", marketplace: "shopee" },
  { title: "Manta de sofá", reason: "Combina com as noites de série que você mencionou.",
    category: "casa", search_query: "manta microfibra sofa", price_range: "R$ 80 - R$ 140", marketplace: "magalu" },
];

// 1. Une sortie conforme passe.
assert.deepEqual(checkRules(good), [], "une sortie conforme ne doit produire aucun problème");

// 2. Trois fois la même catégorie est rejeté.
const sameCat = good.map((s) => ({ ...s, category: "cozinha" }));
assert.ok(checkRules(sameCat).includes("categorias repetidas"));

// 3. La langue de pub est rejetée même si le JSON est valide.
const adSpeak = [{ ...good[0], reason: "É o presente perfeito para ela." }, good[1], good[2]];
assert.ok(checkRules(adSpeak).some((p) => p.includes("propaganda")), "doit attraper « presente perfeito »");

const willLove = [{ ...good[0], reason: "Ela vai amar esse presente de manhã cedo." }, good[1], good[2]];
assert.ok(checkRules(willLove).some((p) => p.includes("propaganda")), "doit attraper « vai amar »");

// 4. Une justification en plusieurs phrases est rejetée.
const twoSentences = [
  { ...good[0], reason: "Ela toma café todo dia. Isso entra direto na rotina dela." },
  good[1], good[2],
];
assert.ok(checkRules(twoSentences).some((p) => p.includes("mais de uma frase")));

// 5. search_query hors de la fenêtre 2-5 mots.
const tooLong = [
  { ...good[0], search_query: "presente para mae que gosta muito de cafe coado" },
  good[1], good[2],
];
assert.ok(checkRules(tooLong).some((p) => p.includes("palavra")));

// 6. Budget : le plafond est dur.
assert.equal(withinBudget("R$ 70 - R$ 120", 50, 150), true);
assert.equal(withinBudget("R$ 200 - R$ 380", 50, 150), false, "doit refuser au-dessus du plafond");
assert.equal(withinBudget("Acima de R$ 400", 300, null), true, "pas de plafond = toujours bon");

// 7. Le schéma exige exactement trois suggestions.
assert.equal(RecommendationSchema.safeParse({ suggestions: good }).success, true);
assert.equal(RecommendationSchema.safeParse({ suggestions: good.slice(0, 2) }).success, false);

console.log("✓ 7 groupes d'assertions passés");
