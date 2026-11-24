"""
Modular residual confidence verification for Raptor-style engines.

Explicit decision layer:
- Persistent residual confidence per engine
- Integrity field that only drops on clear anomaly or contradiction
- Missing history is never an error
- Isolated checks and DigitalTwin agreement can stand in for full static fire
- JSON persistence and multi-engine stack aggregation
"""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional, Dict, List
from enum import Enum
from pathlib import Path


class IntegrityState(Enum):
    INTACT = "intact"
    DROPPED = "dropped"


@dataclass
class EngineResidual:
    engine_id: str
    residual_confidence: float = 1.0
    integrity: IntegrityState = IntegrityState.INTACT
    last_confirmation: Optional[datetime] = None
    burn_missing_box: float = 0.0
    burn_missing_limit: float = 1.0
    history_gaps: int = 0
    fire_threshold: float = 0.3
    decay_per_day: float = 0.04
    twin_boost_threshold: float = 0.7

    def to_dict(self) -> Dict:
        return {
            "engine_id": self.engine_id,
            "residual_confidence": self.residual_confidence,
            "integrity": self.integrity.value,
            "last_confirmation": self.last_confirmation.isoformat() if self.last_confirmation else None,
            "burn_missing_box": self.burn_missing_box,
            "burn_missing_limit": self.burn_missing_limit,
            "history_gaps": self.history_gaps,
            "fire_threshold": self.fire_threshold,
            "decay_per_day": self.decay_per_day,
            "twin_boost_threshold": self.twin_boost_threshold,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "EngineResidual":
        last_conf = None
        if data.get("last_confirmation"):
            last_conf = datetime.fromisoformat(data["last_confirmation"])
        return cls(
            engine_id=data["engine_id"],
            residual_confidence=data.get("residual_confidence", 1.0),
            integrity=IntegrityState(data.get("integrity", "intact")),
            last_confirmation=last_conf,
            burn_missing_box=data.get("burn_missing_box", 0.0),
            burn_missing_limit=data.get("burn_missing_limit", 1.0),
            history_gaps=data.get("history_gaps", 0),
            fire_threshold=data.get("fire_threshold", 0.3),
            decay_per_day=data.get("decay_per_day", 0.04),
            twin_boost_threshold=data.get("twin_boost_threshold", 0.7),
        )


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def update_with_gap(residual: EngineResidual, gap_seconds: float = 0.0) -> EngineResidual:
    residual.history_gaps += 1
    if gap_seconds > 3600:
        residual.residual_confidence = max(0.0, residual.residual_confidence - 0.05)
    return residual


def isolated_check(
    residual: EngineResidual,
    observation_ok: bool = True,
    digital_twin_agreement: float = 0.0,
    anomaly_detected: bool = False,
    burn_missing_increment: float = 0.0,
) -> EngineResidual:
    residual.last_confirmation = now_utc()
    if anomaly_detected:
        residual.integrity = IntegrityState.DROPPED
        residual.residual_confidence = 0.0
        return residual
    residual.burn_missing_box += burn_missing_increment
    if residual.burn_missing_box > residual.burn_missing_limit:
        residual.integrity = IntegrityState.DROPPED
        residual.residual_confidence = 0.0
        return residual
    if digital_twin_agreement >= residual.twin_boost_threshold and observation_ok:
        residual.residual_confidence = min(1.0, residual.residual_confidence + 0.15)
        residual.integrity = IntegrityState.INTACT
    elif observation_ok:
        residual.residual_confidence = min(1.0, residual.residual_confidence + 0.05)
        residual.integrity = IntegrityState.INTACT
    else:
        residual.residual_confidence = max(0.0, residual.residual_confidence - 0.1)
    return residual


def apply_time_decay(residual: EngineResidual, now: Optional[datetime] = None) -> EngineResidual:
    if residual.integrity == IntegrityState.DROPPED or residual.last_confirmation is None:
        return residual
    now = now or now_utc()
    elapsed_days = (now - residual.last_confirmation).total_seconds() / 86400.0
    if elapsed_days > 0:
        residual.residual_confidence = max(0.0, residual.residual_confidence - residual.decay_per_day * elapsed_days)
    return residual


def needs_full_static_fire(residual: EngineResidual) -> bool:
    return residual.integrity == IntegrityState.DROPPED or residual.residual_confidence < residual.fire_threshold


class DigitalTwin:
    def __init__(self, fixed_agreement: Optional[float] = None, noise: float = 0.05):
        self.fixed_agreement = fixed_agreement
        self.noise = noise

    def agreement(self, engine_id: str, observation: Optional[dict] = None) -> float:
        if self.fixed_agreement is not None:
            return max(0.0, min(1.0, self.fixed_agreement))
        base = 0.75 + (hash(engine_id) % 20 - 10) / 100.0
        return max(0.0, min(1.0, base))


@dataclass
class SensorObservation:
    chamber_pressure_bar: Optional[float] = None
    turbopump_rpm: Optional[float] = None
    temperature_c: Optional[float] = None
    chamber_pressure_range: tuple = (250.0, 350.0)
    turbopump_rpm_range: tuple = (30000.0, 40000.0)
    temperature_range: tuple = (-50.0, 120.0)


def evaluate_sensors(obs: SensorObservation) -> tuple:
    reasons = []
    anomaly = False
    burn = 0.0

    def check(name: str, value: Optional[float], low: float, high: float):
        nonlocal anomaly, burn
        if value is None:
            return
        if value < low * 0.8 or value > high * 1.2:
            anomaly = True
            reasons.append(f"{name} hard limit")
        elif value < low or value > high:
            burn += 0.2
            reasons.append(f"{name} soft limit")

    check("chamber_pressure", obs.chamber_pressure_bar, *obs.chamber_pressure_range)
    check("turbopump_rpm", obs.turbopump_rpm, *obs.turbopump_rpm_range)
    check("temperature", obs.temperature_c, *obs.temperature_range)

    reason = "; ".join(reasons) if reasons else "all sensors nominal"
    return anomaly, burn, reason


def reset_after_static_fire(residual: EngineResidual) -> EngineResidual:
    residual.integrity = IntegrityState.INTACT
    residual.residual_confidence = 1.0
    residual.burn_missing_box = 0.0
    residual.last_confirmation = now_utc()
    return residual


@dataclass
class DecisionEvent:
    timestamp: str
    engine_id: str
    action: str
    detail: str
    residual_after: float
    integrity_after: str
    force_fire: bool

    def to_dict(self) -> Dict:
        return asdict(self)


class DecisionLog:
    def __init__(self, path: str | Path = "decisions.jsonl"):
        self.path = Path(path)

    def append(self, residual: EngineResidual, action: str, detail: str) -> None:
        event = DecisionEvent(
            timestamp=now_utc().isoformat(),
            engine_id=residual.engine_id,
            action=action,
            detail=detail,
            residual_after=round(residual.residual_confidence, 4),
            integrity_after=residual.integrity.value,
            force_fire=needs_full_static_fire(residual),
        )
        with self.path.open("a") as f:
            f.write(json.dumps(event.to_dict()) + "\n")

    def recent(self, n: int = 20) -> List[Dict]:
        if not self.path.exists():
            return []
        lines = self.path.read_text().strip().splitlines()
        return [json.loads(line) for line in lines[-n:]]


@dataclass
class EngineStack:
    engines: Dict[str, EngineResidual] = field(default_factory=dict)
    min_healthy: int = 30

    def get_or_create(self, engine_id: str) -> EngineResidual:
        if engine_id not in self.engines:
            self.engines[engine_id] = EngineResidual(engine_id=engine_id)
        return self.engines[engine_id]

    def healthy_count(self) -> int:
        return sum(1 for eng in self.engines.values() if not needs_full_static_fire(eng))

    def needs_full_static_fire(self) -> bool:
        if not self.engines:
            return False
        if any(needs_full_static_fire(eng) for eng in self.engines.values()):
            return True
        return self.healthy_count() < self.min_healthy

    def engines_requiring_fire(self) -> List[str]:
        return [eid for eid, eng in self.engines.items() if needs_full_static_fire(eng)]

    def summary(self) -> Dict:
        return {
            "total_engines": len(self.engines),
            "healthy_engines": self.healthy_count(),
            "min_healthy": self.min_healthy,
            "requires_full_static_fire": self.needs_full_static_fire(),
            "engines_requiring_fire": self.engines_requiring_fire(),
            "min_residual": min((e.residual_confidence for e in self.engines.values()), default=1.0),
        }

    def to_dict(self) -> Dict:
        return {eid: eng.to_dict() for eid, eng in self.engines.items()}

    @classmethod
    def from_dict(cls, data: Dict) -> "EngineStack":
        stack = cls()
        for eid, eng_data in data.items():
            stack.engines[eid] = EngineResidual.from_dict(eng_data)
        return stack

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2))

    @classmethod
    def load(cls, path: str | Path) -> "EngineStack":
        path = Path(path)
        if not path.exists():
            return cls()
        return cls.from_dict(json.loads(path.read_text()))
