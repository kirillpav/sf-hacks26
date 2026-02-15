"""Carbon loss estimation, tree replanting, and intervention scenario modeling.

Uses peer-reviewed estimates for tropical/temperate/boreal biomes:
- Carbon density: tC/ha from IPCC Tier 1 defaults
- Tree density: stems/ha typical for biome
- Regrowth: months to canopy recovery conditioned on biome + severity + intervention
"""

from __future__ import annotations

from app.models.schemas import Severity


# ── Biome parameters ─────────────────────────────────────────────────
# Each biome has: carbon_density (tC/ha), tree_density (trees/ha),
# base_regrowth_months (natural regen for LOW severity)

BIOME_PARAMS = {
    "tropical": {
        "carbon_density": 170.0,   # tC/ha, IPCC moist tropical
        "tree_density": 400,       # stems/ha
        "base_regrowth_months": 180,
    },
    "temperate": {
        "carbon_density": 120.0,
        "tree_density": 300,
        "base_regrowth_months": 240,
    },
    "boreal": {
        "carbon_density": 60.0,
        "tree_density": 200,
        "base_regrowth_months": 360,
    },
    "savanna": {
        "carbon_density": 30.0,
        "tree_density": 80,
        "base_regrowth_months": 120,
    },
}

# Severity multiplies base regrowth time
SEVERITY_REGROWTH_MULT = {
    Severity.LOW: 1.0,
    Severity.MEDIUM: 1.5,
    Severity.HIGH: 2.2,
}

# Intervention scenario multipliers (applied to regrowth months)
# Lower = faster recovery
INTERVENTION_MULTIPLIERS = {
    "natural_regeneration": {
        "regrowth_mult": 1.0,     # baseline — no human help
        "tree_survival": 0.6,     # natural seedling survival rate
        "cost_per_ha": 0,
        "label": "Natural Regeneration",
    },
    "assisted_planting": {
        "regrowth_mult": 0.6,     # 40% faster
        "tree_survival": 0.75,
        "cost_per_ha": 1200,      # USD
        "label": "Assisted Planting",
    },
    "intensive_restoration": {
        "regrowth_mult": 0.35,    # 65% faster
        "tree_survival": 0.88,
        "cost_per_ha": 3500,
        "label": "Intensive Restoration",
    },
}


def detect_biome(lat: float) -> str:
    """Simple latitude-based biome heuristic (MVP approximation)."""
    abs_lat = abs(lat)
    if abs_lat < 23.5:
        return "tropical"
    elif abs_lat < 45:
        return "temperate"
    elif abs_lat < 60:
        return "boreal"
    else:
        return "boreal"


def estimate_patch_impact(
    area_hectares: float,
    severity: Severity,
    ndvi_drop: float,
    lat: float,
    intervention: str = "natural_regeneration",
) -> dict:
    """Estimate carbon loss, trees to replant, and regrowth timeline for a patch.

    Returns dict with:
        biome, carbon_loss_tonnes, trees_to_replant, regrowth_months,
        intervention, cost_estimate_usd
    """
    biome = detect_biome(lat)
    params = BIOME_PARAMS[biome]
    interv = INTERVENTION_MULTIPLIERS.get(
        intervention, INTERVENTION_MULTIPLIERS["natural_regeneration"]
    )

    # Scale carbon loss by severity fraction (how much of the biomass was lost)
    severity_fraction = min(1.0, abs(ndvi_drop) / 0.8)
    carbon_loss = round(area_hectares * params["carbon_density"] * severity_fraction, 1)

    # Trees to replant: full replanting density, adjusted by survival rate
    raw_trees = area_hectares * params["tree_density"]
    trees_to_replant = int(raw_trees / interv["tree_survival"])

    # Regrowth months: base * severity * intervention
    sev_mult = SEVERITY_REGROWTH_MULT.get(severity, 1.5)
    regrowth = round(
        params["base_regrowth_months"] * sev_mult * interv["regrowth_mult"]
    )

    cost = round(area_hectares * interv["cost_per_ha"])

    return {
        "biome": biome,
        "carbon_loss_tonnes": carbon_loss,
        "trees_to_replant": trees_to_replant,
        "regrowth_months": regrowth,
        "intervention": intervention,
        "intervention_label": interv["label"],
        "cost_estimate_usd": cost,
    }


def compute_intervention_comparison(
    area_hectares: float,
    severity: Severity,
    ndvi_drop: float,
    lat: float,
) -> dict:
    """Compute all three intervention scenarios for comparison."""
    scenarios = {}
    for key in INTERVENTION_MULTIPLIERS:
        scenarios[key] = estimate_patch_impact(
            area_hectares, severity, ndvi_drop, lat, intervention=key
        )
    return scenarios


def aggregate_impact(patches_impact: list[dict]) -> dict:
    """Roll up per-patch impact into alert-level totals."""
    total_carbon = round(sum(p["carbon_loss_tonnes"] for p in patches_impact), 1)
    total_trees = sum(p["trees_to_replant"] for p in patches_impact)
    total_cost = sum(p["cost_estimate_usd"] for p in patches_impact)
    avg_regrowth = (
        round(sum(p["regrowth_months"] for p in patches_impact) / len(patches_impact))
        if patches_impact
        else 0
    )
    return {
        "total_carbon_loss_tonnes": total_carbon,
        "total_trees_to_replant": total_trees,
        "avg_regrowth_months": avg_regrowth,
        "total_cost_estimate_usd": total_cost,
    }
