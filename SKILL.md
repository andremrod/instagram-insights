---
name: instagram-insights
description: Analisa as métricas dos posts e Reels já publicados no Instagram do usuário para descobrir o que deu certo — qual tema, tipo de gancho, duração, horário, espaçamento entre posts e formato rende mais views, retenção, compartilhamentos e seguidores — e entrega gráficos (página Artifact) com dicas de melhoria e ideias de próximos vídeos baseadas nos números. Lê os dados pelo Claude in Chrome no Meta Business Suite (Insights → Conteúdo) da sessão logada, ou de um CSV exportado; casa cada Reels com o MP4 local para medir a retenção; compara com a rodada anterior. Use quando o usuário pedir para analisar o Instagram, ver métricas ou desempenho dos Reels/vídeos/posts, "o que deu certo", "qual tema funciona", melhores horários, por que um vídeo flopou ou bombou, ou dicas para crescer no Instagram com base nos próprios dados.
---

# Instagram Insights

Pasta das rodadas: `~/Documents/instagram-insights/runs/AAAA-MM-DD/`. Scripts em `scripts/` (só biblioteca padrão do Python 3.12+; `ffprobe` opcional para a duração dos vídeos).
Escreva tudo para o usuário em português simples. Nunca publique, edite, apague ou impulsione nada na conta: a skill só lê.

## 1. Coletar (Claude in Chrome, só leitura)
Carregue a skill `chrome-browser`. Se houver mais de um Chrome conectado, pergunte qual usar. Abra uma aba nova.

**Caminho principal: Meta Business Suite.** Abra `https://business.facebook.com/latest/insights/content`. Ele redireciona para a conta do Instagram ligada; se houver várias, confira o nome no topo. Para escolher o período, ponha `&time_range=%2522LAST_90D%2522` na URL que abriu (também existem `LAST_28D` e `LAST_7D`) ou use o seletor de datas. Depois:
1. Rode `collect/scroll_table.js` com `javascript_tool` para carregar todas as linhas.
2. Leia tudo com `get_page_text`. Cada post aparece assim: legenda, tipo (Reel), conta, "Turbinar", data ("Segunda, 9 de novembro 10:49") e as colunas na ordem do bloco "Colunas". `‑‑` significa sem dado.
3. Salve o texto como `runs/D/raw_page.txt`, a partir de "Colunas" até a última linha de post, ou monte `raw_mbs.json` (`{"collected_at","headers","rows":[{"cells":[...]}]}`).
   O `javascript_tool` corta respostas longas (cerca de 1 KB), então não tente devolver a tabela inteira por JS.
4. Leia também `.../insights/results?...&time_range=%2522LAST_28D%2522` (views, alcance, visitas ao perfil por dia) e anote seguidores. Salve em `runs/D/account.json` (formato livre, ex.: `{"last_28d": {"views": 7269, "reach": 5200, "profile_visits": 36}, "followers_note": "..."}`).

**Muitos posts (mais de ~60) ou grade virtualizada:** o botão "Exportar dados" → Instagram → nível "Post" gera um CSV com tudo. Baixar arquivo exige a permissão do usuário. Prefira pedir que ele mesmo exporte e diga o caminho. O parser aceita CSV em PT ou EN (`--monthfirst` para datas MM/DD).

**Não use** a API interna do instagram.com: ela devolve 429/404 e pode marcar a sessão. Não peça senha nem token.

## 2. Normalizar e marcar
```
S=~/.claude/skills/instagram-insights/scripts; D=~/Documents/instagram-insights/runs/AAAA-MM-DD
python3 $S/collect_parse.py --in $D/raw_page.txt [--in export.csv] --account <usuario> --collected-at <ISO da coleta> --out $D/posts.json
python3 $S/tag_posts.py --posts $D/posts.json --out $D/tags.json --videos "<pasta dos MP4>" [--keep <rodada anterior>/tags.json]
```
- `--videos`: para a série de história, a pasta onde ficam os MP4 finais. Os arquivos `*-raw.mp4` são ignorados. O casamento usa as palavras do nome da pasta e a data do arquivo. Confira a lista que o script imprime: cada post deve ter o MP4 certo.
- **Revise `tags.json`** e corrija o que for preciso: `theme`, `region`, `era`, `hook_type` (`?` significa não deduzido). Para um tema novo, acrescente palavras em `references/themes.json`. Características extras vão em `extra`, por exemplo `{"capa": "foto real", "skip_rate": 0.42}`: cada chave vira uma dimensão a mais. Marque `reviewed: true`.

## 3. Analisar
```
python3 $S/analyze.py --posts $D/posts.json --tags $D/tags.json --account $D/account.json [--previous <rodada anterior>/analysis.json] --out $D/analysis.json
```
Ele imprime os achados com o nível de confiança. Regras fixas:
- estouro = views ≥ 2× a mediana; flop = menos de 25% da mediana;
- flops ficam fora das comparações por grupo, porque não foram distribuídos;
- confiança pelo n: 5+ forte, 3–4 média, 2 fraca.

## 4. Interpretar (`notes.json`, formato no topo de `render_report.py`)
Leia `analysis.json` e `references/playbook.md`. Escreva:
- `headline`: uma frase verdadeira para todos os casos que cita. Confira cada "todos" e cada "nenhum" contra a tabela.
- `summary`: 2–4 frases.
- `tips`: 4–6 dicas. Cada uma com o número que a sustenta em `evidence`.
- `next_videos`: ideias tiradas dos estouros e dos temas que ainda não foram testados. Confira as pastas de vídeo: se houver vídeos prontos e não publicados, cite-os.
- `experiments`: o que testar, como e o que medir na próxima rodada.
- `caveats`: limites dos dados.

Não invente benchmark de mercado nem número. Com n pequeno, diga que é pista. Siga as memórias do usuário sobre os vídeos (duração, narrativa) quando a dica tocar nisso.

## 5. Entregar
1. `python3 $S/render_report.py --analysis $D/analysis.json --notes $D/notes.json --out $D/report.html`. Para abrir direto do disco, use `--standalone`.
2. Carregue `artifact-design` e publique `report.html` com a ferramenta Artifact (icon `chart`). Se já houver uma página das rodadas anteriores, publique na mesma URL (`url`), lendo-a antes.
3. Responda no chat com:
   - 3–4 achados principais, com números;
   - as 3 dicas de maior impacto;
   - o link da página.
4. Feche as abas que abriu.

## Testes
`python3 -m unittest discover -s ~/.claude/skills/instagram-insights/tests`
