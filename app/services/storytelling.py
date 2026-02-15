"""Generate concise narrative briefings from alert data.

Produces ready-to-paste text for NGO reports and social media.
"""

from __future__ import annotations

from datetime import datetime, timedelta


def _format_area(ha: float) -> str:
    if ha >= 1000:
        return f"{ha/1000:.1f}k hectares"
    return f"{ha:.0f} hectares"


def _format_carbon(tonnes: float) -> str:
    if tonnes >= 1000:
        return f"{tonnes/1000:.1f}k tonnes"
    return f"{tonnes:.0f} tonnes"


def _months_to_date(months: int) -> str:
    target = datetime.utcnow() + timedelta(days=months * 30.4)
    return target.strftime("%B %Y")


def _months_to_human(months: int) -> str:
    if months >= 24:
        years = months / 12
        return f"{years:.1f} years"
    return f"{months} months"


def generate_narrative(
    patch_count: int,
    total_area_hectares: float,
    total_carbon_loss: float,
    total_trees: int,
    avg_regrowth_months: int,
    intervention_label: str,
    worst_severity: str,
    region_bbox: list[float],
    best_case_regrowth: int | None = None,
) -> str:
    """Build a single-paragraph narrative suitable for reports and social posts."""

    area_str = _format_area(total_area_hectares)
    carbon_str = _format_carbon(total_carbon_loss)
    recovery_date = _months_to_date(avg_regrowth_months)
    recovery_human = _months_to_human(avg_regrowth_months)

    # Location description
    lat = (region_bbox[1] + region_bbox[3]) / 2
    lon = (region_bbox[0] + region_bbox[2]) / 2
    lat_dir = "S" if lat < 0 else "N"
    lon_dir = "W" if lon < 0 else "E"
    location = f"{abs(lat):.1f}\u00b0{lat_dir}, {abs(lon):.1f}\u00b0{lon_dir}"

    parts = [
        f"Satellite analysis detected {patch_count} deforestation "
        f"{'patch' if patch_count == 1 else 'patches'} "
        f"totaling {area_str} near {location}.",
        f"The estimated carbon loss is {carbon_str} of CO\u2082, "
        f"with the most severe areas classified as {worst_severity} severity.",
        f"Under the \"{intervention_label}\" scenario, "
        f"an estimated {total_trees:,} trees would need to be planted, "
        f"with full canopy recovery projected by {recovery_date} "
        f"(~{recovery_human}).",
    ]

    if best_case_regrowth is not None and best_case_regrowth < avg_regrowth_months:
        best_date = _months_to_date(best_case_regrowth)
        best_human = _months_to_human(best_case_regrowth)
        parts.append(
            f"With intensive restoration, recovery could be accelerated to "
            f"{best_date} (~{best_human}), "
            f"a {round((1 - best_case_regrowth / avg_regrowth_months) * 100)}% improvement."
        )

    return " ".join(parts)
