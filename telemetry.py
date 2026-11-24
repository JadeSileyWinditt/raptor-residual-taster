"""
Lightweight telemetry adapter for the Raptor residual decision layer.

Accepts a simple JSON stream of sensor readings and feeds them through
the existing isolated-check / sensor path. Missing history remains never an error.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

from raptor_residual import (
    EngineStack,
    SensorObservation,
    evaluate_sensors,
    isolated_check,
    update_with_gap,
    DecisionLog,
    now_utc,
)


def load_stream(path: Path) -> List[Dict]:
    """Load a JSON list of sensor events."""
    data = json.loads(path.read_text())
    if not isinstance(data, list):
        raise ValueError("Telemetry stream must be a JSON list of events")
    return data


def apply_telemetry_stream(
    stack: EngineStack,
    events: List[Dict],
    log: Optional[DecisionLog] = None,
) -> EngineStack:
    """
    Apply a sequence of sensor events to the stack.
    Each event is a dict with at least:
      - engine_id
      - optional: pressure, rpm, temp, twin, gap_hours
    """
    for ev in events:
        engine_id = ev.get("engine_id") or ev.get("engine")
        if not engine_id:
            continue
        eng = stack.get_or_create(engine_id)

        # Optional explicit gap
        if "gap_hours" in ev and ev["gap_hours"]:
            update_with_gap(eng, gap_seconds=float(ev["gap_hours"]) * 3600)

        # Sensor reading
        obs = SensorObservation(
            chamber_pressure_bar=float(ev.get("pressure", 300)),
            turbopump_rpm=float(ev.get("rpm", 35000)),
            temperature_c=float(ev.get("temp", 40)),
        )
        anomaly, burn, reason = evaluate_sensors(obs)
        twin = float(ev.get("twin", 0.0))

        isolated_check(
            eng,
            observation_ok=not anomaly,
            digital_twin_agreement=twin,
            anomaly_detected=anomaly,
            burn_missing_increment=burn,
        )

        if log:
            log.append(eng, "telemetry", reason or f"twin={twin}")

    return stack


def sample_stream() -> List[Dict]:
    """Small example stream for the taster."""
    return [
        {"engine_id": "R7", "pressure": 300, "rpm": 35000, "temp": 40, "twin": 0.85},
        {"engine_id": "R12", "gap_hours": 3.0, "pressure": 310, "rpm": 34800, "temp": 42},
        {"engine_id": "R5", "pressure": 450, "rpm": 35000, "temp": 40},
        {"engine_id": "R9", "pressure": 280, "rpm": 20000, "temp": 90},
        {"engine_id": "R20", "pressure": 305, "rpm": 35100, "temp": 41, "twin": 0.4},
    ]
