#!/usr/bin/env bash
# One-command taster for the Raptor residual decision layer.
# Creates a fresh stack, runs a short scenario, and prints the decision.

set -e
cd "$(dirname "$0")"

echo "=== Raptor Residual — one-command taster ==="
echo "Initialising clean 33-engine stack..."
python demo.py init

echo
echo "--- Scenario ---"
python demo.py check R7 --twin 0.85
python demo.py gap R12 --hours 4
python demo.py anomaly R5
python demo.py sensors R9 --pressure 450 --rpm 35000 --temp 40

echo
echo "--- Stack decision ---"
python demo.py status -v

echo
echo "--- Recent decision log ---"
python demo.py log -n 6

echo
python demo.py report
echo
echo "Taster complete. Full static fire is required because of the anomaly and hard-limit sensor reading."
echo "Files written: stack.json  decisions.jsonl  report.json"
