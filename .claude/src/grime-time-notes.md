# Grime Time: notes for whoever works on it next

Grime Time is the free pressure washing game at /grime-time/. This file keeps what is not obvious from the code: the text, the pacing, the save format, the economy, the portal hooks and what was never tested. The source is grime-time.html in this folder; build_grime.py wraps it into the page, build_images_grime.py draws the share image, grime_test.py is the full test suite, grime_sim.js and livebot.js are the pacing simulator and the bot the suite plays with. The brand colour is fuchsia.

## Names and text
- Slug: grime-time
- Display name: Grime Time
- Tagline (masthead and share image): Blast the grime. Build the business.
- Page title (59 characters): Grime Time: Free Pressure Washing Game, Idle and Satisfying
- Description (142 characters): Free pressure washing game for your browser. Blast layers of grime off driveways, decks and cars, earn cash, upgrade your rig and hire a crew.
- og description (106 characters): A free pressure washing game. Spray the grime away, upgrade your rig and build a crew. No ads, no sign up.
- og image alt text (290 characters): Grime Time, a free pressure washing game. A screenshot of the Garden Patio job about half washed: clean pavers on the left, olive grime and a few green moss patches on the right, and a wand blasting a white spray with sparkles along the edge. Beside it: Blast the grime. Build the business.
- Canonical: https://sanjixysti-creator.github.io/grime-time/ . The privacy page is /grime-time/privacy.html (title "Privacy Policy - Grime Time", no share tags). The title, description and og texts are constants at the top of build_grime.py.
- The og image is a real screenshot of the built game (Garden Patio, white tip, 52 percent clean, wand, foam haze, spray flare and sparkles, pay chip $33) taken through the #test hooks, placed on the fuchsia card with the name, the tagline and the pill "Free pressure washing game". The sparkles are random, so build_images_grime.py takes up to 8 shots and keeps the sparkliest. grime_test.py replays the same scene and checks the words of the alt text against it.

## Hub colours
- Tool colour, light: #A21CAF (fuchsia). Tool colour, dark: #E879F9. Used as the hub underline and the tile ground.
- Page background, light: #F5F1F9. Page background, dark: #120A1D. These are the page's own --bg tokens and also the two theme-color metas.
- In the page: white on #A21CAF in light (6.32 to 1), #2A0832 on #E879F9 in dark (7.24 to 1). The accent as text on the page background is 5.67 to 1 in light and 7.85 to 1 in dark. On the hub grounds (#E5E9EB light, #11171B dark) the underline colours are 5.17 to 1 and 7.34 to 1. Money is gold (#FFC83D). The wash panels stay dark in both schemes, and the scenery inside the canvas is the same in both schemes (bright when clean, murky olive when dirty).

## Hub tile art
The tile is the favicon art: a white spray fan coming off a wand, with three drops, on the fuchsia ground (40 x 40 box, rounded square ground rx 9 added by tile_svg). It is exactly MARK_ON_BRAND in build_grime.py, and the GRIME_TIME tuple in hub_icons.py repeats it (site_check.py compares the hub and 404 tiles with the favicon). The favicon in the page is this tile as a data URI, so a site check that compares the tile with the favicon will pass. It reads as a spray wand at 40, 32, 20 and 16 px.

## Sibling links
- In the Grime Time footer: Xysti Software (https://sanjixysti-creator.github.io/) and Rinse Quote (https://sanjixysti-creator.github.io/rinse-quote/), worded "a free quote calculator for people who run a real pressure washing business". The builder adds the support mailto and "Made by Xysti Software. Privacy". Apart from this site's own pages, the only address named is the GitHub privacy statement on docs.github.com (privacy page). No claude.ai link anywhere.
- Not done yet: links back to the game from the other tools. Rinse Mix and Rinse Rate are free and easy to change, for example with ", and Grime Time, a free pressure washing game". Rinse Quote is the best audience match, but it takes payments: CLAUDE.md says to test its Pro unlock flow after any change, and the real code is not in the repo, so only touch its footer if you can run that test.

## Facts that go stale
- None expected. The game quotes no rates, prices, dates or outside facts, and uses no real product or game names.
- Things that are not facts but must move together: (1) the og.png picture is a real screenshot, so rerun build_images_grime.py after any change to the art, the economy or the Garden Patio scene, and check OG_ALT in build_grime.py still describes it (grime_test.py checks the job name, spray colour and "about half washed"); (2) UPDATED in build_grime.py ("October 2026") is the privacy page date: change it when the policy text changes; (3) the support address is SUPPORT in the fragment, the same one the other tools use.

## Commands
All from a restored work folder (see README.md).

    python3 build_grime.py             # grime-time.html -> site/grime-time/index.html and privacy.html (refuses stray dashes, placeholders, scripts, hosts, a wrong h1 count, stray files)
    python3 build_images_grime.py      # og.png and apple-touch-icon.png (needs the built page; real screenshot through the #test hooks)
    GRIME_STANDALONE=$PWD/site/grime-time/index.html python3 grime_test.py     # the full suite on the BUILT page
    python3 grime_test.py              # the same suite on the fragment (no font, metadata or privacy checks)
    GRIME_SECTIONS=math,pace python3 grime_test.py                            # a subset: hygiene builder meta math wash pace shop save storage keyboard input share env play layout contrast journey
    node grime_sim.js pace 2 1 0       # pacing table (also: node grime_sim.js table, node grime_sim.js job <id>)

- Final counts: the full suite on the BUILT page: PASS 16007 FAIL 0 (261 s). Per section: hygiene 75, builder 52, meta 92, math 14955, wash 242, pace 13, shop 78, save 30, storage 8, keyboard 45, input 30, share 21, env 50, play 76, layout 155, contrast 55, journey 26, final 4. Scratch smoke check of the built page through a local server (_final_smoke.py, 320 x 640 and 1280 x 800, light and dark): 106 checks, 0 failed, no outside request, no console message, fonts load, tutorial starts.
- Needs: python3 with playwright and Pillow, node (the suite loads the pure economy and wash code in Node), and a Chromium Playwright can start. Run one browser process at a time on a 2 core machine; the whole suite takes about 4 to 5 minutes. livebot.js (the same bot as grime_sim.js, run on the live page through the hooks) is used by the suite's play section.
- Sizes (built): index.html 330,274 bytes (322.5 KB), privacy.html 74,960 bytes (73.2 KB), og.png 423,862 bytes (413.9 KB, limit 450 KB), apple-touch-icon.png 9,547 bytes. Exactly these four files in site/grime-time/.
- Embedded fonts, all SIL Open Font License: Big Shoulders Display 700 and 800, Public Sans 400 to 700, IBM Plex Mono 400 and 500, reused from build_site.py. No library, no script other than the one inline script, no cookie, no analytics, no request to any other site.

## Pacing (node grime_sim.js pace 2 1 0, the greedy bot at 900 units a second, 6 s between jobs, deterministic)
| milestone | seconds | target |
| first job done | 27 | within 40 s |
| first upgrade bought | 27 | about 60 s |
| third job unlocked | 112 | by about 5 minutes |
| first crew hired | 224 | by about 5 minutes |
| six jobs unlocked | 788 | by about 20 minutes |
| all eight jobs unlocked | 1049 | |
| surface cleaner bought | 1068 | by about 20 minutes |
| first Franchise offered | 3894 (64.9 min, gain 8 points) | 60 to 90 minutes |
| cycle 2 Franchise offered | 5841, which is 1947 s after the reset (half of cycle 1) | clearly faster |
- Apprentice cost is 120 (it was 150). The sim buys only right after a job ends and the jobs end at 27, 109, 221 and 362 s, so the first crew can only land at 224 s or at about 350 s; nothing lands near 300 s. With the bot's old early rule (spend on upgrades until 600 lifetime dollars) every price from 80 to 180 hired at about 351 to 357 s. With the rule at 200 (a test policy in grime_sim.js, not a game number) prices 80 to 130 hire at 224 s and prices 140 to 180 at 346 to 352 s. 120 sits in the middle of the 224 s band, and 224 s meets "by about 5 minutes".
- Guard ranges in grime_test.py: first job 15 to 40 s, first upgrade 15 to 60 s, third job 90 to 150 s, first crew 180 to 330 s, six jobs 600 to 1000 s, surface cleaner 800 to 1200 s, first Franchise 3600 to 5400 s, cycle 2 at most 75 percent of cycle 1.
- Eight hours of content is not verified: only cycle 1 and a rough cycle 2 are simulated.

## Portal notes (what a game portal submission would need)
- Size: one HTML file of about 322 KB (about 130 KB of that is the embedded fonts), no other assets, no network use. Loads instantly.
- Orientation: portrait first, landscape works too (a two column nozzle dock on short landscape phones). Layout audited from 320 to 1920 px wide, light and dark. The page does not scroll in the wash view; the job board scrolls to How to play, About and the footer.
- Controls: mouse or touch drag to spray (on touch the spray lands 56 px above the finger, with a faint crosshair); keyboard: arrow keys or WASD move the nozzle, hold Space to spray, keys 1 to 5 pick the tip, Escape or P pauses; the before and after slider takes the arrow keys, Home and End. A full job can be played without a pointer. The game pauses by itself when the tab is hidden, and spraying stops when the window loses focus.
- Languages: English only (text is in the page, not in a table). Numbers use Intl en-US with the suffixes K, M, B, T, Qa and Qi, then e notation from 1e21 (money is capped at 1e30).
- Ad break hooks (no-ops, no portal code in the page): portalBreak(reason) is called with 'job-complete' when a job has been finished and paid (just before the result card shows) and with 'franchise' after a Franchise reset; portalRewarded() is called by a hidden #rewardBtn (label "Bonus") and returns false. All three sit in the script near the end of the page code; wire an SDK there.
- Audio: generated with Web Audio, starts only after the first press, mute button in the header, setting saved. The page works silently when Web Audio is missing or blocked.
- Test hooks: window.__grime exists only when the address ends in #test, so a portal embed never has it.

## How the save works
- localStorage key grime-time-v1, one JSON object, always inside try/catch. Fields: v (save version, 1), money, lifetime, earned, stars (per job), up (five rig upgrade levels), gear (four flags), crew (six counts), trucks, fp (Franchise points), cycles, color, savedAt (ms, used for offline pay), tut (tutorial seen), jobs, set (sound, calm).
- Saved 1.5 s after a change, every time the tab is hidden and on pagehide. Load sanitises every field (clamps, drops unknown keys, versioned migrate stub). A save the page cannot read is copied to grime-time-v1-backup and the game starts fresh. If storage throws, the game still plays and nothing is kept.
- Export save gives a text code GT1.<base64 of the JSON>.<checksum>; Import checks the checksum and refuses a cut off or edited code. Reset everything is a two step button, never a dialog.
- Offline pay: crew income times the time since savedAt, capped at 4 hours (each truck adds 1 hour, up to 12), a clock that went backwards pays nothing, a welcome back panel shows the amount.

## Content and where the economy lives
- All tunable numbers are in the DATA table in grime-time.html, in the pure region between the PURE-BEGIN and PURE-END comments (no DOM there, so Node loads it for grime_sim.js and the suite). Cost curves, income, offline credit, Franchise maths, pay, stars, number formatting, save code and the wash core are all in that region.
- Jobs (8, with star gates 0, 2, 4, 7, 10, 13, 16, 19): Oil Stained Driveway, Garden Patio, Picket Fence, Brick Wall, Wooden Deck, Garage Door, Vinyl Siding House (needs the extension pole), Family Car (needs the soap tip). Base pays 28, 70, 100, 250, 420, 950, 2100, 4800. Fence, deck, siding and car are delicate (the red tip scuffs and costs pay).
- Tips: Red 0 degrees, Yellow 15, Green 25, White 40, Soap 65 (low pressure, lays foam that softens grime for 7 s). Narrow means strong and small, wide means gentle and big.
- Rig upgrades (5): Pressure, Flow and area, Tank, Wand reach, Flow bonus. Gear (4): Soap tip $350, Hot water $2,400, Extension pole $3,800, Surface cleaner $6,500. Trucks: up to 8, base $5,000, growth 2.2.
- Crew (6, growth 1.15 per hire, doublers at 10, 25, 50, 100 and 200 owned): Apprentice $120 for 0.4 a second, Technician $1,100 for 2.4, Foreman $13,000 for 16, Site manager $160,000 for 105, Regional boss $2.1M for 720, Franchise director $28M for 4,800.
- Franchise: points floor(sqrt(lifetime / 50,000)), at least 8 to offer it, +12 percent income per point, keeps stars, points, rig colours and settings; six rig colours unlock at 0, 6, 15, 30, 60 and 120 points. Achievements and a daily chest were left out (optional in the original plan).

## Decisions made without asking
- 8 jobs instead of the 10 to 12 in the original plan, no achievements, no daily chest, no extra jobs.
- Apprentice cost 120 (see Pacing). The bot's early rule in grime_sim.js is 200 instead of 600; it is a test policy.
- A job finishes at 96 percent clean with a shimmer sweep for the last specks. Stars: 1 for finishing, 2 for scrubbing at least 70 percent of the tough spots by hand with no scuffs, 3 for finishing within the par time. The third job needs 4 stars, so a casual player replays the driveway once (the result button then reads "Again").
- First visit starts directly in the tutorial job (an oil stain on a driveway, hints that fade, no sound until the first press), so the first screen and the share picture are real.
- The share button draws a 1080 x 1350 before and after picture on the device (job name, pay, stars, the game address) and hands it to Web Share with the file, else downloads the PNG, else shows a message. The privacy page says so in its own section.
- Footer sentence for Rinse Quote: "a free quote calculator for people who run a real pressure washing business". The title is the original plan's example wording (59 characters, under the 60 limit). The shorter "Grime Time: Free Pressure Washing Game" would also pass if you prefer it: change TITLE in build_grime.py.
- Touch input lifts the spray 56 px above the finger; keyboard play is complete.
- Coin flight bug found and fixed during the final smoke check: the coins that fly to the Job pay chip every 4 percent used to start from the top left corner of the picture (their flight origin was never set). They now rise a few pixels at the nozzle and then fly to the chip, which sits in the header above the picture, so each coin leaves through the top edge and the chip bumps as it lands. Checked with a scratch drawImage log on the built page (_dbg_coin2.py and _coin_tracks.py: every coin starts at the nozzle, none near the corner). It is not a check in grime_test.py.
- Tests that edit saved progress do it from the same origin privacy.html page, because the game saves on pagehide and would overwrite edits made on its own page.

## Known limitations and untested (honest list)
- Everything was tested in Chromium only (Playwright, headless, software raster, touch through CDP emulation). Not tested: Safari or WebKit, Firefox, and any real phone. The page uses container queries (Safari 16 and Chrome 105 or newer) and Canvas roundRect with a fallback.
- Real iOS and Android touch feel is untested: the 56 px lift, palm and multi touch behaviour, pinch or scroll gestures near the canvas, and the iPhone home bar swipe near the nozzle row at the bottom edge.
- Audio unlock on phones is untested. The page starts its audio on the first press, but real iOS Safari and Android Chrome were not tried, and iPhones with the ring and silent switch off may stay silent for Web Audio.
- Web Share with files is tested with a stubbed navigator.share and canShare and with the download fallback in Chromium. The real iOS and Android share sheets were not tried, and some browsers may refuse a file share (the page then downloads the PNG).
- Performance on slow phones is untested. Headless software raster at 390 x 844 (dpr 3) ran at 60 fps in 7 of 8 setups, with script time per frame at p50 1 to 2 ms and p95 3 to 6 ms. With the CPU throttled 4x through CDP the frame interval was p50 33 ms and p95 50 ms (script time p50 2 to 3.6 ms, p95 7 to 11 ms), so the target of p95 under 40 ms at 4x is NOT met in this setup; the script is far under budget and the rest is software rasterising, but real slow phones may differ. Battery use during long sessions is unknown.
- Safari can erase a site's localStorage after about a week without a visit (its tracking prevention cap), which would erase a save. Export save is the protection; the footer and Settings say so. This is known platform behaviour and was not reproduced here.
- Late game depth is not verified (see Pacing). Screen reader use (VoiceOver, TalkBack) was not tried; there is a live region that announces progress and results, but the wash itself is pointer and keyboard play.
