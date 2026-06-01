# End-to-End Test Komande

## 1. Bronze — pokreni HN fetch

```powershell
aws lambda list-functions --query "Functions[?contains(FunctionName,'BronzeStack')].FunctionName" --output text --region eu-central-1
```

```powershell
aws lambda invoke --function-name <ime-iz-gornjeg> --invocation-type Event --region eu-central-1 out.json
```

Sačekaj 2-3 minute, pa provjeri S3:

```powershell
aws s3 ls s3://social-medias/bronze/hacker-news/ --recursive --region eu-central-1
```

---

## 2. Silver — pokreni normalizaciju

```powershell
aws stepfunctions start-execution --state-machine-arn arn:aws:states:eu-central-1:765366202270:stateMachine:silver-normalization --region eu-central-1
```

Provjeri status (ponavljaj dok ne bude `SUCCEEDED`):

```powershell
aws stepfunctions list-executions --state-machine-arn arn:aws:states:eu-central-1:765366202270:stateMachine:silver-normalization --query "executions[0].{status:status}" --output text --region eu-central-1
```

---

## 3. Gold — pokreni pipeline

```powershell
aws stepfunctions start-execution --state-machine-arn arn:aws:states:eu-central-1:765366202270:stateMachine:gold-pipeline --region eu-central-1
```

Provjeri status (ponavljaj dok ne bude `SUCCEEDED`):

```powershell
aws stepfunctions list-executions --state-machine-arn arn:aws:states:eu-central-1:765366202270:stateMachine:gold-pipeline --query "executions[0].{status:status}" --output text --region eu-central-1
```

---

## 4. Provjeri PostgreSQL tabele

```powershell
aws ssm start-session --target i-02a7566d61cfc5fa5 --region eu-central-1
```

```bash
sudo docker exec -it medallion-db-1 psql -U superset -d superset -c "SELECT schemaname, relname as table_name, n_live_tup as rows FROM pg_stat_user_tables ORDER BY relname;"
```

---

## 5. Provjeri trenutnu IP adresu EC2 instance

```powershell
aws ec2 describe-instances --instance-ids i-02a7566d61cfc5fa5 --query "Reservations[0].Instances[0].PublicIpAddress" --output text --region eu-central-1
```

---

## 6. Otvori Superset

```
http://<IP-IZ-GORNJEG>:8088
```

- Username: `admin`
- Password: `admin`
- Dashboards → **Medallion Pipeline**

---

## 7. Test Discord notifikacije

```powershell
aws lambda invoke --function-name NotifStack-DiscordNotifierEBEBE851-sapdeIFdFOKE --payload fileb://cdk/payload.json --region eu-central-1 out.json
```
