# Vriddhi Watchlist News Crawler

Collects news and exchange filings for your watchlist all day, and at 8:00 AM sends each analyst one
WhatsApp message through Interakt with their full digest attached as a PDF. Every story is sent to an
analyst once, ever: a sent ledger, not a 24-hour window, decides what is new.

```
every 30 min   BSE + NSE filings, publisher news sitemaps and RSS, watched pages  ─┐
every 3 hours  Google News (several queries, English + Hindi), GDELT               ─┤
                                                                                     ▼
              match to companies (aliases, article text) → de-duplicate into stories → database
                                                                                     ▼
8:00 AM        unsent stories per analyst → PDF → Interakt message with PDF → sent ledger + archive
8:05, 8:15     retries for anyone whose send failed          8:20  status to you
```

---

## Part 1 — For Kalpesh: what you need to do (about 1 hour, plus your developer's time)

1. **Rent a small server** in Vriddhi's name: a 2 GB Ubuntu server on AWS Lightsail, DigitalOcean or
   Google Cloud. Give your developer access.
2. **Create a storage bucket** for the PDFs at the same provider (AWS S3, DigitalOcean Spaces) or
   Cloudflare R2. Keep it private. Your developer needs its access keys.
3. **In Interakt, create the digest template** (Templates → new template):

   | Field | Enter |
   | --- | --- |
   | Category | Utility |
   | Header | Document |
   | Body | Good morning {{1}}. Watchlist news for {{2}}: {{3}} stories across {{4}} companies, including {{5}} exchange disclosures. Top items: {{6}} The full digest is attached. Vriddhi Research Desk. |
   | Samples | Rahul · 13 Oct 2026 · 42 · 17 · 6 · 1) Tata Motors: Q2 volumes up 12% \| 2) Polycab: ₹400 crore order · any sample PDF |

   Once approved, open it: the address reads `app.interakt.ai/template/<code-name>/view`. Send your
   developer the code name. Optionally create a second template, *Digest status: {{1}}*, for the 8:20
   status on your own WhatsApp.
4. **Copy the Interakt API key** (Settings → Developer Settings → Secret Key) and give it to the
   developer through a password manager, not WhatsApp or e-mail.
5. **Get your analysts to fill the Watchlist** in `control_panel.xlsx` (or the Google Sheet version):
   aliases, brands, subsidiaries, management names, Hindi/regional names. This is the single biggest
   driver of coverage. The *Read me* tab explains each column.
6. **Run 3–4 days in test mode** (every digest comes to you), compare with your current system, then
   ask the developer to switch `TEST_MODE=no`.

---

## Part 2 — For the developer: installation (about half a day)

```bash
# 1. system packages (Ubuntu 22.04/24.04): PDF engine + fonts for Indian scripts
sudo apt update
sudo apt install -y python3-venv python3-pip libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 \
                    fonts-noto-core fonts-noto-ui-core fonts-dejavu
sudo timedatectl set-timezone Asia/Kolkata

# 2. the project
cd ~ && unzip vriddhi-news-crawler.zip && cd vriddhi-news-crawler
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python -m pytest -q tests          # 23 tests should pass

# 3. configuration
cp .env.example .env && nano .env   # Interakt key, template name, S3 bucket, TEST_WHATSAPP, contact e-mail
python -m vriddhi_crawler init     # creates the database and control_panel.xlsx with examples
```

### Fill the control panel

- **Watchlist / Analysts**: from Kalpesh's team (Part 1, step 5).
- **Sources**: ten feeds are pre-filled, plus the Business Standard news sitemap. For each publisher row
  with an empty URL, find its news sitemap and paste it in, then set Active to YES:
  ```bash
  python -m vriddhi_crawler discover-sitemaps --url https://www.livemint.com
  ```
  Pick the sitemap whose name mentions *news*. Set **Keep URLs Matching** to the business sections, e.g.
  `/(markets|companies|industry)/`, and **Body Check** to YES for those.
- **Pages** (type `page`): company press/IR pages (fill the Company column), rating agencies' rating
  release listings (CRISIL, ICRA, CARE, India Ratings), SEBI's orders listing. The first visit only
  records existing links; new links after that become stories.
- **Keywords**: Grade A and Grade C lists, pre-filled; edit freely.

To use a Google Sheet instead of the Excel file: create a service account in Google Cloud, download its
key as `google-service-account.json`, upload `control_panel.xlsx` to Google Sheets, share the sheet with
the service account's e-mail, and put the sheet ID in `GOOGLE_SHEET_ID`. The archive works the same way
with `ARCHIVE_SHEET_ID` (a local Excel copy is always kept in `data/`).

### Check every source works from this server

```bash
python -m vriddhi_crawler check-sources
```
Each line says OK with item counts, or FAIL with the reason. Common failures:
- `403` from a publisher: it blocks automated readers; switch that row to its RSS feed or drop it.
- NSE `401/403`: NSE's session rules change from time to time; adjust `sources/exchanges.py`
  (the headers and the two warm-up page loads). BSE keeps working independently.
- `robots.txt disallows`: the site asks crawlers not to read that path; respect it and use another source.

### First run and test send

```bash
python -m vriddhi_crawler crawl --force     # all groups once (search takes 10–20 minutes, by design)
python -m vriddhi_crawler preview           # builds today's PDFs in data/digests/ without sending
python -m vriddhi_crawler test-send         # one sample message + PDF to TEST_WHATSAPP
python -m vriddhi_crawler send              # TEST_MODE=yes: every analyst's digest goes to TEST_WHATSAPP
```

### Schedule it

Edit the paths in `crontab.example`, then `crontab -e` and paste it in. The schedule:
crawl every 30 minutes, search sweeps every 3 hours, final crawl at 7:35, send at 8:00 with retries
at 8:05 and 8:15, status at 8:20.

### Go live

Set `TEST_MODE=no` in `.env`. Test mode keeps its own ledger, so stories already sent to the test
number still go to the analysts on the first live morning.

---

## How the "never resend" rule works

1. **Fingerprints** (kept 30 days): exchange filing ID; the article link with tracking tags, `www/m/amp`
   and AMP suffixes removed; the cleaned headline (3 days); near-identical headlines for the same company
   (3 days). A repeat of a known item is dropped; another outlet's copy joins the existing story.
2. **Sent ledger**: one row per story per analyst. The 8 AM job takes only stories with no row, writes
   *sending* rows before calling Interakt, upgrades them to *sent* on success, and deletes them on failure
   so the retry picks them up. A send whose outcome is unknown (server crash mid-send) stays *sending* and
   is flagged in the 8:20 status for a manual check, rather than risk a repeat.
3. **Proof**: run `python -m vriddhi_crawler send` twice in a row. The second run sends nothing.

## Known limits

- BSE and NSE data come from the feeds behind their public websites, not licensed APIs. If either
  changes, the 8:20 status flags it and the other sources continue.
- Google News article links pass through Google; they open fine but are de-duplicated by headline rather
  than by publisher link.
- An exchange filing and the press write-ups of it usually appear as separate lines (the filing under
  Disclosures, the coverage under the company), because their headlines differ too much to merge safely.
- Paywalled articles are matched on headline and summary only.
- Article text is read in memory to match companies and never stored; the archive holds headline,
  source and link.

## Commands

| Command | What it does |
| --- | --- |
| `init` | Create the database and a starter `control_panel.xlsx` |
| `crawl [--only groups] [--force]` | Run due sources. Groups: `exchanges,publishers,pages,search` |
| `send [--retry] [--only "Name"]` | Send today's digests (skips anyone already done today) |
| `preview [--only "Name"]` | Build PDFs only; sends and records nothing |
| `status` | Build and send the status summary |
| `test-send` | One sample message with PDF to `TEST_WHATSAPP` |
| `check-sources` | Run every source once and report counts; stores nothing |
| `discover-sitemaps --url URL` | List the sitemaps a site declares |

## Files

| Path | Purpose |
| --- | --- |
| `vriddhi_crawler/sources/exchanges.py` | BSE and NSE whole-market announcements |
| `vriddhi_crawler/sources/publishers.py` | News sitemaps, RSS, watched pages |
| `vriddhi_crawler/sources/search.py` | Google News and GDELT |
| `vriddhi_crawler/matching.py` | Alias matching, article-text check, A/B/C grading |
| `vriddhi_crawler/normalize.py` | Link and headline cleaning, near-duplicate test |
| `vriddhi_crawler/pipeline.py` | The crawl: sources → match → de-duplicate → store |
| `vriddhi_crawler/db.py` | Database, fingerprints, sent ledger |
| `vriddhi_crawler/digest.py` | The 8 AM send and the status report |
| `vriddhi_crawler/pdf.py` | The digest PDF |
| `vriddhi_crawler/delivery.py` | PDF upload, Interakt API, status e-mail/WhatsApp |
| `vriddhi_crawler/archive.py` | The archive Excel file / Google Sheet |
| `tests/test_core.py` | Matching, de-duplication and never-resend tests |
| `data/` | Database, daily PDFs, archive Excel (created on first run) |
| `logs/crawler.log` | Everything the crawler did |
