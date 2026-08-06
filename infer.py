"""저장된 LightGBM Enhanced v2 모델로 샘플 고객을 추론한다.

실행 예시:
    python infer.py
    python infer.py --rows 5 --input data/processed/model_table_enhanced_v2.csv
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import lightgbm as lgb
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_MODEL = PROJECT_ROOT / "models" / "lightgbm_enhanced_v2.txt"
DEFAULT_META = PROJECT_ROOT / "models" / "lightgbm_enhanced_v2_meta.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="KKBOX 이탈 예측 모델 샘플 추론",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="입력 CSV 경로(기본값: 메타데이터의 source_table)",
    )
    parser.add_argument(
        "--rows",
        type=int,
        default=5,
        help="추론할 행 수(기본값: 5)",
    )
    parser.add_argument(
        "--model",
        type=Path,
        default=DEFAULT_MODEL,
        help="LightGBM 모델 경로",
    )
    parser.add_argument(
        "--meta",
        type=Path,
        default=DEFAULT_META,
        help="모델 메타데이터 경로",
    )
    return parser.parse_args()


def resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else PROJECT_ROOT / path


def load_artifacts(
    model_path: Path,
    meta_path: Path,
) -> tuple[lgb.Booster, dict]:
    model_path = resolve_path(model_path)
    meta_path = resolve_path(meta_path)

    if not model_path.exists():
        raise FileNotFoundError(f"모델 파일이 없습니다: {model_path}")
    if not meta_path.exists():
        raise FileNotFoundError(f"메타데이터가 없습니다: {meta_path}")

    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    model = lgb.Booster(model_file=str(model_path))

    feature_cols = metadata["feature_cols"]
    if model.feature_name() != feature_cols:
        raise ValueError("모델과 메타데이터의 피처 순서가 일치하지 않습니다.")

    return model, metadata


def prepare_sample(
    input_path: Path,
    rows: int,
    model: lgb.Booster,
    metadata: dict,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if rows < 1:
        raise ValueError("--rows는 1 이상의 정수여야 합니다.")

    input_path = resolve_path(input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"입력 CSV가 없습니다: {input_path}")

    feature_cols = metadata["feature_cols"]
    header = pd.read_csv(input_path, nrows=0).columns.tolist()
    missing = [column for column in feature_cols if column not in header]
    if missing:
        raise ValueError(f"입력 CSV에 필요한 피처가 없습니다: {missing}")

    id_cols = [column for column in ["msno", "is_churn", "split"] if column in header]
    sample = pd.read_csv(
        input_path,
        usecols=id_cols + feature_cols,
        nrows=rows,
        low_memory=False,
    )

    # LightGBM에 저장된 학습 당시 범주 순서를 그대로 적용한다.
    saved_categories = model.pandas_categorical or []
    categorical_cols = metadata["categorical_cols"]
    if len(saved_categories) != len(categorical_cols):
        raise ValueError("모델에 저장된 범주 정보와 메타데이터가 일치하지 않습니다.")

    for column, categories in zip(categorical_cols, saved_categories):
        sample[column] = pd.Categorical(
            sample[column],
            categories=categories,
        )

    return sample[id_cols].copy(), sample[feature_cols]


def main() -> None:
    args = parse_args()
    model, metadata = load_artifacts(args.model, args.meta)

    input_path = args.input
    if input_path is None:
        input_path = (
            PROJECT_ROOT
            / "data"
            / "processed"
            / metadata["source_table"]
        )

    identifiers, features = prepare_sample(
        input_path=input_path,
        rows=args.rows,
        model=model,
        metadata=metadata,
    )

    probabilities = model.predict(
        features,
        num_iteration=metadata["best_iteration"],
    )
    result = identifiers.copy()
    result["churn_probability"] = probabilities
    result["predicted_churn"] = (
        result["churn_probability"] >= metadata["threshold"]
    ).astype("int8")

    print(f"모델: {metadata['model_name']}")
    print(f"입력 피처: {len(metadata['feature_cols'])}개")
    print(f"판정 임계값: {metadata['threshold']:.6f}")
    print("\n샘플 추론 결과")
    print(result.to_string(index=False))


if __name__ == "__main__":
    main()
