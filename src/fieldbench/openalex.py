"""OpenAlex API client: topic search/pool collection, author details, first-publication year."""
import json
import time
import urllib.parse
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from .cache import Cache

BASE = "https://api.openalex.org"
MAILTO = "fieldbench@open.science"


def _get(url: str, tries: int = 5, timeout: int = 60):
    for attempt in range(tries):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": f"fieldbench/0.1 (mailto:{MAILTO})"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except Exception:
            time.sleep(2 + attempt * 2)
    raise RuntimeError(f"OpenAlex request failed after {tries} tries: {url[:120]}")


def _q(params: dict) -> str:
    params = dict(params)
    params.setdefault("mailto", MAILTO)
    return BASE + "/works?" + urllib.parse.urlencode(params)


def search_topics(query: str, per_page: int = 10):
    """Search OpenAlex topics by keyword. Returns [{id, display_name, works_count, description}]."""
    url = (
        BASE + "/topics?search=" + urllib.parse.quote(query)
        + f"&per-page={per_page}&select=id,display_name,works_count,description&mailto=" + MAILTO
    )
    d = _get(url)
    out = []
    for t in d.get("results", []):
        out.append({
            "id": t["id"].split("/")[-1],
            "display_name": t.get("display_name"),
            "works_count": t.get("works_count"),
            "description": (t.get("description") or "")[:280],
        })
    return out


def topic_info(topic_id: str):
    url = (BASE + f"/topics/{topic_id}"
           + "?select=id,display_name,works_count,description,subfield,field,domain&mailto=" + MAILTO)
    d = _get(url)
    out = {
        "id": d["id"].split("/")[-1],
        "display_name": d.get("display_name"),
        "works_count": d.get("works_count"),
        "description": d.get("description"),
    }
    for k in ("subfield", "field", "domain"):
        v = d.get(k) or {}
        out[k] = v.get("display_name")
    return out


def collect_author_counts(topic_ids, year_from: int, year_to: int,
                          cache: Cache | None = None, progress_cb=None) -> dict:
    """Count  year-window works per author across the given primary topics.

    Returns {openalex_author_id: topic_work_count}. Cached by (topics, years).
    """
    payload = {"ns": "author_counts", "topics": sorted(topic_ids),
               "from": year_from, "to": year_to}
    if cache:
        hit = cache.get("openalex", payload)
        if hit is not None:
            return hit
    filt = (f"primary_topic.id:{'|'.join(topic_ids)},"
            f"from_publication_date:{year_from}-01-01,to_publication_date:{year_to}-12-31")
    counts: Counter = Counter()
    cursor, pages, works_seen = "*", 0, 0
    while True:
        d = _get(_q({"filter": filt, "per-page": 200,
                     "select": "id,authorships", "cursor": cursor}))
        results = d.get("results", [])
        if not results:
            break
        for w in results:
            works_seen += 1
            for a in w.get("authorships", []):
                aid = (a.get("author") or {}).get("id")
                if aid:
                    counts[aid.split("/")[-1]] += 1
        pages += 1
        if progress_cb and pages % 10 == 0:
            progress_cb("collect_pool", pages, None,
                        f"{works_seen} works, {len(counts)} authors")
        cursor = d["meta"].get("next_cursor")
        if not cursor:
            break
        time.sleep(0.12)
    result = dict(counts)
    if cache:
        cache.set("openalex", payload, result)
    return result


def author_details(author_ids, cache: Cache | None = None, progress_cb=None,
                   workers: int = 6) -> dict:
    """Batch-fetch OpenAlex author summary stats. Returns {id: {name, h_index, cited_by_count, works_count}}."""
    ids = list(dict.fromkeys(author_ids))
    payload = {"ns": "author_details", "ids": sorted(ids)}
    if cache:
        hit = cache.get("openalex", payload)
        if hit is not None:
            return hit

    def batch(chunk):
        url = (BASE + "/authors?filter=openalex:" + "|".join(chunk)
               + "&per-page=50&select=id,display_name,summary_stats,works_count,cited_by_count&mailto=" + MAILTO)
        d = _get(url)
        out = {}
        for au in d.get("results", []):
            aid = au["id"].split("/")[-1]
            ss = au.get("summary_stats") or {}
            out[aid] = {
                "name": au.get("display_name"),
                "h_index": ss.get("h_index"),
                "cited_by_count": au.get("cited_by_count"),
                "works_count": au.get("works_count"),
            }
        return out

    details, done = {}, 0
    chunks = [ids[i:i + 50] for i in range(0, len(ids), 50)]
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for part in ex.map(batch, chunks):
            details.update(part)
            done += 1
            if progress_cb and done % 20 == 0:
                progress_cb("author_details", done, len(chunks), f"{done}/{len(chunks)} batches")
            time.sleep(0.05)
    if cache:
        cache.set("openalex", payload, details)
    return details


def first_publication_years(author_ids, cache: Cache | None = None,
                            progress_cb=None, workers: int = 6) -> dict:
    """Earliest publication year per author (one cheap query each)."""
    ids = list(dict.fromkeys(author_ids))
    payload = {"ns": "first_pub_year", "ids": sorted(ids)}
    if cache:
        hit = cache.get("openalex", payload)
        if hit is not None:
            return hit

    def lookup(aid):
        try:
            d = _get(BASE + "/works?filter=author.id:" + aid
                     + "&sort=publication_date:asc&per-page=1&select=id,publication_year&mailto=" + MAILTO,
                     tries=3)
            rs = d.get("results", [])
            return aid, (rs[0].get("publication_year") if rs else None)
        except Exception:
            return aid, None

    out, done = {}, 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for aid, yr in ex.map(lookup, ids):
            out[aid] = yr
            done += 1
            if progress_cb and done % 500 == 0:
                progress_cb("first_pub_year", done, len(ids), f"{done}/{len(ids)}")
    if cache:
        cache.set("openalex", payload, out)
    return out


def top_dois(author_id: str, n: int = 3):
    """Up to n DOIs of the author's most-cited works (for S2 author matching)."""
    d = _get(BASE + "/works?filter=author.id:" + author_id
             + "&sort=cited_by_count:desc&per-page=8&select=doi,title&mailto=" + MAILTO,
             tries=4)
    out = []
    for w in (d.get("results", []) if d else []):
        doi = (w.get("doi") or "").replace("https://doi.org/", "").strip().lower()
        if doi and doi not in out:
            out.append(doi)
        if len(out) >= n:
            break
    return out
