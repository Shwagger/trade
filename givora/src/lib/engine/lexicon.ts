import { containsWord, normalize } from "./normalize";

// =====================================================================
// LEXIQUE — la moitié de l'intelligence du moteur.
//
// Personne n'écrit « interesses: corrida ». Les gens écrivent « corre no
// parque de manhã », « tá sempre com o cachorro », « não larga o celular ».
// Ce fichier traduit ce que les Brésiliens tapent réellement en signaux
// que le scoring sait manipuler.
//
// `display` est la forme qu'on remettra dans la phrase de justification :
// elle doit se lire naturellement au milieu d'une phrase.
// =====================================================================

export type LexEntry = {
  tag: string;
  /** Motifs normalisés (sans accents, minuscules). Les préfixes marchent. */
  patterns: string[];
  /** Forme lisible réinjectée dans la justification. */
  display: string;
};

export const LEXICON: LexEntry[] = [
  { tag: "cafe", display: "o café", patterns: ["cafe", "cafeteria", "expresso", "capuccino", "coado", "barista"] },
  { tag: "cha", display: "o chá", patterns: ["cha ", "chas", "matcha", "erva mate", "chimarrao"] },
  { tag: "cozinha", display: "cozinhar", patterns: ["cozinh", "culinar", "receita", "cheff", "chef", "assar", "confeit", "bolo", "panela", "gastronom"] },
  { tag: "vinho", display: "o vinho", patterns: ["vinho", "enolog", "espumante", "adega", "taca"] },
  { tag: "cerveja", display: "a cerveja", patterns: ["cerveja", "chopp", "brej", "artesanal"] },
  { tag: "gourmet", display: "a boa comida", patterns: ["gourmet", "comer bem", "comida boa", "delicat", "queijo", "azeite", "gastronomia", "boteco", "restaurante"] },
  { tag: "doces", display: "os doces", patterns: ["doce", "chocolat", "brigadeiro", "sobremesa", "guloseima"] },

  { tag: "academia", display: "a academia", patterns: ["academia", "muscula", "treino", "treina", "malha", "crossfit", "halter"] },
  { tag: "corrida", display: "a corrida", patterns: ["corr", "maratona", "caminhada", "caminha", "pedala", "bike", "ciclis", "bicicleta"] },
  { tag: "yoga", display: "o yoga", patterns: ["yoga", "ioga", "pilates", "alongamento", "medita"] },
  { tag: "futebol", display: "o futebol", patterns: ["futebol", "flamengo", "corinthians", "palmeiras", "sao paulo", "gremio", "torce", "time do coracao"] },
  { tag: "praia", display: "a praia", patterns: ["praia", "mar ", "surf", "piscina", "verao", "sol "] },
  { tag: "trilha", display: "as trilhas", patterns: ["trilha", "camping", "acamp", "montanha", "cachoeira", "natureza", "ar livre"] },

  { tag: "tecnologia", display: "a tecnologia", patterns: ["tecnolog", "gadget", "eletronic", "celular", "smartphone", "notebook", "computador", "tech"] },
  { tag: "games", display: "os games", patterns: ["game", "gamer", "videogame", "playstation", "xbox", "nintendo", "joga muito", "jogo online"] },
  { tag: "musica", display: "a música", patterns: ["music", "cantar", "violao", "guitarra", "viol", "banda", "playlist", "vinil", "spotify", "escuta"] },
  { tag: "fotografia", display: "a fotografia", patterns: ["fotograf", "foto", "camera", "polaroid", "filma"] },
  { tag: "series", display: "as séries", patterns: ["serie", "netflix", "filme", "cinema", "maratonar", "streaming", "anime"] },

  { tag: "leitura", display: "a leitura", patterns: ["ler ", "leitura", "livro", "romance", "poesia", "biblioteca", "kindle", "le muito"] },
  { tag: "estudo", display: "os estudos", patterns: ["estud", "facul", "vestibular", "concurso", "curso", "aprend"] },
  { tag: "trabalho", display: "o trabalho", patterns: ["trabalh", "escritorio", "home office", "reuni", "empreend", "negocio"] },
  { tag: "arte", display: "a arte", patterns: ["arte", "pint", "desenh", "aquarela", "artesanat", "croche", "tricot", "costur", "bordado"] },

  { tag: "casa", display: "a casa", patterns: ["casa", "lar ", "apartamento", "aconcheg", "sofa", "mudou", "morar"] },
  { tag: "decoracao", display: "a decoração", patterns: ["decora", "design", "aromatiz", "vela", "quadro", "ambiente"] },
  { tag: "jardim", display: "as plantas", patterns: ["planta", "jardin", "horta", "suculent", "flor", "verde", "vaso"] },
  { tag: "organizacao", display: "a organização", patterns: ["organiz", "arruma", "minimalis", "ordem"] },

  { tag: "beleza", display: "os cuidados com a pele", patterns: ["skincare", "beleza", "maquiagem", "make", "pele", "hidrata", "perfume", "cabelo", "unha", "salao"] },
  { tag: "moda", display: "a moda", patterns: ["moda", "roupa", "estilo", "look", "acessorio", "bolsa", "sapato", "tenis", "brinco", "colar"] },
  { tag: "bemestar", display: "o descanso", patterns: ["relax", "descans", "spa", "massag", "banho", "estress", "cansad", "dormir", "sono"] },

  { tag: "pets", display: "o pet", patterns: ["pet ", "cachorro", "cadela", "gato", "gata", "bicho", "dog", "au au", "miau", "vira lata"] },
  { tag: "viagem", display: "as viagens", patterns: ["viag", "viaj", "avia", "mochil", "aeroporto", "passeio", "roteiro", "conhecer o mundo"] },
  { tag: "carro", display: "o carro", patterns: ["carro", "automov", "moto ", "dirig", "garag", "ferrament", "conserta"] },
  { tag: "bebe", display: "o bebê", patterns: ["bebe", "recem nascid", "gravid", "gestante", "enxoval", "maternidade"] },
  { tag: "infantil", display: "as brincadeiras", patterns: ["crianc", "brinquedo", "brinca", "escolar", "desenho animado", "lego"] },
];

export type Signal = { tag: string; display: string };

/**
 * Extrait les signaux d'un texte libre + de chips cochées.
 * Renvoie les tags dans l'ordre où ils apparaissent — le premier servira
 * à écrire la justification, donc l'ordre compte.
 */
export function extractSignals(freeText: string, chips: string[]): Signal[] {
  const haystack = " " + normalize([freeText, ...chips].join(" ")) + " ";
  const found: Signal[] = [];
  const seen = new Set<string>();

  for (const entry of LEXICON) {
    if (seen.has(entry.tag)) continue;
    const hit = entry.patterns.some((p) => containsWord(haystack, p));
    if (hit) {
      found.push({ tag: entry.tag, display: entry.display });
      seen.add(entry.tag);
    }
  }
  return found;
}
