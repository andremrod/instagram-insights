# Como o Instagram distribui Reels (base para as dicas)

Atualizado em 2026-11-10. Atualize se tiver mais de 6 meses. Marque cada item como [OFICIAL] (falado pelo Instagram/Meta) ou [BLOG] (análise de terceiros).

## Sinais de ranking
- [OFICIAL] Adam Mosseri (jan/2025): os três sinais que mais pesam são **tempo assistido, curtidas e envios (sends)**. Ele indicou três números dos Insights: **tempo médio assistido, curtidas por alcance e envios por alcance**. Fonte: Social Media Today, https://www.socialmediatoday.com/news/instagram-shares-algorithm-2025/738034/
- [OFICIAL, citado por terceiros] Mosseri: "sends per reach" é o que mais se correlaciona com alcance, principalmente para quem não segue a conta.
- [BLOG] O "envio vale 3–5× uma curtida" é repetido, mas não tem fonte primária. Não use como número.

## Ferramentas
- [OFICIAL] Trial Reels (dez/2024): o Reels vai primeiro para quem não segue a conta e não aparece no perfil. Os insights saem depois de 24 h, e o vídeo pode ser liberado para os seguidores em 72 h. Serve para testar tema e abertura sem afetar o feed. Fontes: https://9to5mac.com/2024/12/10/instagrams-new-trial-reels-feature-lets-creators-test-content-with-non-followers e https://www.socialmediatoday.com/news/instagram-launches-trial-reels-for-audience-sampling/735136/

## Como a skill transforma isso em métricas
| Sinal | Campo em analysis.json |
|---|---|
| Tempo assistido | `avg_watch_s`, `retention` (= tempo médio ÷ duração) |
| Curtidas por alcance | `likes` ÷ `reach` (dentro de `eng_rate`) |
| Envios por alcance | `share_rate` (o Meta Business Suite junta envios por DM e compartilhamentos em "Compartilhamentos") |
| Conversão | `follows_per_1k` |

## Leitura dos dados de uma conta pequena
- Views de Reels têm cauda longa: use a **mediana**, não a média, e trate "estouro" (≥2× a mediana) à parte.
- Post com views < 25% da mediana quase sempre **não foi distribuído** (por exemplo, publicado colado em outro). Ele não diz nada sobre o tema e fica fora das comparações.
- Com menos de 3 posts por grupo, é pista para testar, não regra. Sempre diga o n.
- Toda dica precisa citar o número que a sustenta. Nada de "poste às 19h" sem dado da própria conta.
