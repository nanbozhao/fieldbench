"""Pure statistics: percentiles, distribution summaries. No I/O."""
import statistics


def percentile(values, x) -> float:
    """100 * (# values strictly below x) / N."""
    n = len(values)
    if n == 0:
        return float("nan")
    below = sum(1 for v in values if v < x)
    return 100.0 * below / n


def summarize(values) -> dict:
    vals = sorted(v for v in values if v is not None)
    n = len(vals)
    if n == 0:
        return {"n": 0}
    def q(p):
        k = (n - 1) * p
        f, c = int(k), min(int(k) + 1, n - 1)
        return vals[f] + (vals[c] - vals[f]) * (k - f)
    return {
        "n": n,
        "min": vals[0],
        "max": vals[-1],
        "mean": statistics.fmean(vals),
        "median": statistics.median(vals),
        "p25": q(0.25),
        "p75": q(0.75),
        "p90": q(0.90),
    }


def rank_report(cohort_values: dict, subject_values: dict) -> dict:
    """cohort_values: {metric: [values]}, subject_values: {metric: value}.

    Returns {metric: {percentile, top_pct, subject, summary}}.
    """
    out = {}
    for metric, vals in cohort_values.items():
        x = subject_values.get(metric)
        pct = percentile(vals, x)
        out[metric] = {
            "subject": x,
            "percentile": pct,
            "top_pct": 100.0 - pct,
            "summary": summarize(vals),
        }
    return out
