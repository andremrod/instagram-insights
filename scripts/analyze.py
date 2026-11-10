#!/usr/bin/env python3
"""Cruza métricas (posts.json) com características (tags.json) e gera analysis.json.

O que calcula:
  • por post: taxas sobre o alcance (engajamento, compartilhamento, salvamento, comentário, seguidores
    por mil), retenção (tempo médio ÷ duração), views por pessoa alcançada, distância para o post vizinho
  • "estouro" = views ≥ 2× a mediana da conta; "flop" = views < 25% da mediana
  • por dimensão (tema, gancho, época, região, duração, horário, dia, espaçamento, série, legenda,
    hashtags): n, mediana de views, taxa de estouro, mediana das taxas e o "lift" sobre a mediana geral
  • correlação de Spearman entre cada número e as views
  • achados em texto com o nível de confiança (pela quantidade de posts) e dicas automáticas

Uso:
  python3 analyze.py --posts runs/D/posts.json --tags runs/D/tags.json [--account runs/D/account.json] \
      [--previous runs/ANTERIOR/analysis.json] --out runs/D/analysis.json
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import WEEKDAYS_PT, dump_json, load_json, mean, median, safe_div, spearman  # noqa: E402

HIT_X = 2.0      # views ≥ 2× mediana = estouro
FLOP_X = 0.25    # views < 25% da mediana = flop
CLUSTER_MIN = 30  # posts a menos de 30 min um do outro = "publicados juntos"

DIMENSIONS = [
    ("theme", "Tema"),
    ("hook_type", "Tipo de gancho (1ª frase)"),
    ("era", "Época"),
    ("region", "Região"),
    ("duration_bucket", "Duração do vídeo"),
    ("spacing", "Espaçamento entre posts"),
    ("daypart", "Horário"),
    ("weekday", "Dia da semana"),
    ("series", "Série (EP.)"),
    ("caption_bucket", "Tamanho da legenda"),
    ("hashtag_bucket", "Hashtags"),
    ("type", "Formato"),
]


def bucket_duration(d):
    if not d:
        return None
    if d < 60:
        return "até 60 s"
    if d < 80:
        return "60–79 s"
    if d < 90:
        return "80–89 s"
    if d < 100:
        return "90–99 s"
    return "100 s ou mais"


def bucket_daypart(h):
    return "manhã (6–12h)" if 6 <= h < 12 else "tarde (12–18h)" if 12 <= h < 18 else "noite (18–24h)" if h >= 18 else "madrugada"


def bucket_caption(n):
    return "até 150 caracteres" if n <= 150 else "151–250" if n <= 250 else "mais de 250"


def bucket_hashtags(n):
    return "0–5" if n <= 5 else "6–10" if n <= 10 else "11–15" if n <= 15 else "16 ou mais"


def enrich(posts: list[dict], tags: dict) -> list[dict]:
    rows = []
    times = sorted(datetime.fromisoformat(p["published_at"]) for p in posts)
    for p in posts:
        t = tags.get(p["id"], {})
        pub = datetime.fromisoformat(p["published_at"])
        reach = p.get("reach") or p.get("views")
        eng = sum(p.get(k) or 0 for k in ("likes", "comments", "shares", "saves"))
        dur = t.get("duration_s") or p.get("duration_s")
        others = [x for x in times if x != pub]
        gap_min = min((abs((x - pub).total_seconds()) / 60 for x in others), default=None)
        prev = [x for x in others if x < pub]
        same_day = sum(1 for x in times if x.date() == pub.date())
        r = {
            **{k: p.get(k) for k in ("id", "caption", "published_at", "type", "views", "reach", "likes", "comments",
                                     "shares", "saves", "follows", "watch_time_s", "avg_watch_s", "views_3s",
                                     "interactions", "link_clicks")},
            "hook": t.get("hook"),
            "theme": t.get("theme"), "hook_type": t.get("hook_type"), "era": t.get("era"),
            "region": t.get("region"), "series": "EP. de série" if t.get("series_ep") else "avulso",
            "duration_s": dur,
            "duration_bucket": bucket_duration(dur),
            "daypart": bucket_daypart(pub.hour), "hour": pub.hour, "weekday": WEEKDAYS_PT[pub.weekday()],
            "posts_same_day": same_day,
            "gap_min": round(gap_min, 1) if gap_min is not None else None,
            "gap_prev_h": round((pub - max(prev)).total_seconds() / 3600, 2) if prev else None,
            "spacing": ("publicado junto (<30 min de outro)" if gap_min is not None and gap_min < CLUSTER_MIN
                        else "sozinho (≥30 min)"),
            "caption_chars": t.get("caption_chars"), "hashtags": t.get("hashtags"),
            "caption_bucket": bucket_caption(t.get("caption_chars") or 0),
            "hashtag_bucket": bucket_hashtags(t.get("hashtags") or 0),
            "extra": t.get("extra") or {},
            "engagements": eng,
            "eng_rate": safe_div(eng, reach),
            "share_rate": safe_div(p.get("shares"), reach),
            "save_rate": safe_div(p.get("saves"), reach),
            "comment_rate": safe_div(p.get("comments"), reach),
            "follows_per_1k": safe_div((p.get("follows") or 0) * 1000, reach) if p.get("follows") is not None else None,
            "views_per_reach": safe_div(p.get("views"), p.get("reach")),
            "retention": safe_div(p.get("avg_watch_s"), dur) if p.get("avg_watch_s") and dur else None,
            "hold_3s": safe_div(p.get("views_3s"), p.get("views")),
        }
        for k, v in (t.get("extra") or {}).items():
            r[f"x_{k}"] = v
        rows.append(r)
    rows.sort(key=lambda r: r["published_at"])
    for i, r in enumerate(rows, 1):
        r["order"] = i
    return rows


def group(rows, key, overall_med):
    groups: dict = {}
    for r in rows:
        v = r.get(key)
        if v in (None, "?", ""):
            continue
        groups.setdefault(v, []).append(r)
    out = []
    for name, rs in groups.items():
        med = median([r["views"] for r in rs])
        out.append({
            "group": name, "n": len(rs),
            "median_views": med, "mean_views": round(mean([r["views"] for r in rs]) or 0, 1),
            "total_views": sum(r["views"] or 0 for r in rs),
            "hit_rate": sum(1 for r in rs if r["hit"]) / len(rs),
            "flop_rate": sum(1 for r in rs if r["flop"]) / len(rs),
            "lift": round(med / overall_med, 2) if med is not None and overall_med else None,
            "median_eng_rate": median([r["eng_rate"] for r in rs]),
            "median_share_save_rate": median([(r["share_rate"] or 0) + (r["save_rate"] or 0) for r in rs]),
            "median_follows_per_1k": median([r["follows_per_1k"] for r in rs]),
            "median_retention": median([r["retention"] for r in rs]),
            "median_avg_watch_s": median([r["avg_watch_s"] for r in rs]),
            "post_ids": [r["id"] for r in rs],
        })
    out.sort(key=lambda g: (-(g["median_views"] or 0), -g["n"]))
    return out


def confidence(n_a, n_b=None):
    n = min(n_a, n_b) if n_b is not None else n_a
    return "forte" if n >= 5 else "média" if n >= 3 else "fraca"


def fmt_pct(x):
    return "—" if x is None else f"{x * 100:.1f}%".replace(".", ",")


def fmt_x(x):
    return "—" if x is None else f"{x:.1f}×".replace(".", ",").replace(",0×", "×")


def fmt_int(x):
    return "—" if x is None else f"{x:,.0f}".replace(",", ".")


def findings_and_tips(rows, dims, overall_med, summary):
    F, T = [], []
    hits = [r for r in rows if r["hit"]]
    flops = [r for r in rows if r["flop"]]

    # 1. espaçamento
    together = [r for r in rows if r["spacing"].startswith("publicado junto")]
    alone = [r for r in rows if not r["spacing"].startswith("publicado junto")]
    if together and alone:
        clusters, cur = [], []
        for r in sorted(rows, key=lambda r: r["published_at"]):  # encadeia posts a < CLUSTER_MIN do anterior
            if cur and (datetime.fromisoformat(r["published_at"]) -
                        datetime.fromisoformat(cur[-1]["published_at"])).total_seconds() < CLUSTER_MIN * 60:
                cur.append(r)
            else:
                if len(cur) > 1:
                    clusters.append(cur)
                cur = [r]
        if len(cur) > 1:
            clusters.append(cur)
        losers = [min(c, key=lambda x: x["views"] or 0) for c in clusters]
        winners = [max(c, key=lambda x: x["views"] or 0) for c in clusters]
        lopsided = sum(1 for w, l in zip(winners, losers) if (w["views"] or 0) >= 3 * max(1, l["views"] or 0))
        flop_in = [r for r in flops if r["spacing"].startswith("publicado junto")]
        F.append({
            "id": "spacing", "title": "Publicar dois Reels colados divide o alcance",
            "text": (f"{len(clusters)} vezes você publicou 2+ posts com menos de {CLUSTER_MIN} min de diferença. "
                     f"Em {lopsided} desses grupos um vídeo levou quase tudo (3× ou mais que o outro): o mais forte de cada grupo "
                     f"teve mediana de {fmt_int(median([w['views'] for w in winners]))} views e o mais fraco, "
                     f"{fmt_int(median([l['views'] for l in losers]))}. Posts publicados sozinhos: mediana de "
                     f"{fmt_int(median([r['views'] for r in alone]))}. "
                     + (f"{len(flop_in)} dos {len(flops)} flops (menos de {int(FLOP_X*100)}% da mediana) foram publicados colados em outro."
                        if flops else "")),
            "confidence": confidence(len(losers), len(alone)),
            "evidence": [x["id"] for c in clusters for x in c],
        })
        if flop_in or (median([l["views"] for l in losers]) or 0) < (median([r["views"] for r in alone]) or 0):
            T.append({"priority": 1, "title": "Um Reels por janela de pelo menos 3–4 horas",
                      "text": "Quando dois vídeos saem juntos, o Instagram testa os dois com o mesmo público inicial e um deles "
                              "fica sem empurrão. Agende os vídeos com horas de intervalo (ou um por dia) em vez de publicar em sequência.",
                      "based_on": "spacing"})

    # 2. dimensões: melhor e pior grupo com pelo menos 2 posts
    for key, label in DIMENSIONS:
        gs = [g for g in dims.get(key, []) if g["n"] >= 2]
        if len(gs) < 2 or key == "spacing":
            continue
        best, worst = gs[0], gs[-1]
        if not best["median_views"] or not worst["median_views"] or best["median_views"] < worst["median_views"] * 1.3:
            continue
        F.append({
            "id": f"dim_{key}", "title": f"{label}: “{best['group']}” rende mais",
            "text": (f"Mediana de {fmt_int(best['median_views'])} views em {best['n']} posts "
                     f"({fmt_x(best['lift'])} a mediana da conta; {fmt_pct(best['hit_rate'])} viraram estouro), "
                     f"contra {fmt_int(worst['median_views'])} em “{worst['group']}” ({worst['n']} posts)."
                     + (" Poucos posts por grupo: trate como pista para testar, não como regra." if min(best["n"], worst["n"]) < 3 else "")),
            "confidence": confidence(best["n"], worst["n"]),
            "evidence": best["post_ids"],
        })

    # 3. o que os estouros têm em comum
    if hits:
        common = []
        for key, label in DIMENSIONS:
            vals = [h.get(key) for h in hits if h.get(key) not in (None, "?")]
            if not vals:
                continue
            top = max(set(vals), key=vals.count)
            share_hits = vals.count(top) / len(hits)
            base = sum(1 for r in rows if r.get(key) == top) / len(rows)
            if share_hits >= 0.75 and share_hits > base + 0.15:
                common.append(f"{label.lower()} = {top} ({vals.count(top)}/{len(hits)} estouros; {fmt_pct(base)} dos posts)")
        F.append({
            "id": "hits", "title": f"{len(hits)} estouros (≥{HIT_X:.0f}× a mediana) concentram {fmt_pct(sum(h['views'] for h in hits) / max(1, summary['total_views']))} das views",
            "text": ("Em comum: " + "; ".join(common) + ".") if common else
                    "Os estouros não dividem um mesmo tema, gancho ou horário: o assunto em si (e o empurrão inicial) pesou mais que o formato.",
            "confidence": confidence(len(hits)), "evidence": [h["id"] for h in hits],
        })

    # 4. retenção
    ret = [r for r in rows if r["retention"] is not None]
    if len(ret) >= 5:
        rho_d = spearman([r["duration_s"] for r in ret], [r["retention"] for r in ret])
        rho_v = spearman([r["avg_watch_s"] for r in ret], [r["views"] for r in ret])
        med_ret = median([r["retention"] for r in ret])
        hit_watch = median([r["avg_watch_s"] for r in ret if r["hit"]])
        rest_watch = median([r["avg_watch_s"] for r in ret if not r["hit"]])
        F.append({
            "id": "retention", "title": f"As pessoas assistem em média {fmt_pct(med_ret)} de cada vídeo",
            "text": (f"Tempo médio assistido: {fmt_int(median([r['avg_watch_s'] for r in ret]))} s "
                     f"para vídeos de {fmt_int(median([r['duration_s'] for r in ret]))} s. "
                     + (f"Nos estouros, {fmt_int(hit_watch)} s; nos demais, {fmt_int(rest_watch)} s. " if hit_watch else "")
                     + (f"Correlação duração × retenção: {rho_d:+.2f} (negativa = vídeo mais longo perde proporção). ".replace(".", ",", 1) if rho_d is not None else "")
                     + (f"Correlação tempo assistido × views: {rho_v:+.2f}".replace(".", ",") + "." if rho_v is not None else "")),
            "confidence": confidence(len(ret)), "evidence": [],
        })
        if med_ret is not None and med_ret < 0.5:
            T.append({"priority": 2, "title": "Segurar os primeiros segundos e encurtar",
                      "text": f"Com retenção perto de {fmt_pct(med_ret)}, a maioria sai antes da metade. Teste versões de 45–60 s "
                              "com uma ideia só, abertura que já mostra o conflito na 1ª frase e corte de cenas de contexto. "
                              "Compare na próxima rodada a retenção e o tempo médio assistido.",
                      "based_on": "retention"})

    # 5. conversão em seguidores e compartilhamentos
    fol = [r for r in rows if r["follows"]]
    if fol:
        best = sorted(fol, key=lambda r: -(r["follows"] or 0))[:3]
        F.append({
            "id": "follows", "title": f"{fmt_int(sum(r['follows'] for r in rows if r['follows']))} seguidores vieram de {len(fol)} posts",
            "text": "Mais seguidores: " + "; ".join(f"“{(r['hook'] or r['caption'] or '')[:60]}…” ({fmt_int(r['follows'])}, "
                                                    f"{r['follows_per_1k']:.1f} por mil alcançados)".replace(".", ",", 1) for r in best) + ".",
            "confidence": confidence(len(fol)), "evidence": [r["id"] for r in best],
        })
    shares = sum(r["shares"] or 0 for r in rows)
    saves = sum(r["saves"] or 0 for r in rows)
    reach = sum(r["reach"] or 0 for r in rows)
    if reach:
        F.append({
            "id": "share_save", "title": f"Compartilhamentos e salvamentos: {fmt_pct((shares + saves) / reach)} do alcance",
            "text": (f"{fmt_int(shares)} compartilhamentos e {fmt_int(saves)} salvamentos para {fmt_int(reach)} contas alcançadas "
                     f"(soma de todos os posts). Envios por DM são um dos sinais que mais pesam no alcance de Reels para quem ainda não segue a conta."),
            "confidence": "média", "evidence": [],
        })
        if (shares + saves) / reach < 0.01:
            T.append({"priority": 2, "title": "Dar um motivo para enviar e salvar",
                      "text": "Feche o vídeo com uma frase que a pessoa queira mandar para alguém (“manda pra quem acha que…”) "
                              "ou com um dado que vale guardar. Séries numeradas (EP. 1, 2, 3) também puxam salvamento.",
                      "based_on": "share_save"})

    # 6. correlações numéricas
    corr = {}
    for k in ("avg_watch_s", "retention", "duration_s", "caption_chars", "hashtags", "hour", "gap_min", "gap_prev_h", "order"):
        rho = spearman([r[k] for r in rows], [r["views"] for r in rows])
        if rho is not None:
            corr[k] = rho
    summary["correlations_with_views"] = corr

    if flops:
        F.append({
            "id": "flops", "title": f"{len(flops)} posts quase não foram distribuídos",
            "text": "Views abaixo de 25% da mediana: " + "; ".join(
                f"“{(r['hook'] or '')[:50]}…” ({fmt_int(r['views'])} views, {r['spacing'].split(' (')[0]}, {r['gap_min']:.0f} min do vizinho)"
                for r in flops) + ".",
            "confidence": confidence(len(flops)), "evidence": [r["id"] for r in flops],
        })
        T.append({"priority": 1, "title": "Republicar os vídeos que não foram distribuídos",
                  "text": "Os flops não chegaram a ser testados (alcance perto de zero), então não dizem nada sobre o tema. "
                          "Publique de novo em outro dia, sozinhos, ou como Reels de teste (Trial Reels) para não-seguidores.",
                  "based_on": "flops"})

    T.append({"priority": 3, "title": "Medir os 3 primeiros segundos",
              "text": "A tabela do Meta Business Suite não mostra quantos saem nos primeiros segundos. Se os Insights do Reels "
                      "no app mostrarem a taxa de pulos (skip rate) ou a curva de retenção, anote o número em tags.json → "
                      "extra.skip_rate. Assim a próxima rodada diz qual abertura segura mais.",
              "based_on": "data_gap"} if not any(r["views_3s"] or r["extra"].get("skip_rate") for r in rows) else
             {"priority": 3, "title": "Abertura", "text": "Compare a taxa de pulos por tipo de gancho.", "based_on": "hold"})
    T.sort(key=lambda t: t["priority"])
    return F, T


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--posts", required=True)
    ap.add_argument("--tags", required=True)
    ap.add_argument("--account")
    ap.add_argument("--previous")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    pdata = load_json(a.posts)
    posts = [p for p in pdata["posts"] if p.get("views") is not None]
    tags = {t["id"]: t for t in load_json(a.tags)["tags"]}
    rows = enrich(posts, tags)
    overall_med = median([r["views"] for r in rows])
    for r in rows:
        r["hit"] = bool(overall_med and r["views"] >= HIT_X * overall_med)
        r["flop"] = bool(overall_med and r["views"] < FLOP_X * overall_med)
        r["lift"] = round(r["views"] / overall_med, 2) if overall_med else None

    summary = {
        "posts": len(rows), "first": rows[0]["published_at"] if rows else None, "last": rows[-1]["published_at"] if rows else None,
        "total_views": sum(r["views"] or 0 for r in rows), "total_reach": sum(r["reach"] or 0 for r in rows),
        "median_views": overall_med, "mean_views": round(mean([r["views"] for r in rows]) or 0, 1),
        "median_reach": median([r["reach"] for r in rows]),
        "median_eng_rate": median([r["eng_rate"] for r in rows]),
        "median_retention": median([r["retention"] for r in rows]),
        "median_avg_watch_s": median([r["avg_watch_s"] for r in rows]),
        "total_follows": sum(r["follows"] or 0 for r in rows),
        "total_shares": sum(r["shares"] or 0 for r in rows), "total_saves": sum(r["saves"] or 0 for r in rows),
        "total_watch_h": round(sum(r["watch_time_s"] or 0 for r in rows) / 3600, 1),
        "hits": sum(r["hit"] for r in rows), "flops": sum(r["flop"] for r in rows),
        "hit_rule": f"views ≥ {HIT_X:.0f}× mediana", "flop_rule": f"views < {int(FLOP_X * 100)}% da mediana",
    }
    # Os flops não chegaram a ser distribuídos (alcance ~0): dizem algo sobre a publicação, não sobre o conteúdo.
    # Por isso as comparações por tema/gancho/duração usam só os posts distribuídos. "spacing" usa todos.
    distributed = [r for r in rows if not r["flop"]] if len(rows) - summary["flops"] >= 5 else rows
    dims = {key: group(rows if key == "spacing" else distributed, key, overall_med) for key, _ in DIMENSIONS}
    extra_keys = sorted({k for r in rows for k in r if k.startswith("x_")})
    for k in extra_keys:
        dims[k] = group(distributed, k, overall_med)
    summary["dimension_basis"] = (f"{len(distributed)} posts distribuídos (sem os {summary['flops']} flops)"
                                  if len(distributed) < len(rows) else f"todos os {len(rows)} posts")
    findings, tips = findings_and_tips(rows, dims, overall_med, summary)

    out = {"account": pdata.get("account"), "collected_at": pdata.get("collected_at"), "summary": summary,
           "dimension_labels": dict(DIMENSIONS) | {k: k[2:] for k in extra_keys},
           "dimensions": dims, "posts": rows, "findings": findings, "auto_tips": tips}
    if a.account and Path(a.account).exists():
        out["account_stats"] = load_json(a.account)
    if a.previous and Path(a.previous).exists():
        prev = load_json(a.previous)
        pv = {p["id"]: p for p in prev["posts"]}
        out["previous"] = {
            "collected_at": prev.get("collected_at"), "summary": prev["summary"],
            "post_growth": {r["id"]: (r["views"] or 0) - (pv[r["id"]]["views"] or 0) for r in rows if r["id"] in pv},
            "new_posts": [r["id"] for r in rows if r["id"] not in pv],
        }
    dump_json(out, a.out)
    s = summary
    print(f"{s['posts']} posts | views: total {s['total_views']:.0f}, mediana {s['median_views']:.0f} | "
          f"estouros {s['hits']} | flops {s['flops']} → {a.out}")
    for f in findings:
        print(f" • [{f['confidence']}] {f['title']}\n     {f['text']}")


if __name__ == "__main__":
    main()
