"""fieldbench CLI: run a benchmark from the terminal."""
import argparse
import json
import sys

sys.path.insert(0, "src")
from fieldbench import run, markdown
from fieldbench.cache import Cache


def main():
    ap = argparse.ArgumentParser(description="Field-normalized citation benchmark")
    ap.add_argument("--topics", nargs="+", required=True, help="OpenAlex topic IDs, e.g. T11948 T10211")
    ap.add_argument("--dois", nargs="+", required=True, help="Subject's paper DOIs (for S2 author resolution)")
    ap.add_argument("--name", required=True, help="Subject display name, e.g. 'Bozhao Nan'")
    ap.add_argument("--oa-id", default=None, help="Subject OpenAlex author ID (excluded from cohort)")
    ap.add_argument("--year-from", type=int, default=2022)
    ap.add_argument("--year-to", type=int, default=2024)
    ap.add_argument("--min-topic-works", type=int, default=2)
    ap.add_argument("--first-pub-from", type=int, default=2020)
    ap.add_argument("--first-pub-to", type=int, default=2022)
    ap.add_argument("--out", default="benchmark_report.md")
    ap.add_argument("--json-out", default="benchmark_result.json")
    args = ap.parse_args()

    def progress(stage, done, total, msg):
        print(f"[{stage}] {msg}", flush=True)

    result = run(
        args.topics, args.dois, args.name,
        year_from=args.year_from, year_to=args.year_to,
        min_topic_works=args.min_topic_works,
        first_pub_from=args.first_pub_from, first_pub_to=args.first_pub_to,
        subject_oa_id=args.oa_id, cache=Cache(), progress_cb=progress)

    with open(args.json_out, "w") as f:
        json.dump(result, f, indent=1)
    with open(args.out, "w") as f:
        f.write(markdown(result))
    r = result["ranks"]["citations"]
    print(f"\nDone: N={result['n_resolved']}, citations {r['percentile']:.1f}th "
          f"(top {r['top_pct']:.1f}%). Report -> {args.out}")


if __name__ == "__main__":
    main()
