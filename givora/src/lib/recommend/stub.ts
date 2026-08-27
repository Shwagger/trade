import type { Marketplace } from "../types";
import type { SuggestionDraft } from "../store";
import { occasionLabel } from "../constants";

// =====================================================================
// MOTEUR PROVISOIRE — PHASE 1.
// Aucune IA ici. C'est un petit catalogue en dur qui sert uniquement à
// remplir l'écran de résultats pour valider le parcours et le temps de
// réponse. En PHASE 2, /api/recommend appellera l'API Anthropic
// (claude-sonnet-4-6), validera la sortie avec Zod et retentera une fois
// si le JSON est invalide ; ce fichier sera supprimé. Le contrat de
// sortie (SuggestionDraft) ne change pas, donc rien d'autre ne bouge.
// =====================================================================

type CatalogItem = {
  category: string;
  title: string;
  searchQuery: string;
  marketplace: Marketplace;
  tags: string[];                       // vide = passe-partout
  floor: number;                        // prix plancher réaliste, en BRL
  matched: (detail: string) => string;  // quand un tag colle à l'entrée
  neutral: (occasion: string) => string; // quand rien ne colle
};

const CATALOG: CatalogItem[] = [
  {
    category: "cozinha",
    title: "Prensa francesa de café",
    floor: 60,
    searchQuery: "prensa francesa café 350ml",
    marketplace: "amazon_br",
    tags: ["café", "cozinha"],
    matched: (d) => `Como ${d} aparece na sua descrição, é um objeto que entra na rotina da manhã.`,
    neutral: (o) => `Transforma o café de todo dia em ritual, o que segura bem um ${o}.`,
  },
  {
    category: "casa",
    title: "Kit de temperos em potes de vidro",
    floor: 35,
    searchQuery: "kit temperos potes vidro",
    marketplace: "magalu",
    tags: ["cozinha", "decoração", "casa"],
    matched: (d) => `Fica à vista na bancada de quem gosta de ${d} e é usado quase todo dia.`,
    neutral: (o) => `Fica na bancada e é usado toda semana, difícil errar num ${o}.`,
  },
  {
    category: "tecnologia",
    title: "Fone bluetooth com cancelamento de ruído",
    floor: 120,
    searchQuery: "fone bluetooth cancelamento ruído",
    marketplace: "mercado_livre",
    tags: ["música", "tecnologia", "games", "séries", "corrida", "academia", "viagem"],
    matched: (d) => `Serve direto para ${d}, que foi o que você contou sobre essa pessoa.`,
    neutral: (o) => `Resolve trajeto, treino e trabalho ao mesmo tempo, e cabe num ${o}.`,
  },
  {
    category: "esporte",
    title: "Garrafa térmica de 750 ml",
    floor: 60,
    searchQuery: "garrafa térmica inox 750ml",
    marketplace: "amazon_br",
    tags: ["academia", "corrida", "praia", "viagem", "futebol"],
    matched: (d) => `Quem tem ${d} na rotina carrega uma garrafa dessas o tempo todo.`,
    neutral: () => `É daquelas coisas que a pessoa usa todo dia e nunca compra sozinha.`,
  },
  {
    category: "livros",
    title: "Livro de bolso com marcador",
    floor: 25,
    searchQuery: "livro bolso best seller",
    marketplace: "amazon_br",
    tags: ["leitura", "séries"],
    matched: (d) => `Combina com o lado ${d} que você descreveu, sem precisar acertar o gosto exato.`,
    neutral: (o) => `Ocupa a mesa de cabeceira e dura muito além do ${o}.`,
  },
  {
    category: "beleza",
    title: "Kit de skincare com hidratante e protetor",
    floor: 40,
    searchQuery: "kit skincare hidratante facial",
    marketplace: "shopee",
    tags: ["skincare", "moda", "beleza"],
    matched: (d) => `Encaixa em quem já cuida de ${d} e sempre repõe o que acaba.`,
    neutral: (o) => `É consumo recorrente: acaba e faz falta, independente do ${o}.`,
  },
  {
    category: "jardim",
    title: "Kit de mini suculentas com vasinhos",
    floor: 25,
    searchQuery: "kit mini suculentas vasos",
    marketplace: "shopee",
    tags: ["jardinagem", "decoração", "casa"],
    matched: (d) => `Vai direto ao ponto para alguém de ${d}, e cabe em qualquer canto da casa.`,
    neutral: () => `Cabe em qualquer canto da casa e não exige cuidado nenhum.`,
  },
  {
    category: "pet",
    title: "Brinquedo interativo para pet",
    floor: 30,
    searchQuery: "brinquedo interativo cachorro",
    marketplace: "mercado_livre",
    tags: ["pets", "cachorro", "gato"],
    matched: (d) => `Você mencionou ${d}: o presente acaba sendo para os dois.`,
    neutral: () => `Se tem bicho em casa, o presente acaba sendo para os dois.`,
  },
  {
    category: "experiencia",
    title: "Vale-presente de cafeteria ou livraria",
    floor: 20,
    searchQuery: "vale presente cartão presente",
    marketplace: "amazon_br",
    tags: [],
    matched: (d) => `Deixa a escolha final com quem curte ${d}, o que evita errar tamanho ou gosto.`,
    neutral: () => `Deixa a escolha final com a pessoa, que é a saída honesta quando você não tem certeza.`,
  },
  {
    category: "acessorios",
    title: "Necessaire de viagem compacta",
    floor: 40,
    searchQuery: "necessaire viagem compacta",
    marketplace: "magalu",
    tags: ["viagem", "moda", "praia"],
    matched: (d) => `Faz sentido para ${d} e é do tipo que ninguém compra para si mesmo.`,
    neutral: () => `É do tipo que ninguém compra para si mesmo e some na primeira viagem.`,
  },
  {
    category: "papelaria",
    title: "Caderno pautado com capa dura",
    floor: 20,
    searchQuery: "caderno capa dura pautado",
    marketplace: "shopee",
    tags: ["leitura", "artesanato", "fotografia", "trabalho", "estudo"],
    matched: (d) => `Serve para anotar o que vem de ${d}, e dura o ano inteiro.`,
    neutral: () => `Dura o ano inteiro e não depende de acertar tamanho nem cor.`,
  },
  {
    category: "bem-estar",
    title: "Manta de microfibra para o sofá",
    floor: 50,
    searchQuery: "manta microfibra sofá casal",
    marketplace: "magalu",
    tags: ["séries", "casa", "decoração", "frio"],
    matched: (d) => `É o presente de quem passa as noites com ${d}.`,
    neutral: () => `Vira o objeto favorito do sofá em duas semanas.`,
  },
];

function priceBands(min: number, max: number | null): string[] {
  if (max === null) {
    return ["R$ 300 - R$ 450", "R$ 350 - R$ 600", "Acima de R$ 400"];
  }
  const span = max - min;
  const band = (a: number, b: number) => {
    const lo = Math.max(min, Math.round((min + span * a) / 5) * 5);
    const hi = Math.min(max, Math.round((min + span * b) / 5) * 5);
    return `R$ ${lo} - R$ ${hi}`;
  };
  return [band(0.2, 0.7), band(0.35, 0.9), band(0.1, 0.55)];
}

// Chips cochées + texte libre + feedback du "refinar" : tout part dans le
// même sac de mots, c'est là-dedans qu'on cherche les tags du catalogue.
function corpusOf(interests: string[], freeText: string): string {
  return [...interests, freeText].join(" ").toLowerCase();
}

export function stubSuggestions(input: {
  occasion: string;
  interests: string[];
  freeText: string;
  budgetMin: number;
  budgetMax: number | null;
  /** Titres déjà montrés : le "refinar" doit renvoyer autre chose. */
  avoidTitles?: string[];
}): SuggestionDraft[] {
  const corpus = corpusOf(input.interests, input.freeText);
  const avoid = new Set(input.avoidTitles ?? []);
  const occasion = occasionLabel(input.occasion).toLowerCase();

  // Pas de fone de R$ 300 dans un budget "até R$ 50" : on écarte ce que
  // le budget ne paie pas. Si le filtre est trop dur, on reprend tout.
  const ceiling = input.budgetMax ?? Number.POSITIVE_INFINITY;
  const affordable = CATALOG.filter((item) => item.floor <= ceiling);
  const pool = affordable.length >= 3 ? affordable : CATALOG;

  const scored = pool.map((item) => {
    const hits = item.tags.filter((t) => corpus.includes(t));
    return {
      item,
      hits,
      // Un titre déjà vu part au fond du classement, mais reste éligible :
      // mieux vaut le reproposer que rendre moins de trois cartes.
      score: hits.length - (avoid.has(item.title) ? 10 : 0),
    };
  }).sort((a, b) => b.score - a.score);

  // Contrainte produit : 3 catégories DIFFÉRENTES.
  const picked: typeof scored = [];
  const seen = new Set<string>();
  for (const entry of scored) {
    if (seen.has(entry.item.category)) continue;
    picked.push(entry);
    seen.add(entry.item.category);
    if (picked.length === 3) break;
  }

  const bands = priceBands(input.budgetMin, input.budgetMax);

  return picked.map(({ item, hits }, i) => ({
    title: item.title,
    // Une phrase, et elle ne cite un détail que si ce détail vient bien
    // de l'utilisateur — sinon on prend la version neutre.
    reason: hits.length > 0 ? item.matched(hits[0]) : item.neutral(occasion),
    category: item.category,
    search_query: item.searchQuery,
    price_range: bands[i],
    marketplace: item.marketplace,
    position: i + 1,
  }));
}
