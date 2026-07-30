import json
import pickle
import time
import warnings

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.metrics import (
    average_precision_score,
    f1_score,
    log_loss,
    precision_score,
    recall_score,
    roc_auc_score,
)

warnings.filterwarnings("ignore")
torch.manual_seed(42)
np.random.seed(42)

ROOT = "/mnt/user-data/uploads/SKN-2nd-2team"

print("=== 1. 데이터 로딩 ===")
t0 = time.time()
df = pd.read_csv(f"{ROOT}/data/processed/model_table_final.csv")
print(f"로딩 완료: {df.shape}, {time.time()-t0:.1f}s")

with open(f"{ROOT}/models/ohe_scaler.pkl", "rb") as f:
    prep = pickle.load(f)
encoder = prep["encoder"]
scaler = prep["scaler"]
numeric_cols = prep["numeric_cols"]
categorical_cols = prep["categorical_cols"]

with open(f"{ROOT}/models/best_params.json") as f:
    lgbm_meta = json.load(f)

print("=== 2. 전처리 (기존 ohe_scaler.pkl 재사용) ===")
# city/registered_via는 encoder가 -999를 결측 카테고리로 학습해뒀으므로 NaN -> -999
cat_df = df[categorical_cols].copy()
cat_df["city"] = cat_df["city"].fillna(-999).astype(int)
cat_df["registered_via"] = cat_df["registered_via"].fillna(-999).astype(int)
cat_df["gender"] = cat_df["gender"].fillna("unknown")

X_cat = encoder.transform(cat_df)
if hasattr(X_cat, "toarray"):
    X_cat = X_cat.toarray()
X_num_raw = df[numeric_cols].fillna(0).values
# scaler는 numeric+onehot을 이어붙인 68차원 전체에 대해 fit되어 있음 (기존 파이프라인과 동일하게 재사용)
X_concat = np.hstack([X_num_raw, X_cat]).astype(np.float64)
X_all = scaler.transform(X_concat).astype(np.float32)
y_all = df["is_churn"].values.astype(np.float32)
split = df["split"].values

feature_dim = X_all.shape[1]
print(f"피처 차원: {feature_dim} (numeric {len(numeric_cols)} + onehot {X_cat.shape[1]})")

idx_train = split == "train"
idx_valid = split == "valid"
idx_test = split == "test"

X_train, y_train = X_all[idx_train], y_all[idx_train]
X_valid, y_valid = X_all[idx_valid], y_all[idx_valid]
X_test, y_test = X_all[idx_test], y_all[idx_test]
print(f"train {X_train.shape}, valid {X_valid.shape}, test {X_test.shape}")

device = torch.device("cpu")


class ChurnMLP(nn.Module):
    def __init__(self, in_dim):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(in_dim, 128),
            nn.BatchNorm1d(128),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(128, 64),
            nn.BatchNorm1d(64),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(64, 32),
            nn.ReLU(),
            nn.Linear(32, 1),
        )

    def forward(self, x):
        return self.net(x).squeeze(-1)


model = ChurnMLP(feature_dim).to(device)

pos = y_train.sum()
neg = len(y_train) - pos
pos_weight = torch.tensor([neg / pos], dtype=torch.float32)
criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weight)
optimizer = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-5)
scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode="max", factor=0.5, patience=2)

X_train_t = torch.from_numpy(X_train)
y_train_t = torch.from_numpy(y_train)
X_valid_t = torch.from_numpy(X_valid)
X_test_t = torch.from_numpy(X_test)

train_ds = torch.utils.data.TensorDataset(X_train_t, y_train_t)
train_loader = torch.utils.data.DataLoader(train_ds, batch_size=4096, shuffle=True)

print("=== 3. 학습 ===")
best_auc = -1
best_state = None
patience, bad_epochs = 6, 0
max_epochs = 40

for epoch in range(1, max_epochs + 1):
    model.train()
    total_loss = 0.0
    for xb, yb in train_loader:
        optimizer.zero_grad()
        out = model(xb)
        loss = criterion(out, yb)
        loss.backward()
        optimizer.step()
        total_loss += loss.item() * len(xb)
    total_loss /= len(train_ds)

    model.eval()
    with torch.no_grad():
        valid_logits = model(X_valid_t).numpy()
    valid_proba = 1 / (1 + np.exp(-valid_logits))
    valid_auc = roc_auc_score(y_valid, valid_proba)
    scheduler.step(valid_auc)

    improved = valid_auc > best_auc
    if improved:
        best_auc = valid_auc
        best_state = {k: v.clone() for k, v in model.state_dict().items()}
        bad_epochs = 0
    else:
        bad_epochs += 1

    print(f"epoch {epoch:02d}  train_loss={total_loss:.4f}  valid_auc={valid_auc:.4f}"
          f"{'  *best*' if improved else ''}")

    if bad_epochs >= patience:
        print(f"early stopping at epoch {epoch} (best valid_auc={best_auc:.4f})")
        break

model.load_state_dict(best_state)
model.eval()

print("=== 4. 평가 ===")


def get_proba(X_t):
    with torch.no_grad():
        logits = model(X_t).numpy()
    return 1 / (1 + np.exp(-logits))


proba_train = get_proba(X_train_t)
proba_valid = get_proba(X_valid_t)
proba_test = get_proba(X_test_t)

# F1-최적 threshold: valid에서 결정 후 전 split에 동일 적용 (기존 파이프라인과 동일 방식)
thresholds = np.linspace(0.01, 0.99, 197)
f1s = [f1_score(y_valid, (proba_valid >= t).astype(int)) for t in thresholds]
best_threshold = float(thresholds[int(np.argmax(f1s))])
print(f"F1-최적 threshold (valid 기준): {best_threshold:.4f}")

rows = []
for name, y_true, proba in [
    ("valid", y_valid, proba_valid),
    ("test", y_test, proba_test),
    ("train", y_train, proba_train),
]:
    pred = (proba >= best_threshold).astype(int)
    rows.append({
        "model": "DeepLearning_MLP",
        "split": name,
        "auc": roc_auc_score(y_true, proba),
        "pr_auc": average_precision_score(y_true, proba),
        "logloss": log_loss(y_true, proba, labels=[0, 1]),
        "threshold": best_threshold,
        "precision": precision_score(y_true, pred),
        "recall": recall_score(y_true, pred),
        "f1": f1_score(y_true, pred),
    })

result_df = pd.DataFrame(rows)
print(result_df.to_string(index=False))

result_df.to_csv("/home/claude/dl_model_result.csv", index=False)
torch.save(model.state_dict(), "/home/claude/churn_mlp.pt")
with open("/home/claude/dl_model_meta.json", "w") as f:
    json.dump({
        "feature_dim": feature_dim,
        "architecture": "128-64-32-1 MLP, BatchNorm+Dropout, BCEWithLogitsLoss(pos_weight)",
        "best_valid_auc": best_auc,
        "best_threshold": best_threshold,
        "epochs_trained": epoch,
    }, f, indent=2)

print("완료. dl_model_result.csv / churn_mlp.pt / dl_model_meta.json 저장됨")
