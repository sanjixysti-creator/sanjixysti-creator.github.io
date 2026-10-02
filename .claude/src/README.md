# Source files for the Xysti Software pages

The pages in this repo were built from the files in this folder, and tested with the scripts in it.
They are saved here so the work is not lost if a session's scratch folder disappears. This is a dot
folder, so GitHub Pages does not publish it, but the repo is public: never put secrets in here.

## What is here

Tool pages (edit these, never the built index.html files):
- rinse-quote.html, rinse-mix.html, rinse-rate.html, drive-rate.html, gpu-check.html: one fragment per
  tool. Each is the whole app (markup, CSS, JavaScript) with no head tags.

Builders:
- build_site.py: shared helpers (font embedding, base CSS) and the Rinse Quote build.
- build_mix.py, build_gpu.py, build_rate.py, build_drive.py: Rinse Mix, Used GPU Check, Rinse Rate and
  Drive Rate. Each wraps its
  fragment into a full page with title, description, share tags, favicon, embedded fonts, and writes
  index.html plus privacy.html to site/<tool>/. Each refuses to build if it finds a dash character or a
  broken link.
- build_images.py, build_images_mix.py, build_images_gpu.py, build_images_rate.py, build_images_drive.py:
  draw og.png (1200x630) and apple-touch-icon.png (180x180) for each tool into site/<tool>/. The Rinse
  Rate and Drive Rate previews contain a real screenshot of the built result, so run the matching build
  script before its build_images script.
- hub.src.html, hub_icons.py, build_hub.py, build_images_hub.py: the home page. These write straight
  into the site repo root (index.html, og.png, apple-touch-icon.png). Run build_images_hub.py first.
- 404.src.html, build_404.py: the page GitHub Pages shows for an address that does not exist
  (404.html in the repo root). It is served at any depth, so every link in it is root-absolute.
- build_sitemap.py: writes sitemap.xml and robots.txt in the repo root. lastmod comes from git.
- fonts_build/package.json and package-lock.json: the font packages that get subset and embedded.

Tests:
- rq_test.py, rm_test.py, rate_test.py, drive_test.py, gpu_test.py: full test suites for each tool (maths
  against independent reference code, layout at many widths, contrast, tap sizes, keyboard, storage,
  share tags). rate_test.py and drive_test.py take a few minutes each.
- site_check.py: checks the home page, the 404 page, the sitemap, the /tuner/ page and the files that
  must never change. It also checks that each tool folder holds the four standard files and that its
  links to other pages on this site all point at pages that exist.
- tuner_check.py, iosfs_check.py, gpu_smoke.py, rate_smoke.py, rm_states.py, hub_shots.py,
  gpu_shots2.py, shots_rate.py, shots_drive.py, ticket_shot.py: smaller checks and screenshot helpers.
- live_smoke.py, live_smoke2.py, live_smoke3.py: run against the live site after a push. They compare
  what GitHub serves with the local files, byte for byte. live_smoke3.py is the current one: it covers
  the home page, all five pages, the hidden folder and the not-found page. Older ones are kept for history.

## Restore and rebuild

Work in a scratch folder, not inside the repo.

    export SITE_REPO=/path/to/the/repo/checkout
    mkdir -p ~/work && cp -r "$SITE_REPO"/.claude/src/. ~/work/ && cd ~/work
    (cd fonts_build && npm install)
    pip install --break-system-packages fonttools brotli playwright pillow   # only if missing

Playwright needs a Chromium. The scripts try the default install first, then
/opt/pw-browsers/chromium-1194/chrome-linux/chrome. Change that path if the version differs.

Build one tool (output lands in ~/work/site/<tool>/):

    python3 build_site.py  && python3 build_images.py        # Rinse Quote
    python3 build_mix.py   && python3 build_images_mix.py    # Rinse Mix
    python3 build_gpu.py   && python3 build_images_gpu.py    # Used GPU Check
    python3 build_rate.py  && python3 build_images_rate.py   # Rinse Rate
    python3 build_drive.py && python3 build_images_drive.py  # Drive Rate

Build the home page, the not-found page, the sitemap and robots.txt (these write into $SITE_REPO).
The tool folders must already be in the repo first, because these builders check that every link
exists:

    python3 build_images_hub.py && python3 build_hub.py
    python3 build_404.py
    python3 build_sitemap.py

Fonts are subset with pyftsubset. Another fonttools version can give slightly different font bytes,
so a rebuilt page may differ from the live one by a few bytes while looking identical.

## Run the tests

    python3 rq_test.py                      # Rinse Quote fragment
    python3 rm_test.py                      # Rinse Mix fragment
    python3 gpu_test.py                     # Used GPU Check fragment
    RQ_STANDALONE=$PWD/site/rinse-quote/index.html python3 rq_test.py     # the built page
    RM_STANDALONE=$PWD/site/rinse-mix/index.html   python3 rm_test.py
    GPU_STANDALONE=$PWD/site/gpu-check/index.html  python3 gpu_test.py
    python3 rate_test.py                    # Rinse Rate fragment
    RATE_STANDALONE=$PWD/site/rinse-rate/index.html python3 rate_test.py
    python3 drive_test.py                   # Drive Rate fragment
    DRIVE_STANDALONE=$PWD/site/drive-rate/index.html python3 drive_test.py
    python3 site_check.py                   # home page, 404, sitemap, /tuner/, untouched files (reads $SITE_REPO)

Every script prints failures and ends with a pass count. Zero failures is the bar before a push.
Run the built-page versions (the *_STANDALONE ones) for the final word: the fragment runs block the
Google font requests, so text-fit checks are only meaningful on the built page with embedded fonts.

## Ship a change

1. Edit the fragment (or hub.src.html), rebuild, run the fragment and built-page tests.
2. Copy site/<tool>/index.html, privacy.html, og.png and apple-touch-icon.png into the repo's tool
   folder. The home page builders already write into the repo.
3. Run site_check.py, look at screenshots in light and dark at phone and desktop width, then commit and push.
4. Wait for Pages (up to a couple of minutes), then run live_smoke3.py.
5. Copy any changed source files back into this folder and commit them with the change.

## Add a new tool

Build its fragment, builders and tests the way the existing ones are done (Drive Rate is the newest
example), then wire it in:
1. hub_icons.py: add its tile art. hub.src.html: add a row (keep the order you want).
2. build_hub.py: update the expected row count. build_images_hub.py: add it to ROWS.
3. 404.src.html: add a row with root-absolute links (build_404.py checks the row count too).
4. build_sitemap.py: add it to PAGES. site_check.py: add it to TITLES and the row checks (row counts,
   tab order, privacy links). live_smoke3.py: add it to the lists there too.
5. Copy the built tool folder into the repo first, then rebuild the hub, the 404 page and the sitemap,
   run site_check.py, then commit and push.
Also add its privacy page to the footer list on the hub and update .claude/CLAUDE.md.

## Yearly upkeep

The IRS business mileage rate shows up in two tools. It is set each January, and the IRS can change it
mid year too (it did in July 2026, from 72.5 to 76 cents). Look at
https://www.irs.gov/tax-professionals/standard-mileage-rates each January and again around July.

- Rinse Rate starts its per mile cost from that rate (76 cents since July 1, 2026). It is the
  IRS_PER_MILE value near the top of the script in rinse-rate.html, and the sentence under the mileage
  field names the rate and when it started. Changing it moves every number of the example job:
  rate_test.py has those readings written out (pay per hour, profit, price for the goal, the two tables),
  build_rate.py repeats two of them in OG_ALT, and live_smoke3.py repeats them too. Recompute them with
  the exact reference model in rate_test.py, rebuild with build_rate.py and build_images_rate.py, run
  rate_test.py on the built page, and ship.
- Drive Rate keeps a dated table, IRS_RATES, with IRS_LAST_YEAR and IRS_AS_OF at the top of the maths
  block in drive-rate.html (ref_rate and the irs tests in drive_test.py repeat it). Each January add the
  new year's row at the top and move IRS_LAST_YEAR and IRS_AS_OF, rebuild, and run drive_test.py on the
  built page. After December 31 of IRS_LAST_YEAR the page tells people its rates are out of date by
  itself. Its starting car numbers (gas price, mpg and so on) are illustrative defaults: look at the gas
  price once a year, and rerun build_images_drive.py after changing the example offer.
- The UPDATED date in build_rate.py and build_drive.py moves with these changes.

## Things that are not stored here on purpose

- pro-code.txt: it holds the real Rinse Quote Pro unlock code (a line that reads code=...). The page
  only contains a hash of it. rq_test.py and live_smoke.py read the file from the scripts' own
  folder, so create it there if you need those two. Never commit it. If the code is lost, ask the
  owner. Replacing it would lock out anyone who already paid, so only do that if he says so.
- Screenshots, node_modules, font subset caches and built pages. .gitignore keeps them out.
- /privacy.html at the repo root is the Tuner privacy policy and is not generated from anything here.
  Leave it byte for byte as it is.
