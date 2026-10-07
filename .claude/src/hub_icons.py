"""Icon art shared by the hub page, its share image and its home screen icon.

The web tools reuse the exact art from their own favicons so the hub shows the same tiles people
see in their browser tabs (site_check.py compares the Rinse Rate, Drive Rate, Grime Time and QR Forever tiles with those pages' favicons).
Tuner's tile follows the three-bar mark on its page.
All art lives in a 40 x 40 box with a rounded square ground.
"""

INK = '#0F181D'
CHALK = '#EDF1F3'
SIGNAL = '#FFD23F'

# name -> (tile ground colour, inner markup after the ground rect)
RINSE_QUOTE = (
    '#0B78A6',
    '<g transform="translate(4 4) scale(.8)">'
    '<rect x="2" y="15" width="13" height="10" rx="2.5" fill="#fff"/>'
    '<rect x="13" y="17.5" width="5" height="5" rx="1" fill="#fff"/>'
    '<g fill="none" stroke="#BDE7F7" stroke-width="2.6" stroke-linecap="round">'
    '<path d="M22 20 L37 9"/><path d="M22 20 L38 14.5"/><path d="M22 20 L38.5 20"/>'
    '<path d="M22 20 L38 25.5"/><path d="M22 20 L37 31"/></g></g>',
)

RINSE_MIX = (
    '#0A7A72',
    '<g transform="translate(4 4) scale(.8)">'
    '<path d="M20 3.5C20 3.5 7.5 17.8 7.5 26a12.5 12.5 0 0 0 25 0C32.5 17.8 20 3.5 20 3.5Z" fill="#fff"/>'
    '<path d="M10 26q2.5-3.4 5 0t5 0 5 0 5 0" fill="none" stroke="#0A7A72" stroke-width="2.6" stroke-linecap="round"/></g>',
)

# A dial: half circle, needle and hub. Same markup as MARK_ON_ORANGE in build_rate.py (the favicon).
RINSE_RATE = (
    '#C2410C',
    '<g transform="translate(2 .4) scale(.9)">'
    '<path d="M6 28a14 14 0 0 1 28 0" fill="none" stroke="#fff" stroke-width="4.4" stroke-linecap="round"/>'
    '<path d="M20 28L27.5 15.5" fill="none" stroke="#FFD9BF" stroke-width="3.4" stroke-linecap="round"/>'
    '<circle cx="20" cy="28" r="3.8" fill="#fff"/></g>',
)

# Two road edges with a dashed centre line. Same markup as MARK_ON_RED in build_drive.py (the favicon).
DRIVE_RATE = (
    '#BE123C',
    '<g transform="translate(2 2) scale(.9)">'
    '<path d="M8.5 35L16.5 5M31.5 35L23.5 5" fill="none" stroke="#fff" stroke-width="4" stroke-linecap="round"/>'
    '<path d="M20 30.5v4.5M20 21.5v5M20 14.5v3.5M20 8.5v2.5" fill="none" stroke="#FFD1DC" stroke-width="3.2" stroke-linecap="round"/></g>',
)

GPU_CHECK = (
    '#4338CA',
    '<g transform="translate(4.2 4) scale(.8)">'
    '<rect x="4.5" y="9" width="33" height="19" rx="3.5" fill="#fff"/>'
    '<rect x="1.5" y="8" width="3.5" height="21" rx="1.2" fill="#fff"/>'
    '<rect x="11" y="28.5" width="17" height="3" rx="0.8" fill="#fff"/>'
    '<circle cx="16" cy="18.5" r="5.2" fill="none" stroke="#4338CA" stroke-width="2"/>'
    '<circle cx="16" cy="18.5" r="1.5" fill="#4338CA"/>'
    '<circle cx="29" cy="18.5" r="5.2" fill="none" stroke="#4338CA" stroke-width="2"/>'
    '<circle cx="29" cy="18.5" r="1.5" fill="#4338CA"/></g>',
)

# Bars 9, 20 and 14 high on a shared baseline, like the mark in the Tuner page header.
TUNER = (
    '#12131A',
    '<rect x="9.5" y="21" width="5" height="9" rx="1.6" fill="#FFD23F"/>'
    '<rect x="17.5" y="10" width="5" height="20" rx="1.6" fill="#FFD23F"/>'
    '<rect x="25.5" y="16" width="5" height="14" rx="1.6" fill="#FFD23F"/>',
)

# A spray fan coming off a wand, with three drops. Same markup as MARK_ON_BRAND in build_grime.py (the favicon).
GRIME_TIME = (
    '#A21CAF',
    '<g transform="translate(1.9 2.1) scale(.9)">'
    '<path d="M20.5 20.5L38 13.5A19 19 0 0 0 27 2.5Z" fill="#fff" fill-opacity=".94"/>'
    '<path d="M5 35L15.5 24.5" fill="none" stroke="#F5D0FE" stroke-width="4.6" stroke-linecap="round"/>'
    '<path d="M14 26L19 21" fill="none" stroke="#fff" stroke-width="7" stroke-linecap="round"/>'
    '<circle cx="33.5" cy="23" r="1.9" fill="#fff"/><circle cx="29" cy="28.5" r="1.4" fill="#fff"/><circle cx="36.5" cy="29" r="1.2" fill="#fff"/>'
    '</g>',
)

# Three finder squares and a few data squares, like a QR code. Same markup as MARK_ON_BRAND in build_qr.py (the favicon).
QR_FOREVER = (
    '#15803D',
    '<g transform="translate(5.2 5.2) scale(.74)" fill="#fff">'
    '<path fill-rule="evenodd" d="M3 3h14v14H3zM6.2 6.2v7.6h7.6V6.2zM23 3h14v14H23zM26.2 6.2v7.6h7.6V6.2zM3 23h14v14H3zM6.2 26.2v7.6h7.6v-7.6z"/>'
    '<path d="M8.2 8.2h3.6v3.6H8.2zM28.2 8.2h3.6v3.6h-3.6zM8.2 28.2h3.6v3.6H8.2zM23 23h5.5v5.5H23zM31.5 23H37v5.5h-5.5zM23 31.5h5.5V37H23zM31.5 31.5H37V37h-5.5z"/></g>',
)


def tile_svg(art, cls='tile', extra=''):
    """A full tile: rounded ground plus the art, as inline SVG."""
    ground, inner = art
    return (f'<svg class="{cls}" viewBox="0 0 40 40" aria-hidden="true" focusable="false"{extra}>'
            f'<rect width="40" height="40" rx="9" fill="{ground}"/>{inner}</svg>')


# The Xysti mark: a crossed pair of strokes with a yellow centre, like a survey mark.
# stroke is currentColor in the page header so it follows the theme.
def mark_svg(cls='mark', stroke='currentColor'):
    return (f'<svg class="{cls}" viewBox="0 0 40 40" aria-hidden="true" focusable="false">'
            f'<path d="M10 10L30 30M30 10L10 30" fill="none" stroke="{stroke}" stroke-width="6" stroke-linecap="round"/>'
            f'<circle cx="20" cy="20" r="4" fill="{SIGNAL}"/></svg>')


def favicon_svg():
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40">'
            f'<rect width="40" height="40" rx="9" fill="{INK}"/>'
            f'<path d="M11 11L29 29M29 11L11 29" fill="none" stroke="{CHALK}" stroke-width="5.5" stroke-linecap="round"/>'
            f'<circle cx="20" cy="20" r="3.8" fill="{SIGNAL}"/></svg>')
