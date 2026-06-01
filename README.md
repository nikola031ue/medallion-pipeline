# AWS Medallion Pipeline

Data pipeline implementiran na AWS koristeći Medallion arhitekturu (Bronze → Silver → Gold).
Prikuplja podatke sa Hacker News i X (Twitter) platformi i vizualizuje ih kroz Apache Superset.

## Arhitektura

```
┌────────────────────────────────────────────────────────────────────────────┐
│                              AWS VPC (10.0.0.0/16)                         │
│                                                                            │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                  │
│  │    BRONZE    │    │    SILVER    │    │     GOLD     │                  │
│  │              │    │              │    │              │                  │
│  │ HN Fetcher   │──▶ │ HN Normalizer│──▶│  Metrics     │                  │
│  │ (Lambda)     │    │ (Lambda)     │    │  Calculator  │                  │
│  │              │    │              │    │  (Lambda)    │                  │
│  │ EventBridge  │    │ Twitter      │    │              │                  │
│  │ (00:00 UTC)  │    │ Normalizer   │    │  S3→Postgres │                  │
│  └──────────────┘    │ (Lambda)     │    │  (Lambda)    │                  │
│                      │              │    │              │                  │
│  ┌───────────┐       │ DataQuality  │    │  EventBridge │                  │
│  │ S3 Bucket │       │ (Lambda)     │    │  (03:00 UTC) │                  │
│  │           │       │              │    └──────────────┘                  │
│  │ bronze/   │       │ EventBridge  │                                      │
│  │ silver/   │       │ (02:00 UTC)  │    ┌──────────────┐                  │
│  │ gold/     │       └──────────────┘    │    EC2       │                  │
│  └───────────┘                           │  t3.micro    │                  │
│                                          │  PostgreSQL  │                  │
│  ┌─────────────────────────────────┐     │  Superset    │                  │
│  │         NOTIFIKACIJE            │     │  :8088       │                  │
│  │  CloudWatch → SNS → Lambda      │     └──────────────┘                  │
│  │  → Discord Webhook              │                                       │
│  └─────────────────────────────────┘                                       │
└────────────────────────────────────────────────────────────────────────────┘

Dnevni raspored:
  00:00 UTC - Bronze: Hacker News fetch
  02:00 UTC - Silver: Normalizacija (HN + Twitter paralelno) + Data Quality
  03:00 UTC - Gold: Metrike + Sync u PostgreSQL
```

## Tehnologije

| Sloj | Servis | Opis |
|------|--------|------|
| IaC | AWS CDK (Python) | Infrastruktura kao kod |
| Storage | Amazon S3 | Data lake (bronze/silver/gold) |
| Compute | AWS Lambda (Docker) | ETL funkcije |
| Orchestration | AWS Step Functions | Pipeline orkestracija |
| Scheduling | Amazon EventBridge | Dnevni okidači |
| Visualization | Apache Superset | Dashboardi |
| Database | PostgreSQL 15 | Gold layer storage |
| Notifications | SNS + Lambda + Discord | Alert sistem |
| Networking | VPC + NAT Gateway | Izolacija i internet pristup |

## Preduslovi

- AWS CLI konfigurisan (`aws configure`)
- AWS CDK instaliran (`npm install -g aws-cdk`)
- Docker Desktop pokrenut
- Python 3.11+ sa virtualenv

## Deployment

```bash
# 1. Kloniraj repozitorij
git clone <repo-url>
cd "AWS medallion pipeline"

# 2. Aktiviraj virtualenv
cd cdk
python -m venv .venv
.venv\Scripts\activate   # Windows
source .venv/bin/activate # Linux/Mac

# 3. Instaliraj zavisnosti
pip install -r requirements.txt

# 4. Bootstrap CDK (samo prvi put)
cdk bootstrap --context account=<AWS_ACCOUNT_ID> --context region=eu-central-1

# 5. Deployuj sve stackove
cdk deploy --all \
  --context account=<AWS_ACCOUNT_ID> \
  --context region=eu-central-1 \
  --context "discord_webhook_url=<DISCORD_WEBHOOK_URL>"
```

### Redosljed stackova

```
NetworkStack → DataLakeStack → BronzeStack → SilverStack → VizStack → GoldStack → NotifStack
```

## Pokretanje pipeline-a

### Ručno pokretanje

```bash
# Bronze (Hacker News fetch)
aws lambda invoke \
  --function-name <bronze-lambda-name> \
  --invocation-type Event \
  --region eu-central-1 out.json

# Silver normalizacija
aws stepfunctions start-execution \
  --state-machine-arn arn:aws:states:eu-central-1:<ACCOUNT>:stateMachine:silver-normalization \
  --region eu-central-1

# Gold pipeline (metrike + sync u PostgreSQL)
aws stepfunctions start-execution \
  --state-machine-arn arn:aws:states:eu-central-1:<ACCOUNT>:stateMachine:gold-pipeline \
  --region eu-central-1
```

### Provjera statusa

```bash
# Status Step Functions egzekucije
aws stepfunctions list-executions \
  --state-machine-arn arn:aws:states:eu-central-1:<ACCOUNT>:stateMachine:gold-pipeline \
  --query "executions[0].{status:status,start:startDate}" \
  --region eu-central-1

# S3 struktura
aws s3 ls s3://<BUCKET_NAME>/ --recursive --region eu-central-1
```

## Superset Dashboard

1. Otvori `http://<EC2_PUBLIC_IP>:8088`
2. Prijavi se: `admin` / `admin`
3. Dashboardi → **Medallion Pipeline**

### Dostupne metrike

| Dashboard | Tabela | Opis |
|-----------|--------|------|
| Objave po tipu | `fact_posts_by_type` | Dnevni broj HN objava po tipu |
| Korisnici po platformi | `daily_users_metric` | Ukupni i novi korisnici (HN + X) |
| Top HN karma | `top_hn_users_max_karma` | Top 10 HN korisnika po karma |
| Top X pratitelji | `top_x_users_by_followers` | Top 10 X korisnika po pratiocima |
| Top stories | `top_hn_stories_by_score` | Top 10 HN stories po score |
| Top jobs | `top_hn_jobs_by_score` | Top 10 HN job objava po score |
| Data Quality | `data_quality_kpi` | Kvalitet podataka po tabeli |

## Pristup EC2 (bez SSH)

```bash
aws ssm start-session --target <INSTANCE_ID> --region eu-central-1
```

## CDK Stackovi

| Stack | Opis |
|-------|------|
| `NetworkStack` | VPC, Security Groups, NAT Gateway |
| `DataLakeStack` | S3 bucket sa RETAIN policy |
| `BronzeStack` | Lambda za HN fetch, EventBridge 00:00 |
| `SilverStack` | Lambda normalizatori, Step Functions, EventBridge 02:00 |
| `GoldStack` | Lambda metrike + S3→PostgreSQL sync, Step Functions, EventBridge 03:00 |
| `VizStack` | EC2 sa PostgreSQL + Superset |
| `NotifStack` | CloudWatch alarmi, SNS, Discord Lambda |
