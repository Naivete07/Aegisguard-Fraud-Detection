# AegisGuard: Dashboard User Guide & Examiner Walkthrough

This document provides a comprehensive breakdown of the **AegisGuard Fraud Analyst Dashboard**, explaining every tab, metric, visualizer, and control in the web interface.

---

## 🧭 Dashboard Architecture & Navigation

When you open **[http://localhost:8000](http://localhost:8000)**, you will see a dark-mode fintech interface designed for real-time fraud triage and ML interpretability.

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ [🛡️ AEGISGUARD]  [● v1.0.0 (XGB + IF)]   [● LIVE SCORING | p95: <18ms]   [⚡ Simulate] [➕ Test Txn]│
├────────────────────────────────────────────────────────────────────────────────────────┤
│ [SIDEBAR]     │  [KPI CARDS: Open Alerts | Blocked | Review Queue | FPR | Prevented $] │
│               ├────────────────────────────────────────────────────────────────────────┤
│ 📋 Triage     │                                                                        │
│ 📊 Analytics  │  [ACTIVE TAB WORKSPACE]                                                │
│ 🔍 Drift/PSI  │  - Alert Table / Filters / Search                                      │
│ 🧠 Models     │  - SHAP Waterfall Drawer / 1-Click Case Resolutions                    │
│ 🔄 Retrain    │  - Real-Time PSI Drift Audit / Model Registry                          │
└───────────────┴────────────────────────────────────────────────────────────────────────┘
```

---

## 🎯 Top Header Controls

| Control | Description |
| :--- | :--- |
| **🛡️ System Status Badge** | Displays current active model version (e.g. `v1.0.0 (XGB + IF)`) and live health status. |
| **● Live Scoring Ticker** | Displays real-time p95 scoring latency (typically `< 18ms`) and cumulative transaction volume processed. |
| **⚡ Simulate Flow Button** | Injects 5 realistic test transactions across fraud and legitimate scenarios (Impossible Travel, Velocity Spikes, Large Amounts, Late Night Anomalies) directly into the pipeline. |
| **➕ Test Transaction Button** | Opens the **Scoring Sandbox Modal**, allowing manual input of card numbers, amounts, merchants, locations, and channels to test inline scoring immediately. |

---

## 📊 Summary KPI Cards (Top Row)

At the top of every tab, five real-time KPI metrics summarize system health:

1. **⚠️ Open Alerts**: Total number of transactions in `review` or `block` status that are currently awaiting fraud analyst triage.
2. **⛔ Blocked Transactions**: Count of high-confidence fraud attempts halted inline ($p \ge 80\%$).
3. **👁️ Review Queue**: Transactions routed for human review due to moderate supervised risk ($20\% \le p < 80\%$) or high statistical anomaly score ($\ge 0.65$).
4. **🎯 False Positive Rate (FPR)**: Real-time ratio of false-positive resolutions to total resolved analyst cases ($\frac{\text{False Positives}}{\text{Confirmed Fraud} + \text{False Positives}}$).
5. **💰 Prevented Fraud**: Total protected dollar volume from blocked transactions and confirmed fraud cases.

---

## 📋 Tab 1: Alert Triage Queue (`pane-triage`)

The primary workspace for fraud analysts to review and resolve flagged transactions.

### 1. Filters & Search Toolbar
- **Search Bar**: Instant search across Card Number (e.g. `40001234...`), Merchant Name (e.g. `fraud_Kirlin`), or Transaction ID.
- **Status Filter**: Filter by `Open Only`, `Confirmed Fraud`, `False Positive`, or `All Statuses`.
- **Decision Filter**: Filter by `Block Tier` (automated blocks) or `Review Tier` (analyst review queue).
- **Risk Band Filter**: Filter by `High Risk`, `Medium Risk`, or `Low Risk`.
- **Auto-Refresh Toggle** (in sidebar footer): Automatically polls for incoming alerts every 3 seconds.

### 2. Alert Table Columns
- **Alert ID**: Unique serial identifier for the investigation case.
- **Timestamp**: Time of transaction in cardholder local time.
- **Card Number**: Masked card identifier (e.g. `**** 9010`).
- **Merchant / Channel**: Merchant name and transaction vector (`POS`, `WEB`, `APP`).
- **Amount**: Transaction amount in USD.
- **XGB Score**: Supervised fraud probability ($0.0\%$ to $100.0\%$).
- **Anomaly Score**: Unsupervised Isolation Forest deviation score ($0.0\%$ to $100.0\%$).
- **Decision Tier**: `BLOCK` (crimson badge) or `REVIEW` (amber badge).
- **Status**: `OPEN` (amber), `FRAUD` (crimson), or `FP` (emerald).
- **Investigate Button**: Opens the **Case Investigation Modal**.

---

## 🔍 Case Investigation Modal & SHAP Visualizer

Clicking **`Investigate`** on any row opens the deep-dive investigation drawer:

### 1. Dual Score Banner
- **XGBoost Risk Score Meter**: Supervised probability of fraud trained on historical fraud patterns.
- **Isolation Forest Anomaly Meter**: Unsupervised score measuring how statistically abnormal the transaction is compared to legitimate cardholder behavior.
- **Decision Pill**: Recommended action (`BLOCK` or `REVIEW`).

### 2. ✨ AI Executive Explanation Narrative
A synthesized, plain-language summary that translates complex ML feature attributions into a 1-sentence decision rationale for the analyst.
> *Example:* `"Alert triggered primarily by spending spike (3.8σ above normal), rapid travel speed (850.0 km/h), and distant location (842.1 km from home)."`

### 3. Interactive SHAP Contribution Chart
Dynamic horizontal bars breaking down exact feature impacts:
- **Red Bars (Positive SHAP)**: Features that pushed the risk score **UP** (e.g. high velocity, impossible travel speed, night transaction, amount spike).
- **Green Bars (Negative SHAP)**: Features that pulled the risk score **DOWN** (e.g. frequent merchant, normal time of day, low amount).
- **Values**: Displays exact formatted value (e.g. `850.0 km/h`, `+3.8σ`, `$1,250.00`).

### 4. Transaction & Behavioral Context Grid
Key point-in-time features computed without future leakage:
- **Distance from Home**: Haversine distance between cardholder home and terminal coordinates.
- **Implied Travel Speed**: Speed in km/h required to travel between previous and current transaction locations.
- **Amount Z-Score**: Number of standard deviations above the card's historical average spending.
- **1-Hour / 24-Hour Velocity**: Transaction count and total spending sum within rolling time windows.

### 5. 1-Click Analyst Resolution Actions
- **`[ Mark False Positive ]`**: Marks case as legitimate cardholder activity, records resolution in `fraud_alerts`, and writes an event to `audit_log`.
- **`[ Confirm Fraud ]`**: Confirms fraudulent activity, marks alert for feedback retraining, and logs action to `audit_log`.

---

## 📊 Tab 2: KPI Analytics & Cost Matrix (`pane-analytics`)

Visualizes system distribution and economic impact:

1. **Decision Tier Distribution**:
   - **Approved**: Percentage of transactions cleared inline with 0 checkout delay.
   - **Review Queue**: Percentage of transactions flagged for analyst inspection.
   - **Blocked**: Percentage of transactions halted immediately.
2. **Cost-Sensitive Decision Matrix**:
   - **Cost of Missed Fraud (False Negative)**: $100\%$ of transaction amount lost.
   - **Cost of False Positive (False Alarm)**: $\$15.00$ analyst review overhead $+ 1\%$ cardholder friction.
   - **Net Economic Savings**: Calculated net financial savings generated by AegisGuard.

---

## 🔍 Tab 3: Drift & PSI Monitor (`pane-drift`)

Monitors production feature distributions against training baselines using the **Population Stability Index (PSI)** (PRD FR-22):

### Status Classifications:
- **🟢 STABLE** ($\text{PSI} < 0.10$): Feature distributions match training baseline. No action required.
- **🟡 MODERATE DRIFT** ($0.10 \le \text{PSI} < 0.25$): Moderate behavioral shift observed. Monitor closely.
- **🔴 SIGNIFICANT DRIFT** ($\text{PSI} \ge 0.25$): Substantial behavioral shift detected. Triggers recommendation to retrain model.

### Monitored Behavioral Attributes:
- Transaction Amount (`amt`)
- Home Distance (`dist_home_km`)
- Implied Travel Speed (`speed_kmh`)
- Amount Z-Score (`amt_z`)
- 24-Hour Velocity (`txn_count_24h`)
- Hour of Day (`hour`)

---

## 🧠 Tab 4: Model Registry (`pane-models`)

Maintains model versioning, training metadata, and validation benchmarks (PRD FR-12):

- **Model Version**: e.g. `v1.0.0`.
- **Architecture**: `hybrid_xgboost_isolation_forest`.
- **Dataset**: `sparkov` (1.85M rows).
- **Validation Metrics**:
  - **PR-AUC**: `0.9710`
  - **Precision**: `0.7673`
  - **Recall**: `0.9600`
  - **F1-Score**: `0.8529`
  - **Training Rows**: `1,296,675`

---

## 🔄 Tab 5: Feedback Retraining (`pane-retrain`)

Implements the continuous MLOps feedback loop (PRD Section 3.6):

1. Shows the count of analyst-resolved labels (`confirmed_fraud` and `false_positive`) currently stored in the database.
2. Allows entering an optional new version tag (e.g. `v1.0.1`).
3. Clicking **`🚀 Start Retraining & Hot-Reload`**:
   - Incorporates analyst feedback labels into training data.
   - Re-trains Supervised XGBoost and Unsupervised Isolation Forest.
   - Saves new versioned bundle to `models/`.
   - Registers new version in `ml_models` database table.
   - **Hot-reloads** the running model in memory with **zero server downtime**.

---

## 🎭 Step-by-Step Viva & Demo Script (5 Minutes)

Follow this sequence to present a compelling live demonstration to examiners or reviewers:

1. **Show System Baseline**:
   - Open **[http://localhost:8000](http://localhost:8000)**.
   - Point out the active version badge `v1.0.0 (XGB + IF)` and `<18ms` latency ticker.
2. **Inject Test Stream**:
   - Click **`⚡ Simulate Flow`** twice.
   - Observe the KPI counters update and the Alert Table populate with new alerts in real time.
3. **Walk Through Case Investigation**:
   - Click **`Investigate`** on an alert with high speed or amount.
   - Point out the dual XGBoost risk score vs Isolation Forest anomaly score.
   - Read the **AI Executive Explanation Narrative**.
   - Explain the **SHAP Feature Contribution Bar Chart** (highlighting red vs green factors).
4. **Resolve the Case**:
   - Add a brief note (e.g. *"Cardholder confirmed unrecognized charge"*) and click **`Confirm Fraud`**.
   - Note the alert status change to `FRAUD` and the instant update to the audit trail.
5. **Demonstrate Inline Sandbox**:
   - Click **`➕ Test Transaction`**.
   - Change distance to `International` and amount to `$1,850.00`.
   - Click **`Score Transaction Inline`** and show the instant `<15ms` scoring decision.
6. **Show Drift & MLOps Governance**:
   - Switch to **`Drift & PSI Monitor`** and click **`Run PSI Audit`** to show mathematical stability verification.
   - Switch to **`Model Registry`** to present the **0.9710 PR-AUC** benchmark table.
