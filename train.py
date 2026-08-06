"""LightGBM Enhanced v2 재학습 스크립트.

기존 최종 모델을 보호하기 위해 기본 출력은 retrained_* 파일을 사용한다.

실행 예시:
    python train.py
    python train.py --output models/retrained_lightgbm_enhanced_v2.txt
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    log_loss,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
)


PROJECT_ROOT = Path(__file__).resolve().parent
BASE_META_PATH = PROJECT_ROOT / "models" / "lightgbm_enhanced_v2_meta.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="KKBOX LightGBM Enhanced v2 재학습",
    )
    parser.add_argument("--input", type=Path, default=None)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("models/retrained_lightgbm_enhanced_v2.txt"),
    )
    parser.add_argument(
        "--meta-output",
        type=Path,
        default=Path("models/retrained_lightgbm_enhanced_v2_meta.json"),
    )
    parser.add_argument("--num-threads", type=int, default=0)
    return parser.parse_args()


def resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else PROJECT_ROOT / path


def calculate_metrics(y_true, probabilities, threshold: float) -> dict:
    predictions = (probabilities >= threshold).astype("int8")
    return {
        "auc": float(roc_auc_score(y_true, probabilities)),
        "pr_auc": float(average_precision_score(y_true, probabilities)),
        "logloss": float(log_loss(y_true, probabilities)),
        "precision": float(precision_score(y_true, predictions, zero_division=0)),
        "recall": float(recall_score(y_true, predictions, zero_division=0)),
        "f1": float(f1_score(y_true, predictions, zero_division=0)),
        "confusion_matrix": confusion_matrix(y_true, predictions).tolist(),
    }


def find_best_f1_threshold(y_true, probabilities) -> float:
    precision, recall, thresholds = precision_recall_curve(y_true, probabilities)
    f1 = 2 * precision[:-1] * recall[:-1] / (
        precision[:-1] + recall[:-1] + 1e-12
    )
    return float(thresholds[int(np.argmax(f1))])


def calculate_top_k(y_true, probabilities, fraction: float) -> dict:
    selected_count = max(1, int(len(y_true) * fraction))
    selected_index = np.argsort(probabilities)[-selected_count:]
    selected_target = np.asarray(y_true)[selected_index]
    precision = float(selected_target.mean())
    recall = float(selected_target.sum() / np.asarray(y_true).sum())
    base_rate = float(np.asarray(y_true).mean())
    return {
        "selected_count": selected_count,
        "precision": precision,
        "recall": recall,
        "lift": float(precision / base_rate),
    }


def main() -> None:
    args = parse_args()
    base_meta = json.loads(BASE_META_PATH.read_text(encoding="utf-8"))
    feature_cols = base_meta["feature_cols"]
    categorical_cols = base_meta["categorical_cols"]

    input_path = resolve_path(args.input) if args.input else (
        PROJECT_ROOT / "data" / "processed" / base_meta["source_table"]
    )
    output_path = resolve_path(args.output)
    meta_output_path = resolve_path(args.meta_output)

    required_cols = ["is_churn", "split", *feature_cols]
    header = pd.read_csv(input_path, nrows=0).columns.tolist()
    missing = [column for column in required_cols if column not in header]
    if missing:
        raise ValueError(f"학습 데이터에 필요한 컬럼이 없습니다: {missing}")

    print(f"데이터 로드: {input_path}")
    df = pd.read_csv(input_path, usecols=required_cols, low_memory=False)
    for column in categorical_cols:
        df[column] = df[column].astype("category")

    train_df = df[df["split"] == "train"]
    valid_df = df[df["split"] == "valid"]
    test_df = df[df["split"] == "test"]

    expected_sizes = {"train": 695051, "valid": 148940, "test": 148940}
    actual_sizes = {
        "train": len(train_df),
        "valid": len(valid_df),
        "test": len(test_df),
    }
    if actual_sizes != expected_sizes:
        raise ValueError(
            f"저장된 split 크기와 다릅니다: {actual_sizes}"
        )

    train_set = lgb.Dataset(
        train_df[feature_cols],
        label=train_df["is_churn"],
        categorical_feature=categorical_cols,
    )
    valid_set = lgb.Dataset(
        valid_df[feature_cols],
        label=valid_df["is_churn"],
        categorical_feature=categorical_cols,
        reference=train_set,
    )

    params = dict(base_meta["params"])
    if args.num_threads > 0:
        params["num_threads"] = args.num_threads

    model = lgb.train(
        params=params,
        train_set=train_set,
        num_boost_round=5000,
        valid_sets=[valid_set],
        valid_names=["valid"],
        callbacks=[
            lgb.early_stopping(100, first_metric_only=True),
            lgb.log_evaluation(100),
        ],
    )

    valid_probabilities = model.predict(
        valid_df[feature_cols],
        num_iteration=model.best_iteration,
    )
    threshold = find_best_f1_threshold(
        valid_df["is_churn"],
        valid_probabilities,
    )
    valid_metrics = calculate_metrics(
        valid_df["is_churn"],
        valid_probabilities,
        threshold,
    )

    test_probabilities = model.predict(
        test_df[feature_cols],
        num_iteration=model.best_iteration,
    )
    test_metrics = calculate_metrics(
        test_df["is_churn"],
        test_probabilities,
        threshold,
    )
    test_predictions = (test_probabilities >= threshold).astype("int8")
    selection_rate = float(test_predictions.mean())
    threshold_lift = float(test_metrics["precision"] / test_df["is_churn"].mean())

    output_path.parent.mkdir(parents=True, exist_ok=True)
    meta_output_path.parent.mkdir(parents=True, exist_ok=True)
    model.save_model(str(output_path), num_iteration=model.best_iteration)

    result_meta = {
        **base_meta,
        "model_name": "LightGBM enhanced v2 retrained",
        "best_iteration": int(model.best_iteration),
        "threshold": threshold,
        **{f"valid_{key}": value for key, value in valid_metrics.items()},
        **{f"test_{key}": value for key, value in test_metrics.items()},
        "test_selection_rate": selection_rate,
        "test_threshold_lift": threshold_lift,
        "top_5_percent": calculate_top_k(
            test_df["is_churn"], test_probabilities, 0.05
        ),
        "top_10_percent": calculate_top_k(
            test_df["is_churn"], test_probabilities, 0.10
        ),
    }
    meta_output_path.write_text(
        json.dumps(result_meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )

    print("\n재학습 완료")
    print(f"Best iteration: {model.best_iteration}")
    print(f"Threshold: {threshold:.6f}")
    print(f"Test ROC-AUC: {test_metrics['auc']:.6f}")
    print(f"Test PR-AUC: {test_metrics['pr_auc']:.6f}")
    print(f"Test F1: {test_metrics['f1']:.6f}")
    print(f"모델 저장: {output_path}")
    print(f"메타데이터 저장: {meta_output_path}")


if __name__ == "__main__":
    main()
