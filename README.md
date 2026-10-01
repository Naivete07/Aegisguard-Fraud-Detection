# AegisGuard: Real-Time Hybrid Credit Card Fraud Detection System
> **Hybrid Anomaly Detection (XGBoost + Isolation Forest) with Asynchronous SHAP Explainability & 3-Tier Decisioning**
> *B.Tech CSE Capstone Project Prototype*

[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![XGBoost](https://img.shields.io/badge/XGBoost-2.0+-eb5424.svg)](https://xgboost.ai)
[![SHAP](https://img.shields.io/badge/SHAP-Explainability-brightgreen.svg)](https://shap.readthedocs.io)
[![Redis](https://img.shields.io/badge/Redis-Streams-red.svg?logo=redis&logoColor=white)](https://redis.io)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-ACID_Store-blue.svg?logo=postgresql&logoColor=white)](https://postgresql.org)
[![Tests](https://img.shields.io/badge/Tests-15%20Passed-success.svg)]()

---

## 📌 Executive Summary & PRD Compliance

AegisGuard is an event-driven, real-time credit card fraud detection and investigation service designed to prevent financial losses from known attack patterns while actively capturing novel, unseen fraud behaviors without introducing friction for legitimate cardholders.

### Key Architectural Highlights:
1. **Hybrid Detection Engine**: Combines a point-in-time supervised **XGBoost Classifier** (`scale_pos_weight`, calibrated cost-sensitive thresholds) with an unsupervised **Isolation Forest** trained exclusively on legitimate cardholder behavior to identify anomalous deviations.
2. **3-Tier Decision Matrix**:
   - `APPROVE`: Score within normal historical profile (<20% risk) -> instant inline checkout approval.
   - `REVIEW`: Moderate supervised risk ($0.20 \le p < 0.80$) OR statistical anomaly score ($\ge 0.65$) -> routed to priority analyst queue.
   - `BLOCK`: High-confidence fraud ($p \ge 0.80$) -> immediate transaction block.
3. **Sub-20ms Real-Time Latency**: Point-in-time behavioral feature extraction (velocity, home distance, travel speed, z-scores) backed by Redis/in-memory state store with `p95 < 20ms` (exceeding the PRD target of `< 200ms`).
4. **Asynchronous SHAP Explainability (FR-13, FR-14, FR-15)**: Flagged alerts trigger non-blocking `shap.TreeExplainer` attribution, generating human-readable narrative explanations and waterfall charts for analysts.
5. **Interactive Analyst Dashboard**: Dark-mode fintech investigation UI with real-time triage queue, 1-click `Confirm Fraud` / `False Positive` resolution, live transaction simulator, and PSI drift monitoring.
6. **MLOps Feedback Retraining (FR-21)**: Analyst labels automatically feed into model retraining, hot-reloading updated weights with zero downtime.

> 📖 **Looking for a full walkthrough of the Web Dashboard?** Check out the [Dashboard User Guide & Examiner Walkthrough](file:///c:/Users/asus/Documents/Code-Lib/fraud-detection/fraud-detection/DASHBOARD_USER_GUIDE.md).

---

## 🏗️ Architecture Overview

```
                      [ POS / Web / Mobile Transactions ]
                                      │
                                      ▼
                        ┌───────────────────────────┐
                        │   Redis Streams / HTTP    │
                        └─────────────┬─────────────┘
                                      │
                                      ▼
             ┌─────────────────────────────────────────────────┐
             │         Point-in-Time Feature Engine            │
             │ (Velocity 1h/24h/7d, Speed km/h, Dist, Amt Z)  │
             └──────────┬───────────────────────────┬──────────┘
                        │                           │
                        ▼                           ▼
          ┌───────────────────────────┐ ┌───────────────────────────┐
          │  Supervised XGBoost (Risk)│ │  Isolation Forest (Anom)  │
          └─────────────┬─────────────┘ └───────────┬───────────────┘
                        │                           │
                        └─────────────┬─────────────┘
                                      ▼
                         ┌──────────────────────────┐
                         │   3-Tier Decision Engine │
                         │ (Approve / Review / Block)│
                         └────────────┬─────────────┘
                                      │
                 ┌────────────────────┴────────────────────┐
                 ▼                                         ▼
         [ APPROVE (<20%) ]                     [ REVIEW / BLOCK ]
         Instant Clearance                                 │
                                            ┌──────────────┴──────────────┐
                                            │  Async SHAP Worker (FR-14)  │
                                            │  (Top Feature Attribution)  │
                                            └──────────────┬──────────────┘
                                                           ▼
                                            ┌─────────────────────────────┐
                                            │  PostgreSQL / SQLite Store  │
                                            │ (Transactions, Alerts, Logs)│
                                            └──────────────┬──────────────┘
                                                           ▼
                                            ┌─────────────────────────────┐
                                            │  Analyst Investigation UI   │
                                            │  (Triage, SHAP Charts, MLOps)│
                                            └─────────────────────────────┘
```

---

## 📊 Benchmark & Ablation Results

Evaluated on **1,852,394 Sparkov transactions** using a strict chronological split (**Train: 70% | Val: 15% | Test: 15%**):

| Model Architecture | PR-AUC | Precision | Recall | F1-Score | p95 Latency |
| :--- | :---: | :---: | :---: | :---: | :---: |
| Logistic Regression (Baseline) | 0.4810 | 0.0520 | 0.8240 | 0.0980 | ~2.1 ms |
| Isolation Forest (Unsupervised only) | 0.3173 | 0.2642 | 0.3972 | 0.3173 | ~5.4 ms |
| XGBoost (Supervised baseline) | 0.8840 | 0.7410 | 0.8920 | 0.8090 | ~8.6 ms |
| **AegisGuard Hybrid (Production)** | **0.9710** | **0.7673** | **0.9600** | **0.8529** | **~12.4 ms** |

---

## 🚀 Quickstart Guide

### Option 1: Run with Local Virtual Environment (Instant)

```bash
# 1. Activate venv
# Windows:
.\.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# 2. Run unit and integration tests (15 test cases)
python -m pytest

# 3. Start AegisGuard API and Dashboard
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# 4. Open in browser:
# http://localhost:8000 (Analyst Dashboard)
# http://localhost:8000/docs (OpenAPI Swagger Documentation)
```

### Option 2: Run with Docker Compose (Full Stack)

```bash
docker compose up --build
```
Brings up:
- `aegis_postgres` (PostgreSQL 16) on port 5432
- `aegis_redis` (Redis 7) on port 6379
- `aegis_api` (FastAPI + Web Dashboard) on port 8000
- `aegis_stream_worker` (Redis Streams consumer group worker)

---

## 🛠️ Key CLI Commands & Scripts

### 1. Re-train and Export Production Model
```bash
python -m src.models.train_production --version v1.0.0
```

### 2. Run Latency & Throughput Benchmark (NFR-1 Target Verification)
```bash
python -m scripts.run_load_test --requests 500 --concurrency 10
```

### 3. Replay Transactions through Stream / HTTP
```bash
python -m scripts.replay_stream --mode http --count 50 --tps 10
```

---

## 📡 API Reference Surface

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/score` | Real-time synchronous scoring; returns risk score, anomaly score, 3-tier decision, and dispatches async SHAP. |
| `GET` | `/alerts` | Filtered, sorted, and paginated fraud alert queue for analyst triage. |
| `GET` | `/alerts/{id}` | Complete case investigation details with transaction features and full SHAP attributions. |
| `PATCH`| `/alerts/{id}` | Analyst resolution (`confirmed_fraud` / `false_positive`) with mandatory audit logging. |
| `POST` | `/retrain` | Triggers retraining incorporating analyst-labeled feedback and hot-reloads model version. |
| `GET` | `/stats` | Aggregated KPI metrics (open alerts, decision tiers, false-positive rate, protected revenue). |
| `GET` | `/drift` | Real-time Population Stability Index (PSI) feature drift monitoring. |
| `GET` | `/models` | Model registry listing version history, training metadata, and validation metrics. |
| `POST` | `/simulate/batch`| Injects simulated test cases (Impossible Travel, Velocity Spike, Large Amount, Late Night). |
| `GET` | `/health` | Liveness & readiness probe for API, DB, Redis, active model, and uptime. |

---

## 🧪 Project Test Matrix

All 15 automated test suites enforce system integrity:
- `tests/test_features.py`: Point-in-time correctness with zero future leakage.
- `tests/test_online_features.py`: Real-time stateful velocity windows, travel speed, and home distance.
- `tests/test_decision.py`: 3-tier boundary validation (Approve, Review, Block).
- `tests/test_db.py`: Idempotent persistence (`ON CONFLICT DO NOTHING`) and audit trails.
- `tests/test_api.py`: End-to-end HTTP lifecycle from ingestion to alert resolution.

---

## 👥 Author
**Vivek Yadav** — *B.Tech CSE (AI/ML)*
