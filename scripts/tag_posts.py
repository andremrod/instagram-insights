#!/usr/bin/env python3
"""Gera tags.json: as características de cada post que a análise cruza com as métricas.

Preenche sozinho o que dá para tirar da legenda (tipo de gancho, série/EP, hashtags, tamanho, época,
região, tema pelo dicionário references/themes.json) e, com --videos, a duração de cada vídeo
(ffprobe nos MP4 da pasta, casados por nome e data). Depois o Claude REVISA tags.json: corrige o
tema, preenche o que ficou "?" e pode acrescentar campos livres em "extra" (ex.: "capa": "foto real").

Uso:
  python3 tag_posts.py --posts runs/D/posts.json --out runs/D/tags.json \
      [--videos "<pasta dos MP4>"] [--themes references/themes.json] [--keep runs/D-1/tags.json]
--keep reaproveita as tags revisadas de uma rodada anterior (mesmo id de post).
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import dump_json, fold, load_json  # noqa: E402

SKILL = Path(__file__).resolve().parent.parent


def split_caption(caption: str) -> tuple[str, list[str]]:
    tags = re.findall(r"#(\w+)", caption)
    text = re.sub(r"#\w+", "", caption).strip()
    return re.sub(r"\s+", " ", text), tags


def first_sentence(text: str) -> str:
    t = re.sub(r"^EP\.?\s*\d+\s*", "", text, flags=re.I).strip()
    # título em CAIXA ALTA antes do texto ("A NUVEM DE GÁS ... | PRIMEIRA GUERRA MUNDIAL Imagine ...")
    m = re.match(r"^([A-ZÀ-Ý0-9 ,.'|:\-–]{12,}?)\s+(?=[A-ZÀ-Ý][a-zà-ÿ])", t)
    if m:
        t = t[m.end():]
    m = re.search(r"(.+?[.!?…])(\s|$)", t)
    return (m.group(1) if m else t)[:220].strip()


def hook_type(sentence: str, text: str) -> str:
    f = fold(sentence)
    if f.startswith("imagine"):
        return "Imagine (você na cena)"
    if f.startswith(("voce sabia", "sabia que")):
        return "Você sabia?"
    if f.endswith("?") or f.startswith(("por que", "como ", "o que ", "quem ")):
        return "Pergunta"
    if re.match(r"^(em|no ano de|durante)\s+(\d{3,4}|mais de|o ano)", f) or re.match(r"^durante", f):
        return "Contexto/data"
    if f.startswith(("ele ", "ela ", "eles ", "elas ")):
        return "Mistério (quem é?)"
    return "Afirmação"


def era_from(text: str, tags: list[str]) -> str:
    years = [int(y) for y in re.findall(r"(?<!\d)(\d{3,4})(?!\d)", text + " " + " ".join(tags))
             if 100 <= int(y) <= 2030]
    if "d.C." in text or "d.c." in fold(text):
        years += [int(y) for y in re.findall(r"(\d{1,4})\s*d\.?\s?C", text)]
    if not years:
        return "?"
    y = min(years)
    if y < 500:
        return "Antiguidade"
    if y < 1500:
        return "Idade Média"
    if y < 1800:
        return "Idade Moderna"
    if y < 1914:
        return "Século XIX"
    if y <= 1945:
        return "Guerras Mundiais (1914–1945)"
    return "Pós-1945"


def theme_from(text: str, tags: list[str], themes: dict) -> str:
    hay = fold(text + " " + " ".join(tags))
    best, score = "?", 0
    for name, words in themes.items():
        s = sum(1 for w in words if fold(w) in hay)
        if s > score:
            best, score = name, s
    return best


def region_from(text: str, tags: list[str], regions: dict) -> str:
    hay = fold(text + " " + " ".join(tags))
    for name, words in regions.items():
        if name.startswith("_"):
            continue
        if any(fold(w) in hay for w in words):
            return name
    return regions.get("_default", "?") if isinstance(regions.get("_default"), str) else "?"


def scan_videos(folder: Path) -> list[dict]:
    if not shutil.which("ffprobe"):
        print("aviso: ffprobe não encontrado (brew install ffmpeg); durações ficam vazias", file=sys.stderr)
        return []
    vids = []
    for f in folder.rglob("*.mp4"):
        if any(p in f.parts for p in ("node_modules", "public", ".cache")) or "raw" in f.stem.lower():
            continue
        try:
            d = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(f)],
                               capture_output=True, text=True, timeout=30).stdout.strip()
            vids.append({"path": str(f), "duration_s": round(float(d), 1),
                         "mtime": datetime.fromtimestamp(f.stat().st_mtime),
                         "tokens": set(re.findall(r"[a-z0-9]{3,}", fold(f.parent.parent.name + " " + f.stem)))})
        except (ValueError, subprocess.TimeoutExpired):
            continue
    return vids


STOP = {"reels", "por", "que", "como", "comecou", "dos", "das", "the", "out", "raw", "mp4"}


def post_tokens(text: str, tags: list[str]) -> set[str]:
    hay = set(re.findall(r"[a-z0-9]{3,}", fold(text + " " + " ".join(tags))))
    for tag in tags:  # #UniaoSovietica → uniao, sovietica; #Chernobyl1986 → chernobyl, 1986
        parts = re.findall(r"[A-Z]?[a-zà-ÿ]+|\d+", tag)
        hay |= {fold(x) for x in parts if len(x) >= 3}
    return hay


def assign_videos(posts: list[dict], texts: dict, vids: list[dict]) -> dict:
    """Casa cada post com um vídeo: palavras raras em comum (peso IDF) e proximidade da data.
    Cada vídeo vai para um post só."""
    import math
    df: dict[str, int] = {}
    for v in vids:
        for tok in v["tokens"] - STOP:
            df[tok] = df.get(tok, 0) + 1
    cands = []
    for p in posts:
        pub = datetime.fromisoformat(p["published_at"])
        hay = post_tokens(*texts[p["id"]])
        for i, v in enumerate(vids):
            common = (v["tokens"] - STOP) & hay
            dt = (pub - v["mtime"]).total_seconds() / 3600
            if not common or dt < -0.1 or dt > 72:
                continue
            w = sum(math.log(1 + len(vids) / df[t]) for t in common)
            cands.append((w / (1 + dt / 12), p["id"], i))
    used_p, used_v, out = set(), set(), {}
    for score, pid, i in sorted(cands, reverse=True):
        if pid in used_p or i in used_v:
            continue
        used_p.add(pid); used_v.add(i); out[pid] = vids[i]
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--posts", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--videos", help="pasta com os MP4 publicados (para duração e retenção)")
    ap.add_argument("--themes", default=str(SKILL / "references" / "themes.json"))
    ap.add_argument("--keep", help="tags.json de rodada anterior para reaproveitar revisões")
    a = ap.parse_args()

    data = load_json(a.posts)
    cfg = load_json(a.themes)
    old = {t["id"]: t for t in load_json(a.keep)["tags"]} if a.keep and Path(a.keep).exists() else {}
    vids = scan_videos(Path(a.videos)) if a.videos else []

    texts = {p["id"]: split_caption(p.get("caption", "")) for p in data["posts"]}
    matched = assign_videos(data["posts"], texts, vids) if vids else {}
    out = []
    for p in data["posts"]:
        text, tags = split_caption(p.get("caption", ""))
        sent = first_sentence(text)
        ep = re.match(r"^EP\.?\s*(\d+)", text, re.I)
        v = matched.get(p["id"])
        t = {
            "id": p["id"],
            "published_at": p["published_at"],
            "hook": sent,
            "hook_type": hook_type(sent, text),
            "theme": theme_from(text, tags, cfg.get("themes", {})),
            "region": region_from(text, tags, cfg.get("regions", {})),
            "era": era_from(text, tags),
            "series_ep": int(ep.group(1)) if ep else None,
            "title_in_caption": bool(re.search(r"[A-ZÀ-Ý]{4,}(\s+[A-ZÀ-Ý]{2,}){2,}", text)),
            "caption_chars": len(text),
            "hashtags": len(tags),
            "duration_s": p.get("duration_s") or (v and v["duration_s"]),
            "video_file": v and v["path"],
            "extra": {},
            "reviewed": False,
        }
        if p["id"] in old:
            keep = old[p["id"]]
            for k in ("theme", "region", "era", "hook_type", "extra", "duration_s", "video_file", "reviewed"):
                if keep.get(k) not in (None, "?", {}):
                    t[k] = keep[k]
        out.append(t)

    dump_json({"note": "Revise theme/region/era/hook_type; '?' = não deduzido. Marque reviewed=true.",
               "tags": out}, a.out)
    unk = sum(1 for t in out for k in ("theme", "region", "era") if t[k] == "?")
    nodur = sum(1 for t in out if not t["duration_s"])
    print(f"{len(out)} posts → {a.out}  ({unk} campos '?', {nodur} sem duração)")
    for t in out:
        print(f"  {t['published_at']}  {t['hook_type'][:22]:22}  {t['theme'][:26]:26}  {t['era'][:14]:14}  "
              f"{t['duration_s'] or '-':>6}  {Path(t['video_file']).name if t['video_file'] else ''}")


if __name__ == "__main__":
    main()
