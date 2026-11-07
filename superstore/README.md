# Superstore collector

[Project overview](../README.md) · [Offline tests](../docs/SETUP.md#tests) · [Source](tracker.py)

Tracks Beyblade X Starter Pack Set Assortment (`21595715_EA`) at the stores in [config.json](config.json).

## Availability, not quantities

The collector uses PC Express `stockStatus`:

| Value | Meaning |
| --- | --- |
| `OUT` | Out of stock |
| `LOW` | Low stock |
| `OK` | Available |

`maxOrderQuantity` is an ordering limit, not a trustworthy stock count, so it is not used to measure inventory.

Only `OUT → LOW`, `OUT → OK`, and `LOW → OK` create events. The first successful reading establishes a baseline. Failed requests, missing products, and missing statuses retain the last known reading rather than turning it into `OUT`.

The saved files are [status.json](data/status.json), [events.json](data/events.json), and [history.ndjson](data/history.ndjson). Check `fresh` and `last_success_at` before treating a status as current. `NOT_RETURNED` means the search did not return the product; it does not mean sold out.

## Running the collector

**Offline tests need no credentials.** Follow the [test instructions](../docs/SETUP.md#tests).

Live collection needs your own authorized PC ID token state. The personal login helper referenced as `login_pcid.py` in error messages is **not included in this repository**. A fresh clone is therefore not enough to configure a new account.

For an already authorized setup, [auth.py](auth.py) loads `.state/pcid_token_state.json`, or uses `PCEXPRESS_REFRESH_TOKEN` when no local state exists. Then, from this directory:

```sh
python -m pip install -r requirements.txt
python tracker.py
```

This updates local files. It does not send notifications or push changes to GitHub. Do not run local experiments against the same rotating token chain used by the scheduled workflow.

## Scheduled authorization state

The [GitHub Actions workflow](../.github/workflows/superstore-stock-watch.yml) uses:

| Secret | Purpose |
| --- | --- |
| `PCEXPRESS_REFRESH_TOKEN` | Seeds an authorized setup when saved state is absent |
| `PCEXPRESS_STATE_KEY` | Encrypts and decrypts the saved state with Fernet |

Refresh tokens can rotate. The workflow decrypts `data/pcid_state.enc`, runs the collector, and saves the latest state encrypted again. The encryption key stays in GitHub Actions secrets, not in the repository.

For a separate authorized setup, generate a **new** key locally:

```sh
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Store it privately as `PCEXPRESS_STATE_KEY`. A new key cannot decrypt this repository's existing encrypted state. A separate fork needs its own state; do not replace the key or state used by the running tracker.

Plaintext authorization state and local virtual environments are not protected by an existing repository `.gitignore`. Keep them out of commits. Never paste tokens or keys into issues, logs, or documentation.

The separate ChatGPT task reads only the [event feed](data/events.json), not authorization state.
