# AI-Powered Predictive Maintenance on AWS

An end-to-end, serverless predictive maintenance system built on AWS. It streams real bearing vibration data from a simulated sensor, detects and classifies faults with a trained ML model, generates grounded maintenance recommendations with Amazon Bedrock (Claude), estimates the cost of downtime avoided, and emails one alert per fault.

## The problem

Unplanned equipment downtime is one of the most expensive problems in manufacturing. Having worked as a production line operator in automotive manufacturing, I've seen what an unexpected bearing failure does to a shift. This project combines that floor-level experience with real cloud architecture: sensors feeding a cloud pipeline, automated fault detection, AI-assisted diagnosis, and a business case attached to every alert.

## Architecture

```
Sensor (simulated) → IoT Core → Lambda (store + ML classify) → DynamoDB
                                                                  ↓
                                                          DynamoDB Streams
                                                                  ↓
          Knowledge base table ←  Lambda (explain)  → Amazon Bedrock (Claude)
          Machine config table ←        ↓           ↔ Spare-parts table (tool use)
            (downtime costs)            ↓
                          explanation + savings saved back to DynamoDB
                                        ↓
                         Amazon SNS → email alert (once per fault)

          Dashboard (your browser) ← API Gateway ← Lambda ← DynamoDB
```

## What it does

1. **Ingests** real bearing vibration data (CWRU dataset), replayed as 1-second summary statistics (mean, std, RMS, peak) over MQTT to AWS IoT Core.
2. **Stores** every reading in DynamoDB and **flags anomalies** with a threshold on vibration standard deviation (healthy ≈ 0.07, faulty ≈ 0.29).
3. **Classifies the fault type** (inner race, outer race, ball, normal) with a logistic regression model trained in scikit-learn and embedded in Lambda as plain arithmetic.
4. **Explains the fault** with Claude on Amazon Bedrock, grounded in a reference knowledge base (RAG) and a live spare-parts inventory check (agentic tool use).
5. **Prices the fault**: estimates the cost of unplanned downtime avoided by acting early, from per-machine assumptions in a config table.
6. **Alerts** by email through Amazon SNS, exactly once per fault.
7. **Visualizes** everything on a live, auto-refreshing dashboard.

## Key engineering decisions

- **Threshold detection before machine learning.** A simple, explainable baseline first, then a multi-class classifier as a genuine second iteration.
- **Honest evaluation.** The classifier scored 100% on held-out data. I caught and fixed a data leakage issue (overlapping windows across the train/test split) and documented why this dataset makes the problem easier than real-world conditions.
- **Model deployment without new infrastructure.** No SageMaker endpoint or scikit-learn package in Lambda: the learned coefficients are applied as plain arithmetic, so there's no idle cost.
- **Fast path vs AI path.** DynamoDB Streams trigger the Bedrock Lambda only for anomalies, so routine writes stay fast and cheap.
- **Exact lookup over similarity search.** Vector search returned a misleading match on a small document set. Since the classifier already gives the exact fault type, a direct key lookup is faster and fully reliable.
- **Tool use, not just context.** Claude decides whether to call `check_spare_parts`. The Lambda runs the real lookup and returns the result.
- **Count faults, not readings.** One fault produces a reading every second, so savings and alerts are grouped per fault incident. Totals only include savings the system actually calculated.
- **Exactly one alert per fault, even under concurrency.** A DynamoDB conditional write (`attribute_not_exists(last_alert_at) OR last_alert_at < :cutoff`) atomically claims the alert slot, so parallel Lambda invocations can't send duplicates.

## Example output

> **Recommendation:** Schedule bearing replacement at the next planned maintenance window; given that 3 replacement bearings (Deep groove ball bearing 6205-2RS) are in stock, accelerate to within 24–48 hours if the standard deviation keeps rising. **Acting now avoids approximately $60,000 in unplanned downtime (6 hours of production loss).**

Savings figures use illustrative assumptions: $10,000 per hour of downtime, 8 hours unplanned vs 2 hours planned repair.

## Repository structure

```
device/            replay_to_iot.py: replays dataset windows to AWS IoT Core
lambdas/
  pdm_store_telemetry/   stores readings, flags anomalies, classifies fault type
  pdm_explain_anomaly/   RAG + tool use with Bedrock, savings, SNS alerts
  pdm_get_readings/      API behind the dashboard
dashboard/         dashboard.html: live dashboard with cost-of-downtime panel
knowledge_base/    reference text per fault type, and the embedding script
docs/              screenshots
```

## AWS services

IoT Core · Lambda · DynamoDB · DynamoDB Streams · Amazon Bedrock (Claude Haiku 4.5, Titan Embeddings) · Amazon SNS · API Gateway · S3 · IAM (least-privilege inline policies)

## Running it yourself

This repository contains **no credentials**. Values specific to my AWS account have been replaced with placeholders:

| Placeholder | Replace with |
|---|---|
| `YOUR_ACCOUNT_ID` | your 12-digit AWS account ID |
| `YOUR_ENDPOINT-ats` | your IoT Core endpoint prefix |
| `YOUR_CERT_ID` | your IoT device certificate ID |
| `YOUR_API_ID` | your API Gateway ID |

Place your own IoT device certificate, private key, and Amazon Root CA in a local `certs/` folder (ignored by Git). The dataset comes from [srigas/CWRU_Bearing_NumPy](https://github.com/srigas/CWRU_Bearing_NumPy), a NumPy conversion of the Case Western Reserve University bearing dataset.

A full step-by-step build guide covering all eight stages, including the pitfalls hit along the way, is available on request.

## Author

Mechanical engineer (BTech Mechanical Engineering, MSc Industrial & Production Engineering, MBA) and AWS Certified Solutions Architect – Associate. Experience spans construction project management and MEP design, automotive manufacturing (production line operations), maintenance of an electric power generation plant (internship), and ecommerce.
