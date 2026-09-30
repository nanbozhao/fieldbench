"""Markdown benchmark report generation."""
import datetime


def _fmt(x, nd=1):
    return f"{x:.{nd}f}" if isinstance(x, float) else str(x)


def markdown(result, topic_names=None) -> str:
    meta, ranks = result["meta"], result["ranks"]
    topics = ", ".join(
        f"{topic_names.get(t, t)}" if topic_names else t for t in meta["topics"])
    lines = []
    lines.append("# Field Citation Benchmark Report")
    lines.append("")
    lines.append(f"_Generated {datetime.date.today().isoformat()} by fieldbench 0.1.0_")
    lines.append("")
    lines.append("## Subject")
    s = meta["subject_s2"]
    lines.append(f"- **{meta['subject_name']}** — Semantic Scholar: "
                 f"{s.get('citationCount')} citations, h-index {s.get('hIndex')}, "
                 f"{s.get('paperCount')} papers (match confidence: "
                 f"{meta.get('subject_match_confidence')})")
    lines.append("")
    lines.append("## Cohort definition")
    lines.append(f"- Topics: {topics}")
    lines.append(f"- Publication window: {meta['year_window'][0]}–{meta['year_window'][1]}, "
                 f"at least {meta['min_topic_works']} topic works")
    lines.append(f"- Career stage: first publication "
                 f"{meta['career_window'][0]}–{meta['career_window'][1]}")
    lines.append(f"- Cohort size: **{meta['n_cohort']}** researchers "
                 f"({result['n_resolved']} resolved in Semantic Scholar, "
                 f"{result['n_unmatched']} unmatched/excluded)")
    lines.append("")
    lines.append("## Results (Semantic Scholar)")
    lines.append("")
    lines.append("| metric | subject | cohort median | p75 | p90 | percentile | top |")
    lines.append("|---|---|---|---|---|---|---|")
    for metric, label in (("citations", "Total citations"), ("h_index", "h-index")):
        r = ranks[metric]
        sm = r["summary"]
        lines.append(f"| {label} | {r['subject']} | {_fmt(sm['median'])} | "
                     f"{_fmt(sm['p75'])} | {_fmt(sm['p90'])} | "
                     f"{_fmt(r['percentile'])}th | top {_fmt(r['top_pct'])}% |")
    lines.append("")
    lines.append("## How to read this")
    lines.append("- Percentile = share of cohort members strictly below the subject, "
                 "computed within a single database (no cross-database mixing).")
    lines.append("- The cohort definition travels with the number: a percentile is only "
                 "meaningful relative to the comparison group stated above.")
    lines.append("- Unmatched authors (no S2 record / name-match failed) are excluded; "
                 "their exclusion is disclosed, not hidden.")
    lines.append("")
    lines.append("## Reproducibility")
    lines.append("All inputs are API-derived (OpenAlex, Semantic Scholar) and the "
                 "pipeline is deterministic given the access date. Re-run with the "
                 "same parameters to reproduce; expect small drift as the underlying "
                 "databases reindex.")
    lines.append("")
    return "\n".join(lines)
