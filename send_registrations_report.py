import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import psycopg2
import datetime
import json
import os
import msal
import requests
from collections import defaultdict, Counter

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
    SELECT wrap_id, order_id, facility_name, application_type,
           country, region, payment_completed_date, payment_method,
           amount_paid, monitoring_firm, buyers, products
    FROM public."Weekly Registrations"
    LIMIT 1000;
""")
cols = [d[0] for d in cur.description]
data = [dict(zip(cols, row)) for row in cur.fetchall()]
cur.close()
conn.close()

total_count = len(data)

# ── Most common buyer ─────────────────────────────────────────────────────────
buyer_counter = Counter()
for row in data:
    raw = row.get('buyers') or ''
    for b in raw.split(','):
        b = b.strip()
        if b:
            buyer_counter[b] += 1
most_common_buyer = buyer_counter.most_common(1)[0][0] if buyer_counter else '—'

# ── Summary: New vs Renewal by country ───────────────────────────────────────
summary = defaultdict(lambda: {'new': 0, 'renewal': 0})
for row in data:
    country = row.get('country') or 'Unknown'
    typ = (row.get('application_type') or '').lower().strip()
    if typ == 'new':
        summary[country]['new'] += 1
    else:
        summary[country]['renewal'] += 1

sorted_countries = sorted(summary.items(), key=lambda x: -(x[1]['new'] + x[1]['renewal']))
total_new = sum(v['new']     for v in summary.values())
total_ren = sum(v['renewal'] for v in summary.values())
total_all = total_new + total_ren

# ── Build summary table rows ──────────────────────────────────────────────────
summary_rows = ""
for idx, (country, counts) in enumerate(sorted_countries):
    bg = "#FFFFFF" if idx % 2 == 0 else "#F7F6F2"
    row_total = counts['new'] + counts['renewal']
    summary_rows += (
        f'<tr style="background-color:{bg};">'
        f'<td style="padding:5px 10px;border:1px solid #d0d0d0;">{country}</td>'
        f'<td style="padding:5px 10px;border:1px solid #d0d0d0;text-align:center;">{counts["new"]}</td>'
        f'<td style="padding:5px 10px;border:1px solid #d0d0d0;text-align:center;">{counts["renewal"]}</td>'
        f'<td style="padding:5px 10px;border:1px solid #d0d0d0;text-align:center;font-weight:bold;">{row_total}</td>'
        f'</tr>\n'
    )
summary_rows += (
    f'<tr style="background-color:#212C59;">'
    f'<td style="padding:5px 10px;border:1px solid #1a2347;color:#B8A45F;font-weight:bold;">TOTAL</td>'
    f'<td style="padding:5px 10px;border:1px solid #1a2347;text-align:center;color:#B8A45F;font-weight:bold;">{total_new}</td>'
    f'<td style="padding:5px 10px;border:1px solid #1a2347;text-align:center;color:#B8A45F;font-weight:bold;">{total_ren}</td>'
    f'<td style="padding:5px 10px;border:1px solid #1a2347;text-align:center;color:#B8A45F;font-weight:bold;">{total_all}</td>'
    f'</tr>\n'
)

# ── Build details table rows ──────────────────────────────────────────────────
type_colors = {"new": "#832B22", "renewal": "#212C59"}
details_rows = ""
for idx, row in enumerate(data):
    bg  = "#FFFFFF" if idx % 2 == 0 else "#F7F6F2"
    typ = (row.get('application_type') or '').lower().strip()
    badge_color = type_colors.get(typ, "#555555")
    label    = (row.get('application_type') or '').capitalize()
    wrap_id  = row.get('wrap_id') or ''
    order_id = row.get('order_id') or ''
    facility = row.get('facility_name') or ''
    country  = row.get('country') or ''
    pay_date = row.get('payment_completed_date') or ''
    if hasattr(pay_date, 'strftime'):
        pay_date = pay_date.strftime('%m/%d/%Y')
    amount_raw = row.get('amount_paid') or ''
    try:
        amount_fmt = f"${float(amount_raw):,.2f}"
    except (ValueError, TypeError):
        amount_fmt = str(amount_raw)
    cb       = row.get('monitoring_firm') or ''
    buyers   = row.get('buyers') or ''
    products = row.get('products') or ''

    details_rows += (
        f'<tr style="background-color:{bg};">'
        f'<td style="padding:5px 8px;border:1px solid #d0d0d0;color:#555;font-size:10px;white-space:nowrap;">{wrap_id}</td>'
        f'<td style="padding:5px 8px;border:1px solid #d0d0d0;color:#555;font-size:10px;white-space:nowrap;">{order_id}</td>'
        f'<td style="padding:5px 8px;border:1px solid #d0d0d0;font-weight:bold;color:#212C59;">{facility}</td>'
        f'<td style="padding:5px 8px;border:1px solid #d0d0d0;">'
        f'  <span style="display:inline-block;padding:2px 7px;border-radius:3px;background-color:{badge_color};color:#fff;font-size:10px;font-weight:bold;">{label}</span>'
        f'</td>'
        f'<td style="padding:5px 8px;border:1px solid #d0d0d0;white-space:nowrap;">{country}</td>'
        f'<td style="padding:5px 8px;border:1px solid #d0d0d0;white-space:nowrap;color:#555;">{pay_date}</td>'
        f'<td style="padding:5px 8px;border:1px solid #d0d0d0;text-align:right;white-space:nowrap;">{amount_fmt}</td>'
        f'<td style="padding:5px 8px;border:1px solid #d0d0d0;color:#444;font-size:10px;">{cb}</td>'
        f'<td style="padding:5px 8px;border:1px solid #d0d0d0;font-size:10px;color:#555;">{buyers}</td>'
        f'<td style="padding:5px 8px;border:1px solid #d0d0d0;color:#333;font-size:10px;">{products}</td>'
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
  WRAP Weekly Registrations Report
</p>
<p style="font-family:Calibri,Arial,sans-serif;font-size:12px;color:#444;margin-top:0;margin-bottom:20px;">
  <strong>{total_count}</strong> registrations processed between {date_range_str}
</p>

<p style="font-family:Calibri,Arial,sans-serif;font-size:12px;color:#444;margin-top:0;margin-bottom:24px;">
  <span style="color:#212C59;font-weight:bold;">Most Commonly Mentioned Buyer This Week:</span>&nbsp;{most_common_buyer}
</p>

<p style="font-family:Calibri,Arial,sans-serif;font-size:12px;color:#212C59;font-weight:bold;margin-bottom:6px;">
  Applications by Country
</p>
<table style="width:auto;min-width:360px;margin-bottom:28px;">
  <thead>
    <tr>
      <th>Country</th>
      <th style="text-align:center;">New</th>
      <th style="text-align:center;">Renewal</th>
      <th style="text-align:center;">Total</th>
    </tr>
  </thead>
  <tbody>{summary_rows}</tbody>
</table>

<p style="font-family:Calibri,Arial,sans-serif;font-size:12px;color:#212C59;font-weight:bold;margin-bottom:6px;">
  Application Details
</p>
<table>
  <thead>
    <tr>
      <th>WRAP ID</th>
      <th>Order ID</th>
      <th>Facility Name</th>
      <th>Type</th>
      <th>Country</th>
      <th>Payment Date</th>
      <th>Amount</th>
      <th>Monitoring Firm</th>
      <th>Buyers</th>
      <th>Products</th>
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

subject = f"WRAP Weekly Registrations Report — Monday {last_monday.strftime('%B %d, %Y')} to Sunday {last_sunday.strftime('%B %d, %Y')}"
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
print(f"Registrations report sent. Subject: {subject}")
