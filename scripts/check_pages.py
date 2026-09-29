"""Validate the static publishing boundary and compare website values with released results."""
import csv
import json
import math
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, unquote

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / 'docs'
ARXIV = 'https://arxiv.org/pdf/2609.22753'
checks = 0


def compare(value, raw, tolerance):
    global checks
    checks += 1
    if raw in ('', 'nan', 'NaN'):
        assert value is None, (value, raw)
    else:
        expected = float(raw)
        assert value is not None and math.isfinite(value)
        assert abs(value - expected) <= tolerance + 1e-10, (value, expected, tolerance)


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.refs = []
        self.ids = set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            assert attrs['id'] not in self.ids, attrs['id']
            self.ids.add(attrs['id'])
        for key in ('href', 'src'):
            if attrs.get(key):
                self.refs.append(attrs[key])


for relative in ('index.html', 'zh/index.html'):
    path = SITE / relative
    page = Page()
    page.feed(path.read_text())
    assert page.refs.count(ARXIV) == 3, relative
    for ref in page.refs:
        url = urlsplit(ref)
        if url.scheme or url.netloc:
            assert 'localhost' not in ref and '127.0.0.1' not in ref
            continue
        assert not url.path.startswith('/'), ('project-prefix-incompatible path', ref)
        if not url.path:
            assert url.fragment in page.ids, ref
        else:
            asset = (path.parent / unquote(url.path)).resolve()
            assert asset.is_relative_to(SITE.resolve()), ref
            assert asset.exists(), ref

allowed = {'.html', '.css', '.js', '.json', '.png', '.xml', '.md'}
for path in SITE.rglob('*'):
    if path.is_file():
        assert not path.is_symlink(), path
        assert path.name == '.nojekyll' or path.suffix in allowed, path
        if path.suffix != '.png':
            text = path.read_text()
            assert '/Users/' not in text, path
for name in ('system-architecture.png', 'explorer-data.json', 'extended-data.json'):
    assert (SITE / 'assets' / name).is_file()
assert f"a.href='{ARXIV}'" in (SITE / 'script.js').read_text()

with (ROOT / 'experiments/rq1-rq4-interpretation/results/cells.csv').open() as f:
    interpretation = {(r['rq'], r['condition'], r['model']): r for r in csv.DictReader(f)}
with (ROOT / 'experiments/rq5-end-to-end/results/cells.csv').open() as f:
    service = {(r['part'], r['cell'], r['model']): r for r in csv.DictReader(f)}
a = json.loads((SITE / 'assets/explorer-data.json').read_text())
b = json.loads((SITE / 'assets/extended-data.json').read_text())
assert len(a['models']) == 7


def service_row(row, part, cell):
    assert len(row['completion']) == len(row['latency']) == 7
    for i, model in enumerate(a['models']):
        ref = service[part, cell, model]
        compare(row['completion'][i], ref['strict_completion' if part == 'A' else 'operational_completion'], .0005)
        compare(row['latency'][i], ref['T_p95_completions'], .005)


for key, row in a['load'].items():
    service_row(row, 'A', 'load_' + key)
for key, row in a['deadline'].items():
    service_row(row, 'A', 'load_4' if key == '2' else 'deadline_' + key)
for key, row in a['cache'].items():
    service_row(row, 'A', 'load_4' if key == 'changing, off' else 'reuse_' + key.replace(', ', '_'))
for arrival, rows in a['ocr'].items():
    for key, row in rows.items():
        service_row(row, 'B', arrival + '_' + key.replace(', ', '_'))
for fields, row in a['contract'].items():
    for i, model in enumerate(a['models']):
        ref = interpretation['RQ3', 'F' + fields + '_medium', model]
        compare(row['completion'][i], ref['em'], .0005)
        compare(row['latency'][i], ref['latency_p50'], .0005)
for key, rows in b['input'].items():
    assert len(rows) == 7
    for row in rows:
        ref = interpretation['RQ1a', 'base' if key == 'base' else 'pad_' + key, row['model']]
        compare(row['accuracy'], ref['em'], .0005)
        compare(row['latency'], ref['latency_p50'], .0005)
        raw = ref['cost_usd_per_1000_correct']
        # Fees in the manuscript use four significant digits.
        tolerance = abs(float(raw)) * .0005 if raw else 0
        compare(row['fee'], raw, tolerance)
for key, rows in b['catalog'].items():
    assert len(rows) == 7
    for row in rows:
        ref = interpretation['RQ4', 'K' + key, row['model']]
        for field, column in [('seen', 'seen_top1'), ('unseen', 'unseen_top1'),
                              ('unsupported', 'unsupported_f1'), ('valid', 'valid_rate'),
                              ('accuracy', 'em'), ('latency', 'latency_p50')]:
            compare(row[field], ref[column], .0005)
print(f'PASS: both routes, static asset boundary, arXiv links, and {checks} source-data comparisons.')
