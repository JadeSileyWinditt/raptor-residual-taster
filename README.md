# Raptor Residual Decision Layer — Controlled Taster

One-command demonstration of a restart-safe residual confidence decision layer for Raptor-style engines.

## Core idea

- Persistent residual confidence per engine
- Integrity field drops only on clear anomaly or contradiction
- **Missing history is never an error**
- Isolated checks + DigitalTwin agreement (≥ 0.7) can stand in for a full static fire
- Stack-level rule (default: at least 30 of 33 healthy) forces a real test when too many engines are degraded

## Run the taster

```bash
bash setup_and_run.sh
```

It initialises a clean 33-engine stack, applies a short scenario (twin boost, gap, anomaly, hard-limit sensor reading), and prints the stack decision together with a recent decision log.

## Telemetry example

A sample sensor stream is included (`sample_stream.json`).  
The adapter accepts simple JSON events and feeds them through the same isolated-check path.

## License

Copyright © 2026 Jade Siley-Winditt. All rights reserved.

This taster is provided for evaluation only.  
The full implementation is **not open source**.  
Commercial licenses are available — contact for terms.

## Release Date

Prototype release scheduled for January 1, 2027.
