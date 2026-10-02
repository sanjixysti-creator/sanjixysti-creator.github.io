# Notes for Claude: Xysti Software site

This repo is the public site https://sanjixysti-creator.github.io/ (GitHub Pages, branch main, live about 2 minutes after a push). This file sits in a dot folder, which GitHub Pages does not publish, but the repo itself is public. Never put secrets, keys, unlock codes or private details in it.

## The owner
- Solo developer. Works from his phone, often late at night (Los Angeles time). Keep messages short and easy to read on a phone.
- Never use the em dash character anywhere: messages, site copy, code comments. Use "-", "," or ":". The same goes for the en dash.
- Do the work instead of asking small questions. Ask before anything hard to undo. A quick "yes" or a thumbs up counts as a go-ahead.
- He does not want visitors sent to claude.ai links. The real product always lives on this site. Claude artifacts are private previews only.

## Pages
- / : Xysti Software hub. A ledger of rows, one per tool (index.html, og.png, apple-touch-icon.png). Fonts embedded as base64, no scripts.
- /tuner/ : Tuner for YouTube, a Chrome extension (Chrome Web Store listing in review). Free plus a Pro upgrade.
- /privacy.html : Tuner's privacy policy. Do not move, rename or edit it. The Chrome Web Store listing most likely points at this exact address.
- /rinse-quote/ : pressure washing quote calculator. Free, with a one-time Pro upgrade sold through a Stripe payment link. It earns money, so test its Pro unlock flow after any change to it.
- /rinse-mix/ : soft wash mix calculator, free.
- /rinse-rate/ : pressure washing job profit calculator, free. Shows what a job really paid per hour and what to charge to hit an hourly goal. Its per mile cost starts from the IRS mileage rate, which changes every January (see Yearly upkeep in .claude/src/README.md).
- /drive-rate/ : delivery and rideshare offer calculator, free. Shows what an offer really pays per hour after car costs, gives a Take it, Borderline or Pass verdict against the driver's own goals, and keeps a day log. Its car cost can use the IRS mileage rate from a dated table, which changes every January and sometimes mid year (see Yearly upkeep in .claude/src/README.md).
- /gpu-check/ : used graphics card listing checker, free. It does not scan marketplaces. It scores a listing from the user's answers and opens search links.
- /404.html : the page GitHub Pages shows for any address that does not exist. Every link in it is root-absolute because it is served at any depth. It is marked noindex.
- /sitemap.xml and /robots.txt : made by .claude/src/build_sitemap.py. Add a new tool to its PAGES list.
Each tool folder holds index.html (one self-contained file), privacy.html, og.png (1200x630) and apple-touch-icon.png.

## Standards for every page
- No em or en dashes. No cookies, no analytics, no third-party requests. What the user types stays in the browser (localStorage).
- Works from 320px wide up, in light and dark (prefers-color-scheme), text contrast at least 4.5:1, tap targets at least 40px.
- Before pushing: serve the repo locally, load each changed page at phone and desktop widths in both color schemes, look at screenshots, check the console for errors.
- After pushing: wait for Pages, fetch the live URLs and confirm they match what was tested.
- Do not add a .nojekyll file. Without Jekyll, this dot folder would become public.

## Source files
The pages are built from source files saved in .claude/src/, which is hidden from the site like this file. Start with .claude/src/README.md: it explains how to restore the build folder, rebuild each page, run the test suites and ship a change. Edit the fragments (rinse-quote.html, rinse-mix.html, rinse-rate.html, drive-rate.html, gpu-check.html) and hub.src.html, never the built index.html files, and copy changed sources back into .claude/src/ in the same commit. A rebuild from these sources was checked to reproduce every live page byte for byte. The real Pro unlock code is not stored in the repo.

## Commits
End commit messages with the Co-Authored-By and Claude-Session lines the session gives.
