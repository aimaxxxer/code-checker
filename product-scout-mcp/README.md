# Product Scout MCP

An MCP server that connects Claude to Chinese wholesale marketplaces — AliExpress,
Alibaba.com and Temu — and turns a keyword into a ranked, risk-screened product
shortlist with real unit economics.

It is not a wrapper around a search box. The interesting part is what happens
between the search and the answer: a retail price benchmark to compute margin
against, import duty modelled as a real cost, an IP and compliance screen, and a
scoring model that treats zero competitors as a warning sign rather than a
jackpot.

See **[RESEARCH.md](RESEARCH.md)** for the full comparison of every route from
Claude to these marketplaces — official APIs, what they cost, what approval each
one needs, and what is realistically obtainable.

---

**New to this? Read [SETUP.md](SETUP.md)** — the same thing with nothing assumed,
including where to click and what each key is for.

## Quickstart

```bash
git clone <your-repo-url> product-scout-mcp
cd product-scout-mcp
bash scripts/setup.sh
```

That installs everything, verifies it runs, and prints the exact config block for
your machine. It is safe to re-run at any time.

Run it with no credentials at all to see the output shape (synthetic data,
clearly labelled):

```bash
uv run python scripts/smoke.py
```

Then connect it to Claude Code:

```bash
claude mcp add product-scout -- /absolute/path/to/product-scout-mcp/.venv/bin/python -m product_scout.server
```

Or drop this in `.mcp.json` in any project, or in `claude_desktop_config.json`
for Claude Desktop:

```json
{
  "mcpServers": {
    "product-scout": {
      "command": "/absolute/path/to/product-scout-mcp/.venv/bin/python",
      "args": ["-m", "product_scout.server"],
      "env": {
        "ALIEXPRESS_APP_KEY": "...",
        "ALIEXPRESS_APP_SECRET": "...",
        "ALIEXPRESS_TRACKING_ID": "default",
        "SERPAPI_KEY": "...",
        "APIFY_TOKEN": "..."
      }
    }
  }
}
```

Then ask Claude things like:

> Find winning products for a pet-supplies store targeting the US, budget under $15 landed.

> I saw this on TikTok: a cordless heated neck massager, supplier price $8.40, 14k sold, 4.7 stars. Is it worth testing?

> At a $34 sell price and $8.40 cost, what CPA can I afford before I lose money?

---

## Credentials

Everything is optional. With no keys the server runs in demo mode; each key
switches one capability from synthetic to live. `provider_status` tells you
exactly what is on.

| Variable | Unlocks | Where to get it |
|---|---|---|
| `ALIEXPRESS_APP_KEY` / `ALIEXPRESS_APP_SECRET` | Live AliExpress catalogue via the official API | [portals.aliexpress.com](https://portals.aliexpress.com) → join affiliate programme → create app |
| `ALIEXPRESS_TRACKING_ID` | Affiliate attribution (defaults to `default`) | Same console |
| `SERPAPI_KEY` | Retail price benchmark + Google Trends | [serpapi.com](https://serpapi.com) — 100 free searches/month |
| `APIFY_TOKEN` | Temu and Alibaba (neither has a public product API) | Apify Console → Settings → API & Integrations |

Copy `.env.example` to `.env` and fill in what you have.

If the AliExpress gateway rejects your signature, flip `ALIEXPRESS_SIGN_METHOD`
between `sha256` and `md5` and `ALIEXPRESS_TIMESTAMP_STYLE` between `ms` and
`datetime`. Which pair your app key wants depends on when it was provisioned;
the error message from `provider_status` says the same thing.

---

## Tools

| Tool | What it does |
|---|---|
| `find_winning_products` | The main one. Search → benchmark → screen → rank, with every score component shown. |
| `search_supplier_catalog` | Raw normalised listings from AliExpress, Temu or Alibaba. |
| `score_product` | Score a product you found yourself. Needs no API keys. |
| `estimate_unit_economics` | Landed cost, margin, breakeven CPA and ROAS, duty included. |
| `benchmark_retail_price` | What it actually sells for at retail, and how many sellers offer it. |
| `check_demand_trend` | 12-month search interest; separates a sustained rise from a fad spike. |
| `check_product_risk` | IP, regulatory and shipping-restriction screen. |
| `shortlist_add` / `shortlist_list` / `shortlist_remove` | Persistent shortlist across sessions. |
| `provider_status` | Which sources are live, which are synthetic, and what is missing. |
| `scoring_model` | How the score is computed, so you can disagree with it. |

---

## How the score works

Six weighted components, each 0–100:

| Component | Weight | Signal |
|---|---|---|
| Demand | 25% | Search-trend direction blended with **units/day**, not lifetime units sold |
| Margin | 25% | Gross margin vs a real retail benchmark, after duty, VAT, fees and refunds |
| Competition | 15% | **Inverted U** — see below |
| Supplier | 15% | Product rating, store rating, review depth, store age |
| Logistics | 10% | Delivery days, weight, carrier-restricted attributes, local stock |
| Content | 10% | Creative headroom read from the title |

Four decisions in here differ from the usual product-research tool, and they are
the reason the output is worth reading:

**Competition is an inverted U.** Most tools score "few competitors" as good.
In practice zero competitors almost always means no demand, not an untapped
market. The curve peaks around 6–40 competing listings — enough to prove people
buy this, few enough that you can still get in.

**Margin is computed against retail, not against the listing's fake discount.**
The crossed-out "original price" on a marketplace listing is marketing. The
number that matters is what the product sells for in your market, which is what
the shopping benchmark answers.

**Duty is a real line item.** The US $800 de minimis exemption was suspended for
China and Hong Kong in May 2025, extended to all origins that August, and the
flat per-parcel fee option was withdrawn in March 2026 — so China-direct parcels
are assessed on declared value. A margin model that still assumes duty-free
import is wrong by tens of percent. Confirm the live rate for your HTS code;
the default here is a modelling starting point, not customs advice.

**Missing data lowers confidence, it does not score zero.** A product with no
trend data is unknown, not bad. Components that are absent are renormalised out
and reported in `missing_signals`.

Risk gates cap the total rather than subtracting from it, so a trademark problem
cannot be outvoted by a fat margin:

- IP/counterfeit exposure → capped at 25
- Three or more regulatory obligations → capped at 55
- Any regulated category → capped at 72
- Negative contribution margin → capped at 20

---

## What this cannot do

- **It does not predict sales.** It ranks candidates against each other on the
  data available. Your creative, your audience and your fulfilment decide most
  of the outcome, and none of them are visible here.
- **The compliance screen is keyword matching**, tuned to over-flag. It is a
  first pass that catches the obvious, not a legal clearance.
- **Temu and Alibaba data comes from scrapers**, because neither offers a public
  product API. Scraper output is less reliable than an official API and sits in
  a greyer area with respect to those sites' terms of service. RESEARCH.md
  covers the trade-off honestly.
- **The AliExpress provider is written to the published API spec but has not
  been executed against a live approved app key**, because that requires an
  approved affiliate account. The signing implementation is unit-tested against
  the documented algorithm; the first live call is still the real test, and the
  error messages are written to help you debug exactly that moment.

## Development

```bash
uv run pytest          # unit tests
uv run python scripts/smoke.py   # end-to-end pipeline in demo mode
```

## Licence

MIT
