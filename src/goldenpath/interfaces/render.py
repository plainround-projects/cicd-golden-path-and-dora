"""Text tables for the command line: plain, aligned, no dependencies."""

from __future__ import annotations

from collections.abc import Sequence

from goldenpath.domain.metrics import ServiceMetrics


def _fmt(value: float | None, unit: str, digits: int = 1) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}{unit}"


def metrics_table(rows: Sequence[ServiceMetrics], weekly: bool = False) -> str:
    """The lesson's table: deploys per week, median lead time, change fail rate, recovery time, per service."""
    header = [
        "service",
        "deploys/week",
        "median lead time",
        "change fail rate",
        "recovery time",
        "batch",
        "empty",
        "open",
        "refused",
    ]
    body = []
    for row in rows:
        body.append(
            [
                row.service,
                f"{row.deploys_per_week:.1f}" if weekly else f"{row.deploys_per_week:g}",
                _fmt(row.median_lead_time_hours, " h"),
                "n/a" if row.change_fail_rate is None else f"{row.change_fail_rate:.0%}",
                _fmt(row.median_recovery_minutes, " min", 0),
                _fmt(row.median_batch_size, "", 1),
                str(row.empty_deploys),
                str(row.open_failures),
                str(row.refused),
            ]
        )
    widths = [max(len(line[index]) for line in [header, *body]) for index in range(len(header))]
    lines = [
        "  ".join(cell.ljust(width) for cell, width in zip(line, widths, strict=True)).rstrip()
        for line in [header, *body]
    ]
    return "\n".join(lines)
