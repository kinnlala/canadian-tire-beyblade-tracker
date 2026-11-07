# Setup and testing

[Back to the project](../README.md)

Use Python 3.12, the version configured in the GitHub Actions workflows. Start with the tests; they do not contact retailers or send notifications.

## Get the code

```sh
git clone https://github.com/kinnlala/canadian-tire-beyblade-tracker.git
cd canadian-tire-beyblade-tracker
python -m venv .venv
```

Activate the environment:

```sh
# macOS / Linux
source .venv/bin/activate
```

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

On systems where Python is named `python3`, use that command instead of `python`. If PowerShell blocks activation, run `$python = (Resolve-Path .\.venv\Scripts\python.exe).Path` from the repository root, then replace `python` with `& $python` in the commands below. That absolute path still works after changing into `superstore`; changing your execution policy is not required.

## Tests

Run the Canadian Tire tests from the repository root:

```sh
python -m unittest discover -s tests -v
```

Run the Superstore tests separately:

```sh
python -m pip install -r superstore/requirements.txt
cd superstore
python -m unittest discover -s tests -v
cd ..
```

Both test files import a module named `tracker`, so run each suite from its own directory as shown. The Canadian Tire code uses the standard library; the Superstore suite needs its dependencies installed but does not need account credentials.

| Suite | Existing coverage |
| --- | --- |
| [Canadian Tire](../tests/test_tracker.py) | Store-key and store-list payloads; missing stores remain missing rather than becoming zero |
| [Superstore](../superstore/tests/test_tracker.py) | Status normalization; qualifying-transition membership; matching the target product |

These are focused unit tests, not an end-to-end test of retailer access or notification delivery. The current scheduled workflows run collection; they do not run these test suites.

## Canadian Tire: live collection

From the repository root:

```sh
python tracker.py
```

This contacts Canadian Tire's PriceAvailability API and updates your local `data/` files. It does not push changes to GitHub or send a notification. The old StockTrack SKU remains an identifier in the data; StockTrack is no longer the active collector source.

Use a disposable checkout for experiments. Cloning also copies the saved baseline and event history, so a local run is not automatically a new baseline. Do not overwrite the live repository's data with test output.

Requests may fail or return HTTP 403. Review `errors`, `fresh`, and `last_success_at` in [inventory.json](../data/inventory.json), not just the process exit code. Successful execution does not guarantee current stock information.

## Superstore: live collection

See the [Superstore guide](../superstore/README.md). Collection needs account-specific PC ID authorization and rotating token state. The login/bootstrap helper is not included, so this is not a one-command setup for a new account. Use the offline tests to inspect the code without those credentials.

## Scheduled checks

The existing workflows are:

| Collector | Workflow | Configured schedule |
| --- | --- | --- |
| Canadian Tire | [stock-watch.yml](../.github/workflows/stock-watch.yml) | Hourly, minute 17 UTC |
| Superstore | [superstore-stock-watch.yml](../.github/workflows/superstore-stock-watch.yml) | Hourly, minute 37 UTC |

They save results back to the repository. The configured schedules are not a guarantee of an exact execution time. Keep the existing paths and event format stable for readers of these files.

## ChatGPT notification handoff

The personal scheduled tasks read these public event feeds:

- [Canadian Tire events](https://raw.githubusercontent.com/kinnlala/canadian-tire-beyblade-tracker/main/data/events.json)
- [Superstore events](https://raw.githubusercontent.com/kinnlala/canadian-tire-beyblade-tracker/main/superstore/data/events.json)

Each feed contains an `events` array. An event has an `event_id`, a `checked_at` timestamp, and a `changes` array with the affected stores. A task should review unseen events and track the IDs already notified, rather than treating an old event as a new restock.

The notification task and its seen-event state are outside this repository. Forking the code does not copy that task. A separate setup would need its own feed URLs and notification state.

## Files at a glance

| Path | Purpose |
| --- | --- |
| [`tracker.py`](../tracker.py) | Canadian Tire requests, quantity parsing and comparison |
| [`superstore/tracker.py`](../superstore/tracker.py) | Superstore requests, status normalization and comparison |
| [`superstore/auth.py`](../superstore/auth.py) | PC ID token refresh handling |
| [`superstore/secure_state.py`](../superstore/secure_state.py) | Encryption and decryption of saved authorization state |
| `data/` and `superstore/data/` | Last-known readings, events and per-run history; Superstore also stores encrypted authorization state |

Never commit access tokens, refresh tokens, encryption keys, or plaintext authorization state. The public data is for stock monitoring; it should not contain personal account information.
