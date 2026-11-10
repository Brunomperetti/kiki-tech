"""Validate an offline pilot plan; never initialize app/DB, resolve DNS or fetch URLs."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from integration_sandbox.pilot_policy import PilotPlan  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    args = parser.parse_args()
    try:
        if args.plan.stat().st_size > 65536:
            raise ValueError
        plan = PilotPlan.model_validate_json(args.plan.read_bytes())
        for source in plan.sources:
            plan.source_for(source.ecomm_ids[0], source.urls[0])
    except Exception:
        # Do not echo untrusted document data, URLs or validation input.
        parser.exit(
            1,
            "Plan inválido. Revisá esquema, alcance, evidencia, fechas y límites. No se habilitó red.\n",
        )
    print(
        f"Plan válido: {len(plan.products)} productos y {len(plan.sources)} dominios. Red real DESACTIVADA; no se ejecutaron consultas."
    )


if __name__ == "__main__":
    main()
