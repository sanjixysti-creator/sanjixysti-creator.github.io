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
- /gpu-check/ : used graphics card listing checker, free. It does not scan marketplaces. It scores a listing from the user's answers and opens search links.
Each tool folder holds index.html (one self-contained file), privacy.html, og.png (1200x630) and apple-touch-icon.png.

## Standards for every page
- No em or en dashes. No cookies, no analytics, no third-party requests. What the user types stays in the browser (localStorage).
- Works from 320px wide up, in light and dark (prefers-color-scheme), text contrast at least 4.5:1, tap targets at least 40px.
- Before pushing: serve the repo locally, load each changed page at phone and desktop widths in both color schemes, look at screenshots, check the console for errors.
- After pushing: wait for Pages, fetch the live URLs and confirm they match what was tested.
- Do not add a .nojekyll file. Without Jekyll, this dot folder would become public.

## Source files
The tool pages were built from source files and test scripts kept in the working session's scratch folder, not in this repo. That folder is lost if the workspace resets. If the sources are gone, edit the built index.html directly and keep the fonts embedded. Ask the owner if he wants the sources saved here.

## Commits
End commit messages with the Co-Authored-By and Claude-Session lines the session gives.
