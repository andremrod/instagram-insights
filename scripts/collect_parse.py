#!/usr/bin/env python3
"""Converte o que foi coletado em posts.json (formato único usado pelo resto da skill).

Entradas aceitas (detecta pelo conteúdo):
  1. Texto da página Insights → Conteúdo do Meta Business Suite, salvo do get_page_text (.txt)
  2. JSON gerado por collect/mbs_table.js ({"headers": [...], "rows": [{"cells": [...]}]})
  3. CSV exportado pelo Meta Business Suite / Instagram (PT ou EN; "Exportar dados" → Instagram → Post)

Uso:
  python3 collect_parse.py --in raw.txt [--in export.csv ...] --account <usuario> \
      --collected-at 2026-11-10T12:30 --out runs/D/posts.json
Vários --in são juntados; o mesmo post (mesma data+legenda) fica com a versão de maior número de views.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import dump_json, fold, parse_date, parse_duration, parse_number  # noqa: E402

# chave interna → apelidos de coluna (comparados com fold(); basta o cabeçalho COMEÇAR com o apelido)
COLUMNS = {
    "caption": ["titulo", "descricao", "legenda", "description", "caption", "title"],
    "published": ["data da publicacao", "horario de publicacao", "publish time", "data de publicacao", "date", "data"],
    "type": ["tipo de post", "tipo de midia", "post type", "media type", "tipo"],
    "permalink": ["link permanente", "permalink", "link"],
    "duration_s": ["duracao", "duration"],
    "views": ["visualizacoes", "views", "reproducoes", "plays"],
    "reach": ["alcance", "reach", "contas alcancadas", "accounts reached"],
    "viewers": ["visualizadores", "viewers"],
    "interactions": ["interacoes liquidas", "interacoes", "net interactions", "interactions"],
    "likes": ["curtidas e reacoes", "curtidas", "likes", "reactions"],
    "comments": ["comentarios", "comments"],
    "shares": ["compartilhamentos", "shares", "envios", "sends"],
    "saves": ["salvamentos", "saves"],
    "link_clicks": ["cliques no link", "link clicks"],
    "replies": ["respostas", "replies"],
    "follows": ["seguidores", "seguimentos", "follows", "new followers", "follows from post"],
    "watch_time_s": ["tempo de visualizacao", "tempo de reproducao", "watch time", "total watch time"],
    "avg_watch_s": ["tempo medio de reproducao", "tempo medio de visualizacao", "average watch time", "avg watch time"],
    "views_3s": ["visualizacoes de 3 segundos", "3-second views", "3 second views"],
    "skip_rate": ["taxa de pulos", "skip rate"],
    "earnings": ["ganhos", "estimated earnings", "approximate earnings"],
}
# ordem importa: apelidos mais específicos primeiro
MATCH_ORDER = ["avg_watch_s", "views_3s", "watch_time_s", "interactions", "link_clicks", "skip_rate", "earnings",
               "viewers", "views", "reach", "likes", "comments", "shares", "saves", "replies", "follows",
               "published", "type", "permalink", "duration_s", "caption"]
DURATION_KEYS = {"watch_time_s", "avg_watch_s", "duration_s"}
TEXT_KEYS = {"caption", "published", "type", "permalink"}

DATE_LINE = re.compile(
    r"^(segunda|terca|quarta|quinta|sexta|sabado|domingo|monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
    r"(-feira)?,? .*\d{1,2}:\d{2}", re.I)
TYPE_WORDS = {"reel", "reels", "post", "carrossel", "carousel", "imagem", "image", "foto", "photo", "video", "story", "stories"}
NOISE = {"turbinar", "boost", "abrir menu suspenso", "open dropdown", "​", "", "impulsionar"}

DEFAULT_HEADERS = ["Título", "Data da publicação", "Visualizações", "Alcance", "Visualizadores", "Interações líquidas",
                   "Curtidas e reações", "Comentários", "Compartilhamentos", "Salvamentos", "Cliques no link",
                   "Respostas", "Seguidores", "Tempo de visualização", "Tempo médio de reprodução do vídeo",
                   "Visualizações de 3 segundos", "Ganhos aproximados com anúncios in-stream"]


def map_header(h: str) -> str | None:
    f = fold(h)
    # MATCH_ORDER testa primeiro os nomes mais longos ("visualizacoes de 3 segundos" antes de "visualizacoes")
    for key in MATCH_ORDER:
        if any(f.startswith(a) for a in COLUMNS[key]):
            return key
    return None


def record_from(headers: list[str], cells: list[str], ref: datetime, dayfirst: bool, account: str | None) -> dict | None:
    rec: dict = {}
    for h, v in zip(headers, cells):
        key = map_header(h)
        if not key or key in rec:
            continue
        if key in TEXT_KEYS:
            rec[key] = (v or "").strip()
        elif key in DURATION_KEYS:
            rec[key] = parse_duration(v)
        else:
            rec[key] = parse_number(v)
    cap = rec.get("caption") or ""
    if "||" in cap:  # formato do mbs_table.js: legenda||tipo
        cap, rec["type"] = cap.split("||", 1)
    cap = re.sub(r"\s+(Reel|Post|Carrossel|Carousel|Story)\s+\S+\s+(Turbinar|Boost).*$", "", cap).strip()
    rec["caption"] = cap
    dt = parse_date(rec.pop("published", ""), ref, dayfirst)
    if dt is None or rec.get("views") is None and rec.get("reach") is None:
        return None
    rec["published_at"] = dt.isoformat(timespec="minutes")
    rec["type"] = normalize_type(rec.get("type") or ("reel" if rec.get("avg_watch_s") else "post"))
    rec["account"] = account
    rec["id"] = rec.get("permalink") and re.sub(r"\W+", "", rec["permalink"].rstrip("/").split("/")[-1]) or \
        hashlib.sha1((rec["published_at"] + cap[:60]).encode()).hexdigest()[:10]
    return rec


def normalize_type(t: str) -> str:
    f = fold(t)
    if "reel" in f or f in ("video", "ig_reel", "clips"):
        return "reel"
    if "carros" in f or "carousel" in f or "album" in f:
        return "carrossel"
    if "story" in f or "stories" in f:
        return "story"
    return "foto"


def parse_page_text(text: str, ref: datetime, dayfirst: bool, account: str | None) -> list[dict]:
    lines = [l.strip() for l in text.splitlines()]
    lines = [l for l in lines if l not in ("​",)]
    # cabeçalhos: o bloco depois de "Colunas"/"Columns" até a primeira legenda
    headers = DEFAULT_HEADERS
    try:
        start = next(i for i, l in enumerate(lines) if fold(l) in ("colunas", "columns")) + 1
        hdr = []
        for l in lines[start:start + 60]:
            if not l:
                continue
            if map_header(l) is None or len(l) > 70:
                break
            hdr.append(l)
        if len(hdr) >= 5:
            headers = hdr
    except StopIteration:
        pass
    n_values = len(headers) - 2
    out = []
    for i, l in enumerate(lines):
        if not DATE_LINE.match(fold(l)):
            continue
        # sobe até achar a legenda (pula conta, tipo, botões)
        j, ptype, cap = i - 1, None, None
        while j >= 0 and i - j < 10:
            f = fold(lines[j])
            if f in NOISE:
                j -= 1
                continue
            if f in TYPE_WORDS:
                ptype = lines[j]
            elif ptype and cap is None and len(lines[j]) > 20:
                cap = lines[j]
                break
            j -= 1
        vals, k = [], i + 1
        while len(vals) < n_values and k < len(lines):
            if lines[k]:
                vals.append(lines[k])
            k += 1
        rec = record_from(headers, [cap or "", l] + vals, ref, dayfirst, account)
        if rec:
            rec["type"] = normalize_type(ptype or rec["type"])
            out.append(rec)
    return out


def parse_csv(text: str, ref: datetime, dayfirst: bool, account: str | None) -> list[dict]:
    text = text.lstrip("﻿")
    dialect = csv.Sniffer().sniff(text[:4000], delimiters=",;\t")
    rows = list(csv.reader(io.StringIO(text), dialect))
    hi = next(i for i, r in enumerate(rows) if sum(map_header(c) is not None for c in r) >= 3)
    headers = rows[hi]
    out = []
    for r in rows[hi + 1:]:
        rec = record_from(headers, r, ref, dayfirst, account)
        if rec:
            out.append(rec)
    return out


def parse_any(path: Path, ref: datetime, dayfirst: bool, account: str | None) -> list[dict]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    head = text.lstrip()[:1]
    if head in "{[":
        import json
        data = json.loads(text)
        if isinstance(data, dict) and "rows" in data:
            ref2 = data.get("collected_at")
            if ref2:
                ref = datetime.fromisoformat(ref2.replace("Z", "+00:00")).replace(tzinfo=None)
            return [r for r in (record_from(data["headers"], row["cells"] if isinstance(row, dict) else row, ref,
                                            dayfirst, account) for row in data["rows"]) if r]
        raise SystemExit(f"{path}: JSON sem 'rows'")
    if path.suffix.lower() in (".csv", ".tsv") or text.count(",") + text.count(";") > text.count("\n") * 3 and "\n" in text[:3000] and "Colunas" not in text:
        return parse_csv(text, ref, dayfirst, account)
    return parse_page_text(text, ref, dayfirst, account)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="inputs", action="append", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--account")
    ap.add_argument("--collected-at", help="data da coleta (ISO). Usada para deduzir o ano quando a página não mostra")
    ap.add_argument("--monthfirst", action="store_true", help="datas MM/DD/AAAA (CSV em inglês)")
    a = ap.parse_args()
    ref = datetime.fromisoformat(a.collected_at) if a.collected_at else datetime.now()
    merged: dict[str, dict] = {}
    for p in a.inputs:
        for rec in parse_any(Path(p), ref, not a.monthfirst, a.account):
            key = rec["published_at"] + "|" + fold(rec["caption"])[:50]
            old = merged.get(key)
            if old is None or (rec.get("views") or 0) >= (old.get("views") or 0):
                if old:
                    rec = {**old, **{k: v for k, v in rec.items() if v is not None}}
                merged[key] = rec
    posts = sorted(merged.values(), key=lambda r: r["published_at"])
    dump_json({"account": a.account, "collected_at": ref.isoformat(timespec="minutes"), "sources": a.inputs,
               "posts": posts}, a.out)
    have = {k for p in posts for k, v in p.items() if v is not None}
    print(f"{len(posts)} posts → {a.out}")
    print("métricas presentes:", ", ".join(sorted(have - {"id", "caption", "account", "published_at", "type"})))
    if not posts:
        sys.exit("Nenhum post reconhecido. Confira se o texto/CSV é da tabela Insights → Conteúdo.")


if __name__ == "__main__":
    main()
