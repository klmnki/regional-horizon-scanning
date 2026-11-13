"""Offline support for a researcher-led regional scan. Python 3.11+, stdlib only."""
from __future__ import annotations

import argparse
from contextlib import closing
import csv
from datetime import date
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
REGISTERS = json.loads((ROOT / 'schemas/registers.json').read_text(encoding='utf-8'))
SCORE_MAX = {'relevance': 3, 'novelty': 2, 'importance': 2, 'distribution': 1, 'evidence': 2}
STATUSES = {'Complete', 'No qualifying items', 'Incomplete', 'Failed'}
CLASSES = {'Weak signal', 'Emerging-issue indicator', 'Driver indicator', 'Wild card', 'Context'}


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def configuration(path=None):
    config = read_json(path or ROOT / 'config/region.json')
    lanes = config['lanes']
    ids = [x['id'] for x in lanes]
    if not lanes or len(ids) != len(set(ids)):
        raise ValueError('Configuration must have unique, nonempty lanes')
    if any(not re.fullmatch(r'[A-Z]{2,12}', x) for x in ids):
        raise ValueError('Lane IDs must use 2–12 uppercase letters')
    if any(x['kind'] not in ('signals', 'products') for x in lanes):
        raise ValueError('Lane kind must be signals or products')
    if type(config['max_per_lane']) is not int or config['max_per_lane'] < 1:
        raise ValueError('max_per_lane must be a positive integer')
    return config


def blank_row(kind):
    return dict.fromkeys(REGISTERS[kind], '')


def empty_run(config, run_date=''):
    return {'schema_version': 1, 'run_date': run_date, 'example': False,
            'signals': [], 'products': [], 'synthesis': [], 'coverage': [], 'candidates': []}


def iso_day(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('Expected YYYY-MM-DD')
    return date.fromisoformat(value)


def text_value(value):
    return isinstance(value, str) and bool(value.strip())


def validate(run, config):
    """Check structural consistency; never claim to establish source truth."""
    errors = []
    if not isinstance(run, dict):
        return ['Run must be an object']
    try:
        day = iso_day(run.get('run_date'))
    except (ValueError, TypeError):
        return ['run_date must be a valid YYYY-MM-DD local date']
    if run.get('schema_version') != 1 or type(run.get('example')) is not bool:
        errors.append('schema_version must be 1 and example must be a boolean')
    for kind in REGISTERS:
        if not isinstance(run.get(kind), list):
            errors.append(f'{kind} must be a list')
    if errors:
        return errors
    lanes = {x['id']: x for x in config['lanes']}
    selected = {x: [] for x in lanes}
    ids, keys = set(), set()

    def row_ok(row, kind, where):
        if not isinstance(row, dict) or set(row) != set(REGISTERS[kind]):
            errors.append(f'{where}: fields must match {kind} schema exactly')
            return False
        if any(not isinstance(v, (str, int, float)) or isinstance(v, bool) for v in row.values()):
            errors.append(f'{where}: cells must be strings or numbers; use empty strings for unknowns')
            return False
        return True

    for kind in ('signals', 'products'):
        for n, item in enumerate(run[kind], 1):
            where = f'{kind} item {n}'
            if not isinstance(item, dict):
                errors.append(f'{where}: must be an object')
                continue
            lane, key, row = item.get('lane'), item.get('canonical_key'), item.get('fields')
            if lane not in lanes or lanes[lane]['kind'] != kind:
                errors.append(f'{where}: unknown lane or wrong record kind')
                continue
            if not row_ok(row, kind, where):
                continue
            id_field = 'Signal ID' if kind == 'signals' else 'Product ID'
            record_id = row[id_field]
            pattern = (rf'SIG-{day:%Y%m%d}-{lane}-\d{{2}}' if kind == 'signals'
                       else rf'AP-{day:%Y%m%d}-\d{{2}}')
            if not isinstance(record_id, str) or not re.fullmatch(pattern, record_id):
                errors.append(f'{where}: invalid ID for date/lane')
            if record_id in ids:
                errors.append(f'{where}: duplicate record ID')
            ids.add(record_id)
            if not text_value(key):
                errors.append(f'{where}: canonical_key is required')
            elif key in keys:
                errors.append(f'{where}: duplicate underlying development/version')
            else:
                keys.add(key)
            selected[lane].append(record_id)
            url = row['Source URL']
            parsed = urlparse(str(url))
            if parsed.scheme not in ('https', 'http') or not parsed.hostname or parsed.username or parsed.password:
                errors.append(f'{where}: public HTTP(S) source URL required')
            if not run['example'] and parsed.hostname in ('example.org', 'example.com', 'example.net'):
                errors.append(f'{where}: fictional URL cannot be used in a real run')
            date_field = 'Scan date' if kind == 'signals' else 'Added date'
            if row[date_field] != run['run_date']:
                errors.append(f'{where}: record date differs from run date')
            for field in ('Publication date',) + (('First seen',) if kind == 'signals' else ()):
                if row[field] != '':
                    try:
                        if iso_day(row[field]) > day:
                            errors.append(f'{where}: {field} is future-dated')
                    except (ValueError, TypeError):
                        errors.append(f'{where}: invalid {field}')
            if row['Review status'] not in ('Unreviewed', 'Reviewed', 'Rejected', 'Needs review'):
                errors.append(f'{where}: invalid review status')
            if row['Confidence'] not in ('Low', 'Medium', 'High'):
                errors.append(f'{where}: confidence must be Low, Medium or High')
            if kind == 'signals':
                required = ['Headline', 'Observed change', 'Evidence geography', 'AI economic mechanism',
                            'Evidence stage', 'Evidence / corroboration', 'Alternative explanations',
                            'Territory transfer limits', 'Search window']
                if row['Primary territory'] != lanes[lane]['name']:
                    errors.append(f'{where}: primary territory does not match lane')
                if row['Foresight class'] not in CLASSES:
                    errors.append(f'{where}: invalid foresight class')
                if not re.match(r'^E[1-8](?:\b|:)', str(row['AI economic mechanism'])):
                    errors.append(f'{where}: primary mechanism must begin E1–E8')
                try:
                    score = json.loads(row['Score breakdown'])
                    valid = set(score) == set(SCORE_MAX) and all(
                        type(score[k]) is int and 0 <= score[k] <= limit for k, limit in SCORE_MAX.items())
                    if not valid or score['evidence'] == 0 or score['novelty'] == 0 or score['relevance'] == 0:
                        raise ValueError()
                    if type(row['Score /10']) is not int or row['Score /10'] != sum(score.values()):
                        raise ValueError()
                except (ValueError, TypeError, KeyError):
                    errors.append(f'{where}: invalid score/components or ineligible zero evidence/novelty/relevance')
                if type(row['Lane rank']) is not int or row['Lane rank'] != len(selected[lane]):
                    errors.append(f'{where}: lane ranks must be ordered consecutively from 1')
            else:
                required = ['Title', 'Method / identification', 'Evidence geography / population',
                            'Main finding', 'Observed vs modelled', 'Transfer test for territories',
                            'Limits / counterevidence', 'Read depth', 'Discovery window']
                if row['Record type'] not in ('Analytical product', 'Analytical baseline'):
                    errors.append(f'{where}: invalid analytical record type')
            for field in required:
                if not text_value(row[field]):
                    errors.append(f'{where}: {field} is required (state limits explicitly)')

    seen_lanes = set()
    for n, row in enumerate(run['coverage'], 1):
        where = f'coverage row {n}'
        if not row_ok(row, 'coverage', where):
            continue
        matches = [k for k, v in lanes.items() if v['name'] == row['Lane']]
        if len(matches) != 1 or matches[0] in seen_lanes:
            errors.append(f'{where}: unknown or duplicate coverage lane')
            continue
        lane = matches[0]
        seen_lanes.add(lane)
        if row['Scan date'] != run['run_date'] or row['Run ID'] != f'{day.isoformat()}-{lane}':
            errors.append(f'{where}: invalid coverage run ID/date')
        if row['Status'] not in STATUSES:
            errors.append(f'{where}: invalid coverage status')
        linked = [x.strip() for x in str(row['Record IDs']).split(';') if x.strip()]
        if sorted(linked) != sorted(selected[lane]):
            errors.append(f'{where}: saved IDs do not match selected records')
        expected = {k: len(selected[lane]) if lanes[lane]['kind'] == k else 0 for k in ('signals', 'products')}
        for field, kind in [('Selected signals', 'signals'), ('Selected products', 'products')]:
            if type(row[field]) is not int or row[field] != expected[kind]:
                errors.append(f'{where}: selected count mismatch')
        if type(row['Candidate count']) is not int or row['Candidate count'] < len(selected[lane]):
            errors.append(f'{where}: candidate count must cover selected records')
        if row['Status'] == 'No qualifying items' and selected[lane]:
            errors.append(f'{where}: no-qualifying status cannot have selected items')
        if row['Status'] == 'Failed' and selected[lane]:
            errors.append(f'{where}: use Incomplete for partial research with saved items')
        if row['Status'] in ('Complete', 'No qualifying items'):
            for field in ('Window searched', 'Languages searched', 'Source families / queries'):
                if not text_value(row[field]):
                    errors.append(f'{where}: completed search requires {field}')
        if row['Status'] in ('Incomplete', 'Failed') and not text_value(row['Gaps / access failures']):
            errors.append(f'{where}: incomplete coverage needs a reason')
        if len(selected[lane]) > config['max_per_lane']:
            errors.append(f'{where}: lane selection ceiling exceeded')
    if seen_lanes != set(lanes):
        errors.append('Coverage must contain exactly one row for every configured lane')
    for kind in ('synthesis', 'candidates'):
        for n, row in enumerate(run[kind], 1):
            row_ok(row, kind, f'{kind} row {n}')
    return errors


def safe_csv_cell(value):
    value = str(value)
    return "'" + value if value.lstrip().startswith(('=', '+', '-', '@', '\t', '\r')) else value


def write_registers(run, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    for kind, headers in REGISTERS.items():
        rows = [x['fields'] for x in run[kind]] if kind in ('signals', 'products') else run[kind]
        with (out / f'{kind}.csv').open('x', encoding='utf-8-sig', newline='') as handle:
            writer = csv.writer(handle)
            writer.writerow(headers)
            writer.writerows([safe_csv_cell(row[h]) for h in headers] for row in rows)


def briefing(run, config):
    lines = [f"# Regional scan — {run['run_date']}", '']
    if run['example']:
        lines += ['**FICTIONAL DEMONSTRATION. Not research evidence.**', '']
    lines += ['This is a structured evidence digest. Add source-checked cross-scan interpretation before sharing.', '']
    coverage = {row['Lane']: row for row in run['coverage']}
    for lane in config['lanes']:
        row = coverage[lane['name']]
        lines += [f"## {lane['name']}", '', f"Status: {row['Status']}. Window: {row['Window searched']}",
                  f"Languages: {row['Languages searched']}", f"Gaps: {row['Gaps / access failures'] or 'None recorded'}", '']
        items = [x['fields'] for x in run[lane['kind']] if x['lane'] == lane['id']]
        if not items:
            lines += ['No selected records. Interpret this alongside the coverage status above.', '']
        for item in items:
            if lane['kind'] == 'signals':
                lines += [f"### {item['Headline']} ({item['Signal ID']})", '', item['Observed change'], '',
                          f"Mechanism: {item['AI economic mechanism']}",
                          f"Alternative explanations: {item['Alternative explanations']}",
                          f"Territorial limits: {item['Territory transfer limits']}",
                          f"Uncertainty: {item['Key uncertainty directions'] or 'Not specified'}"]
            else:
                lines += [f"### {item['Title']} ({item['Product ID']})", '', item['Main finding'], '',
                          f"Method: {item['Method / identification']}",
                          f"Transfer test: {item['Transfer test for territories']}",
                          f"Limits: {item['Limits / counterevidence']}"]
            lines += [f"Confidence: {item['Confidence']}; review: {item['Review status']}.",
                      f"Source: {item['Source URL']}", '']
    return '\n'.join(lines)


def archive(run, config, out):
    errors = validate(run, config)
    if errors:
        raise ValueError('Cannot archive: ' + '; '.join(errors))
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(run, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    digest = hashlib.sha256(payload.encode()).hexdigest()
    with closing(sqlite3.connect(out / 'archive.sqlite3', timeout=10)) as db, db:
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('CREATE TABLE IF NOT EXISTS runs (day TEXT PRIMARY KEY, digest TEXT NOT NULL, payload TEXT NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS evidence (id TEXT PRIMARY KEY, canonical_key TEXT UNIQUE NOT NULL, day TEXT REFERENCES runs(day))')
        db.execute('BEGIN IMMEDIATE')
        old = db.execute('SELECT digest FROM runs WHERE day=?', (run['run_date'],)).fetchone()
        if old:
            if old[0] == digest:
                return 'Unchanged: this exact run is already archived'
            raise ValueError('This date is already archived with different content; preserve it and use a linked correction in a later run')
        db.execute('INSERT INTO runs VALUES (?, ?, ?)', (run['run_date'], digest, payload))
        try:
            for kind in ('signals', 'products'):
                for item in run[kind]:
                    id_field = 'Signal ID' if kind == 'signals' else 'Product ID'
                    db.execute('INSERT INTO evidence VALUES (?, ?, ?)',
                               (item['fields'][id_field], item['canonical_key'], run['run_date']))
        except sqlite3.IntegrityError as exc:
            raise ValueError('Duplicate ID or canonical development already archived; no run was added') from exc
    return 'Archived: validated run saved atomically'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, help='Custom region.json; put before the subcommand')
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('init', 'demo'):
        p = sub.add_parser(name)
        p.add_argument('--out', type=Path, required=True)
    p = sub.add_parser('prompt')
    p.add_argument('--date', required=True, help='Operator-supplied local date, YYYY-MM-DD')
    p.add_argument('--out', type=Path, required=True)
    for name in ('validate', 'archive', 'brief'):
        p = sub.add_parser(name)
        p.add_argument('run', type=Path)
        if name == 'archive':
            p.add_argument('--archive', type=Path, required=True)
        if name == 'brief':
            p.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        config = configuration(args.config)
        if args.command == 'prompt':
            iso_day(args.date)
            args.out.parent.mkdir(parents=True, exist_ok=True)
            content = (ROOT / 'prompts/daily-scan.md').read_text(encoding='utf-8')
            content += f'\n\n## Run configuration\n\nLocal date: {args.date}. Timezone: {config["timezone"]}.\n\n```json\n'
            content += json.dumps(config, ensure_ascii=False, indent=2) + '\n```\n'
            with args.out.open('x', encoding='utf-8') as handle:
                handle.write(content)
            print('Dated prompt created; research has not run')
        elif args.command in ('init', 'demo'):
            args.out.mkdir(parents=True, exist_ok=False)
            run = read_json(ROOT / 'examples/run.json') if args.command == 'demo' else empty_run(config)
            if args.command == 'demo':
                errors = validate(run, config)
                if errors:
                    raise ValueError('; '.join(errors))
            (args.out / 'run.json').write_text(json.dumps(run, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            write_registers(run, args.out / 'registers')
            if args.command == 'demo':
                (args.out / 'briefing.md').write_text(briefing(run, config), encoding='utf-8')
            print('Fictional demo created' if args.command == 'demo' else 'Empty scaffold created; fill it after research')
        else:
            run = read_json(args.run)
            errors = validate(run, config)
            if errors:
                print('\n'.join(errors), file=sys.stderr)
                return 1
            if args.command == 'archive':
                print(archive(run, config, args.archive))
            elif args.command == 'brief':
                args.out.parent.mkdir(parents=True, exist_ok=True)
                with args.out.open('x', encoding='utf-8') as handle:
                    handle.write(briefing(run, config))
                print('Evidence digest created; review and add cross-scan interpretation before sharing')
            else:
                print('Structure and cross-field checks passed; source truth and research completeness require review')
        return 0
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
        # Avoid dumping private record contents or connector payloads on malformed input.
        if isinstance(exc, (json.JSONDecodeError, KeyError, TypeError)):
            print('Invalid JSON or missing configuration fields', file=sys.stderr)
        elif isinstance(exc, OSError):
            print(f'File operation failed ({type(exc).__name__}); check destination and access', file=sys.stderr)
        else:
            print(str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
