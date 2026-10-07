from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ai_training import prepare_dataset, train_health_classifier


def main() -> None:
    print("[1/2] Preparing dataset with AD8232 ECG fields...")
    prepare_dataset.main()
    print("\n[2/2] Training classifier + Isolation Forest...")
    train_health_classifier.main()
    print("\nDone. Updated files in models/:")
    print("  - health_classifier.pkl")
    print("  - health_classifier_report.json")
    print("  - scaler.pkl")
    print("  - isolation_forest.pkl")
    print("  - model_info.json")


if __name__ == "__main__":
    main()
