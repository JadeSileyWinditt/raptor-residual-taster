#!/usr/bin/env python3
"""
One-command demo / CLI for the Raptor residual confidence decision layer.

Usage examples:
  python demo.py init
  python demo.py check R7 --twin 0.82
  python demo.py gap R12 --hours 3
  python demo.py anomaly R5
  python demo.py status
"""

import argparse
import json
from pathlib import Path

from raptor_residual import (
    EngineStack,
    isolated_check,
    update_with_gap,
    reset_after_static_fire,
    DigitalTwin,
    apply_time_decay,
    DecisionLog,
    now_utc,
    SensorObservation,
    evaluate_sensors,
    needs_full_static_fire,
)
from telemetry import load_stream, apply_telemetry_stream

DEFAULT_STACK = Path("stack.json")
DEFAULT_LOG = Path("decisions.jsonl")

def get_log(path: Path) -> DecisionLog:
    return DecisionLog(path.with_name("decisions.jsonl") if path.name == "stack.json" else path.with_suffix(".jsonl"))

def load_stack(path: Path) -> EngineStack:
    return EngineStack.load(path)

def save_stack(stack: EngineStack, path: Path) -> None:
    stack.save(path)
    print(f"Saved stack to {path}")

def cmd_init(args):
    stack = EngineStack()
    for i in range(1, 34):
        stack.get_or_create(f"R{i}")
    save_stack(stack, args.file)
    print(f"Initialised 33-engine stack at {args.file}")

def cmd_check(args):
    stack = load_stack(args.file)
    log = get_log(args.file)
    eng = stack.get_or_create(args.engine)
    twin_score = args.twin
    if args.use_twin and twin_score == 0.0:
        twin = DigitalTwin()
        twin_score = twin.agreement(args.engine)
        print(f"DigitalTwin agreement for {args.engine}: {twin_score:.2f}")
    isolated_check(
        eng,
        observation_ok=not args.bad,
        digital_twin_agreement=twin_score,
        anomaly_detected=False,
        burn_missing_increment=args.burn,
    )
    log.append(eng, "check", f"twin={twin_score:.2f} bad={args.bad} burn={args.burn}")
    save_stack(stack, args.file)
    fire = eng.integrity.value == "dropped" or eng.residual_confidence < eng.fire_threshold
    print(f"{args.engine}: confidence={eng.residual_confidence:.2f} integrity={eng.integrity.value} "
          f"{'→ FORCE FIRE' if fire else '→ residual OK'}")

def cmd_sensors(args):
    stack = load_stack(args.file)
    log = get_log(args.file)
    eng = stack.get_or_create(args.engine)
    obs = SensorObservation(
        chamber_pressure_bar=args.pressure,
        turbopump_rpm=args.rpm,
        temperature_c=args.temp,
    )
    anomaly, burn, reason = evaluate_sensors(obs)
    twin_score = args.twin
    isolated_check(
        eng,
        observation_ok=not anomaly,
        digital_twin_agreement=twin_score,
        anomaly_detected=anomaly,
        burn_missing_increment=burn,
    )
    log.append(eng, "sensors", reason)
    save_stack(stack, args.file)
    fire = needs_full_static_fire(eng)
    print(f"{args.engine}: {reason}")
    print(f"  confidence={eng.residual_confidence:.2f} integrity={eng.integrity.value} "
          f"{'→ FORCE FIRE' if fire else '→ residual OK'}")

def cmd_gap(args):
    stack = load_stack(args.file)
    log = get_log(args.file)
    eng = stack.get_or_create(args.engine)
    seconds = args.hours * 3600
    update_with_gap(eng, gap_seconds=seconds)
    log.append(eng, "gap", f"hours={args.hours}")
    save_stack(stack, args.file)
    print(f"{args.engine}: recorded gap of {args.hours}h (history_gaps={eng.history_gaps}, "
          f"confidence={eng.residual_confidence:.2f}) — missing history is never an error")

def cmd_anomaly(args):
    stack = load_stack(args.file)
    log = get_log(args.file)
    eng = stack.get_or_create(args.engine)
    isolated_check(eng, anomaly_detected=True)
    log.append(eng, "anomaly", "forced drop")
    save_stack(stack, args.file)
    print(f"{args.engine}: anomaly detected → integrity DROPPED → full static fire required")

def cmd_log(args):
    log = get_log(args.file)
    events = log.recent(args.n)
    if not events:
        print("No decision events yet.")
        return
    for e in events:
        print(f"{e['timestamp'][:19]}  {e['engine_id']:4}  {e['action']:8}  "
              f"conf={e['residual_after']:.2f}  {e['integrity_after']:7}  "
              f"{'FORCE' if e['force_fire'] else 'ok'}  {e['detail']}")

def cmd_telemetry(args):
    stack = load_stack(args.file)
    log = get_log(args.file)
    events = load_stream(args.stream)
    apply_telemetry_stream(stack, events, log)
    save_stack(stack, args.file)
    print(f"Applied {len(events)} telemetry events from {args.stream}")
    print("--- Stack decision ---")
    # Reuse status logic
    summary = stack.summary()
    print(f"Total engines: {summary['total_engines']}")
    print(f"Healthy engines: {summary['healthy_engines']} (minimum {summary['min_healthy']})")
    print(f"Full static fire required: {'YES' if summary['requires_full_static_fire'] else 'NO'}")
    if summary["engines_requiring_fire"]:
        print("Engines requiring fire:", ", ".join(summary["engines_requiring_fire"]))

def cmd_report(args):
    stack = load_stack(args.file)
    for eng in stack.engines.values():
        apply_time_decay(eng)
    report = {
        "generated_at": now_utc().isoformat(),
        "stack_decision": stack.summary(),
        "engines": {eid: eng.to_dict() for eid, eng in stack.engines.items()},
    }
    out = args.file.with_name("report.json")
    out.write_text(json.dumps(report, indent=2))
    print(f"Report written to {out}")
    print(f"Full static fire required: {'YES' if report['stack_decision']['requires_full_static_fire'] else 'NO'}")
    if report["stack_decision"]["engines_requiring_fire"]:
        print("Engines requiring fire:", ", ".join(report["stack_decision"]["engines_requiring_fire"]))

def cmd_status(args):
    stack = load_stack(args.file)
    summary = stack.summary()
    print(f"Total engines: {summary['total_engines']}")
    print(f"Healthy engines: {summary['healthy_engines']} (minimum {summary['min_healthy']})")
    print(f"Full static fire required: {'YES' if summary['requires_full_static_fire'] else 'NO'}")
    if summary["engines_requiring_fire"]:
        print("Engines requiring fire:", ", ".join(summary["engines_requiring_fire"]))
    print(f"Lowest residual confidence: {summary['min_residual']:.2f}")
    if args.verbose:
        print("\nPer-engine:")
        for eid in sorted(stack.engines.keys(), key=lambda x: int(x[1:]) if x[1:].isdigit() else x):
            eng = stack.engines[eid]
            flag = "FORCE" if (eng.integrity.value == "dropped" or eng.residual_confidence < 0.3) else "ok"
            print(f"  {eid:4}  conf={eng.residual_confidence:.2f}  {eng.integrity.value:7}  gaps={eng.history_gaps}  [{flag}]")

def cmd_reset(args):
    stack = load_stack(args.file)
    log = get_log(args.file)
    eng = stack.get_or_create(args.engine)
    reset_after_static_fire(eng)
    log.append(eng, "reset", "after static fire")
    save_stack(stack, args.file)
    print(f"{args.engine}: reset after static fire → confidence=1.00 integrity=intact")

def main():
    parser = argparse.ArgumentParser(description="Raptor residual confidence CLI")
    parser.add_argument("--file", "-f", type=Path, default=DEFAULT_STACK, help="Stack JSON file (default: stack.json)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Create a fresh 33-engine stack")

    p_check = sub.add_parser("check", help="Run an isolated check on one engine")
    p_check.add_argument("engine")
    p_check.add_argument("--twin", type=float, default=0.0)
    p_check.add_argument("--use-twin", action="store_true")
    p_check.add_argument("--bad", action="store_true")
    p_check.add_argument("--burn", type=float, default=0.0)

    p_sensors = sub.add_parser("sensors", help="Run an isolated check from sensor readings")
    p_sensors.add_argument("engine")
    p_sensors.add_argument("--pressure", type=float)
    p_sensors.add_argument("--rpm", type=float)
    p_sensors.add_argument("--temp", type=float)
    p_sensors.add_argument("--twin", type=float, default=0.0)

    p_gap = sub.add_parser("gap", help="Record a telemetry gap (missing history is never an error)")
    p_gap.add_argument("engine")
    p_gap.add_argument("--hours", type=float, default=1.0)

    p_anom = sub.add_parser("anomaly", help="Force an anomaly → drop integrity")
    p_anom.add_argument("engine")

    p_reset = sub.add_parser("reset", help="Reset an engine after a real static fire")
    p_reset.add_argument("engine")

    p_status = sub.add_parser("status", help="Show stack-level decision")
    p_status.add_argument("-v", "--verbose", action="store_true")

    p_log = sub.add_parser("log", help="Show recent decision events")
    p_log.add_argument("-n", type=int, default=15)

    sub.add_parser("report", help="Write a machine-readable stack decision report")

    p_tel = sub.add_parser("telemetry", help="Apply a JSON sensor stream")
    p_tel.add_argument("stream", type=Path)

    args = parser.parse_args()

    cmds = {
        "init": cmd_init,
        "check": cmd_check,
        "sensors": cmd_sensors,
        "gap": cmd_gap,
        "anomaly": cmd_anomaly,
        "reset": cmd_reset,
        "status": cmd_status,
        "log": cmd_log,
        "report": cmd_report,
        "telemetry": cmd_telemetry,
    }
    cmds[args.command](args)

if __name__ == "__main__":
    main()
