# Beyblade Restock Tracker

Personal stock monitoring for Canadian Tire and Real Canadian Superstore.

I built this to avoid checking store pages by hand. Python scripts collect stock readings, record qualifying changes, and save events for my separate ChatGPT scheduled tasks to review and notify me.

[Canadian Tire code](tracker.py) · [Superstore code](superstore/tracker.py) · [Tests](docs/SETUP.md#tests) · [Setup](docs/SETUP.md)

## How it works

```text
Scheduled checks → stock comparison → saved restock events → ChatGPT notification
```

GitHub Actions schedules the collectors hourly. This repository handles collection and event detection; the ChatGPT tasks are configured separately. Cloning the repository does not create notifications.

## What it tracks

| Retailer | Product | Configured coverage | Restock rule |
| --- | --- | --- | --- |
| Canadian Tire | Starter Pack `150-1281-6` | 60 stores: GTA, Peterborough and Barrie | Quantity increases by 3 or more |
| Real Canadian Superstore | Starter Pack Assortment `21595715_EA` | 17 stores: GTA and Peterborough | `OUT → LOW`, `OUT → OK`, or `LOW → OK` |

Store lists live in [tracker.py](tracker.py) and [superstore/config.json](superstore/config.json). Coverage means configured stores, not guaranteed successful readings. Superstore reports availability status, not a reliable item count.

## Example

Illustrative readings for one Canadian Tire store:

```text
First reading:  2 units  → establish baseline; no event
Next reading:  10 units  → +8 units; record a restock event
Request fails:          → retain 10 as last known; mark it stale
```

The first successful reading never triggers an event. Failed requests and missing products are not treated as zero stock or sold out.

## Explore the results

| Retailer | Last-known readings | Recorded restocks | Tests |
| --- | --- | --- | --- |
| Canadian Tire | [Inventory](data/inventory.json) | [Events](data/events.json) | [Quantity parsing](tests/test_tracker.py) |
| Superstore | [Store status](superstore/data/status.json) | [Events](superstore/data/events.json) | [Status handling](superstore/tests/test_tracker.py) |

Start with the [offline tests](docs/SETUP.md#tests) to inspect the project without retailer credentials. The setup guide also explains local runs and the event files used by the ChatGPT tasks.

## Limitations

Retailer requests can fail or be blocked. Check each store's `fresh` and `last_success_at` fields before using a saved reading; a completed workflow is not proof of fresh data.

These are assortment listings, not specific Beyblade models. This is an unofficial personal tool, not a retailer service. Confirm availability with the store before travelling.
