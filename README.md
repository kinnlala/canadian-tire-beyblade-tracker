# Canadian Tire BeyBlade Starter Restock Watch

Tracks **BeyBlade X Starter Pack** — Canadian Tire product **#150-1281-6**
(StockTrack SKU **1501281**) across 24 selected Canadian Tire locations in
Durham Region, York Region, Peterborough, and Barrie.

## Alert rule

A store qualifies only when its numeric quantity:

- increases by **3 or more** versus the immediately previous successful reading; or
- changes from **0 to 3 or more**.

The first successful reading for each individual store becomes that store's
baseline and never generates an alert.

If a StockTrack request fails, that store's last known quantity is retained.
Missing data is **never** treated as zero.

## Files

- `tracker.py` — fetches and compares store quantities.
- `data/inventory.json` — latest state for all 24 stores.
- `data/events.json` — durable list of qualifying restock events.
- `data/history.ndjson` — one compact history record per run.
- `.github/workflows/stock-watch.yml` — hourly GitHub Actions schedule.

## GitHub setup

1. Create a **public** GitHub repository named `canadian-tire-beyblade-tracker`.
2. Put these files in the repository's `main` branch.
3. Open **Actions** and enable workflows if GitHub asks.
4. Open the **Beyblade stock watch** workflow and choose **Run workflow** once.
5. Confirm `data/inventory.json` now contains numeric quantities for the stores
   that were successfully read.

The repository needs to be public only because the ChatGPT watch reads the raw
`events.json` file without your GitHub login. The files contain only store
inventory data; there are no credentials or secrets.

## ChatGPT bridge URLs

After the repository is created under GitHub user `kinnlala`, the two bridge
URLs are:

- `https://raw.githubusercontent.com/kinnlala/canadian-tire-beyblade-tracker/main/data/inventory.json`
- `https://raw.githubusercontent.com/kinnlala/canadian-tire-beyblade-tracker/main/data/events.json`

The ChatGPT automation should read `events.json`, compare the newest
`event_id` with the last notified event ID, and notify only for a new event.

## Stores

### Durham
- 0187 — Whitby South
- 0460 — Whitby North
- 0075 — Oshawa Mid
- 0336 — Oshawa North
- 0160 — Ajax
- 0324 — Pickering
- 0170 — Bowmanville
- 0127 — Uxbridge
- 0226 — Port Perry

### York Region
- 0164 — Markham
- 0087 — Richmond Hill
- 0697 — Richmond Hill North
- 0399 — Markham East
- 0653 — Maple (Vaughan)
- 0237 — Woodbridge
- 0321 — Dufferin & 407 (Thornhill)
- 0189 — Aurora
- 0069 — Newmarket
- 0280 — Stouffville
- 0134 — Keswick

### Peterborough + Barrie
- 0081 — Peterborough
- 0660 — Peterborough North
- 0006 — Barrie
- 0444 — Barrie South

## Source

The tracker calls StockTrack's public Canadian Tire multi-store availability
endpoint. StockTrack is independent of Canadian Tire, and inventory counts can
be inaccurate or delayed. Call the store before making a special trip.
