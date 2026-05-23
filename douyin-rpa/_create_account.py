import psycopg2, os
from dotenv import load_dotenv
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

load_dotenv(Path(r'd:\trea ai\Google\GLM\项目2\.env'))
db_url = os.getenv('DATABASE_URL','')

POSTGRES_PARAMS = {'sslmode','sslcert','sslkey','sslrootcert','application_name','options','keepalives','keepalives_idle','keepalives_interval','keepalives_count','target_session_attrs'}
parsed = urlparse(db_url)
if parsed.query:
    params = parse_qs(parsed.query)
    clean_params = {k: v[0] for k, v in params.items() if k in POSTGRES_PARAMS}
    clean_query = urlencode(clean_params) if clean_params else ''
    db_url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, clean_query, parsed.fragment))

conn = psycopg2.connect(db_url)
cur = conn.cursor()
cur.execute("INSERT INTO merchant (phone, balance, status, updated_at) VALUES ('18888888888', 500.00, 1, NOW()) RETURNING id, phone, balance, status")
row = cur.fetchone()
conn.commit()
print(f'Account created! ID={row[0]}, Phone={row[1]}, Balance={row[2]}, Status={row[3]}')
cur.close()
conn.close()
