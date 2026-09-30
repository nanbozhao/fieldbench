"""End-to-end cohort benchmark orchestration.

Pipeline:
  1. collect OpenAlex author pool for (topics, year window)
  2. filter: >= min_topic_works topic works, career-stage via first-pub year
  3. resolve cohort + subject to Semantic Scholar author records
  4. compute percentile ranks (citations, h-index)
"""
from . import benchmark as B
from . import openalex as OA
from . import semanticscholar as S2
from .cache import Cache


def _noop(*a, **k):
    pass


def build_cohort(topic_ids, year_from=2022, year_to=2024,
                 min_topic_works=2, first_pub_from=2020, first_pub_to=2022,
                 exclude_ids=(), cache: Cache | None = None,
                 progress_cb=None, workers=6):
    """Returns (cohort, meta). cohort: {oa_id: {name, h_index, cited_by_count,
    works_count, first_pub_year, topic_works}}."""
    cb = progress_cb or _noop
    counts = OA.collect_author_counts(topic_ids, year_from, year_to,
                                      cache=cache, progress_cb=cb)
    cands = [aid for aid, c in counts.items() if c >= min_topic_works]
    cb("filter", 0, 1, f"{len(cands)} authors with >={min_topic_works} topic works")
    details = OA.author_details(cands, cache=cache, progress_cb=cb, workers=workers)
    surv = {a: v for a, v in details.items() if (v.get("works_count") or 0) >= 3}
    firstyrs = OA.first_publication_years(list(surv), cache=cache,
                                          progress_cb=cb, workers=workers)
    cohort = {}
    for aid, yr in firstyrs.items():
        if (isinstance(yr, int) and first_pub_from <= yr <= first_pub_to
                and aid not in exclude_ids and aid in surv
                and counts.get(aid, 0) >= min_topic_works):
            cohort[aid] = {**surv[aid], "first_pub_year": yr,
                           "topic_works": counts.get(aid, 0)}
    meta = {"n_candidates": len(cands), "n_cohort": len(cohort),
            "topics": topic_ids, "year_window": [year_from, year_to],
            "min_topic_works": min_topic_works,
            "career_window": [first_pub_from, first_pub_to]}
    cb("filter", 1, 1, f"cohort N={len(cohort)}")
    return cohort, meta


def resolve_s2(cohort, subject_dois, subject_name,
               cache: Cache | None = None, progress_cb=None):
    """Resolve cohort members + subject to S2 author stats.

    subject_dois: DOIs identifying the subject (their papers).
    Returns dict with matches, stats, subject record.
    """
    cb = progress_cb or _noop
    aids = list(cohort)
    # DOIs for matching (subject first so their papers are in the batch)
    dois_per_author = {}
    all_dois = []
    for d in subject_dois:
        dl = d.lower()
        if dl not in all_dois:
            all_dois.append(dl)
    subj_key = "__subject__"
    dois_per_author[subj_key] = [d.lower() for d in subject_dois]
    for n, aid in enumerate(aids):
        ds = OA.top_dois(aid, 3)
        dois_per_author[aid] = ds
        for d in ds:
            if d not in all_dois:
                all_dois.append(d)
        if (n + 1) % 200 == 0:
            cb("s2_dois", n + 1, len(aids), f"{n + 1}/{len(aids)}")
    papers = S2.papers_by_doi(all_dois, cache=cache, progress_cb=cb)
    oa_names = {subj_key: subject_name}
    oa_names.update({aid: cohort[aid]["name"] for aid in aids})
    matches, unmatched = S2.match_authors(oa_names, dois_per_author, papers,
                                          progress_cb=cb)
    subj_match = matches.pop(subj_key, None)
    stats = S2.authors_by_id([m["s2_id"] for m in matches.values()] +
                             ([subj_match["s2_id"]] if subj_match else []),
                             cache=cache, progress_cb=cb)
    return {"matches": matches, "unmatched": unmatched,
            "stats": stats, "subject": subj_match}


def run(topic_ids, subject_dois, subject_name,
        year_from=2022, year_to=2024, min_topic_works=2,
        first_pub_from=2020, first_pub_to=2022,
        subject_oa_id=None, cache: Cache | None = None,
        progress_cb=None, workers=6):
    """Full benchmark. Returns serializable result dict."""
    cb = progress_cb or _noop
    cache = cache or Cache()
    exclude = (subject_oa_id,) if subject_oa_id else ()
    cohort, meta = build_cohort(
        topic_ids, year_from, year_to, min_topic_works,
        first_pub_from, first_pub_to, exclude_ids=exclude,
        cache=cache, progress_cb=cb, workers=workers)
    s2 = resolve_s2(cohort, subject_dois, subject_name,
                    cache=cache, progress_cb=cb)
    stats, subj = s2["stats"], s2["subject"]
    if not subj or subj["s2_id"] not in stats:
        raise RuntimeError("subject could not be resolved in Semantic Scholar")
    srec = stats[subj["s2_id"]]
    cohort_cites, cohort_h = [], []
    for oa_id, m in s2["matches"].items():
        st = stats.get(m["s2_id"]) or {}
        if st.get("citationCount") is not None:
            cohort_cites.append(st["citationCount"])
        if st.get("hIndex") is not None:
            cohort_h.append(st["hIndex"])
    ranks = B.rank_report(
        {"citations": cohort_cites, "h_index": cohort_h},
        {"citations": srec.get("citationCount"), "h_index": srec.get("hIndex")})
    cb("done", 1, 1, "complete")
    return {
        "meta": {**meta, "subject_name": subject_name,
                 "subject_s2": srec, "subject_match_confidence": subj.get("confidence")},
        "n_resolved": len(cohort_cites),
        "n_unmatched": len(s2["unmatched"]),
        "ranks": ranks,
    }
