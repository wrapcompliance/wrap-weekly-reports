import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import psycopg2
import datetime
import json
import os
import msal
import requests
from collections import defaultdict

# ── DB connect (env vars in GitHub Actions, JSON file locally) ────────────────
if os.environ.get('DB_HOST'):
    conn = psycopg2.connect(
        host=os.environ['DB_HOST'],
        database=os.environ['DB_DATABASE'],
        user=os.environ['DB_USERNAME'],
        password=os.environ['DB_PASSWORD'],
        port=os.environ['DB_PORT'],
        sslmode="require"
    )
else:
    CONFIG_PATH = r"C:\Users\NacerBenDriouich\.claude\wrap_db_config.json"
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)
    conn = psycopg2.connect(
        host=cfg["host"], database=cfg["database"], user=cfg["username"],
        password=cfg["password"], port=cfg["port"], sslmode="require"
    )

# ── Date range (previous Mon → Sun) ──────────────────────────────────────────
today = datetime.date.today()
days_since_monday = today.weekday()
last_monday = today - datetime.timedelta(days=days_since_monday + 7)
last_sunday  = last_monday + datetime.timedelta(days=6)
fmt = "%B %d, %Y"
date_range_str = f"Monday {last_monday.strftime(fmt)} to Sunday {last_sunday.strftime(fmt)}"

cur = conn.cursor()
cur.execute("""
    SELECT "WRAP ID", "Company Name EN", "Country", "Monitoring Firm",
           "Cert Status", "Industry", "Products", "Cert Expiration Date", "Worker Num"
    FROM public."Weekly Certifications"
    LIMIT 1000;
""")
cols = [d[0] for d in cur.description]
all_rows = [dict(zip(cols, row)) for row in cur.fetchall()]
cur.close()
conn.close()

# Separate the TOTAL summary row from real records
workers_covered = 0
data = []
for row in all_rows:
    if str(row.get('WRAP ID') or '').strip().upper() == 'TOTAL':
        try:
            workers_covered = int(row.get('Worker Num') or 0)
        except (ValueError, TypeError):
            workers_covered = 0
    else:
        data.append(row)

total_count = len(data)

# ── Summary: Certified count by country ──────────────────────────────────────
summary = defaultdict(int)
for row in data:
    country = (row.get('Country') or '').strip()
    if country and country.lower() != 'unknown':
        summary[country] += 1

sorted_countries = sorted(summary.items(), key=lambda x: x[0])
total_cert = sum(summary.values())

# ── Build summary table rows ──────────────────────────────────────────────────
summary_rows = ""
for idx, (country, count) in enumerate(sorted_countries):
    bg = "#FFFFFF" if idx % 2 == 0 else "#F7F6F2"
    summary_rows += (
        f'<tr style="background-color:{bg};">'
        f'<td style="padding:5px 10px;border:1px solid #d0d0d0;">{country}</td>'
        f'<td style="padding:5px 10px;border:1px solid #d0d0d0;text-align:center;">{count}</td>'
        f'</tr>\n'
    )
summary_rows += (
    f'<tr style="background-color:#212C59;">'
    f'<td style="padding:5px 10px;border:1px solid #1a2347;color:#B8A45F;font-weight:bold;">TOTAL</td>'
    f'<td style="padding:5px 10px;border:1px solid #1a2347;text-align:center;color:#B8A45F;font-weight:bold;">{total_cert}</td>'
    f'</tr>\n'
)

# ── Build details table rows ──────────────────────────────────────────────────
status_colors = {"certified": "#212C59", "pending": "#832B22"}
details_rows = ""
for idx, row in enumerate(data):
    bg     = "#FFFFFF" if idx % 2 == 0 else "#F7F6F2"
    status = (row.get('Cert Status') or '').lower().strip()
    badge_color = status_colors.get(status, "#555555")
    wrap_id     = row.get('WRAP ID') or ''
    name        = row.get('Company Name EN') or ''
    country     = row.get('Country') or ''
    cb          = row.get('Monitoring Firm') or ''
    industry    = row.get('Industry') or ''
    products    = row.get('Products') or ''
    expiry      = row.get('Cert Expiration Date') or ''
    if hasattr(expiry, 'strftime'):
        expiry = expiry.strftime('%m/%d/%Y')
    workers_raw = row.get('Worker Num') or ''
    try:
        workers_fmt = f"{int(workers_raw):,}"
    except (ValueError, TypeError):
        workers_fmt = str(workers_raw)

    details_rows += (
        f'<tr style="background-color:{bg};">'
        f'<td style="padding:5px 8px;border:1px solid #d0d0d0;color:#555;font-size:10px;white-space:nowrap;">{wrap_id}</td>'
        f'<td style="padding:5px 8px;border:1px solid #d0d0d0;font-weight:bold;color:#212C59;">{name}</td>'
        f'<td style="padding:5px 8px;border:1px solid #d0d0d0;white-space:nowrap;">{country}</td>'
        f'<td style="padding:5px 8px;border:1px solid #d0d0d0;color:#444;font-size:10px;">{cb}</td>'
        f'<td style="padding:5px 8px;border:1px solid #d0d0d0;">'
        f'  <span style="display:inline-block;padding:2px 7px;border-radius:3px;background-color:{badge_color};color:#fff;font-size:10px;font-weight:bold;">{status}</span>'
        f'</td>'
        f'<td style="padding:5px 8px;border:1px solid #d0d0d0;font-size:10px;color:#555;">{industry}</td>'
        f'<td style="padding:5px 8px;border:1px solid #d0d0d0;color:#333;font-size:10px;">{products}</td>'
        f'<td style="padding:5px 8px;border:1px solid #d0d0d0;white-space:nowrap;color:#555;">{expiry}</td>'
        f'<td style="padding:5px 8px;border:1px solid #d0d0d0;text-align:right;font-weight:bold;color:#333;white-space:nowrap;">{workers_fmt}</td>'
        f'</tr>\n'
    )

# ── Assemble HTML ─────────────────────────────────────────────────────────────
html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: Calibri, Arial, sans-serif; font-size: 11px; margin: 20px; }}
  table {{ border-collapse: collapse; width: 100%; margin-bottom: 24px; }}
  th {{
    background-color: #212C59;
    color: #ffffff;
    padding: 7px 10px;
    text-align: left;
    font-size: 11px;
    white-space: nowrap;
    border: 1px solid #1a2347;
  }}
  tr:hover td {{ filter: brightness(0.96); }}
</style>
</head>
<body>

<p style="font-family:Calibri,Arial,sans-serif;font-size:15px;color:#212C59;font-weight:bold;margin-bottom:4px;">
  WRAP Weekly Certifications Report
</p>
<p style="font-family:Calibri,Arial,sans-serif;font-size:12px;color:#444;margin-top:0;margin-bottom:20px;">
  <strong>{total_count}</strong> certifications processed between {date_range_str}
</p>

<p style="font-family:Calibri,Arial,sans-serif;font-size:12px;color:#212C59;font-weight:bold;margin-bottom:6px;">
  Workers Covered
</p>
<table style="width:auto;min-width:200px;margin-bottom:28px;">
  <thead>
    <tr><th style="text-align:center;">Total Workers</th></tr>
  </thead>
  <tbody>
    <tr style="background-color:#FFFFFF;">
      <td style="padding:8px 20px;border:1px solid #d0d0d0;text-align:center;font-size:15px;font-weight:bold;color:#212C59;">{workers_covered:,}</td>
    </tr>
  </tbody>
</table>

<p style="font-family:Calibri,Arial,sans-serif;font-size:12px;color:#212C59;font-weight:bold;margin-bottom:6px;">
  Certifications by Country
</p>
<table style="width:auto;min-width:340px;margin-bottom:28px;">
  <thead>
    <tr>
      <th>Country</th>
      <th style="text-align:center;">Certified</th>
    </tr>
  </thead>
  <tbody>{summary_rows}</tbody>
</table>

<p style="font-family:Calibri,Arial,sans-serif;font-size:12px;color:#212C59;font-weight:bold;margin-bottom:6px;">
  Certification Details
</p>
<table>
  <thead>
    <tr>
      <th>WRAP ID</th>
      <th>Company Name</th>
      <th>Country</th>
      <th>Monitoring Firm</th>
      <th>Status</th>
      <th>Industry</th>
      <th>Products</th>
      <th>Cert Expiry</th>
      <th>Workers</th>
    </tr>
  </thead>
  <tbody>{details_rows}</tbody>
</table>

</body>
</html>"""

# ── Send via Microsoft Graph API ──────────────────────────────────────────────
sender    = os.environ['MAIL_SENDER']
all_staff = os.environ['MAIL_ALL_STAFF']

app = msal.ConfidentialClientApplication(
    client_id=os.environ['AZURE_CLIENT_ID'],
    client_credential=os.environ['AZURE_CLIENT_SECRET'],
    authority=f"https://login.microsoftonline.com/{os.environ['AZURE_TENANT_ID']}"
)
token = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
if "access_token" not in token:
    raise RuntimeError(f"Auth failed: {token.get('error_description')}")

subject = f"WRAP Weekly Certifications Report — Monday {last_monday.strftime('%B %d, %Y')} to Sunday {last_sunday.strftime('%B %d, %Y')}"
payload = {
    "message": {
        "subject": subject,
        "body": {"contentType": "HTML", "content": html},
        "toRecipients":  [{"emailAddress": {"address": sender}}],
        "bccRecipients": [{"emailAddress": {"address": all_staff}}]
    }
}
resp = requests.post(
    f"https://graph.microsoft.com/v1.0/users/{sender}/sendMail",
    headers={"Authorization": f"Bearer {token['access_token']}", "Content-Type": "application/json"},
    json=payload
)
resp.raise_for_status()
print(f"Certifications report sent. Subject: {subject}")
