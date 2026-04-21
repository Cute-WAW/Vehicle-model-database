from pathlib import Path
from typing import Dict


def get_project_root() -> Path:
    """Return the project root directory."""
    return Path(__file__).resolve().parent.parent


def get_model_dirs(project_root: Path = None) -> Dict[str, Path]:
    """
    Return the canonical model directories shared by training and prediction.

    Prediction currently loads models from `output/...`. Training and rebuild
    scripts should use the same directories to avoid silent divergence.
    """
    root = project_root or get_project_root()
    return {
        "brand_series": root / "output" / "brand_series_models",
        "car_types": root / "output" / "car_types_models",
        "segmented": root / "output" / "segmented_models",
        "lightgbm_root": root / "output" / "lightgbm",
        "lightgbm_brand_series": root / "output" / "lightgbm" / "brand_series_models",
        "lightgbm_car_types": root / "output" / "lightgbm" / "car_types_models",
        "lightgbm_reports": root / "output" / "lightgbm" / "reports",
    }
