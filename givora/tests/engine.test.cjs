// Tests du moteur de recommandation. Lancer : npm test
// Le moteur est déterministe à graine fixée, donc chaque cas est
// reproductible — c'est tout l'intérêt d'un algorithme plutôt que d'un
// modèle : quand une suggestion est mauvaise, on rejoue exactement le cas.
const assert = require("node:assert/strict");

const { recommend, explain } = require("../.test-build/engine/index.js");
const { extractSignals } = require("../.test-build/engine/lexicon.js");
const { normalize } = require("../.test-build/engine/normalize.js");
const { CATALOG } = require("../.test-build/engine/catalog.js");
const { checkRules, withinBudget } = require("../.test-build/recommend/schema.js");

const base = {
  relation: "mae", ageRange: "50-64", interests: [], freeText: null,
  occasion: "aniversario", budgetMin: 50, budgetMax: 150,
  deadlineDays: null, seed: "test-seed",
};

let passed = 0;
function check(name, fn) {
  fn();
  passed++;
  console.log("  ✓", name);
}

console.log("\nNormalisation et lexique");
check("les accents et emoji ne cassent pas la détection", () => {
  assert.equal(normalize("Ela AMA café ☕!"), "ela ama cafe");
});
check("« corre no parque » donne le signal corrida", () => {
  const tags = extractSignals("corre no parque de manhã", []).map((s) => s.tag);
  assert.ok(tags.includes("corrida"), tags.join(","));
});
check("« tá sempre com o cachorro » donne pets", () => {
  const tags = extractSignals("tá sempre com o cachorro", []).map((s) => s.tag);
  assert.ok(tags.includes("pets"), tags.join(","));
});
check("un texte sans signal ne fabrique rien", () => {
  assert.deepEqual(extractSignals("ela é uma pessoa discreta", []), []);
});
check("les chips comptent comme signaux", () => {
  const tags = extractSignals("", ["jardinagem"]).map((s) => s.tag);
  assert.ok(tags.includes("jardim"));
});

console.log("\nRègles produit (les mêmes que pour l'IA)");
check("trois suggestions, trois catégories différentes", () => {
  const out = recommend({ ...base, freeText: "ama café e cuida das plantas" });
  assert.equal(out.length, 3);
  assert.equal(new Set(out.map((s) => s.category)).size, 3);
});
check("la justification cite un détail réellement donné", () => {
  const out = recommend({ ...base, freeText: "ama café" });
  assert.ok(out.some((s) => s.reason.includes("o café")), out.map((s) => s.reason).join(" | "));
});
check("sans détail, on l'assume au lieu d'inventer", () => {
  const out = recommend({ ...base, freeText: "não sei muito sobre ela" });
  assert.ok(out.every((s) => !s.reason.includes("Você mencionou")));
});
check("les règles anti-pub passent sur toute la sortie", () => {
  const out = recommend({ ...base, freeText: "ama café e corre de manhã" });
  const asModel = out.map((s) => ({
    title: s.title, reason: s.reason, category: s.category,
    search_query: s.search_query, price_range: s.price_range, marketplace: s.marketplace,
  }));
  assert.deepEqual(checkRules(asModel), []);
});

console.log("\nBudget");
check("rien au-dessus du plafond, sur les 4 tranches", () => {
  for (const [min, max] of [[0, 50], [50, 150], [150, 300], [300, null]]) {
    const out = recommend({ ...base, budgetMin: min, budgetMax: max, freeText: "gosta de tudo" });
    assert.equal(out.length, 3, `tranche ${min}-${max} : seulement ${out.length} suggestions`);
    for (const s of out) {
      assert.ok(withinBudget(s.price_range, min, max),
        `hors budget ${min}-${max} : ${s.title} à ${s.price_range}`);
    }
  }
});
check("le prix affiché n'est jamais gonflé pour ressembler au budget", () => {
  // Défaut réel repéré en relisant les sorties : avec « R$ 300 ou mais »,
  // un kit d'aquarelle à 95 reais s'affichait « A partir de R$ 300 ».
  // Un article trop bon marché pour la tranche ne doit pas apparaître du
  // tout, plutôt que d'apparaître à un prix qu'il n'a pas.
  const out = recommend({ ...base, budgetMin: 300, budgetMax: null, freeText: "gosta de artesanato e pintura" });
  const cheap = ["Kit de aquarela com pincéis", "Estojo de canetas de qualidade",
                 "Marcadores de página em metal", "Caderno pautado com capa dura"];
  for (const s of out) assert.ok(!cheap.includes(s.title), `${s.title} affiché à ${s.price_range}`);
});
check("un budget de 50 n'affiche jamais un article à 350", () => {
  const out = recommend({ ...base, budgetMin: 0, budgetMax: 50, freeText: "adora ler" });
  assert.ok(out.every((s) => !s.title.includes("e-books")));
});

console.log("\nPrazo");
check("« é pra amanhã » remonte le digital", () => {
  const out = recommend({ ...base, deadlineDays: 1, freeText: "gosta de séries" });
  const digitais = ["Vale-presente de loja online", "Assinatura de streaming ou música",
                    "Assinatura de livros digitais", "Cartão-presente de loja de games"];
  assert.ok(out.some((s) => digitais.includes(s.title)), out.map((s) => s.title).join(" | "));
});
check("la carte digitale explique qu'elle arrive à temps", () => {
  const out = recommend({ ...base, deadlineDays: 1, freeText: "gosta de séries" });
  assert.ok(out.some((s) => s.reason.includes("Chega na hora")));
});

console.log("\nRefinar");
check("le feedback change le trio", () => {
  const first = recommend({ ...base, freeText: "ama café" });
  const second = recommend({
    ...base, freeText: "ama café", feedback: "ela já tem prensa, prefiro algo para a casa",
    avoidTitles: first.map((s) => s.title),
  });
  assert.equal(first.map((s) => s.title).some((t) => second.map((x) => x.title).includes(t)), false,
    "le refinar a resservi un titre déjà vu");
});
check("le feedback est lu comme un signal", () => {
  const out = recommend({ ...base, freeText: "sei lá", feedback: "prefiro algo para as plantas dela" });
  assert.ok(out.some((s) => s.category === "jardim"), out.map((s) => s.category).join(","));
});
check("ce que le groupe a descendu ne revient pas en tête", () => {
  const plain = recommend({ ...base, freeText: "ama café" });
  const rejected = [plain[0].title];
  const after = recommend({ ...base, freeText: "ama café", rejectedTitles: rejected });
  assert.notEqual(after[0].title, rejected[0]);
});

console.log("\nDéterminisme et robustesse");
check("même graine, même résultat", () => {
  const a = recommend({ ...base, freeText: "ama café" });
  const b = recommend({ ...base, freeText: "ama café" });
  assert.deepEqual(a, b);
});
check("graines différentes, résultats qui varient", () => {
  const seeds = ["a", "b", "c", "d", "e"].map((seed) =>
    recommend({ ...base, seed, freeText: "gosta de coisas legais" }).map((s) => s.title).join("|"));
  assert.ok(new Set(seeds).size > 1, "toutes les graines donnent le même trio");
});
check("entrée vide : on rend quand même trois idées", () => {
  const out = recommend({ ...base, freeText: "", interests: [] });
  assert.equal(out.length, 3);
});
check("aucune combinaison plausible ne rend moins de 3 idées", () => {
  const relations = ["mae", "pai", "namorada", "amigo", "colega", "filho", "avo", "outro"];
  const ages = ["0-12", "18-24", "25-34", "50-64", "65+"];
  const occasions = ["aniversario", "natal", "dia-das-maes", "amigo-secreto", "sem-motivo"];
  const budgets = [[0, 50], [50, 150], [150, 300], [300, null]];
  let cases = 0;
  for (const relation of relations)
    for (const ageRange of ages)
      for (const occasion of occasions)
        for (const [budgetMin, budgetMax] of budgets) {
          const out = recommend({ ...base, relation, ageRange, occasion, budgetMin, budgetMax, freeText: "" });
          assert.equal(out.length, 3,
            `${relation}/${ageRange}/${occasion}/${budgetMin}-${budgetMax} : ${out.length}`);
          assert.equal(new Set(out.map((s) => s.category)).size, 3);
          cases++;
        }
  console.log(`      (${cases} combinaisons couvertes)`);
});

console.log("\nExplicabilité");
check("explain() rend le détail du calcul de chaque candidat", () => {
  // C'est ce qu'un modèle ne donne pas : quand une suggestion est mauvaise,
  // on doit pouvoir lire POURQUOI elle a gagné.
  const e = explain({ ...base, freeText: "ama café" });
  assert.ok(e.signals.some((s) => s.tag === "cafe"));
  assert.ok(e.candidates > 10, `seulement ${e.candidates} candidats`);
  assert.ok(e.top[0].breakdown.budget > 0);
  assert.ok(Object.keys(e.top[0].breakdown).length >= 2);
});

console.log("\nCatalogue");
check("chaque search_query fait 2 à 5 mots", () => {
  for (const a of CATALOG) {
    const n = a.query.trim().split(/\s+/).length;
    assert.ok(n >= 2 && n <= 5, `${a.id} : "${a.query}" (${n} mots)`);
  }
});
check("floor < typical partout", () => {
  for (const a of CATALOG) assert.ok(a.floor < a.typical, `${a.id}: ${a.floor} >= ${a.typical}`);
});
check("les notes s'enchaînent en minuscule et sans point final", () => {
  for (const a of CATALOG) {
    assert.equal(a.note, a.note.trim());
    assert.ok(!a.note.endsWith("."), `${a.id} finit par un point`);
    assert.equal(a.note[0], a.note[0].toLowerCase(), `${a.id} commence par une majuscule`);
  }
});
check("catalogue et lexique se recouvrent dans les deux sens", () => {
  const { LEXICON } = require("../.test-build/engine/lexicon.js");
  const known = new Set(LEXICON.map((e) => e.tag));
  const used = new Set(CATALOG.flatMap((a) => a.tags));

  // Un tag du catalogue absent du lexique est un tag mort : aucun texte
  // utilisateur ne peut le déclencher.
  for (const t of used) assert.ok(known.has(t), `tag "${t}" utilisé mais absent du lexique`);

  // Un tag du lexique que rien ne porte, c'est un signal détecté puis
  // jeté : la personne parle de quelque chose et on n'a rien à offrir.
  for (const t of known) assert.ok(used.has(t), `tag "${t}" détecté mais aucun cadeau ne le porte`);
});

console.log(`\n✓ ${passed} tests passés\n`);
