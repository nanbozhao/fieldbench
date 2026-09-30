# fieldbench

**Open, reproducible field-normalized citation benchmarking.**

Give it a researcher and a field definition; get back an evidence-grade percentile rank:
*"Dr. X ranks at the 86th percentile for citations among 5,300 active early-career
researchers in computational chemistry"* — with the cohort definition, the data sources,
and the code to reproduce it, all disclosed.

Built for high-stakes research evaluation (e.g., EB-1A "final merits" field benchmarks),
but useful for anyone who wants an honest, transparent alternative to black-box
"top researcher" scores.

## How it works

1. **Pool** — all authors with ≥ *k* works (default 2) in a year window whose
   `primary_topic` is one of the chosen OpenAlex topics.
2. **Career-stage filter** — keep authors whose first publication year falls in a
   window matching the subject (default ±1 year around the subject's first pub).
3. **Resolve** — every cohort member (and the subject) is resolved to a
   Semantic Scholar author record via DOI → paper → author name-match
   (exact match, else last-name + first-initial; confidence recorded).
4. **Rank** — percentile = share of cohort members *strictly below* the subject,
   computed within a single database (no cross-database mixing). Headline metrics:
   total citations and h-index, both from Semantic Scholar.

Unmatched authors are excluded and the count is disclosed, never hidden.

## Quick start

```bash
pip install -e .
# optional: higher Semantic Scholar limits
export S2_API_KEY=your_key

python cli.py \
  --topics T11948 T10211 T10836 \
  --dois 10.1039/D2SC06041H 10.48550/arXiv.2311.07341 \
  --name "Bozhao Nan" --oa-id A5023104692 \
  --min-topic-works 2 --first-pub-from 2020 --first-pub-to 2022
```

## Web app

```bash
pip install -e ".[web]"
uvicorn web.app:app --host 0.0.0.0 --port 8000
```

Open http://localhost:8000 — fill the form, get a job ticket, come back when it's done.
Jobs run one at a time (Semantic Scholar rate limits); progress is live-polled.
Results include a downloadable markdown report.

Deploy notes: put it behind any reverse proxy; set `S2_API_KEY` for production;
`web/jobs.db` (SQLite) and `data/cache/` hold job state and API caches.

## Python API

```python
from fieldbench import run, markdown
from fieldbench.cache import Cache

result = run(
    topic_ids=["T11948", "T10211", "T10836"],
    subject_dois=["10.1039/D2SC06041H"],
    subject_name="Bozhao Nan",
    subject_oa_id="A5023104692",
    min_topic_works=2,
    cache=Cache(),
)
print(markdown(result))
```

## Methodology notes (read before citing numbers)

- **The cohort definition travels with the number.** A percentile is meaningless
  without its denominator: topics, work threshold, year window, and career stage
  are part of the claim.
- **Database matters.** Semantic Scholar covers AI conferences well and chemistry
  journals less completely (and vice versa for OpenAlex vs. conference papers).
  The honest practice is to use one database consistently for subject and cohort,
  and disclose the choice. Google Scholar has no API and can't be used for
  cohort percentiles.
- **A percentile is supporting evidence, not a verdict.** There is no official
  cutoff for "top of the field"; field benchmarks support a totality-of-evidence
  argument.
- **Reproducibility.** The pipeline is deterministic given the access date; expect
  small drift as OpenAlex/Semantic Scholar reindex. Every run records its
  parameters, cohort size, match counts, and unmatched count.

## Citation

```bibtex
@software{nan2026fieldbench,
  author = {Nan, Bozhao},
  title = {fieldbench: open field-normalized citation benchmarking},
  version = {0.1.0},
  date = {2026-09-30},
  doi = {10.5281/zenodo.XXXXXXX},
  url = {https://github.com/nanbozhao/fieldbench}
}
```

Get a real DOI: push to GitHub → create a release → enable the Zenodo–GitHub
integration → replace `XXXXXXX` above, in `CITATION.cff`, and in
`web/templates/result.html`.

## Limitations

- OpenAlex topic tags are algorithmic; "field" is operationalized, not ontological.
- S2 author disambiguation is heuristic; mismatches are possible (confidence recorded per match).
- Name-match failures and missing DOIs exclude authors; exclusion counts are reported.
- Slow: a thousand-author cohort takes ~30–60 min end to end (mostly API paging).

## License

MIT — see [LICENSE](LICENSE).
