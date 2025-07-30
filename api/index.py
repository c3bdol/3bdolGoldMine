import os
import time
import requests
import logging
from datetime import datetime
from urllib.parse import urlparse
import json

logging.basicConfig(level=logging.INFO)

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_USER_ID = os.getenv('TELEGRAM_USER_ID')

H1_URL = "https://raw.githubusercontent.com/arkadiyt/bounty-targets-data/master/data/hackerone_data.json"
BUGCROWD_URL = "https://raw.githubusercontent.com/arkadiyt/bounty-targets-data/master/data/bugcrowd_data.json"

def send_telegram(msg):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_USER_ID:
        return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_USER_ID, "text": msg}
        response = requests.post(url, data=payload, timeout=10)
        response.raise_for_status()
        return True
    except:
        return False

def extract_urls_from_asset(asset, asset_type):
    urls = []
    if asset_type == "url":
        urls.append(asset if asset.startswith('http') else f"https://{asset}")
    elif asset_type == "wildcard":
        if asset.startswith('*.'):
            domain = asset[2:]
            urls += [f"https://{prefix}.{domain}" for prefix in ['www', 'api', 'admin', 'portal', 'app', 'beta', 'staging', 'dev']]
            urls.append(f"https://{domain}")
        else:
            urls.append(f"https://{asset}")
    return [u for u in urls if urlparse(u).netloc]

def fetch_assets():
    try:
        h1 = requests.get(H1_URL, timeout=30).json()
        bc = requests.get(BUGCROWD_URL, timeout=30).json()
        combined = h1 + bc
        data = {}
        for prog in combined:
            name = prog.get("name", "Unknown")
            platform = "HackerOne" if prog in h1 else "Bugcrowd"
            for scope in prog.get("targets", {}).get("in_scope", []):
                aid = scope.get("asset_identifier")
                atype = scope.get("asset_type", "").lower()
                if aid and atype in ["url", "wildcard"] and scope.get("eligible_for_bounty", False):
                    key = f"{aid}|{name}|{platform}"
                    data[key] = {
                        "asset": aid,
                        "program": name,
                        "platform": platform,
                        "asset_type": atype
                    }
        return data
    except Exception as e:
        logging.error(f"Error fetching assets: {e}")
        return {}

def format_asset_message(a):
    return f"""🆕 New Asset
🔍 Asset: {a['asset']}
🏢 Program: {a['program']}
🌐 Platform: {a['platform']}
📋 Type: {a['asset_type'].upper()}
💸 Bounty Eligible: YES
🕓 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""

def run_monitor():
    current = fetch_assets()
    last = {}  # You can replace this with logic to load from storage
    new_keys = set(current) - set(last)
    sent = 0
    urls = []
    for k in new_keys:
        a = current[k]
        urls.extend(extract_urls_from_asset(a["asset"], a["asset_type"]))
        if send_telegram(format_asset_message(a)):
            sent += 1
    return {
        "new_assets": len(new_keys),
        "telegram_sent": sent,
        "timestamp": datetime.now().isoformat(),
        "examples": urls[:5]
    }

def handler(request):
    result = run_monitor()
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(result)
    }
