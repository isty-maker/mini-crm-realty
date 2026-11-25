from django.db.models import Prefetch

from .models import PriceHistory


RECENT_LIMIT = 5


def with_recent_prices(properties):
    return properties.prefetch_related(
        Prefetch("price_history", queryset=PriceHistory.objects.filter(
            kind=PriceHistory.Kind.CHANGE
        )[:RECENT_LIMIT], to_attr="recent_price_changes"),
        Prefetch("price_history", queryset=PriceHistory.objects.exclude(
            kind=PriceHistory.Kind.CHANGE
        ), to_attr="price_origins"),
    )


def chart_points(history):
    """Plot actual elapsed time and leave a gap when the price is unknown."""
    chronological = list(reversed(history))
    prices = [entry.new_price for entry in chronological if entry.new_price is not None]
    if not prices:
        return "", []
    start = chronological[0].recorded_at
    duration = (chronological[-1].recorded_at - start).total_seconds()
    low, high = min(prices), max(prices)
    path = []
    points = []
    previous = None
    for entry in chronological:
        elapsed = (entry.recorded_at - start).total_seconds()
        x = round(12 + 376 * elapsed / duration, 2) if duration else 12
        if previous is not None:
            path.append(f"H{x}")
        if entry.new_price is None:
            previous = None
            continue
        y = round(12 + 76 * float((high - entry.new_price) / (high - low)), 2) if high != low else 50
        path.append(f"V{y}" if previous is not None else f"M{x},{y}")
        points.append((x, y))
        previous = entry
    return " ".join(path), points


def price_history_context(prop):
    history = list(prop.price_history.all()) if prop else []
    chart_path, chart_markers = chart_points(history)
    return {
        "price_changes": [entry for entry in history if entry.kind == PriceHistory.Kind.CHANGE],
        "price_origin": next((entry for entry in history if entry.kind != PriceHistory.Kind.CHANGE), None),
        "chart_path": chart_path,
        "chart_markers": chart_markers,
        "chart_start": history[-1].recorded_at if history else None,
        "chart_end": history[0].recorded_at if len(history) > 1 else None,
    }
