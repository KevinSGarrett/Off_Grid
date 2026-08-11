# Scripts

Wave 1 provides reusable pack automation:
- `build_wave_packs.py` builds cumulative + hydration archives.
- `verify_wave_packs.py` independently validates a produced archive.
- `packlib.py` contains shared exclusion/checksum/ZIP/Git-state logic.

Later operational scripts (inbox ingestion, demo seed/reset, synthetic generation) are added only when the underlying domain/application exists.

## Wave 7

`analyze_wave07_account.py` ingests the two private golden PDFs into an ephemeral database, runs the Wave 6 Stafford assessment and Wave 7 project/account/entity resolution, then emits a JSON snapshot without making external calls.

- `analyze_wave09_commercial_motion.py` — reconstructs the real Stafford golden path through Waves 5–9 and emits the deterministic dual-motion/NBA/First-Call/outcome-feedback snapshot.
