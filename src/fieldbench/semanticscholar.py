"""Semantic Scholar API client with polite rate limiting, retries, and disk caching.

Unauthenticated limit is ~100 requests / 5 min. Set S2_API_KEY env var for
higher limits (sent as x-api-key header).
"""
import json
import os
import re
import time
import unicodedata
import urllib.request

from .cache import Cache

BASE = "https://api.semanticscholar.org/graph/v1"
API_KEY = os.environ.get("S2_API_KEY", "")
_LAST_CALL = [0.0]
MIN_INTERVAL = 1.2 if not API_KEY else 0.4


def _throttle():
    dt = time.time() - _LAST_CALL[0]
    if dt < MIN_INTERVAL:
        time.sleep(MIN_INTERVAL - dt)
    _LAST_CALL[0] = time.time()


def _post(path: str, payload: dict, fields: str, tries: int = 6):
    data = json.dumps(payload).encode()
    for attempt in range(tries):
        _throttle()
        try:
            headers = {"Content-Type": "application/json"}
            if API_KEY:
                headers["x-api-key"] = API_KEY
            req = urllib.request.Request(BASE + path + "?fields=" + fields,
                                         data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.load(r)
        except Exception as e:
            wait = 5 + attempt * 6
            print(f"  S2 {path} retry {attempt} ({str(e)[:80]}), waiting {wait}s")
            time.sleep(wait)
    raise RuntimeError(f"S2 {path} failed after {tries} tries")


def _get(path: str, fields: str, tries: int = 5):
    for attempt in range(tries):
        _throttle()
        try:
            headers = {}
            if API_KEY:
                headers["x-api-key"] = API_KEY
            req = urllib.request.Request(BASE + path + "?fields=" + fields,
                                         headers=headers)
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except Exception as e:
            wait = 5 + attempt * 6
            print(f"  S2 GET {path} retry {attempt} ({str(e)[:80]}), waiting {wait}s")
            time.sleep(wait)
    raise RuntimeError(f"S2 GET {path} failed after {tries} tries")


def _norm(name: str) -> str:
    n = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z ]", "", n.lower()).strip()


def _match_score(oa_name: str, s2_name: str) -> int:
    a, b = _norm(oa_name), _norm(s2_name)
    if a and a == b:
        return 2
    pa, pb = a.split(), b.split()
    if pa and pb and pa[-1] == pb[-1] and pa[0][:1] == pb[0][:1]:
        return 1
    return 0


def papers_by_doi(dois, cache: Cache | None = None, progress_cb=None):
    """Resolve DOI list -> S2 paper records (title, authors, externalIds)."""
    dois = [d.lower() for d in dict.fromkeys(dois)]
    payload = {"ns": "papers_by_doi", "dois": sorted(dois)}
    if cache:
        hit = cache.get("s2", payload)
        if hit is not None:
            return hit
    out = []
    for i in range(0, len(dois), 400):
        chunk = ["DOI:" + d for d in dois[i:i + 400]]
        res = _post("/paper/batch", {"ids": chunk}, "title,authors,externalIds")
        out.extend(res if isinstance(res, list) else [])
        if progress_cb:
            progress_cb("s2_papers", i + len(chunk), len(dois),
                        f"paper batch {i // 400 + 1}")
    if cache:
        cache.set("s2", payload, out)
    return out


def authors_by_id(s2_ids, cache: Cache | None = None, progress_cb=None):
    """S2 author records: name, hIndex, citationCount, paperCount."""
    s2_ids = list(dict.fromkeys(s2_ids))
    payload = {"ns": "authors_by_id", "ids": sorted(s2_ids)}
    if cache:
        hit = cache.get("s2", payload)
        if hit is not None:
            return hit
    out = {}
    for i in range(0, len(s2_ids), 400):
        chunk = s2_ids[i:i + 400]
        res = _post("/author/batch", {"ids": chunk},
                    "name,hIndex,citationCount,paperCount")
        for au in (res if isinstance(res, list) else []):
            if isinstance(au, dict) and au.get("authorId"):
                out[au["authorId"]] = {
                    "name": au.get("name"),
                    "hIndex": au.get("hIndex"),
                    "citationCount": au.get("citationCount"),
                    "paperCount": au.get("paperCount"),
                }
        if progress_cb:
            progress_cb("s2_authors", i + len(chunk), len(s2_ids),
                        f"author batch {i // 400 + 1}")
    if cache:
        cache.set("s2", payload, out)
    return out


def match_authors(oa_names: dict, dois_per_author: dict, paper_records,
                  progress_cb=None):
    """Match OpenAlex authors -> S2 authorIds via DOI->paper->author name match.

    oa_names: {oa_id: display_name}; dois_per_author: {oa_id: [doi,...]}.
    Returns (matches, unmatched): matches {oa_id: {s2_id, name_s2, confidence}}.
    """
    doi2paper = {}
    for p in paper_records:
        if not isinstance(p, dict):
            continue
        doi = ((p.get("externalIds") or {}).get("DOI") or "").lower()
        if doi:
            doi2paper[doi] = p
    matches, unmatched = {}, []
    for n, (oa_id, oa_name) in enumerate(oa_names.items()):
        hit = None
        for d in dois_per_author.get(oa_id, [])[:3]:
            p = doi2paper.get(d.lower())
            if not p:
                continue
            best, best_score = None, 0
            for au in p.get("authors") or []:
                sc = _match_score(oa_name, au.get("name", ""))
                if sc > best_score:
                    best, best_score = au, sc
            if best and best_score >= 1 and best.get("authorId"):
                hit = {"s2_id": best["authorId"], "name_s2": best.get("name"),
                       "confidence": "exact" if best_score == 2 else "last+initial",
                       "via_doi": d}
                break
        if hit:
            matches[oa_id] = hit
        else:
            unmatched.append(oa_id)
        if progress_cb and (n + 1) % 500 == 0:
            progress_cb("s2_match", n + 1, len(oa_names), f"{n + 1}/{len(oa_names)}")
    return matches, unmatched


def search_author(name: str):
    """Author search (for verifying single vs split profiles)."""
    d = _get("/author/search?query=" + __import__("urllib.parse").quote(name),
             "name,paperCount,citationCount,hIndex")
    return d.get("data", [])
