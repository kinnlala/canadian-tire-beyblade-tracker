# Real Canadian Superstore Beyblade Restock Tracker

Tracks **Beyblade X Starter Pack Set Assortment** (`21595715_EA`) through the
current PC Express backend.

## What this tracker can reliably observe

PC Express exposes store-specific `stockStatus`, but it does not expose a
trustworthy numeric on-hand count. Testing showed that `maxOrderQuantity=25`
is an ordering cap: an OUT store can still report 25.

This tracker therefore records these normalized statuses:

- `OUT` — out of stock
- `LOW` — low stock
- `OK` — available

A restock event is created only for an improvement:

- `OUT -> LOW`
- `OUT -> OK`
- `LOW -> OK`

The first successful reading at each store becomes its baseline and does not
generate an alert.

API failures and successful searches that do not return the product are **not**
treated as OUT and do not overwrite the last known good status.

## Stores

### Durham
- `1012` — Kingston Road, Ajax
- `1043` — Harmony Road, Oshawa
- `1058` — Taunton Road, Whitby
- `2842` — Gibb Street, Oshawa

### York Region
- `1018` — Yonge Street, Newmarket / East Gwillimbury
- `1030` — Bayview Avenue, Aurora

### Peterborough
- `2831` — Borden Avenue, Peterborough

### Barrie
No physical Real Canadian Superstore location is included because Barrie does
not currently have a physical RCSS store.

## Why token state is encrypted

PC ID refresh tokens rotate: once a refresh token is used, the returned newer
refresh token must be saved for the next run.

GitHub Actions runners are temporary, so this tracker stores the latest PC ID
state as `data/pcid_state.enc`. That file is encrypted with a Fernet key kept
only in the GitHub Actions secret `PCEXPRESS_STATE_KEY`.

The plaintext token state is never committed.

## GitHub Secrets you need

In your repository:

`Settings -> Secrets and variables -> Actions -> New repository secret`

Create:

### 1. PCEXPRESS_REFRESH_TOKEN

Use the refresh token produced by `login_pcid.py`.

If you already ran the local probes, your original printed token has probably
been consumed. Use the latest `refresh_token` inside your local
`.pcx-state/pcid_token_state.json`, or run `login_pcid.py` one more time to
create a fresh token chain.

**Never commit or paste this token into a public file.**

### 2. PCEXPRESS_STATE_KEY

Generate a random key locally:

```text
python -c "import os,base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
```

Copy the result into the GitHub secret named `PCEXPRESS_STATE_KEY`.

Do not put this key in the repository.

## First run

Once the files and both secrets exist:

1. Go to `Actions`.
2. Open `Superstore Beyblade stock watch`.
3. Click `Run workflow`.
4. Wait for it to complete.
5. Open `superstore/data/status.json`.

The first successful run establishes the baseline and should not alert you.

## Files

- `config.json` — product and store list
- `auth.py` — rotating PC ID token manager
- `secure_state.py` — encrypts/decrypts PC ID state
- `tracker.py` — hourly store checker and transition comparison
- `data/status.json` — latest known store status
- `data/events.json` — durable qualifying restock events
- `data/history.ndjson` — hourly history
- `data/pcid_state.enc` — generated after first run; encrypted token state

The ChatGPT alert should read only `superstore/data/events.json`.
