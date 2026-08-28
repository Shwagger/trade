import type { Marketplace } from "../types";

// =====================================================================
// CATALOGUE — le véritable actif du produit.
//
// Ce ne sont pas des produits, ce sont des ARCHÉTYPES de cadeau. Un
// archétype porte une requête marketplace qui ramène des dizaines de
// produits réels : on n'a donc jamais de lien mort ni de rupture de
// stock, et rien à re-synchroniser quand un vendeur disparaît.
//
// Chaque entrée est du travail éditorial, pas du remplissage. Ajouter un
// archétype, c'est ajouter de la couverture ; enlever un mauvais, c'est
// enlever une suggestion embarrassante. C'est ici qu'on gagne ou qu'on
// perd contre les concurrents, pas dans le scoring.
//
// floor   = prix plancher réaliste. En dessous, le produit n'existe pas.
// typical = prix où se trouve la majorité de l'offre. Sert au scoring.
// note    = la seconde moitié de la phrase de justification. Doit
//           s'enchaîner après une virgule, en minuscule, sans point.
// =====================================================================

export type Archetype = {
  id: string;
  title: string;
  category: string;
  /** Requête marketplace : 2 à 5 mots, comme un vrai humain la tape. */
  query: string;
  store: Marketplace;
  floor: number;
  typical: number;
  tags: string[];
  /** Vide = convient à toutes les relations. */
  relations?: string[];
  /** Vide = convient à tous les âges. */
  ages?: string[];
  /** Vide = convient à toutes les occasions. */
  occasions?: string[];
  /** Arrive tout de suite : sauve les cadeaux de dernière minute. */
  digital?: boolean;
  note: string;
};

const A = (a: Archetype) => a;

export const CATALOG: Archetype[] = [
  // ---- café, chá, gourmet ------------------------------------------
  A({ id: "prensa-francesa", title: "Prensa francesa de café", category: "café", query: "prensa francesa 350ml",
      store: "amazon_br", floor: 60, typical: 110, tags: ["cafe"],
      note: "vira parte do ritual da manhã em vez de ficar guardado" }),
  A({ id: "moedor-cafe", title: "Moedor de café manual", category: "café", query: "moedor café manual",
      store: "mercado_livre", floor: 90, typical: 190, tags: ["cafe", "cozinha"],
      note: "muda o sabor de verdade para quem já leva o café a sério" }),
  A({ id: "kit-cafe-especial", title: "Kit de cafés especiais em grão", category: "gourmet", query: "kit café especial grãos",
      store: "shopee", floor: 50, typical: 95, tags: ["cafe", "gourmet"],
      note: "acaba e é lembrado de novo na próxima compra" }),
  A({ id: "caneca-termica", title: "Caneca térmica que mantém quente", category: "café", query: "caneca térmica 400ml",
      store: "amazon_br", floor: 45, typical: 90, tags: ["cafe", "trabalho"],
      note: "resolve o problema do café que esfria antes da metade" }),
  A({ id: "kit-cha", title: "Kit de chás com infusor", category: "gourmet", query: "kit chá infusor",
      store: "shopee", floor: 40, typical: 85, tags: ["cha", "bemestar"],
      note: "acompanha o fim do dia sem ocupar espaço nenhum" }),
  A({ id: "tabua-frios", title: "Tábua de frios com facas", category: "gourmet", query: "tábua frios madeira kit",
      store: "magalu", floor: 70, typical: 150, tags: ["gourmet", "vinho", "cozinha", "casa"],
      note: "transforma uma noite comum em recebendo gente em casa" }),
  A({ id: "kit-vinho", title: "Kit acessórios de vinho", category: "bebidas", query: "kit acessórios vinho saca rolha",
      store: "mercado_livre", floor: 60, typical: 130, tags: ["vinho"],
      note: "é o tipo de coisa que quem gosta nunca compra para si" }),
  A({ id: "taças-vinho", title: "Jogo de taças de cristal", category: "bebidas", query: "jogo taças vinho cristal",
      store: "magalu", floor: 80, typical: 170, tags: ["vinho", "casa", "decoracao"],
      note: "fica bonito na mesa e não some no armário" }),
  A({ id: "kit-cerveja", title: "Kit de cervejas artesanais", category: "bebidas", query: "kit cerveja artesanal presente",
      store: "mercado_livre", floor: 70, typical: 140, tags: ["cerveja"],
      ages: ["18-24", "25-34", "35-49", "50-64", "65+"],
      note: "dá o que conversar antes mesmo de abrir a primeira" }),
  A({ id: "chocolate-fino", title: "Caixa de chocolates finos", category: "gourmet", query: "caixa chocolate presente",
      store: "amazon_br", floor: 35, typical: 80, tags: ["doces"],
      note: "nunca sobra, e é a aposta mais segura da lista" }),

  // ---- cozinha e casa ----------------------------------------------
  A({ id: "kit-temperos", title: "Kit de temperos em potes de vidro", category: "cozinha", query: "kit temperos potes vidro",
      store: "magalu", floor: 35, typical: 75, tags: ["cozinha", "casa", "decoracao"],
      note: "fica à vista na bancada e é usado quase todo dia" }),
  A({ id: "airfryer", title: "Air fryer compacta", category: "eletro", query: "air fryer 4 litros",
      store: "magalu", floor: 250, typical: 420, tags: ["cozinha", "casa"],
      note: "é o eletrodoméstico que mais muda a rotina de quem cozinha" }),
  A({ id: "panela-ferro", title: "Frigideira de ferro fundido", category: "cozinha", query: "frigideira ferro fundido",
      store: "amazon_br", floor: 90, typical: 180, tags: ["cozinha"],
      note: "dura décadas e melhora com o uso" }),
  A({ id: "livro-receitas", title: "Livro de receitas ilustrado", category: "livros", query: "livro receitas culinária",
      store: "amazon_br", floor: 45, typical: 90, tags: ["cozinha", "leitura"],
      note: "junta as duas coisas sem precisar escolher" }),
  A({ id: "avental", title: "Avental de cozinha resistente", category: "cozinha", query: "avental cozinha profissional",
      store: "shopee", floor: 30, typical: 60, tags: ["cozinha"],
      note: "é barato, é usado toda semana, e ninguém compra para si" }),
  A({ id: "manta-sofa", title: "Manta de microfibra para o sofá", category: "casa", query: "manta microfibra sofá casal",
      store: "magalu", floor: 50, typical: 110, tags: ["casa", "series", "bemestar"],
      note: "vira o objeto favorito do sofá em duas semanas" }),
  A({ id: "difusor", title: "Difusor de aromas com varetas", category: "decoração", query: "difusor aromas varetas",
      store: "shopee", floor: 35, typical: 70, tags: ["decoracao", "casa", "bemestar"],
      note: "muda o clima do cômodo inteiro por meses" }),
  A({ id: "luminaria", title: "Luminária de mesa com luz quente", category: "decoração", query: "luminária mesa luz quente",
      store: "mercado_livre", floor: 60, typical: 130, tags: ["decoracao", "casa", "leitura"],
      note: "resolve a luz dura do teto que ninguém aguenta à noite" }),
  A({ id: "porta-retrato", title: "Porta-retrato com foto impressa", category: "decoração", query: "porta retrato personalizado",
      store: "shopee", floor: 25, typical: 55, tags: ["decoracao", "fotografia", "casa"],
      note: "é o presente que continua ali daqui a dez anos" }),
  A({ id: "organizador", title: "Organizadores para armário", category: "casa", query: "organizador armário caixa",
      store: "shopee", floor: 30, typical: 70, tags: ["organizacao", "casa"],
      note: "resolve um incômodo diário que a pessoa nunca prioriza" }),

  // ---- jardim ------------------------------------------------------
  A({ id: "suculentas", title: "Kit de mini suculentas com vasinhos", category: "jardim", query: "kit mini suculentas vasos",
      store: "shopee", floor: 25, typical: 60, tags: ["jardim", "decoracao"],
      note: "cabe em qualquer canto e não exige cuidado nenhum" }),
  A({ id: "kit-jardinagem", title: "Kit de ferramentas de jardinagem", category: "jardim", query: "kit ferramentas jardinagem",
      store: "mercado_livre", floor: 50, typical: 110, tags: ["jardim"],
      note: "substitui a colher de sopa que ela usa para replantar" }),
  A({ id: "horta-casa", title: "Kit de horta caseira com sementes", category: "jardim", query: "kit horta caseira sementes",
      store: "shopee", floor: 40, typical: 85, tags: ["jardim", "cozinha"],
      note: "junta as plantas e a cozinha na mesma janela" }),
  A({ id: "vaso-autoirrigavel", title: "Vasos autoirrigáveis", category: "jardim", query: "vaso autoirrigável planta",
      store: "magalu", floor: 35, typical: 80, tags: ["jardim", "decoracao"],
      note: "perdoa a semana em que ninguém lembrou de regar" }),

  // ---- esporte e bem-estar -----------------------------------------
  A({ id: "garrafa-termica", title: "Garrafa térmica de 750 ml", category: "esporte", query: "garrafa térmica inox 750ml",
      store: "amazon_br", floor: 55, typical: 110, tags: ["academia", "corrida", "trilha", "trabalho"],
      note: "acompanha todo dia e nunca é comprada por conta própria" }),
  A({ id: "fone-esportivo", title: "Fone bluetooth para treino", category: "áudio", query: "fone bluetooth esportivo",
      store: "mercado_livre", floor: 90, typical: 190, tags: ["academia", "corrida", "musica"],
      note: "é o que separa um treino chato de um treino que passa rápido" }),
  A({ id: "smartwatch", title: "Smartwatch com monitor de passos", category: "tecnologia", query: "smartwatch monitor cardíaco",
      store: "mercado_livre", floor: 150, typical: 320, tags: ["academia", "corrida", "tecnologia"],
      note: "transforma o treino em número, e número vicia" }),
  A({ id: "tapete-yoga", title: "Tapete de yoga antiderrapante", category: "bem-estar", query: "tapete yoga antiderrapante",
      store: "shopee", floor: 50, typical: 100, tags: ["yoga", "academia"],
      note: "tira a desculpa do chão frio de manhã cedo" }),
  A({ id: "massageador", title: "Massageador de pescoço elétrico", category: "bem-estar", query: "massageador pescoço elétrico",
      store: "magalu", floor: 90, typical: 190, tags: ["bemestar", "trabalho"],
      note: "ataca exatamente onde o dia de trabalho acumula" }),
  A({ id: "kit-banho", title: "Kit de banho relaxante", category: "bem-estar", query: "kit banho relaxante presente",
      store: "shopee", floor: 40, typical: 90, tags: ["bemestar", "beleza"],
      note: "é uma pausa embrulhada, o que ninguém se dá sozinho" }),
  A({ id: "mochila-hidratacao", title: "Mochila leve para trilha", category: "ar-livre", query: "mochila trilha leve",
      store: "mercado_livre", floor: 90, typical: 200, tags: ["trilha", "viagem"],
      note: "é o item que decide se o passeio é confortável ou não" }),
  A({ id: "camiseta-time", title: "Camiseta do time", category: "esporte", query: "camisa time futebol oficial",
      store: "mercado_livre", floor: 90, typical: 220, tags: ["futebol"],
      note: "é identidade, não roupa — e isso não passa de moda" }),

  // ---- tecnologia e áudio ------------------------------------------
  A({ id: "fone-anc", title: "Fone bluetooth com cancelamento de ruído", category: "áudio", query: "fone bluetooth cancelamento ruído",
      store: "mercado_livre", floor: 120, typical: 280, tags: ["musica", "tecnologia", "series", "trabalho", "viagem"],
      note: "resolve trajeto, trabalho e treino com um objeto só" }),
  A({ id: "caixa-som", title: "Caixa de som bluetooth portátil", category: "áudio", query: "caixa som bluetooth portátil",
      store: "amazon_br", floor: 80, typical: 180, tags: ["musica", "praia", "casa"],
      note: "aparece em toda reunião de amigos depois que chega" }),
  A({ id: "powerbank", title: "Power bank de carga rápida", category: "tecnologia", query: "power bank 10000mah",
      store: "amazon_br", floor: 60, typical: 130, tags: ["tecnologia", "viagem", "trabalho"],
      note: "é o presente sem graça que vira o mais usado da lista" }),
  A({ id: "suporte-celular", title: "Suporte de celular articulado", category: "tecnologia", query: "suporte celular articulado mesa",
      store: "shopee", floor: 25, typical: 55, tags: ["tecnologia", "trabalho", "series"],
      note: "custa pouco e é usado literalmente todo dia" }),
  A({ id: "teclado-mecanico", title: "Teclado mecânico compacto", category: "tecnologia", query: "teclado mecânico compacto",
      store: "mercado_livre", floor: 150, typical: 320, tags: ["games", "tecnologia", "trabalho"],
      note: "é o upgrade que quem passa o dia digitando mais sente" }),
  A({ id: "gift-card-games", title: "Cartão-presente de loja de games", category: "games", query: "gift card jogos digital",
      store: "amazon_br", floor: 50, typical: 100, tags: ["games"], digital: true,
      note: "deixa a escolha do jogo com quem realmente sabe qual quer" }),
  A({ id: "mousepad-grande", title: "Mousepad grande de mesa", category: "games", query: "mousepad grande gamer",
      store: "shopee", floor: 30, typical: 65, tags: ["games", "trabalho", "tecnologia"],
      note: "arruma a mesa inteira por menos do que custa um lanche" }),
  A({ id: "ring-light", title: "Ring light com tripé", category: "tecnologia", query: "ring light tripé",
      store: "shopee", floor: 50, typical: 110, tags: ["fotografia", "tecnologia", "beleza"],
      note: "muda o resultado de qualquer foto ou chamada de vídeo" }),

  // ---- livros, papelaria, arte -------------------------------------
  A({ id: "livro-bolso", title: "Livro de bolso com marcador", category: "livros", query: "livro bolso best seller",
      store: "amazon_br", floor: 25, typical: 55, tags: ["leitura"],
      note: "ocupa a mesa de cabeceira por semanas" }),
  A({ id: "ereader", title: "Leitor de e-books", category: "livros", query: "kindle leitor ebook",
      store: "amazon_br", floor: 350, typical: 550, tags: ["leitura", "tecnologia", "viagem"],
      note: "é o presente que quem lê muito sempre adia comprar" }),
  A({ id: "caderno-capa-dura", title: "Caderno pautado com capa dura", category: "papelaria", query: "caderno capa dura pautado",
      store: "shopee", floor: 20, typical: 50, tags: ["estudo", "trabalho", "arte", "leitura"],
      note: "dura o ano inteiro e não depende de acertar tamanho" }),
  A({ id: "canetas-boas", title: "Estojo de canetas de qualidade", category: "papelaria", query: "estojo canetas coloridas",
      store: "shopee", floor: 30, typical: 70, tags: ["arte", "estudo", "trabalho"],
      note: "é o pequeno luxo diário que ninguém se permite" }),
  A({ id: "kit-pintura", title: "Kit de aquarela com pincéis", category: "arte", query: "kit aquarela pincéis",
      store: "shopee", floor: 40, typical: 95, tags: ["arte"],
      note: "é um convite a começar, e é isso que trava a maioria" }),
  A({ id: "kit-croche", title: "Kit de crochê com linhas", category: "arte", query: "kit crochê agulhas linha",
      store: "shopee", floor: 35, typical: 80, tags: ["arte"],
      note: "rende semanas de mãos ocupadas na frente da TV" }),
  A({ id: "marcador-livros", title: "Marcadores de página em metal", category: "papelaria", query: "marcador página metal",
      store: "shopee", floor: 15, typical: 35, tags: ["leitura"],
      note: "é pequeno de propósito: acompanha o presente principal" }),

  // ---- beleza e moda -----------------------------------------------
  A({ id: "kit-skincare", title: "Kit de skincare com hidratante e protetor", category: "beleza", query: "kit skincare hidratante protetor",
      store: "shopee", floor: 45, typical: 110, tags: ["beleza"],
      note: "é consumo recorrente: acaba e faz falta" }),
  A({ id: "perfume", title: "Perfume de assinatura", category: "beleza", query: "perfume feminino masculino",
      store: "magalu", floor: 90, typical: 220, tags: ["beleza", "moda"],
      note: "é lembrado toda vez que é usado, e isso é raro" }),
  A({ id: "secador-escova", title: "Escova secadora", category: "beleza", query: "escova secadora cabelo",
      store: "magalu", floor: 100, typical: 200, tags: ["beleza"],
      note: "economiza vinte minutos de manhã, todo dia" }),
  A({ id: "necessaire", title: "Necessaire de viagem compacta", category: "acessórios", query: "necessaire viagem compacta",
      store: "magalu", floor: 40, typical: 90, tags: ["viagem", "beleza", "moda"],
      note: "só se descobre que faltava na primeira viagem com ela" }),
  A({ id: "cachecol", title: "Cachecol ou echarpe de tricô", category: "moda", query: "cachecol tricô inverno",
      store: "shopee", floor: 35, typical: 80, tags: ["moda"],
      note: "não tem tamanho para errar, e isso importa muito" }),
  A({ id: "carteira-couro", title: "Carteira de couro slim", category: "acessórios", query: "carteira couro slim",
      store: "mercado_livre", floor: 50, typical: 120, tags: ["moda", "trabalho"],
      note: "fica no bolso todos os dias pelos próximos anos" }),
  A({ id: "oculos-sol", title: "Óculos de sol com proteção UV", category: "acessórios", query: "óculos sol proteção uv",
      store: "shopee", floor: 50, typical: 120, tags: ["moda", "praia", "viagem"],
      note: "é acessório e é proteção, o que justifica o gasto" }),
  A({ id: "relogio-classico", title: "Relógio de pulso clássico", category: "acessórios", query: "relógio pulso masculino feminino",
      store: "mercado_livre", floor: 120, typical: 280, tags: ["moda", "trabalho"],
      note: "é um presente que se percebe como escolhido, não como comprado" }),

  // ---- pets --------------------------------------------------------
  A({ id: "brinquedo-pet", title: "Brinquedo interativo para pet", category: "pet", query: "brinquedo interativo cachorro",
      store: "mercado_livre", floor: 30, typical: 70, tags: ["pets"],
      note: "o presente acaba sendo para os dois, e todo mundo sabe" }),
  A({ id: "cama-pet", title: "Cama confortável para pet", category: "pet", query: "cama pet cachorro gato",
      store: "magalu", floor: 60, typical: 140, tags: ["pets", "casa"],
      note: "tira o bicho do sofá sem briga nenhuma" }),
  A({ id: "coleira-personalizada", title: "Coleira com plaquinha gravada", category: "pet", query: "coleira personalizada plaquinha",
      store: "shopee", floor: 30, typical: 65, tags: ["pets"],
      note: "leva o nome dele, e é isso que faz o presente" }),

  // ---- viagem ------------------------------------------------------
  A({ id: "mala-cabine", title: "Mala de cabine com rodinhas", category: "viagem", query: "mala cabine rodinhas",
      store: "magalu", floor: 180, typical: 380, tags: ["viagem"],
      note: "é o item que se usa por dez anos e se lembra de quem deu" }),
  A({ id: "organizador-mala", title: "Organizadores de mala", category: "viagem", query: "organizador mala viagem kit",
      store: "shopee", floor: 35, typical: 75, tags: ["viagem", "organizacao"],
      note: "quem viaja muito reconhece o valor na primeira arrumação" }),
  A({ id: "travesseiro-pescoco", title: "Travesseiro de pescoço de viagem", category: "viagem", query: "travesseiro pescoço viagem",
      store: "amazon_br", floor: 40, typical: 85, tags: ["viagem"],
      note: "decide se as próximas seis horas de ônibus são suportáveis" }),

  // ---- infantil e bebê ---------------------------------------------
  A({ id: "brinquedo-montar", title: "Brinquedo de montar criativo", category: "infantil", query: "brinquedo montar blocos",
      store: "magalu", floor: 60, typical: 140, tags: ["infantil"], ages: ["0-12"],
      note: "ocupa horas e não precisa de tela nenhuma" }),
  A({ id: "livro-infantil", title: "Livro infantil ilustrado", category: "livros", query: "livro infantil ilustrado",
      store: "amazon_br", floor: 30, typical: 65, tags: ["infantil", "leitura"], ages: ["0-12"],
      note: "vira a leitura antes de dormir por meses" }),
  A({ id: "kit-bebe", title: "Kit enxoval de bebê", category: "bebê", query: "kit enxoval bebê algodão",
      store: "magalu", floor: 70, typical: 160, tags: ["bebe"],
      note: "é o que mais acaba e o que os pais menos lembram de repor" }),
  A({ id: "quebra-cabeca", title: "Quebra-cabeça de mil peças", category: "infantil", query: "quebra cabeça 1000 peças",
      store: "shopee", floor: 40, typical: 90, tags: ["infantil", "arte"],
      ages: ["13-17", "18-24", "25-34", "35-49", "50-64", "65+"],
      note: "junta a família na mesa por vários fins de semana" }),

  // ---- carro e ferramentas -----------------------------------------
  A({ id: "kit-ferramentas", title: "Kit de ferramentas domésticas", category: "ferramentas", query: "kit ferramentas casa completo",
      store: "mercado_livre", floor: 80, typical: 180, tags: ["carro", "casa"],
      note: "é o presente que se agradece na primeira prateleira torta" }),
  A({ id: "aspirador-carro", title: "Aspirador portátil para carro", category: "auto", query: "aspirador portátil carro",
      store: "magalu", floor: 90, typical: 190, tags: ["carro"],
      note: "resolve uma chatice semanal que ninguém quer pagar para resolver" }),
  A({ id: "suporte-veicular", title: "Suporte veicular para celular", category: "auto", query: "suporte celular carro",
      store: "shopee", floor: 25, typical: 55, tags: ["carro", "tecnologia"],
      note: "é barato e é usado em cada viagem, sem exceção" }),

  // ---- experiências et cadeaux « je ne sais pas » -------------------
  A({ id: "vale-presente", title: "Vale-presente de loja online", category: "vale-presente", query: "vale presente cartão presente",
      store: "amazon_br", floor: 30, typical: 100, tags: [], digital: true,
      note: "deixa a escolha final com quem recebe, e chega na hora" }),
  A({ id: "assinatura-streaming", title: "Assinatura de streaming ou música", category: "assinatura", query: "gift card streaming assinatura",
      store: "amazon_br", floor: 30, typical: 90, tags: ["series", "musica"], digital: true,
      note: "acompanha a pessoa todo mês em vez de um dia só" }),
  A({ id: "assinatura-livros", title: "Assinatura de livros digitais", category: "assinatura", query: "gift card livros digital",
      store: "amazon_br", floor: 40, typical: 100, tags: ["leitura"], digital: true,
      note: "renova sozinho o que ler em seguida" }),
  A({ id: "caixa-presente", title: "Cesta de presente montada", category: "gourmet", query: "cesta presente café da manhã",
      store: "mercado_livre", floor: 80, typical: 180, tags: ["doces", "cafe", "gourmet"],
      occasions: ["aniversario", "dia-das-maes", "dia-dos-pais", "namorados", "sem-motivo"],
      note: "chega pronta para entregar, sem precisar embrulhar nada" }),

  // ---- haut de gamme -----------------------------------------------
  // La tranche « R$ 300 ou mais » a besoin de vraie profondeur : sans
  // ça, le budget le plus rentable en commission tourne sur cinq idées.
  A({ id: "cafeteira-expresso", title: "Cafeteira expresso automática", category: "eletro", query: "cafeteira expresso automática",
      store: "magalu", floor: 350, typical: 650, tags: ["cafe", "cozinha"],
      note: "acaba com a fila da cafeteria pelos próximos anos" }),
  A({ id: "robo-aspirador", title: "Robô aspirador de pó", category: "eletro", query: "robô aspirador pó",
      store: "magalu", floor: 500, typical: 900, tags: ["casa", "organizacao"],
      note: "devolve uma tarefa inteira da semana para a pessoa" }),
  A({ id: "tablet", title: "Tablet para leitura e vídeo", category: "tecnologia", query: "tablet 10 polegadas",
      store: "magalu", floor: 500, typical: 950, tags: ["tecnologia", "leitura", "series"],
      note: "substitui três objetos de uma vez na mesa de cabeceira" }),
  A({ id: "cadeira-ergonomica", title: "Cadeira de escritório ergonômica", category: "móveis", query: "cadeira escritório ergonômica",
      store: "magalu", floor: 400, typical: 800, tags: ["trabalho", "bemestar"],
      note: "é o presente que as costas agradecem todos os dias" }),
  A({ id: "camera-instantanea", title: "Câmera instantânea com filme", category: "foto", query: "câmera instantânea filme",
      store: "amazon_br", floor: 300, typical: 500, tags: ["fotografia", "viagem"],
      note: "produz um objeto físico na hora, o que quase nada faz hoje" }),
  A({ id: "halteres-ajustaveis", title: "Kit de halteres ajustáveis", category: "esporte", query: "halteres ajustáveis kit",
      store: "mercado_livre", floor: 250, typical: 480, tags: ["academia"],
      note: "monta uma academia inteira num canto de dois palmos" }),
  A({ id: "churrasqueira", title: "Churrasqueira portátil", category: "gourmet", query: "churrasqueira portátil carvão",
      store: "mercado_livre", floor: 200, typical: 400, tags: ["gourmet", "cerveja", "casa"],
      note: "cria o motivo de juntar todo mundo, não só a refeição" }),
  A({ id: "violao", title: "Violão acústico para iniciante", category: "música", query: "violão acústico iniciante",
      store: "mercado_livre", floor: 350, typical: 600, tags: ["musica"],
      note: "é o presente que vira um hábito, não um objeto" }),
  A({ id: "cadeira-gamer", title: "Cadeira gamer com apoio lombar", category: "games", query: "cadeira gamer apoio lombar",
      store: "magalu", floor: 500, typical: 900, tags: ["games"],
      note: "muda as horas de jogo de um jeito que só quem joga entende" }),
  A({ id: "parafusadeira", title: "Parafusadeira sem fio", category: "ferramentas", query: "parafusadeira sem fio bateria",
      store: "mercado_livre", floor: 200, typical: 380, tags: ["carro", "casa"],
      note: "transforma o fim de semana de reformas num sábado normal" }),
  A({ id: "tenis-corrida", title: "Tênis de corrida com amortecimento", category: "esporte-calçado", query: "tênis corrida amortecimento",
      store: "mercado_livre", floor: 250, typical: 480, tags: ["corrida", "academia", "moda"],
      note: "é o único equipamento que muda mesmo o joelho no dia seguinte" }),
  A({ id: "maquina-costura", title: "Máquina de costura portátil", category: "artesanato", query: "máquina costura portátil",
      store: "magalu", floor: 350, typical: 650, tags: ["arte", "moda"],
      note: "abre um mundo inteiro para quem já faz as coisas à mão" }),
  A({ id: "jogo-panelas", title: "Jogo de panelas antiaderente", category: "cozinha-pro", query: "jogo panelas antiaderente",
      store: "magalu", floor: 250, typical: 500, tags: ["cozinha"],
      note: "é o presente de cozinha que se usa literalmente todo dia" }),
  A({ id: "kit-vinhos-premium", title: "Seleção de vinhos importados", category: "bebidas-pro", query: "kit vinhos importados presente",
      store: "mercado_livre", floor: 250, typical: 450, tags: ["vinho", "gourmet"],
      note: "vira várias noites, não uma só" }),
  A({ id: "massageador-pistola", title: "Pistola de massagem muscular", category: "bem-estar", query: "pistola massagem muscular",
      store: "mercado_livre", floor: 200, typical: 400, tags: ["academia", "bemestar", "corrida"],
      note: "resolve a dor do dia seguinte, que é o que faz desistir" }),
];
