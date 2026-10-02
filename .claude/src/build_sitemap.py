#!/usr/bin/env python3
"""Write sitemap.xml and robots.txt into the site repo.

Add a line to PAGES when a new tool goes live. lastmod is the date of the last commit that touched the
page's own files, or today if they have uncommitted changes, so it is never invented.
"""
import datetime
import os
import pathlib
import subprocess
import sys

REPO = pathlib.Path(os.environ.get('SITE_REPO', '/home/claude/sanjixysti-creator.github.io'))
SITE = 'https://sanjixysti-creator.github.io/'

# Address under the site root, and the file that is the page.
PAGES = [
    ('', 'index.html'),
    ('rinse-quote/', 'rinse-quote/index.html'),
    ('rinse-mix/', 'rinse-mix/index.html'),
    ('gpu-check/', 'gpu-check/index.html'),
    ('tuner/', 'tuner/index.html'),
]


def git(*args):
    return subprocess.check_output(['git', '-C', str(REPO), *args], stderr=subprocess.DEVNULL).decode().strip()


def lastmod(rel):
    if git('status', '--porcelain', '--', rel):
        return datetime.date.today().isoformat()
    day = git('log', '-1', '--format=%cs', '--', rel)
    return day or datetime.date.today().isoformat()


def main():
    rows = []
    for addr, rel in PAGES:
        if not (REPO / rel).exists():
            sys.exit(f'missing page file: {rel}')
        rows.append(f'  <url>\n    <loc>{SITE}{addr}</loc>\n    <lastmod>{lastmod(rel)}</lastmod>\n  </url>')
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + '\n'.join(rows) + '\n</urlset>\n')
    robots = f'User-agent: *\nAllow: /\n\nSitemap: {SITE}sitemap.xml\n'
    (REPO / 'sitemap.xml').write_text(xml, encoding='utf-8')
    (REPO / 'robots.txt').write_text(robots, encoding='utf-8')
    print(f'sitemap.xml: {len(PAGES)} pages; robots.txt written')


if __name__ == '__main__':
    main()
