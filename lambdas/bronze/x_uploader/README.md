# X (Twitter) Bronze Data — Manuelni Upload

Budući da je besplatna verzija X API-ja jako limitirana, koriste se pre-postojeći Kaggle dataseti.

## Preuzimanje dataseta

Primeri dataseta koje možeš koristiti:
- [Bitcoin Tweets](https://www.kaggle.com/datasets/kaushiksuresh147/bitcoin-tweets)
- [Covid Tweets](https://www.kaggle.com/datasets/gpreda/covid19-tweets)

## Upload u S3

Nakon preuzimanja CSV fajla, uploaduj ga u bronze layer:

```bash
aws s3 cp bitcoin_tweets.csv s3://social-medias/bronze/x/raw/bitcoin_tweets.csv
aws s3 cp covid_tweets.csv   s3://social-medias/bronze/x/raw/covid_tweets.csv
```

## S3 struktura

```
s3://social-medias/bronze/x/raw/
    bitcoin_tweets.csv
    covid_tweets.csv
    ...
```

Silver layer Lambda čita iz `bronze/x/raw/` prefiksa.
