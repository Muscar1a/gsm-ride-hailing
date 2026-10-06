"""Validated configuration. Dates are local wall-clock dates, never implicit UTC."""

from __future__ import annotations

import dataclasses
import datetime as dt
import tomllib
from pathlib import Path
from typing import Any

DGPS = ("RCT_SYN", "OBSERVED_CONFOUNDING", "HIDDEN_CONFOUNDING", "NULL_EFFECT", "COLLINEAR_PRICE")
ESTIMATORS = ("naive_ols", "adjusted_ols", "dml")
TLC_SOURCE_VERSION = "NYC_TLC_HVFHV_2024-01"
TLC_SOURCE_START = "2024-01-01"
TLC_SOURCE_END = "2024-02-01"


@dataclasses.dataclass(frozen=True)
class ProjectConfig:
    name: str = "gsm-poc"
    context_mode: str = "synthetic"


@dataclasses.dataclass(frozen=True)
class SourceConfig:
    trip_url: str = "https://d37ci6vzurychx.cloudfront.net/trip-data/fhvhv_tripdata_2024-01.parquet"
    zone_url: str = "https://d37ci6vzurychx.cloudfront.net/misc/taxi_zone_lookup.csv"
    start: str = "2024-01-01"
    end: str = "2024-02-01"
    train_end: str = "2024-01-21"
    validation_end: str = "2024-01-26"
    dashboard_end: str = "2024-02-01"
    zones: tuple[int, ...] = (161, 162, 163, 164, 170)
    platforms: tuple[str, ...] = ("HV0003", "HV0005")
    slot_minutes: int = 30
    assumed_timezone: str = "America/New_York"
    min_group_count: int = 30
    duration_difference_warning_seconds: int = 60
    download_timeout_seconds: int = 60
    download_retries: int = 3
    max_download_bytes: int = 1_000_000_000
    duckdb_memory_limit: str = "4GB"
    threads: int = 4

    def require_tlc_scope(self) -> None:
        """Check the v0 monthly source contract, independently of observed trip dates."""
        lower, upper = map(dt.date.fromisoformat, (TLC_SOURCE_START, TLC_SOURCE_END))
        start, end, dashboard_end = map(
            dt.date.fromisoformat, (self.start, self.end, self.dashboard_end)
        )
        if not lower <= start < dashboard_end <= end <= upper:
            raise ValueError(
                "The v0 TLC adapter covers January 2024 only; source.start, source.end "
                f"and source.dashboard_end must stay within [{TLC_SOURCE_START}, {TLC_SOURCE_END}) "
                "with exclusive end dates"
            )


@dataclasses.dataclass(frozen=True)
class SimulationConfig:
    seed: int = 42
    dgp: str = "RCT_SYN"
    slot_minutes: int = 30
    sessions_per_block: int = 50


@dataclasses.dataclass(frozen=True)
class ModelConfig:
    estimators: tuple[str, ...] = ESTIMATORS
    scenario_estimator: str = "dml"
    folds: int = 5
    n_trees: int = 50
    max_depth: int = 6
    min_samples_leaf: int = 20
    min_price_cell_count: int = 20
    max_condition_number: float = 1000.0
    elasticity_min_probability: float = 0.01


@dataclasses.dataclass(frozen=True)
class EvaluationConfig:
    seeds: int = 3
    dgps: tuple[str, ...] = ("RCT_SYN", "OBSERVED_CONFOUNDING", "NULL_EFFECT")
    bootstrap_draws: int = 30
    reporting_min_draws: int = 199
    max_failure_fraction: float = 0.05
    interval_level: float = 0.95
    theta_rmse_target: float = 0.10
    probability_rmse_target: float = 0.02


@dataclasses.dataclass(frozen=True)
class ScenarioConfig:
    delta_price_x: float = 0.10
    delta_price_y: float = 0.0
    n_sessions: int = 10000


@dataclasses.dataclass(frozen=True)
class Config:
    workspace: Path
    project: ProjectConfig = dataclasses.field(default_factory=ProjectConfig)
    source: SourceConfig = dataclasses.field(default_factory=SourceConfig)
    simulation: SimulationConfig = dataclasses.field(default_factory=SimulationConfig)
    model: ModelConfig = dataclasses.field(default_factory=ModelConfig)
    evaluation: EvaluationConfig = dataclasses.field(default_factory=EvaluationConfig)
    scenario: ScenarioConfig = dataclasses.field(default_factory=ScenarioConfig)

    def __post_init__(self) -> None:
        if self.project.context_mode not in ("synthetic", "tlc"):
            raise ValueError("project.context_mode must be synthetic or tlc")
        dates = [
            dt.date.fromisoformat(getattr(self.source, k))
            for k in ("start", "train_end", "validation_end", "end")
        ]
        if not dates[0] < dates[1] < dates[2] < dates[3]:
            raise ValueError("Require start < train_end < validation_end < end")
        dashboard_end = dt.date.fromisoformat(self.source.dashboard_end)
        if not dates[0] < dashboard_end <= dates[3]:
            raise ValueError("dashboard_end must be inside the source date scope")
        if self.project.context_mode == "tlc":
            self.source.require_tlc_scope()
        if (dates[1] - dates[0]).days < self.model.folds:
            raise ValueError("Training must contain at least one original day per fold")
        if not self.source.zones or len(set(self.source.zones)) != len(self.source.zones):
            raise ValueError("source.zones must be nonempty and unique")
        if any(type(z) is not int or z <= 0 for z in self.source.zones):
            raise ValueError("Zone IDs must be positive integers")
        if not set(self.source.platforms) <= {"HV0003", "HV0005"}:
            raise ValueError("The v0 TLC adapter supports HV0003 and HV0005")
        if not self.source.platforms or len(set(self.source.platforms)) != len(
            self.source.platforms
        ):
            raise ValueError("source.platforms must be nonempty and unique")
        for minutes in (self.source.slot_minutes, self.simulation.slot_minutes):
            if type(minutes) is not int or minutes <= 0 or 1440 % minutes:
                raise ValueError("slot_minutes must be a positive integer dividing 1440")
        if self.simulation.dgp not in DGPS or not set(self.evaluation.dgps) <= set(DGPS):
            raise ValueError(f"DGP must be one of {DGPS}")
        if not self.model.estimators or not set(self.model.estimators) <= set(ESTIMATORS):
            raise ValueError(f"Estimators must be selected from {ESTIMATORS}")
        if self.model.scenario_estimator not in self.model.estimators:
            raise ValueError("scenario_estimator must be one of model.estimators")
        for name, value in (
            ("sessions_per_block", self.simulation.sessions_per_block),
            ("folds", self.model.folds),
            ("n_trees", self.model.n_trees),
            ("max_depth", self.model.max_depth),
            ("min_samples_leaf", self.model.min_samples_leaf),
            ("seeds", self.evaluation.seeds),
            ("reporting_min_draws", self.evaluation.reporting_min_draws),
            ("min_price_cell_count", self.model.min_price_cell_count),
            ("min_group_count", self.source.min_group_count),
            ("threads", self.source.threads),
            ("download_timeout_seconds", self.source.download_timeout_seconds),
            ("download_retries", self.source.download_retries),
            ("max_download_bytes", self.source.max_download_bytes),
            ("n_sessions", self.scenario.n_sessions),
        ):
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if self.model.folds < 2:
            raise ValueError("Cross-fitting needs at least two folds")
        if type(self.simulation.seed) is not int or self.simulation.seed < 0:
            raise ValueError("seed must be a nonnegative integer")
        if type(self.evaluation.bootstrap_draws) is not int or self.evaluation.bootstrap_draws < 0:
            raise ValueError("bootstrap_draws must be a nonnegative integer")
        if not 0 < self.evaluation.interval_level < 1:
            raise ValueError("interval_level must lie between 0 and 1")
        if not 0 <= self.evaluation.max_failure_fraction < 1:
            raise ValueError("max_failure_fraction must lie in [0, 1)")

    def as_dict(self) -> dict[str, Any]:
        value = dataclasses.asdict(self)
        value.pop("workspace")
        return value

    @classmethod
    def load(cls, path: str | Path) -> Config:
        path = Path(path).resolve()
        with path.open("rb") as stream:
            raw = tomllib.load(stream)
        root = path.parent.parent if path.parent.name == "configs" else Path.cwd()
        return cls.from_dict(raw, root)

    @classmethod
    def from_dict(cls, raw: dict[str, Any], workspace: Path) -> Config:
        section_types = {
            "project": ProjectConfig,
            "source": SourceConfig,
            "simulation": SimulationConfig,
            "model": ModelConfig,
            "evaluation": EvaluationConfig,
            "scenario": ScenarioConfig,
        }
        unknown = set(raw) - set(section_types)
        if unknown:
            raise ValueError(f"Unknown config sections: {sorted(unknown)}")
        sections = {}
        for name, section_type in section_types.items():
            values = dict(raw.get(name, {}))
            for key, value in values.items():
                if isinstance(value, list):
                    values[key] = tuple(value)
            try:
                sections[name] = section_type(**values)
            except TypeError as exc:
                raise ValueError(f"Invalid {name} configuration: {exc}") from exc
        return cls(workspace=workspace, **sections)
