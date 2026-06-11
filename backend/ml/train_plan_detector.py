"""EXPERIMENTAL training entry point for a future Keras 3 plan detector.

This script is deliberately not imported by the API server. It validates the
annotation schema and leaves model architecture selection to the project team,
because detector choice depends on the available labelled dataset.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

try:
    from .keras_adapter import dependency_status
except ImportError:  # direct script execution
    from keras_adapter import dependency_status

REQUIRED = {
    "image_file", "class_name", "x_min", "y_min", "x_max", "y_max", "level",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--annotations", required=True, type=Path)
    parser.add_argument("--images", required=True, type=Path)
    args = parser.parse_args()
    with args.annotations.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = REQUIRED - set(reader.fieldnames or [])
        if missing:
            raise SystemExit(f"missing annotation columns: {sorted(missing)}")
        rows = list(reader)
    print(f"validated {len(rows)} annotations in {args.annotations}")
    print("adapter status:", dependency_status())
    print("Next: select a KerasHub/KerasCV detector, create tf.data/torch/jax "
          "batches, fine-tune, evaluate, and export a Keras serving model.")


if __name__ == "__main__":
    main()
