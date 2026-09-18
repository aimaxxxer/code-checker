# Setup, step by step

No experience assumed. Follow in order. Total hands-on time is about 15 minutes,
then a 1–3 day wait for one approval that you can start using it without.

**Where you type things:** everything in a grey box goes into your computer's
command line — **Terminal** on Mac (press `Cmd+Space`, type "Terminal", Enter),
or **PowerShell** on Windows (press the Windows key, type "PowerShell", Enter).
Type or paste one box at a time, press Enter, wait for it to finish.

---

## Part 1 — Get it onto your computer

### Step 1. Check you have the two things you need

Paste this and press Enter:

```bash
python3 --version && git --version
```

You want two version numbers back, and the Python one must be **3.10 or higher**.

- *"command not found"* for python3 → install it from [python.org/downloads](https://www.python.org/downloads/), then close and reopen your terminal.
- *"command not found"* for git → Mac: run `xcode-select --install`. Windows: install from [git-scm.com](https://git-scm.com/downloads).

### Step 2. Download the code

```bash
cd ~/Desktop
git clone -b claude/gifted-mayer-5y4ojg https://github.com/aimaxxxer/code-checker temp-download
cp -r temp-download/product-scout-mcp ./product-scout-mcp
rm -rf temp-download
cd product-scout-mcp
```

You now have a folder called **product-scout-mcp** on your Desktop. Nothing else
lives in that folder but this project, so it is safe to move or delete later.

### Step 3. Install it

```bash
bash scripts/setup.sh
```

This takes a minute. It installs everything, tests that it works, and prints the
settings you need for the next part. **Leave this window open** — you will copy
something out of it.

If it ends with **"Setup finished."** you are good. If it stops with a red `X`,
jump to [If something goes wrong](#if-something-goes-wrong).

---

## Part 2 — Connect it to Claude

Pick whichever Claude you use.

### If you use the Claude desktop app

1. Open Claude.
2. **Settings → Developer → Edit Config.** A file opens in a text editor.
3. Open the file `claude-config-snippet.json` — it is inside your
   **product-scout-mcp** folder, and Step 3 just created it.
4. Copy **everything** from that snippet file.
5. Paste it into the config file that Claude opened, replacing whatever is there.
   - Already have other tools set up in that file? Then only copy the
     `"product-scout": { ... }` block, and paste it inside the existing
     `"mcpServers": {` section, putting a comma after the previous entry.
6. Save the file.
7. **Quit Claude completely and reopen it.** Closing the window is not enough —
   Mac: `Cmd+Q`. Windows: right-click the icon in the system tray and choose Quit.

### If you use Claude Code (the terminal one)

One line. Copy the exact `claude mcp add ...` command that Step 3 printed —
it already has the correct path filled in for your computer.

---

## Part 3 — Check it worked

Ask Claude:

> Use product scout to check what data sources are connected.

Claude should reply with a list of sources, most of them saying **not
configured**. That is correct for now — it means the connection works.

Not seeing it? Claude did not pick up the config. Confirm you fully quit and
reopened the app, and that the file you pasted into was the one Claude opened
for you.

Now try a real question:

> Use product scout to find winning products for a pet store in the US.

You will get a ranked list. **Right now the numbers are made up** — every result
says SYNTHETIC. Part 4 makes them real.

---

## Part 4 — Make the data real

Two keys. Do the first one now; it is free and takes two minutes. Start the
second one today because it has a waiting period.

### Key 1 — SerpApi (free, instant, biggest improvement)

This is what tells you **what a product actually sells for** and **whether
demand is growing**. Without it, every profit figure is an assumption.

1. Go to [serpapi.com](https://serpapi.com) and sign up. 100 free searches a
   month, no card needed.
2. After signing up, find **Your Private API Key** on the dashboard. Copy it.
3. In your **product-scout-mcp** folder, open the file called **`.env`** in any
   text editor. (It may be hidden — on Mac press `Cmd+Shift+.` in Finder to show
   hidden files. Or just run `open -e .env` on Mac / `notepad .env` on Windows.)
4. Find the line `SERPAPI_KEY=` and paste your key straight after the `=`, no
   spaces and no quotes:
   ```
   SERPAPI_KEY=abc123yourkeyhere
   ```
5. Save the file. Quit and reopen Claude.

### Key 2 — AliExpress (free, but 1–3 days for approval)

This is what gives you **real AliExpress products** instead of the demo ones.

1. Go to [portals.aliexpress.com](https://portals.aliexpress.com) and join the
   affiliate programme. Use real details — accurate information gets approved
   faster. Where it asks for a business licence, a photo of your personal ID is
   accepted if you are self-employed.
2. Wait for the approval email. Usually 1–3 business days.
3. Once approved, go to [openservice.aliexpress.com](https://openservice.aliexpress.com),
   open the console, and create an application. Give it any name.
4. You will be shown an **App Key** and an **App Secret**. Copy both immediately —
   **the secret is only shown once.**
5. Open the **`.env`** file again and fill in:
   ```
   ALIEXPRESS_APP_KEY=your_app_key
   ALIEXPRESS_APP_SECRET=your_app_secret
   ```
6. Save. Quit and reopen Claude.

### Optional — Apify (only if you want Temu or Alibaba)

Temu and Alibaba have no public API, so their data comes from scrapers. If you
only care about AliExpress, skip this.

1. Sign up at [console.apify.com](https://console.apify.com).
2. **Settings → API & Integrations →** copy your token.
3. Put it in `.env` as `APIFY_TOKEN=...`. Save, restart Claude.

Note: this one costs money per search after the free credit.

### Confirm your keys are live

Ask Claude:

> Use product scout to check what data sources are connected.

Whatever you added should now say **configured / live**. Results will stop
saying SYNTHETIC.

---

## Part 5 — Actually using it

Just talk to Claude normally. Some things that work well:

> Find winning products for a home fitness store in the UK, under £10 landed cost.

> I saw a cordless heated neck massager on TikTok — supplier price $8.40, 14,000 sold, 4.7 stars. Is it worth testing?

> If I sell that for $39.99 and it costs me $8.40, how much can I spend per sale on ads before I lose money?

> Is "LED posture corrector" growing or dying as a search term?

> Check this product for trademark or compliance problems before I order samples.

> Save the top two to my shortlist, and show me everything I've saved.

**How to read the score:** 78+ is strong, 64+ promising, 48+ marginal, under 48
is a pass. Always ask Claude *why* — every score shows its parts, and the
reasoning is often more useful than the number. A score is a ranking against the
other candidates, not a promise of sales.

---

## If something goes wrong

| What you see | What to do |
|---|---|
| `python3: command not found` | Install Python from [python.org](https://www.python.org/downloads/). Close and reopen the terminal afterwards. |
| `git: command not found` | Mac: `xcode-select --install`. Windows: [git-scm.com](https://git-scm.com/downloads). |
| `permission denied` on Step 3 | Use `bash scripts/setup.sh` rather than running the file directly. |
| Setup fails while installing | Usually the internet connection. Wait a moment and run `bash scripts/setup.sh` again — it is safe to repeat. |
| Claude does not see the tools | You must **fully quit** Claude, not just close the window. Mac `Cmd+Q`; Windows quit from the system tray. |
| Claude still does not see them | Your config file probably has a typo. Paste its contents into [jsonlint.com](https://jsonlint.com) — it will point at the broken line. A missing or extra comma is the usual cause. |
| Everything says SYNTHETIC | Normal until you add keys. See Part 4. |
| `invalid signature` from AliExpress | Their signing has four valid combinations and yours depends on when your key was made. In `.env`, try `ALIEXPRESS_SIGN_METHOD=md5`, then `ALIEXPRESS_TIMESTAMP_STYLE=datetime`, restarting Claude after each change. One of the four works. |
| A tool returns an error | Ask Claude: *"run product scout provider status"*. It names the exact missing key and where to get it. |

Still stuck? Run this and show Claude the output:

```bash
cd ~/Desktop/product-scout-mcp && bash scripts/setup.sh
```

---

## Things worth knowing before you spend money

- **The scores rank candidates against each other.** They do not predict sales.
  Your ads, your audience and your shipping decide most of the outcome, and none
  of them are visible to this tool.
- **Import duty is real now.** The US $800 duty-free allowance for small parcels
  ended in 2025. The tool accounts for it, but confirm the actual rate for what
  you are importing before committing to an order.
- **The compliance check is a first pass, not legal advice.** It catches obvious
  trademark and regulation problems. It is deliberately over-cautious — better it
  flags a product you could have sold than miss one that closes your store.
- **Validate cheaply before scaling.** Test the top one or two with a small
  budget. That test tells you more than any score can.
