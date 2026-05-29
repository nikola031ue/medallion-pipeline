# Silver Layer — Šema podataka

## Tabele

### `users`

| Kolona | Tip | Opis |
|---|---|---|
| `user_id` | UUID | Generisani primarni ključ |
| `username` | String | HN ili X korisničko ime |
| `platform` | String | `HackerNews` ili `X` |
| `karma_score` | Integer | Karma poeni — null za X korisnike |
| `is_verified` | Boolean | Verifikovan nalog — null za HN korisnike |
| `created_at` | Timestamp | Datum kreiranja naloga (UTC ISO-8601) |

**Primarni ključ:** `user_id`  
**Jedinstveni ključ:** `(username, platform)` — isti username može postojati na obje platforme

---

### `posts`

| Kolona | Tip | Opis |
|---|---|---|
| `post_id` | String | Originalni ID iz izvorne platforme |
| `author_username` | String | FK ka `users.username` |
| `content_text` | String | Očišćen sadržaj objave |
| `created_at` | Timestamp | Datum objave (UTC ISO-8601) |
| `post_type` | String | `story` / `comment` / `ask_hn` / `show_hn` / `job` / `poll` / `tweet` / `retweet` |

**Primarni ključ:** `post_id`

---

## Particioniranje

| Tabela | Particija | Razlog |
|---|---|---|
| `users` | `platform` | Odvojeno čitanje HN i X korisnika |
| `posts` | `post_type` | Gold upiti filtriraju po tipu objave |

Format u S3:
```
silver/
  users/
    platform=HackerNews/
    platform=X/
  posts/
    post_type=story/
    post_type=comment/
    post_type=tweet/
    post_type=retweet/
    ...
```

---

## Normalizacija (3NF)

Šema zadovoljava treću normalnu formu:

- `users` — svi atributi zavise isključivo od `user_id` (primarnog ključa)
- `posts` — svi atributi zavise isključivo od `post_id`
- Nema tranzitivnih zavisnosti — `author_username` je FK, ne denormalizovani podatak

---

## Mapiranje iz Bronze layera

### Hacker News → Silver

| Bronze polje | Silver kolona | Tabela |
|---|---|---|
| `author` | `username` | `users` |
| `created_at` (Unix ts) | `created_at` | `users`, `posts` |
| `objectID` | `post_id` | `posts` |
| `story_text` / `comment_text` / `title` | `content_text` | `posts` |
| `_tags[0]` | `post_type` | `posts` |

### X (Twitter) → Silver

| Bronze polje | Silver kolona | Tabela |
|---|---|---|
| `user_name` | `username` | `users` |
| `user_verified` | `is_verified` | `users` |
| `user_created` | `created_at` | `users` |
| `user_followers` | — | Koristi se za Gold metriku |
| `text` | `content_text` | `posts` |
| `date` | `created_at` | `posts` |
| `is_retweet` | `post_type` (`tweet` / `retweet`) | `posts` |
