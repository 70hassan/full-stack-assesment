"""Summarise each route's risk and rank the options.

The brief's preference order is applied literally, as a lexicographic sort:
fewest Severe miles, then fewest High miles, then lowest average risk, then
shortest travel time. "No Travel" is worse than Severe, so miles at that
level are compared before everything else.
"""
from . import risk

CRITERIA = (
    ("no_travel_miles", "No Travel miles"),
    ("severe_miles", "Severe miles"),
    ("high_miles", "High-risk miles"),
    ("average_risk", "average risk"),
    ("duration_seconds", "travel time"),
)


def summarize(spans, duration_seconds):
    """`spans` is a list of (miles, level) covering the whole route."""
    miles_by_level = [0.0] * len(risk.LEVEL_KEYS)
    for miles, level in spans:
        miles_by_level[level] += miles
    total = sum(miles_by_level)
    average = sum(m * level for level, m in enumerate(miles_by_level)) / total if total else 0.0
    return {
        "miles_by_level": {key: round(m, 1) for key, m in zip(risk.LEVEL_KEYS, miles_by_level)},
        "no_travel_miles": round(miles_by_level[risk.NO_TRAVEL], 1),
        "severe_miles": round(miles_by_level[risk.SEVERE], 1),
        "high_miles": round(miles_by_level[risk.HIGH], 1),
        # Mean risk level weighted by distance: 0 = all Low ... 4 = all No Travel.
        "average_risk": round(average, 2),
        "max_level": max((level for miles, level in spans if miles > 0), default=risk.LOW),
        "duration_seconds": round(duration_seconds),
    }


def sort_key(summary):
    return tuple(summary[name] for name, _ in CRITERIA)


def rank(summaries):
    """Return route indices from best to worst."""
    return sorted(range(len(summaries)), key=lambda i: sort_key(summaries[i]))


def _format(name, value):
    if name == "duration_seconds":
        hours, minutes = divmod(round(value / 60), 60)
        return f"{hours}h {minutes:02d}m"
    if name == "average_risk":
        return f"{value:.2f}"
    return f"{value:g} mi"


def explain(summaries, order):
    """Say which criterion separated the winner from the runner-up."""
    best = summaries[order[0]]
    if len(order) == 1:
        return {"criterion": None, "text": "Only one route is available between these places."}
    runner_up = summaries[order[1]]
    for name, label in CRITERIA:
        if best[name] != runner_up[name]:
            text = (
                f"Shortest travel time ({_format(name, best[name])} vs {_format(name, runner_up[name])}); "
                "weather risk is equal on the leading options."
                if name == "duration_seconds"
                else f"Lowest {label} ({_format(name, best[name])} vs {_format(name, runner_up[name])} "
                "on the next-best route)."
                if name == "average_risk"
                else f"Fewest {label} ({_format(name, best[name])} vs {_format(name, runner_up[name])} "
                "on the next-best route)."
            )
            return {"criterion": name, "text": text}
    return {"criterion": None, "text": "The leading options are equal on risk and travel time."}
