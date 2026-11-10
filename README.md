# Instagram Insights

[![tests](https://github.com/andremrod/instagram-insights/actions/workflows/tests.yml/badge.svg)](https://github.com/andremrod/instagram-insights/actions/workflows/tests.yml)

Descobre **o que deu certo nos seus Reels e posts do Instagram**: qual tema, tipo de abertura, duração, horário, espaçamento entre posts e formato trazem mais views, retenção, compartilhamentos e seguidores. O resultado é uma página com gráficos e dicas de melhoria, todas baseadas nos números da própria conta.

- **Lê os dados que você já tem.** Usa a tabela *Insights → Conteúdo* do Meta Business Suite (texto da página ou CSV exportado). Não precisa de API, token nem senha.
- **Mede a retenção de verdade.** Se você tiver os MP4 publicados, a skill acha o arquivo de cada Reels (pelo nome e pela data) e divide o tempo médio assistido pela duração.
- **Não engana com amostra pequena.** Usa mediana, trata à parte os estouros (≥2× a mediana) e os posts que não foram distribuídos (<25%), e mostra o nível de confiança de cada achado pelo número de posts.
- **Acompanha a evolução.** Compara com a rodada anterior e reaproveita as marcações já revisadas.
- **Só Python, biblioteca padrão.** `ffprobe` é opcional (só para a duração dos vídeos).
- **Funciona como skill do Claude Code.** O Claude coleta os dados no seu navegador (só leitura), marca os temas, escreve a interpretação e publica a página.

*English: a Claude Code skill and stdlib-only Python toolkit that reads your Instagram post metrics (Meta Business Suite content table or CSV export), tags each post (theme, hook type, era, duration, spacing…), finds what drives views, retention, shares and follows, and renders a self-contained HTML report with charts and data-backed tips. The report and texts are in Brazilian Portuguese.*

## Como funciona

```
coletar ─► collect_parse.py ─► posts.json
                                   │
            tag_posts.py ◄─────────┘  (+ MP4 locais para a duração)
                │
             tags.json  ◄── revisão (tema, época, gancho…)
                │
            analyze.py ─► analysis.json ─► render_report.py ─► report.html
                                ▲                ▲
                    rodada anterior        notes.json (interpretação)
```

| Etapa | O que faz |
|---|---|
| `collect/scroll_table.js` | Rola a tabela do Meta Business Suite até carregar todos os posts |
| `scripts/collect_parse.py` | Converte texto da página, CSV (PT/EN) ou JSON em `posts.json`: views, alcance, curtidas, comentários, compartilhamentos, salvamentos, seguidores, tempo assistido |
| `scripts/tag_posts.py` | Deduz da legenda o tipo de gancho (“Imagine…”, pergunta, data…), série/EP, época, região e tema (`references/themes.json`); casa cada post com o MP4 |
| `scripts/analyze.py` | Taxas por alcance, retenção, estouros e flops, grupos por dimensão com *lift*, posts publicados colados, correlação de Spearman, achados e dicas automáticas |
| `scripts/render_report.py` | Página HTML com KPIs, views por post, barras por dimensão, dispersões, correlações, tabela ordenável, tema claro/escuro e tooltips |

## Rodar à mão

Requer Python 3.12+.

```bash
git clone https://github.com/andremrod/instagram-insights.git
cd instagram-insights
D=runs/$(date +%F); mkdir -p $D

# 1. salve o texto da página Insights → Conteúdo em $D/raw_page.txt (ou exporte o CSV)
python3 scripts/collect_parse.py --in $D/raw_page.txt --account seu_usuario --out $D/posts.json
#    CSV em inglês (datas MM/DD): --in export.csv --monthfirst

# 2. marque os posts (com --videos, mede a retenção pelos MP4)
python3 scripts/tag_posts.py --posts $D/posts.json --out $D/tags.json --videos ~/Videos/reels
#    revise tags.json: tema, época, gancho. Campos em "extra" viram dimensões novas.

# 3. analise e gere a página
python3 scripts/analyze.py --posts $D/posts.json --tags $D/tags.json --out $D/analysis.json
python3 scripts/render_report.py --analysis $D/analysis.json --out $D/report.html --standalone
open $D/report.html
```

`notes.json` (opcional) acrescenta título, resumo, dicas, próximos vídeos e testes escritos por você ou pelo Claude. O formato está no topo de `render_report.py`.

`runs/` está no `.gitignore` porque guarda dados da sua conta.

## Usar como skill do Claude Code

```bash
git clone https://github.com/andremrod/instagram-insights.git ~/.claude/skills/instagram-insights
```

Peça algo como *“analisa meu Instagram e me diz o que deu certo”*. Com a extensão [Claude in Chrome](https://claude.com/chrome) conectada, o Claude:

1. abre o Meta Business Suite na sua sessão e lê a tabela de conteúdo (só leitura);
2. roda os scripts e revisa as marcações;
3. escreve a interpretação (cada dica cita o número que a sustenta);
4. publica a página e responde com os principais achados.

O passo a passo está em [`SKILL.md`](SKILL.md). Para o YouTube, veja [youtube-insights](https://github.com/andremrod/youtube-insights), que também compara o mesmo vídeo nas duas plataformas.

## O que a página mostra

- Views de cada post na ordem de publicação, com estouros e posts não distribuídos destacados
- Achados em texto com nível de confiança (forte, média, fraca)
- Dicas, próximos vídeos e testes para as próximas semanas
- Mediana de views por tema, gancho, época, duração, horário, dia, espaçamento, série, legenda e hashtags
- Tempo assistido × views e duração × views
- Correlação de cada característica com as views
- Tabela ordenável com todos os posts

## Limites

- Com poucos posts por grupo, os achados são pistas para testar, não regras.
- O Meta Business Suite não mostra a taxa de pulos dos primeiros segundos; se você tiver o número, anote em `tags.json → extra`.
- Fontes sobre como o Instagram distribui Reels: [`references/playbook.md`](references/playbook.md).

## Testes

```bash
python3 -m unittest discover -s tests -v
```

## Licença

[MIT](LICENSE)
