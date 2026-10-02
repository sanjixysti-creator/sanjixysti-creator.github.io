# Source files for the Xysti Software pages

The pages in this repo were built from the files in this folder, and tested with the scripts in it.
They are saved here so the work is not lost if a session's scratch folder disappears. This is a dot
folder, so GitHub Pages does not publish it, but the repo is public: never put secrets in here.

## What is here

Tool pages (edit these, never the built index.html files):
- rinse-quote.html, rinse-mix.html, gpu-check.html: one fragment per tool. Each is the whole app
  (markup, CSS, JavaScript) with no head tags.

Builders:
- build_site.py: shared helpers (font embedding, base CSS) and the Rinse Quote build.
- build_mix.py, build_gpu.py: Rinse Mix and Used GPU Check. Each wraps its fragment into a full page
  with title, description, share tags, favicon, embedded fonts, and writes index.html plus
  privacy.html to site/<tool>/. Each refuses to build if it finds a dash character or a broken link.
- build_images.py, build_images_mix.py, build_images_gpu.py: draw og.png (1200x630) and
  apple-touch-icon.png (180x180) for each tool into site/<tool>/.
- hub.src.html, hub_icons.py, build_hub.py, build_images_hub.py: the home page. These write straight
  into the site repo root (index.html, og.png, apple-touch-icon.png). Run build_images_hub.py first.
- fonts_build/package.json and package-lock.json: the font packages that get subset and embedded.

Tests:
- rq_test.py, rm_test.py, gpu_test.py: full test suites for each tool (maths against independent
  reference code, layout at many widths, contrast, tap sizes, keyboard, storage, share tags).
- site_check.py: checks the home page, the /tuner/ page and the files that must never change.
- tuner_check.py, iosfs_check.py, gpu_smoke.py, rm_states.py, hub_shots.py, gpu_shots2.py,
  ticket_shot.py: smaller checks and screenshot helpers.
- live_smoke.py, live_smoke2.py, live_smoke3.py: run against the live site after a push. They compare
  what GitHub serves with the local files, byte for byte.

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

Build the home page (writes into $SITE_REPO):

    python3 build_images_hub.py && python3 build_hub.py

Fonts are subset with pyftsubset. Another fonttools version can give slightly different font bytes,
so a rebuilt page may differ from the live one by a few bytes while looking identical.

## Run the tests

    python3 rq_test.py                      # Rinse Quote fragment
    python3 rm_test.py                      # Rinse Mix fragment
    python3 gpu_test.py                     # Used GPU Check fragment
    RQ_STANDALONE=$PWD/site/rinse-quote/index.html python3 rq_test.py     # the built page
    RM_STANDALONE=$PWD/site/rinse-mix/index.html   python3 rm_test.py
    GPU_STANDALONE=$PWD/site/gpu-check/index.html  python3 gpu_test.py
    python3 site_check.py                   # home page, /tuner/, untouched files (reads $SITE_REPO)

Every script prints failures and ends with a pass count. Zero failures is the bar before a push.

## Ship a change

1. Edit the fragment (or hub.src.html), rebuild, run the fragment and built-page tests.
2. Copy site/<tool>/index.html, privacy.html, og.png and apple-touch-icon.png into the repo's tool
   folder. The home page builders already write into the repo.
3. Run site_check.py, look at screenshots in light and dark at phone and desktop width, then commit and push.
4. Wait for Pages (up to a couple of minutes), then run live_smoke2.py and live_smoke3.py.
5. Copy any changed source files back into this folder and commit them with the change.

## Things that are not stored here on purpose

- pro-code.txt: it holds the real Rinse Quote Pro unlock code (a line that reads code=...). The page
  only contains a hash of it. rq_test.py and live_smoke.py read the file from the scripts' own
  folder, so create it there if you need those two. Never commit it. If the code is lost, ask the
  owner. Replacing it would lock out anyone who already paid, so only do that if he says so.
- Screenshots, node_modules, font subset caches and built pages. .gitignore keeps them out.
- /privacy.html at the repo root is the Tuner privacy policy and is not generated from anything here.
  Leave it byte for byte as it is.
