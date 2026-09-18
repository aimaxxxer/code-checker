# Connecting Claude to Chinese wholesale marketplaces

Research notes behind this repo: every route from Claude to AliExpress, Alibaba
and Temu, what each one actually requires, and which are worth your time.

**Short version:** there is exactly one marketplace here with a real, public,
approvable API — AliExpress. Alibaba.com's API is a seller/ERP tool that will
not answer "find me good products". Temu has no buyer-facing API at all. So a
serious setup uses the AliExpress official API as its spine, a scraper provider
for Temu/Alibaba coverage, and a separate source for the demand and retail-price
data that decides whether a product is actually worth selling.

---

## 1. The mechanism: MCP

Claude connects to outside systems through the **Model Context Protocol** — a
server exposes tools, Claude calls them. That is what this repo is. Three ways
to get one:

| Route | Effort | When it fits |
|---|---|---|
| **Write your own MCP server** (this repo) | Hours | You want your own scoring logic, your own cost model, and no per-call fee on the thinking |
| **Use a hosted MCP server** (e.g. Apify's at `https://mcp.apify.com`) | Minutes | You just want raw marketplace data in Claude and will do the judging yourself |
| **Connect through an automation platform** (n8n, Make, Zapier) | Medium | You already run flows there and want Claude as one node |

The hosted route is genuinely fast — add the URL, do the OAuth, done. The reason
to write your own is that raw listings are the easy part. Deciding what is worth
selling needs a retail benchmark, an import-duty model and a risk screen, and
none of those come out of a scraper.

---

## 2. AliExpress — the one with a real API

**AliExpress Open Platform** (`openservice.aliexpress.com`) is the only
marketplace here where an individual can get approved API access to product
data. Two relevant API families:

### Affiliate API — `aliexpress.affiliate.*`

The practical choice for product research.

| | |
|---|---|
| **Access** | Join the affiliate programme at `portals.aliexpress.com`, then create an app in the console |
| **Requirements** | Basic details plus ID; a business licence field accepts personal ID if self-employed |
| **Approval time** | Typically 1–3 business days |
| **Cost** | Free (you are a publisher; they pay you) |
| **Gateway** | `https://api-sg.aliexpress.com/sync` |

Useful methods:
- `aliexpress.affiliate.product.query` — keyword search with price, category, ship-to and sort filters
- `aliexpress.affiliate.hotproduct.query` — marketplace-curated high-volume listings
- `aliexpress.affiliate.productdetail.get` — full detail for specific product IDs
- `aliexpress.affiliate.category.get` — category tree
- `aliexpress.affiliate.link.generate` — trackable affiliate links

### Dropshipping API — `aliexpress.ds.*`

Adds order placement, logistics quotes and a recommendation feed
(`aliexpress.ds.recommend.feed.get`, `aliexpress.ds.text.search`). Requires a
dropshipping-centre account rather than an affiliate one; some feed methods need
your app key separately whitelisted by email.

### Request signing — the part that wastes everyone's afternoon

Every call is signed with the Taobao/Alibaba "TOP" scheme:

1. Take every request parameter including `method`, `app_key`, `timestamp`, `v`, `sign_method`
2. Sort by key name, ASCII order
3. Concatenate as `key1value1key2value2…` — no separators, no `=`, no URL encoding
4. Hash, and uppercase the hex

Two hash modes exist in the wild, and **which one your app key wants depends on
when it was provisioned**:

- `sha256` → `HMAC-SHA256(app_secret, concatenated_string)`
- `md5` → `MD5(app_secret + concatenated_string + app_secret)`

The timestamp has the same problem: current docs say milliseconds since epoch,
legacy gateways want `YYYY-MM-DD HH:MM:SS` **in GMT+8**. Signature values are
case-sensitive throughout, including enum values like `SALE_PRICE_ASC`.

This repo implements all four combinations and lets you flip between them with
two environment variables, because the error you get when you pick wrong is an
unhelpful "invalid signature" and this is the single most common place people
give up.

> Implemented here in `src/product_scout/providers/aliexpress.py`. The signing
> is unit-tested against the documented algorithm. It has **not** been executed
> against a live approved app key — that needs an approved affiliate account —
> so treat your first live call as the real test. The error messages are written
> to help with exactly that moment.

---

## 3. Alibaba.com — an API, but not the one you want

`openapi.alibaba.com` exists and is documented, but it is built for **sellers
and ERP integration**: syncing your own product catalogue, managing your own
orders. Roughly 20+ endpoints, JSON/XML, with examples in most languages.

The dropshipping endpoints are gated behind Dropshipping Center membership —
non-members cannot call them at all.

**What this means for product research:** Alibaba's API will not answer "search
all suppliers for trending products". It answers "manage my account". For B2B
sourcing research — MOQs, supplier verification status, tiered pricing — you are
looking at scrapers or a data vendor.

Worth knowing: **1688.com** (Alibaba's domestic Chinese marketplace) has
genuinely better prices than Alibaba.com's export listings, but its open
platform generally expects a Chinese business entity, and the site is
Chinese-language with domestic-only payment and shipping. Most Western buyers
reach it through a sourcing agent rather than an API.

---

## 4. Temu — no public API

Temu has a **Partner Platform** (`partner.temu.com`, `partner-eu.temu.com`) with
open APIs, but it is for **approved sellers and software vendors** building
tools for merchants selling *on* Temu. There is no buyer-side product search API
for developers.

Temu does document a **Research API** (`temu.research.sor.query`) behind a Data
Access Portal, which appears aimed at academic and regulatory researchers under
DSA-style data-access obligations rather than at commercial product scouting.
Worth an application if you have a research affiliation; not a realistic route
for a store owner.

**In practice, Temu data comes from scrapers.** Multiple Apify actors cover Temu
search, product detail and store catalogues, returning price, market price,
discount, rating, review count, sales volume and shipping.

---

## 5. Third-party data providers

Where the official APIs run out.

| Provider | Covers | Pricing shape | Notes |
|---|---|---|---|
| **Apify** | AliExpress, Temu, Alibaba, most e-commerce | Per actor-run compute | Large actor library; **has its own hosted MCP server**, so it also works with zero code |
| **Bright Data** | Broad, incl. structured e-commerce datasets | Volume-based, enterprise-leaning | Also ships an MCP server |
| **Oxylabs** | Similar footprint | Subscription | Also ships an MCP server |
| **SerpApi** | Google Shopping, Amazon, Walmart, eBay, **Google Trends** | ~100 free searches/month, then per-credit; priciest per call but reliable | The retail-benchmark and trend source used here |
| **Scrape.do / Scrapfly / Serper** | SERP and shopping | ~1,000 free credits/month; much cheaper per call | Worth swapping in if SerpApi cost bites |

**On terms of service, plainly:** scraping AliExpress, Temu or Alibaba is
against those sites' terms, whoever runs the scraper. Using a provider moves the
operational risk, not the contractual position. The official AliExpress API is
the only route here that is unambiguously sanctioned, which is a real argument
for making it your primary source and treating scraped Temu/Alibaba data as
supplementary. That is how this repo is wired by default.

---

## 6. The data that actually decides the answer

This is the part most "connect AI to AliExpress" setups skip, and it is the part
that determines whether a product makes money.

A supplier listing tells you cost. It cannot tell you:

**What it sells for at retail.** Margin is the gap between landed cost and
market price. The marketplace's own crossed-out "original price" is marketing
fiction. Real sources: Google Shopping (via SerpApi or a cheaper SERP API),
Amazon (Keepa, Rainforest), eBay's official Browse API.

**Whether demand is rising.** Google Trends has no official public API — the
alpha is waitlisted, and `pytrends` was archived in April 2025. Working options
are SerpApi's `google_trends` engine, Glimpse, or Trends MCP. What matters is
the *shape*: a sustained 3–6 month rise is a market, a vertical spike is a fad
whose window has usually closed by the time you can stock it.

**How saturated it already is.** Count sellers at the retail benchmark, check
the Facebook Ad Library API for ad volume, and look at TikTok Creative Center.
Note the counter-intuitive part: **zero competition is a bad sign, not a good
one.** It almost always means unproven demand. The sweet spot is a handful of
sellers visibly making money.

**What it costs to land.** See below — this changed recently and materially.

---

## 7. The thing that changed the maths: US de minimis is gone

This invalidates most dropshipping margin advice written before 2025.

| Date | What changed |
|---|---|
| **2 May 2025** | De minimis suspended for China and Hong Kong |
| **May–Aug 2025** | 54% ad valorem duty, or a flat $100/parcel |
| **29 Aug 2025** | Suspension extended to **all** countries; flat fee $200/parcel |
| **Feb 2026** | Supreme Court struck down IEEPA tariffs — but the de minimis suspension rests on separate authority (Section 321 / TFTEA) and **survived** |
| **1 Mar 2026** | Flat per-parcel fee option withdrawn — duty is assessed on declared value |
| **24 Jun 2026** | CBP suspension of the $800 threshold for non-postal modes made indefinite |

**The practical consequence:** a $8 product that used to land at $8 now lands at
$8 plus duty plus the brokerage the carrier adds. A margin model that assumes
duty-free import is wrong by tens of percent, and the error lands entirely in
your contribution margin — the number your whole ad budget is sized from.

This repo therefore treats duty as a first-class line item in
`src/product_scout/economics.py`, with the caveat attached to every result that
rates move with policy and you should confirm yours against your actual HTS
code. It is a modelling default, not customs advice.

UK and EU have their own version of this: UK import VAT applies from the first
pound (customs duty generally above £135), EU VAT from the first euro under
IOSS (duty generally above €150).

---

## 8. What this repo does with all of that

```
Claude
  │
  ├── find_winning_products("pet water fountain", market="US")
  │      │
  │      ├─ 1. supplier listings ── AliExpress official API
  │      │                          └─ falls back to Apify, then demo
  │      ├─ 2. retail benchmark ─── SerpApi Google Shopping
  │      ├─ 3. demand trend ─────── SerpApi Google Trends
  │      ├─ 4. risk screen ──────── local: IP, regulatory, shipping
  │      ├─ 5. unit economics ───── local: duty, VAT, fees, refund reserve
  │      └─ 6. score & rank ─────── local: six weighted components
  │
  └── ranked shortlist, every component visible and arguable
```

Design decisions worth defending:

- **Official API first, scrapers as fallback.** Sanctioned access beats
  convenient access when both are available.
- **Everything degrades rather than fails.** No keys at all still runs, on
  clearly-labelled synthetic data. One missing key breaks one capability, not
  the session.
- **Scoring is local and transparent.** No per-call fee on judgement, and every
  component, weight and penalty is returned so you can disagree with it.
- **Unmatched listings do not inherit the benchmark price.** A search returns
  products that are not what you searched for; pricing those against the query's
  retail median invents margin from nothing. They get markup-based pricing, a
  capped margin score and a rank discount instead.
- **Fake data announces itself.** Every synthetic result carries a `SYNTHETIC`
  note. Unlabelled fake data is worse than no data.

---

## 9. If you want the fastest possible version instead

Skip this repo. Add Apify's hosted MCP server to Claude:

```json
{ "mcpServers": { "apify": { "url": "https://mcp.apify.com" } } }
```

Complete the OAuth, and Claude can run AliExpress and Temu scrapers directly.
You get raw listings in minutes and do the judging in conversation.

What you give up: the retail benchmark, the duty-aware economics, the compliance
screen, the consistent scoring, and the shortlist that persists between
sessions. Which is to say — the parts that turn a list of cheap products into a
decision.

---

## Sources

- [AliExpress Open Platform](https://openservice.aliexpress.com/) · [API reference](https://openservice.aliexpress.com/doc/api.htm) · [getting started](https://openservice.aliexpress.com/doc/doc.htm)
- [Alibaba.com Open Platform](https://openapi.alibaba.com/doc/doc.htm) · [API reference](https://openapi.alibaba.com/doc/api.htm)
- [Temu Partner Platform](https://partner.temu.com/) · [Research API overview](https://partner-eu.temu.com/documentation?menu_code=98501210a0cc465695e6d94e364bb83c) · [Data Access Portal](https://partner-eu.temu.com/researcher-instruction)
- [Apify MCP server](https://github.com/apify/apify-mcp-server) · [Apify Claude Desktop integration](https://docs.apify.com/integrations/claude-desktop)
- [Model Context Protocol](https://www.anthropic.com/news/model-context-protocol) · [MCP servers](https://github.com/modelcontextprotocol/servers) · [Claude Agent SDK MCP docs](https://platform.claude.com/docs/en/agent-sdk/mcp)
- [SerpApi Google Trends](https://serpapi.com/blog/scraping-google-trends-with-python-pytrends-alternative/) · [pytrends (archived)](https://github.com/GeneralMills/pytrends) · [Google Trends API alternatives](https://meetglimpse.com/google-trends-api/)
- [Best Google Shopping APIs 2026](https://scrape.do/blog/best-google-shopping-api/) · [SERP API comparison](https://scrapfly.io/blog/posts/google-serp-api-and-alternatives)
- [CBP: tariff on de minimis shipments from China](https://www.help.cbp.gov/s/article/Article-1915) · [US de minimis status 2026](https://ustariffrates.com/de-minimis) · [timeline and costs](https://www.cmgm.net/us-de-minimis-exemption-ended-2026-china/)
- [AliExpress affiliate API guide (Node)](https://vandevliet.me/how-to-make-aliexpress-affiliate-api-call/) · [python-aliexpress-api](https://pypi.org/project/python-aliexpress-api) · [developer's guide](https://zuplo.com/learning-center/aliexpress-api-guide)
- [Winning product criteria 2026](https://www.minea.com/dropshipping-winning-products) · [data-driven methods](https://www.dropified.com/blog/how-to-find-winning-dropshipping-products-in-2026-7-data-driven-methods/)
