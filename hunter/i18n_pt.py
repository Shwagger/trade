"""Portuguese playbooks: the parts of the message a Brazilian buyer reads.

The English playbook in ``playbook.py`` stays the source of truth for prices,
delivery times and keywords. What is translated here is only what ends up in
front of the client: the scope bullets, the free proof, and the qualifying
question. Keeping them in a separate file means adding French later is a copy
of this file, not a rewrite of the catalogue.

Written in Brazilian Portuguese, in the register a small business owner
actually uses - not textbook Portuguese.
"""

from __future__ import annotations

PT: dict[str, dict] = {
    "automation": {
        "scope": ("mapeio os passos manuais de hoje em um fluxo automático",
                  "monto e conecto tudo de ponta a ponta (formulário -> lógica -> destino -> aviso)",
                  "entrego um Loom de 3 minutos + o fluxo rodando na sua própria conta"),
        "proof": "um diagrama de uma tela com o fluxo exato, pra você ver o que está comprando",
        "question": "Em quais ferramentas os dados precisam cair, e quem precisa ser avisado?",
    },
    "ai_agent": {
        "scope": ("defino as perguntas que o agente tem que responder e as que ele tem que recusar",
                  "construo em cima dos seus dados, com prompt testado e limites claros",
                  "coloco no ar onde seus clientes já estão (site, WhatsApp, Slack) com log de uso"),
        "proof": "o agente respondendo três perguntas reais suas, em uma gravação de tela",
        "question": "Quais são as três perguntas que seus clientes mais fazem, com as palavras deles?",
    },
    "scraping_data": {
        "scope": ("combinamos antes as colunas exatas e as páginas de origem",
                  "rodo a extração com deduplicação e checagem de validade em cada linha",
                  "entrego um CSV/Planilha limpo + o script, pra você rodar de novo sozinho"),
        "proof": "as 20 primeiras linhas, pra você conferir a qualidade por conta própria",
        "question": "Quais colunas você realmente usa quando o arquivo chega na sua mão?",
    },
    "landing_page": {
        "scope": ("uma página escrita em volta de uma única ação (o texto está incluso)",
                  "responsiva, no ar no seu domínio, carregando em menos de 2 segundos",
                  "formulário e analytics ligados, pra você ver se converte de verdade"),
        "proof": "o título e a primeira dobra, escritos antes de você se comprometer",
        "question": "Qual é a única ação que o visitante precisa fazer nessa página?",
    },
    "web_dev": {
        "scope": ("primeiro reproduzo o problema no seu código e te mostro a causa",
                  "corrijo com um teste que falha antes e passa depois",
                  "entrego um pull request que você consegue ler, não um zip"),
        "proof": "um diagnóstico escrito da causa provável, a partir do erro que você já tem",
        "question": "Consegue me dar acesso ao repositório (ou o log do erro) antes de eu fechar o preço?",
    },
    "content": {
        "scope": ("um texto pesquisado contra os seus concorrentes reais, sem enrolação",
                  "escrito na sua voz, a partir de dois exemplos que você me manda",
                  "entregue no seu CMS ou em doc limpo, com a meta description"),
        "proof": "o roteiro e o primeiro parágrafo, de graça",
        "question": "Me manda dois textos com a voz que você gosta - quem é o leitor?",
    },
    "video": {
        "scope": ("corte pensado em retenção: gancho nos 3 primeiros segundos, sem tempo morto",
                  "legenda queimada, som nivelado, dois formatos (9:16 e 16:9)",
                  "uma rodada de ajustes inclusa"),
        "proof": "os primeiros 15 segundos, já editados",
        "question": "Qual é o trecho do seu material que não pode ficar de fora?",
    },
    "design": {
        "scope": ("três direções diferentes, não cinquenta variações da mesma ideia",
                  "arquivos finais em todos os formatos que você vai precisar (svg, png, favicon)",
                  "uma rodada de ajuste na direção escolhida"),
        "proof": "um rascunho de uma direção",
        "question": "Cita uma marca com a qual você quer ser confundido visualmente.",
    },
    "research": {
        "scope": ("uma pergunta definida com formato de resposta definido, combinado antes",
                  "todo achado com a fonte junto - nenhuma afirmação solta",
                  "um resumo de uma página pra decisão, em cima do material bruto"),
        "proof": "a lista de fontes que eu usaria, mandada antes",
        "question": "Que decisão você vai tomar com essa pesquisa?",
    },
    "deck": {
        "scope": ("história primeiro: uma mensagem por slide, na ordem em que se lê",
                  "slides desenhados no seu template, editáveis, não imagem achatada",
                  "uma nota de apresentação embaixo de cada slide"),
        "proof": "o roteiro slide a slide, escrito",
        "question": "Quem está na sala quando esse deck é apresentado, e o que decide?",
    },
    "spreadsheet": {
        "scope": ("o cálculo funcionando, no seu arquivo real",
                  "sem passo manual sobrando: atualiza quando os dados mudam",
                  "uma nota explicando cada fórmula, pra você não ficar dependente"),
        "proof": "a fórmula resolvendo a sua linha de exemplo, já na resposta",
        "question": "Consegue mandar uma cópia anonimizada com 10 linhas reais?",
    },
    "seo": {
        "scope": ("varredura do site com os problemas ordenados por impacto em tráfego",
                  "as 20 palavras-chave que dá pra ganhar neste trimestre",
                  "uma lista de correções que seu dev executa sem mim"),
        "proof": "os três maiores problemas, achados e enviados antes",
        "question": "Qual página você mais quer rankeando, e para qual busca?",
    },
    "other": {
        "scope": ("escopo combinado por escrito antes de qualquer coisa começar",
                  "uma entrega, um prazo, um preço",
                  "uma rodada de ajustes inclusa"),
        "proof": "um plano escrito de como eu faria",
        "question": "O que significa 'pronto' pra você?",
    },
}
