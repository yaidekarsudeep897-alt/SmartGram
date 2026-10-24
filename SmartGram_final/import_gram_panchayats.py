"""Import a normalized CSV directory into the SmartGram database.

Expected columns: lgd_code,name,district,taluk
Run: python import_gram_panchayats.py data/karnataka_gram_panchayats.csv
"""
import csv
import sqlite3
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
DB = BASE / 'database' / 'smartgram.db'
REQUIRED = ('lgd_code', 'name', 'district', 'taluk')


def import_csv(path: Path) -> int:
    if not path.is_file():
        raise FileNotFoundError(f'CSV file not found: {path}')
    with path.open('r', encoding='utf-8-sig', newline='') as source:
        reader = csv.DictReader(source)
        headers = {h.strip().lower() for h in (reader.fieldnames or [])}
        missing = set(REQUIRED) - headers
        if missing:
            raise ValueError('Missing CSV columns: ' + ', '.join(sorted(missing)))
        records = {}
        for row in reader:
            row = {(key or '').strip().lower(): (value or '').strip() for key, value in row.items()}
            code, name, district, taluk = (row.get(key, '') for key in REQUIRED)
            if code and name and district and taluk:
                records[code] = (name, district, taluk)
    if not records:
        raise ValueError('No valid Panchayat records were found in the CSV.')
    DB.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB) as con:
        con.execute('''CREATE TABLE IF NOT EXISTS gram_panchayats (
            id INTEGER PRIMARY KEY AUTOINCREMENT, lgd_code TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL, district TEXT NOT NULL, taluk TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'Karnataka', active INTEGER NOT NULL DEFAULT 1)''')
        con.executemany('''INSERT INTO gram_panchayats(lgd_code,name,district,taluk,state,active)
            VALUES(?,?,?,?,'Karnataka',1) ON CONFLICT(lgd_code) DO UPDATE SET
            name=excluded.name,district=excluded.district,taluk=excluded.taluk,state='Karnataka',active=1''',
            [(code, name, district, taluk) for code, (name, district, taluk) in records.items()])
    return len(records)


if __name__ == '__main__':
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else BASE / 'data' / 'karnataka_gram_panchayats.csv'
    try:
        imported = import_csv(source)
        with sqlite3.connect(DB) as con:
            count = con.execute('SELECT COUNT(*) FROM gram_panchayats WHERE active=1').fetchone()[0]
        print(f'Imported/updated {imported} unique local-body records.')
        print(f'Active records in database: {count}')
    except (OSError, ValueError, sqlite3.Error) as error:
        print(f'Import failed: {error}', file=sys.stderr)
        raise SystemExit(1)
