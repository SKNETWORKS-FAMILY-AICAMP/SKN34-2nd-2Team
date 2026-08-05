# KKBOX 고객 이탈 예측 및 리텐션 운영 시스템

> 과거 고객 행동으로 구독 이탈 위험을 예측하고, 고객 선별부터 캠페인 실행과 고객 알림까지 연결한 End-to-End 데이터 프로젝트

## 팀명: 2Team

## 팀 소개

| 구분 | MoonSungHo | HyeongJjun | Genus-Jae | minhwan noh |
|:---:|:---:|:---:|:---:|:---:|
| 프로필 | <br><br><br><br><br> | <br><br><br><br><br> | <br><br><br><br><br> | <br><br><br><br><br> |
| 담당 | 시점 누출 개선<br>ML·DL 모델링<br>Analytics 고도화<br>관리자 캠페인·문서화 | 고객 페이지 구현<br>FastAPI·음악 API<br>모델 결과 검증<br>서비스 안정화 | 생존분석<br>고객 세그먼트 분석<br>마케팅 전략 도출 | EDA·전처리<br>ML 모델링<br>분석 파이프라인<br>프로젝트 초기 구성 |
| GitHub | 프로필 링크 입력 | 프로필 링크 입력 | 프로필 링크 입력 | 프로필 링크 입력 |

## 사용 기술

| 영역 | 기술 |
|---|---|
| 언어·분석 | Python, pandas, NumPy, SQL, DuckDB |
| 머신러닝·딥러닝 | LightGBM, XGBoost, CatBoost, scikit-learn, PyTorch |
| 모델 해석·시각화 | SHAP, Matplotlib, Seaborn |
| 백엔드 | FastAPI, Uvicorn, SQLAlchemy, PyMySQL, JWT |
| 데이터베이스 | MySQL |
| 프론트엔드 | HTML, CSS, JavaScript, React 18 |
| 협업·배포 | Git, GitHub, Cloudflare Tunnel |

## 핵심 결과

| 구분 | 결과 |
|---|---:|
| 예측 문제 | 만료 후 30일 이내 유효한 재구독이 없으면 이탈 |
| 피처 관측 종료일 | 2017-01-31 |
| 라벨 고객 | 992,931명 |
| 이탈률 | 6.39% |
| 최종 모델 | LightGBM Enhanced v2 |
| 입력 피처 | 57개 |
| Test ROC-AUC | 0.90356 |
| Test PR-AUC | 0.58343 |
| Test F1 | 0.55674 |
| 운영 임계값 | 0.270839 (Validation F1 최적) |
| 스코어링 고객 | 990,834명 |

모델 점수만 출력하는 데서 끝나지 않고 이탈 위험 고객을 `Retention`, `긴급 갱신`, `Win-back` 캠페인으로 연결하고, 실행 결과를 고객 페이지 알림으로 전달하는 흐름을 구현했습니다.

## 문제 정의

KKBOX 데이터의 이탈률은 6.39%입니다. 모든 고객을 잔존으로 예측해도 Accuracy가 약 93.6%이므로 정확도만으로 모델을 평가할 수 없습니다.

프로젝트 목표는 다음과 같습니다.

1. 미래 정보가 섞이지 않도록 예측 시점을 통제합니다.
2. 불균형 데이터에 적합한 PR-AUC, Recall, Precision, F1을 함께 평가합니다.
3. 예측 결과를 고객 세그먼트, 캠페인, 고객 알림으로 연결합니다.

## 시스템 구조

```mermaid
flowchart LR
    A["KKBOX Raw CSV<br/>members · transactions · user_logs · train"]
    B["전처리 및 피처 엔지니어링<br/>2017-01-31 기준"]
    C["LightGBM Enhanced v2<br/>57 Features"]
    D["MySQL Serving DB<br/>예측 · 세그먼트 · LTV · 캠페인"]
    E["FastAPI"]
    F["관리자 페이지<br/>분석 · 고객 탐색 · 캠페인 · 이력"]
    G["고객 페이지<br/>알림 · 혜택 · 구독"]

    A --> B --> C --> D --> E
    E --> F
    E --> G
    F -->|"캠페인 실행"| D
    D -->|"customer_actions"| G
```

## 데이터와 예측 시점

데이터는 Kaggle [WSDM KKBox's Churn Prediction Challenge](https://www.kaggle.com/competitions/kkbox-churn-prediction-challenge/data)를 사용했습니다.

- `train.csv`: 고객 ID와 이탈 라벨
- `members.csv`: 가입 정보와 인구통계
- `transactions.csv`: 결제, 자동 갱신, 취소, 만료일
- `user_logs.csv`: 일별 음악 이용 행동

최종 학습에서는 기본 `train.csv` 코호트만 사용하고 `train_v2.csv`는 사용하지 않았습니다.

### 2017-01-31로 관측을 종료한 이유

2월 거래와 로그를 피처에 포함하면 이탈 여부가 결정되는 기간의 미래 정보를 미리 보는 누출이 발생할 수 있습니다. 모든 거래·로그 피처를 2017-01-31까지로 제한하고 이후 확정된 `is_churn`과 비교했습니다.

| Split | 고객 수 | 이탈률 |
|---|---:|---:|
| Train | 695,051 | 6.3923% |
| Validation | 148,940 | 6.3925% |
| Test | 148,940 | 6.3918% |

고객 ID 기준 stratified 70/15/15 분할을 사용했습니다.

## 데이터 처리 흐름

```text
EDA
→ 고객 단위 Train/Validation/Test 분할
→ members 피처 생성
→ transactions 피처 생성
→ user_logs 청크 집계
→ 피처 병합 및 Train 기준 결측치 대체
→ 파생 피처와 최근 로그 피처 추가
→ 모델 학습·비교·평가
→ 전체 고객 스코어링
→ MySQL 적재
→ FastAPI 및 프론트엔드 연결
```

약 30GB, 3.9억 행 규모의 `user_logs.csv`는 메모리에 한 번에 올리지 않고 청크 단위로 집계했습니다. 동일 집계를 DuckDB SQL로 교차 검증했습니다.

주요 피처:

- 고객: 도시, 가입 경로, 가입 기간, 정제 연령
- 결제: 거래 수, 자동 갱신률, 취소율, 최근 결제일, 만료일까지 남은 일수
- 이용: 최근 7·30·90일 활동일, 재생시간, 고유 곡 수
- 파생: 행동 변화, 결제 변화, 만료일 정합성, 최근 로그 경과일

## 모델과 성능

최종 모델의 로컬 기준 파일은 `models/lightgbm_enhanced_v2_meta.json`입니다. `models/`는 대용량 아티팩트 정책으로 Git에서 제외되므로 재현 환경에서는 별도로 전달해야 합니다.

| 모델 | Test ROC-AUC | Test PR-AUC | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|
| LightGBM Enhanced v2 | 0.90356 | 0.58343 | 0.53676 | 0.57826 | 0.55674 |
| MLP | 0.89235 | 0.55990 | 0.53514 | 0.55273 | 0.54379 |

집계된 정형 데이터에서는 LightGBM이 MLP보다 모든 주요 지표에서 우수했고 SHAP 기반 설명도 가능해 최종 모델로 채택했습니다.

- ROC-AUC: 전체 고객의 이탈 위험 순위를 구분하는 능력
- PR-AUC: 희소한 이탈 고객을 정확하게 찾는 능력으로, 본 프로젝트의 주요 지표
- Precision: 이탈로 예측한 고객 중 실제 이탈 고객 비율
- Recall: 실제 이탈 고객 중 모델이 찾아낸 비율
- F1: Precision과 Recall의 균형

상위 5% 위험 고객군은 Precision 약 61.1%, Recall 약 47.8%, Lift 약 9.55배로 제한된 마케팅 자원의 우선순위 선정에 활용할 수 있습니다.

## 세그먼트와 캠페인

위험도, 월평균 결제액, 고객 생명주기를 결합해 운영 대상을 나눕니다. LTV는 구매 인과효과가 아니라 고객 가치와 자원 배분을 위한 근사 지표입니다.

| 생명주기 | 캠페인 | 실행 예시 |
|---|---|---|
| 구독 활성 | Retention | 갱신 안내, 선택적 할인 |
| 갱신 유예기간 | 긴급 갱신 | 결제·만료 안내, 기한 제한 혜택 |
| 장기 만료 | Win-back | 복귀 콘텐츠, 복귀 할인 |

관리자는 조건을 충족하는 전체 고객, 위험도 상위 N명, 고객 탐색에서 직접 추가한 고객을 대상으로 캠페인을 구성할 수 있습니다. 실행 전 중복과 목적·생명주기가 맞지 않는 고객을 제외합니다.

## 서비스 기능

### 관리자 페이지

- 운영 현황과 우선 관리 고객군
- 모델 성능, SHAP, 퍼널, 리텐션·세그먼트 분석
- 생명주기·위험도·가치·고객 ID 기반 탐색
- Retention·긴급 갱신·Win-back 캠페인 생성
- 대상 미리보기, 제외 결과, 캠페인 이력
- 모델 버전, 임계값, 데이터 해석 한계 관리

### 고객 페이지

- 고객 ID 기반 데모 로그인
- 개인 세그먼트 기반 화면과 혜택
- 관리자 캠페인 알림 조회 및 읽음 처리
- 쿠폰·프로모션·연차 혜택 수령
- 구독 요금제와 결제수단 선택
- 음악 차트, 최신 음악, 검색·플레이어

현재 데모는 실제 이메일이나 푸시를 발송하지 않고 `customer_actions`에 캠페인 결과를 기록해 고객 알림으로 보여줍니다.

## 서비스 구현 및 배포

- FastAPI가 API와 고객·관리자 HTML을 함께 제공하는 단일 배포 구조입니다.
- 프론트엔드는 `window.location.origin`을 API 기준 주소로 사용하므로 로컬과 공개 데모 환경에서 별도 주소 수정이 필요하지 않습니다.
- 관리자와 고객은 서로 다른 JWT 타입으로 인증하며, 라우터 의존성에서 권한을 구분합니다.
- 오프라인 스코어링 배치는 Enhanced v2 예측과 분석 참조 테이블을 생성한 뒤 MySQL에 적재합니다.
- 음악 검색·차트·신곡 기능은 FastAPI가 Apple 공개 API를 프록시하고 서버 메모리 캐시를 적용합니다.
- 발표용 외부 접속은 로컬 Uvicorn 서버를 Cloudflare Quick Tunnel로 노출하는 방식으로 구성할 수 있습니다.

전체 API 목록, 인증 흐름, 캠페인 시퀀스, Cloudflare 배포 과정과 Apple Music 프록시 제약은 [프로젝트 통합 상세 문서](./docs/KKBOX_프로젝트_통합문서.md)에서 확인할 수 있습니다.

## DB 구조

| 테이블 | 역할 |
|---|---|
| `customer_churn_scores` | 고객별 이탈확률, 위험도, 가치, 생명주기, LTV |
| `campaigns` | 캠페인 조건과 실행 결과 |
| `campaign_recipients` | 캠페인별 최종 대상 및 제외 결과 |
| `customer_actions` | 고객 알림, 읽음 상태, 혜택 수령 기록 |
| `staff_accounts` | 관리자 계정 |
| `model_stats`, `shap_importance` 등 | 분석 화면 참조 데이터 |

자세한 내용은 [DB ERD 및 실행 가이드](./DB_ERD_가이드.md)를 참고하세요.

## 실행 방법

### 1. 가상환경과 패키지

```powershell
python -m venv My_venv
.\My_venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install -r requirements-extra.txt
```

프로젝트 루트에 `.env`를 생성합니다.

```dotenv
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=your_user
MYSQL_PASSWORD=your_password
MYSQL_SERVING_DB=kkbox_serving
```

### 2. DB 구성

```powershell
mysql -u root -p < backend/scoring/schema.sql
mysql -u root -p kkbox_serving < backend/scoring/migrate_campaigns.sql
mysql -u root -p kkbox_serving < backend/scoring/migrate_notifications.sql
mysql -u root -p kkbox_serving < backend/scoring/migrate_plan_fields.sql
```

스코어링 산출물을 새로 생성하고 적재하려면 다음을 실행합니다.

```powershell
python backend/scoring/build_scoring_table.py
python backend/scoring/export_reference_tables.py
python backend/scoring/load_to_mysql.py
```

대용량 원본 데이터와 모델 파일은 Git에 포함되지 않으므로 별도로 준비해야 합니다.

### 3. 서버 실행

```powershell
cd backend
uvicorn app.main:app --reload --port 8000
```

- 고객 페이지: `http://127.0.0.1:8000/`
- 관리자 페이지: `http://127.0.0.1:8000/admin-page`
- API 문서: `http://127.0.0.1:8000/docs`

프론트엔드는 현재 서버의 origin을 API 주소로 사용하므로 HTML 파일을 직접 열지 말고 FastAPI 주소로 접속해야 합니다.

## 데모 순서

1. 관리자 로그인 후 운영 현황과 우선 고객군을 확인합니다.
2. 고객 탐색에서 조건을 적용하고 캠페인 초안에 고객을 추가합니다.
3. 캠페인 실행 화면에서 대상과 제외 결과를 확인한 뒤 실행합니다.
4. 캠페인 이력에서 기록을 확인합니다.
5. 대상 고객으로 로그인해 알림과 혜택이 연결된 것을 확인합니다.

## 프로젝트 구조

```text
EDA/                 원본 테이블별 탐색
preprocessing/       시점 분할, 피처 생성, 최종 모델 테이블
modeling/            ML 베이스라인, 비교, 파생 피처, 최종 LightGBM
dl_modeling/         MLP 베이스라인과 클래스 가중치 실험
analytics/           SQL 검증, 퍼널, LTV, SHAP, 세그먼트, 생존분석
backend/app/         FastAPI 인증·고객·관리자·음악 API
backend/scoring/     스코어링, DB 스키마와 마이그레이션
frontend/            관리자 및 고객 페이지
docs/                발표 및 운영 문서
```

## 한계와 향후 개선

- 2017-01-31 기준 과거 스냅샷이므로 현재 고객 상태를 나타내지 않습니다.
- 무작위 분할 성능 외에 `train_v2` 같은 이후 코호트를 활용한 시간 외 검증이 필요합니다.
- 실제 메시지 발송과 노출·클릭·재구독·매출 이벤트는 구현하지 않았습니다.
- 캠페인 효과 평가는 대조군을 포함한 A/B 테스트와 전환 이벤트 수집이 필요합니다.
- 여러 월의 동적 스냅샷을 만들면 시계열·생존분석 기반 조기 예측으로 확장할 수 있습니다.

A/B 테스트와 시계열 고도화는 현재 구현 기능이 아니라 발표의 향후 개선 방향으로만 다룹니다.

## 문서

- [프로젝트 통합 상세 문서](./docs/KKBOX_프로젝트_통합문서.md)
- [서빙 DB ERD 및 실행 가이드](./DB_ERD_가이드.md)
- [트러블슈팅](./TROUBLESHOOTING.md)
