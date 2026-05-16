# Twitter/X Dataset — Schema dokumentacija

## Dataset

**Naziv:** COVID-19 Tweets  
**Izvor:** [Kaggle — gpreda/covid19-tweets](https://www.kaggle.com/datasets/gpreda/covid19-tweets)  
**Format:** CSV  
**S3 lokacija:** `s3://social-medias/bronze/twitter/covid_tweets.csv`

## Kolone

| Kolona | Tip | Opis | Primer |
|---|---|---|---|
| `user_name` | String | Twitter korisničko ime | `Tom Basile` |
| `user_location` | String | Lokacija korisnika (slobodan tekst, može biti null) | `New York, NY` |
| `user_description` | String | Bio korisnika | `Husband, Father, Columnist...` |
| `user_created` | Timestamp | Datum kreiranja naloga (`YYYY-MM-DD HH:MM:SS`) | `2009-04-16 20:06:23` |
| `user_followers` | Integer | Broj pratilaca | `2253` |
| `user_friends` | Integer | Broj naloga koje korisnik prati | `1677` |
| `user_favourites` | Integer | Ukupan broj lajkovanih tvitova | `24` |
| `user_verified` | Boolean | Da li je nalog verifikovan | `True` / `False` |
| `date` | Timestamp | Datum objave tvita (`YYYY-MM-DD HH:MM:SS`) | `2020-07-25 12:27:17` |
| `text` | String | Sadržaj tvita (do 280 karaktera) | `Hey @Yankees...` |
| `hashtags` | String | Hashtagovi (može biti prazan string) | `#COVID19` |
| `source` | String | Twitter klijent korišten za objavu | `Twitter for Android` |
| `is_retweet` | Boolean | Da li je tvit retvit | `True` / `False` |

## Mapiranje na silver layer šemu

| CSV kolona | Silver kolona | Tabela |
|---|---|---|
| `user_name` | `username` | `users` |
| `user_followers` | — | koristi se za gold metriku (top 10 pratilaca) |
| `user_verified` | `is_verified` | `users` |
| `user_created` | `created_at` | `users` |
| `date` | `created_at` | `posts` |
| `text` | `content_text` | `posts` |
| `is_retweet` | `post_type` (`tweet` ili `retweet`) | `posts` |
