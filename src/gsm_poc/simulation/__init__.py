"""Marketplace simulation, synthetic DGP generation, and demand planning."""

from __future__ import annotations

from gsm_poc.simulation.demand import DemandPlan, prepare_demand_plan, validate_snapshot
from gsm_poc.simulation.dgp import Generated, generate, save_generated
from gsm_poc.simulation.marketplace import (
    EVENT_COLUMNS,
    REQUEST_COLUMNS,
    VEHICLE_COLUMNS,
    SimulationResult,
    simulate_marketplace,
    simulate_marketplace_continuation,
    validate_carry_in,
    validate_rules,
)

__all__ = [
    "EVENT_COLUMNS",
    "REQUEST_COLUMNS",
    "VEHICLE_COLUMNS",
    "DemandPlan",
    "Generated",
    "SimulationResult",
    "generate",
    "prepare_demand_plan",
    "save_generated",
    "simulate_marketplace",
    "simulate_marketplace_continuation",
    "validate_carry_in",
    "validate_rules",
    "validate_snapshot",
]
