# QR Forever: notes for whoever works on it next

QR Forever is the free QR code generator at /qr-forever/. This file keeps what is not obvious from the code: the text, the colours, how the page is put together, what each test proves, the decisions that were made without asking, and what was never tested. The source is qr-forever.html in this folder (one fragment, no head tags). build_qr.py wraps it into the page and writes the privacy page, build_images_qr.py draws the share image and the home screen icon, and the qr_*.py and *_core.js files are the tests. The brand colour is green.

## Names and text
- Slug: qr-forever
- Display name: QR Forever
- Tagline (share image): Codes that never expire.
- Page title (53 characters): QR Forever: Free QR Code Generator That Never Expires
- Description (143 characters): Make a free QR code for a link, Wi-Fi, contact card, email, map or event. Download PNG or SVG, or print it. No sign up, no expiry, no tracking.
- og description (104 characters): Make QR codes that never expire. Links, Wi-Fi, contacts and more. PNG and SVG, free, no sign up, no ads.
- og image alt text (285 characters): QR Forever, a free QR code generator. A screenshot of the page with the Link tab open: a web address typed in the box and a finished black and white QR code to the right of it, with a Download PNG button below the code. Beside the screenshot: Codes that never expire. Free, no sign up.
- Canonical: https://sanjixysti-creator.github.io/qr-forever/ . The privacy page is /qr-forever/privacy.html (title "Privacy Policy - QR Forever", no share tags). The title, description and og texts are constants at the top of build_qr.py. The test suite and live_smoke3.py repeat the title.
- The og image is a real screenshot of the built page (Link tab, this site's own address typed in the box, the finished code, the buttons) placed on a green card with the name, the tagline and the pill "Free, no sign up". The code in the picture is a working code for https://sanjixysti-creator.github.io/qr-forever/ : build_images_qr.py reads it back with zxing-cpp and refuses to continue unless it says exactly that. Scanning the preview with a phone opens the tool.
- The page says "QR Code is a registered trademark of DENSO WAVE INCORPORATED." in its footer. Keep that line.

## Hub colours
- Tool colour, light: #15803D (green). Tool colour, dark: #4ADE80. Used as the hub underline and the tile ground.
- Page background, light: #E8F0EA. Page background, dark: #09130E. These are the page's own --bg tokens and also the two theme-color metas.
- In the page: white on #15803D in light is 5.02 to 1, #04210F on #4ADE80 in dark is 9.80 to 1. The accent as text on the page background is 4.32 to 1 in light (too weak for small text) and 10.85 to 1 in dark, so the main page never sets small text in the accent on the background. The privacy page sets its links in #0F6B31 in light (5.71 to 1 on the background) for that reason. On the hub grounds the underline colours are 4.10 to 1 (light) and 10.37 to 1 (dark), which is fine for a graphical line.
- The codes themselves are black on white by default. Colour pickers and swatches are offered, with a warning below 3 to 1 and an info note for light on dark.

## Hub tile art
The tile is the favicon art: three finder squares and a few data squares in white on the green ground (40 x 40 box, rounded square ground rx 9 added by tile_svg). It is exactly MARK_ON_BRAND in build_qr.py, and the QR_FOREVER tuple in hub_icons.py repeats it (site_check.py compares the hub and 404 tiles with the favicon, so the two must stay identical). The touch icon uses the same markup at 180 px on a green gradient.

## Sibling links
- In the QR Forever footer: Xysti Software (https://sanjixysti-creator.github.io/) and Drive Rate (https://sanjixysti-creator.github.io/drive-rate/), worded "a free calculator that shows what a delivery offer really pays per hour". The builder adds the support mailto and "Made by Xysti Software. Privacy". Apart from this site's own pages, the only addresses the builder allows are the GitHub privacy statement on docs.github.com (privacy page) and the text https://www.google.com/maps/search/?api=1&query= , which is only the text a Map code can hold (the page writes it into a code and never loads it). No claude.ai link anywhere.
- Not done yet: links back to QR Forever from the other tools.

## Facts that go stale
- None expected. The page quotes no prices, rates or dates. The standard it follows (ISO/IEC 18004: versions 1 to 40, levels L, M, Q, H, 7, 15, 25 and 30 percent) does not change, and the vCard 3.0 and iCalendar 2.0 formats it writes are stable.
- Things that are not facts but must move together: (1) the og.png picture is a real screenshot, so rerun build_images_qr.py after any change to the layout, the colours or the Link tab, and check OG_ALT in build_qr.py still describes it; (2) UPDATED in build_qr.py ("October 2026") is the privacy page date: change it when the policy text changes; (3) the support address is SUPPORT in the fragment, the same one the other tools use; (4) the title is repeated in qr_harness.py, site_check.py and live_smoke3.py.

## Commands
All from a restored work folder (see README.md).

    python3 build_qr.py                # qr-forever.html -> site/qr-forever/index.html and privacy.html (refuses dashes, placeholders, scripts, hosts, a wrong h1 count, stray files)
    python3 build_images_qr.py         # og.png and apple-touch-icon.png (needs the built page; real screenshot, reads the code back)
    python3 qr_proof.py all            # the encoder against segno, zxing-cpp and OpenCV (about 10 minutes; modes: matrix, decode, all)
    python3 qr_pay_test.py             # the text each kind of code writes (Wi-Fi, mailto, vCard, iCalendar and so on), parsed by independent parsers
    python3 qr_test.py                 # the browser suite on the BUILT page (about 10 minutes, one Chromium at a time)
    QR_STANDALONE=/path/to/other/index.html python3 qr_test.py   # the same suite on another copy of the page
    QR_ONLY=t_layout python3 qr_test.py                          # one section: run, t_fields, t_options, t_storage, t_downloads, t_copy_share, t_print, t_layout, t_accessibility, t_site, t_perf

Long runs: start them in the background (setsid nohup bash -c "...; touch x.done") and poll the log, because a tool call times out. The machine has two cores, so run one browser at a time.

## What the tests prove
- qr_proof.py (4606 checks) reads the encoder out of the PURE region of the fragment and runs it in Node. Every version 1 to 40 at every level and every mask is compared module for module with segno (an independent implementation), for byte, numeric and alphanumeric data, for data filling the code and for short data inside big codes, for the exact edge where one more character needs the next version, and for automatic version and mask choice. Pictures are then read back with zxing-cpp (every version and level, all 8 masks, non-ASCII text) and OpenCV (its Aruco based reader has to read nearly all of them; its classic reader is weak and is only a second opinion). Random modules are flipped to prove error correction really repairs, with a negative control (a third of the modules wrecked must fail). segno has one quirk, an extra zero byte when the data ends on a byte boundary, which departs from ISO/IEC 18004 and ZXing; the proof monkeypatches that one function, and the page follows the standard.
- qr_pay_test.py (10641 checks) runs the Pay, Tone and Draw code (also in the PURE region) in Node: Wi-Fi strings with escaping, mailto and sms with percent encoding, geo and map links, vCard 3.0 parsed by vobject, iCalendar parsed by icalendar, a ZXing style Wi-Fi parser, url normalisation and warnings, the lat and lng pair splitter, contrast maths, SVG path data, and a round trip of about 480 payloads through the encoder and a reader.
- qr_test.py and qr_test_b.py to qr_test_d.py (the browser suite, on the built page): load and structure, tabs and arrow keys, every kind reads back from the code on the screen, the form fields and errors, the style and size options, storage (settings always, entries only if the switch is on, the Wi-Fi password never, blocked or odd storage), PNG and SVG downloads with exact per module colours decoded by zxing and OpenCV, rounded squares decoding across versions, copy and share (stubbed), print (the print sheet rasterized from a real PDF at 300 dpi, decoded, measured against the chosen size and centred), 2x and 3x screens, layout at 13 widths in 7 states (no sideways scroll), the pinned bottom bar, the sticky results column, contrast of every text in both colour schemes in many states, tap targets, the 16 px iOS zoom guard, names, ids and headings, the live region, keyboard flow and focus rings, reduced motion, fonts, metadata, footer, FAQ, the privacy page in both schemes, no scripts without JavaScript, the image files, and speed.
- site_check.py and live_smoke3.py cover the hub, the 404 page, the sitemap and the live copy of this page.

## How the page is put together
- One IIFE. Between the PURE-BEGIN and PURE-END comments sit the parts with no page code: QR (the encoder), Pay (the text for each kind), Tone (colour maths) and Draw (path data, layout, SVG). The tests read that region straight out of the fragment, so keep the markers and keep it free of document and window references.
- QR.encode(segs, {level, version, mask}) returns {version, level, mask, size, modules (Uint8Array, 1 is dark)} and throws an Error with code TOO_LONG. QR.segmentsFor(text) picks numeric, alphanumeric or UTF-8 byte mode (no ECI). QR.maxBytes(level) is the most bytes the biggest code (version 40) can hold at that level.
- Pay.build(type, fields) returns {text, shown, empty, errors, warns, notes}. shown masks a Wi-Fi password with up to 12 bullets.
- Storage key qr-forever-v1 in localStorage: settings are always saved, entries only if Remember is on, and a Wi-Fi password never. Every storage call is in try and catch, and the page works with storage blocked.
- Test hook: window.__qr exists only when the address ends in #test. A normal visit has none (live_smoke3.py checks that).
- Downloads are a blob and an a-download link made inside the tap (some browsers refuse a download that starts after a delay). Print fills a hidden #printArea with an SVG sized in millimetres, calls window.print and clears it on afterprint.
- Fonts are subset and embedded by build_site.py (the same pipeline as the other tools). The caption on a code is drawn with Public Sans 700, loaded only when a caption is typed.

## Decisions made without asking
- Static codes only. The code holds the content itself, with no redirect through a server of ours. That is what makes "never expires" true, and it means scans cannot be counted or the destination changed later. The FAQ says so in plain words.
- Own encoder instead of a library, so the page stays one file with no outside code. The cost was the proof work above.
- Not built: Kanji mode (Japanese text is written as UTF-8 bytes, which works but is denser), ECI headers, structured append, Micro QR, a logo in the middle, and any server side anything.
- Defaults: error correction M, download 1024 px, border 4 squares, black on white, square modules, no caption. Warnings for a border under 2 squares, contrast under 3 to 1, a dense code (version 12 or more), an address with no dot or on a private network, and Wi-Fi names or passwords that look wrong. A PNG with squares under 3 px wide is flagged.
- "Remember what I type" is off by default, and the Wi-Fi password is never kept even when it is on.
- Nine kinds: Link, Text, Wi-Fi, Email, Phone, SMS, Contact, Map, Event. The tab row is a 3 by 3 grid under 720 px so nothing hides off screen, and wrapped pills above.
- Enter or Space on a tab chooses it and leaves focus on the tab. Only a real pointer click on a fine pointer moves into the first box.
- Print sizes: 4, 5, 7.5, 10, 15 and 20 cm. A separate Wi-Fi sign prints the heading Join our Wi-Fi, the code, the network name and, only if the person ticks it, the password.

## Known limitations and untested (honest list)
- Only zxing-cpp and OpenCV were used to read codes. No real phone camera was tried, so how different phones handle rounded squares, light on dark codes, low contrast colours or very dense codes is unknown.
- Web Share with files, the clipboard image write and afterprint were only tested with stubs. Real iOS Safari, Android Chrome and Firefox behaviour is untested, as is the feel of the page on a real touch screen.
- Printing was tested by rasterizing the PDF Chromium produces, not on real printers or paper.
- Speed was measured on a desktop CPU (a version 40 code redraws in well under 250 ms there). A slow phone has not been tried.
- Non-ASCII text is written as UTF-8 bytes with no ECI header. Most modern readers handle that, some old scanners may show it garbled.
- The page has never been seen by a search engine yet: it still needs to be added to Search Console and the sitemap submitted, which the owner does.
