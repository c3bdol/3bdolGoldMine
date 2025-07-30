from flask import Flask, jsonify, request
import logging
import os
import time
import requests
from datetime import datetime
import json
import re
from urllib.parse import urlparse
import tempfile

app = Flask(__name__)

# Set up logging
logging.basicConfig(level=logging.INFO)

# Configuration
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_USER_ID = os.getenv('TELEGRAM_USER_ID')

H1_URL = "https://raw.githubusercontent.com/arkadiyt/bounty-targets-data/master/data/hackerone_data.json"
BUGCROWD_URL = "https://raw.githubusercontent.com/arkadiyt/bounty-targets-data/master/data/bugcrowd_data.json"

# For Vercel, we'll use KV storage or external storage instead of local files
# For now, we'll use a simple in-memory approach or external service

def send_telegram(msg):
    """Send message to Telegram with error handling"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_USER_ID:
        logging.warning("Telegram credentials not configured")
        return False
        
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_USER_ID, 
            "text": msg
        }
        response = requests.post(url, data=payload, timeout=10)
        response.raise_for_status()
        time.sleep(0.1)  # Rate limiting
        return True
        
    except Exception as e:
        logging.error(f"Failed to send Telegram message: {e}")
        return False

def extract_urls_from_asset(asset, asset_type):
    """Extract clean URLs from various asset formats"""
    urls = []
    
    if asset_type == "url":
        if asset.startswith(('http://', 'https://')):
            urls.append(asset)
        else:
            urls.append(f"https://{asset}")
    
    elif asset_type == "wildcard":
        if asset.startswith('*.'):
            domain = asset[2:]
            urls.extend([
                f"https://{domain}",
                f"https://www.{domain}",
                f"https://api.{domain}",
                f"https://admin.{domain}",
                f"https://portal.{domain}",
                f"https://app.{domain}",
                f"https://beta.{domain}",
                f"https://staging.{domain}",
                f"https://dev.{domain}"
            ])
        else:
            urls.append(f"https://{asset}")
    
    # Clean and validate URLs
    clean_urls = []
    for url in urls:
        try:
            parsed = urlparse(url)
            if parsed.netloc:
                clean_urls.append(url)
        except:
            continue
    
    return clean_urls

def fetch_assets():
    """Fetch assets from both platforms with error handling"""
    asset_data = {}
    
    try:
        logging.info("Fetching HackerOne data...")
        h1_response = requests.get(H1_URL, timeout=30)
        h1_response.raise_for_status()
        h1_data = h1_response.json()
        
        logging.info("Fetching Bugcrowd data...")
        bc_response = requests.get(BUGCROWD_URL, timeout=30)
        bc_response.raise_for_status()
        bc_data = bc_response.json()
        
        combined = h1_data + bc_data
        logging.info(f"Processing {len(combined)} programs...")
        
        for prog in combined:
            try:
                program_name = prog.get("name", "Unknown Program")
                platform = "HackerOne" if prog in h1_data else "Bugcrowd"
                
                if "targets" not in prog or "in_scope" not in prog["targets"]:
                    continue
                    
                for scope in prog["targets"]["in_scope"]:
                    asset_id = scope.get("asset_identifier")
                    asset_type = scope.get("asset_type", "").lower()
                    eligible_for_bounty = scope.get("eligible_for_bounty", False)
                    
                    # Only include bounty eligible assets
                    if not eligible_for_bounty:
                        continue
                    
                    # Only include URL and wildcard types
                    allowed_types = ["url", "wildcard"]
                    if asset_type not in allowed_types:
                        continue
                    
                    if asset_id:
                        asset_key = f"{asset_id}|{program_name}|{platform}"
                        asset_data[asset_key] = {
                            "asset": asset_id,
                            "program": program_name,
                            "platform": platform,
                            "asset_type": asset_type,
                            "eligible_for_bounty": eligible_for_bounty
                        }
                        
            except (KeyError, TypeError) as e:
                logging.warning(f"Skipping malformed program data: {e}")
                continue
        
        logging.info(f"Found {len(asset_data)} total assets")
        return asset_data
        
    except Exception as e:
        logging.error(f"Failed to fetch data: {e}")
        return {}

def load_last_assets():
    """Load previously seen assets from external storage"""
    # For Vercel, you'll need to implement this with:
    # - Vercel KV storage
    # - External database (Redis, MongoDB, etc.)
    # - GitHub API to store/retrieve from a repository
    # For now, returning empty dict (will treat all as new on first run)
    return {}

def save_assets(asset_dict):
    """Save current assets to external storage"""
    # For Vercel, implement with external storage
    # For demo purposes, we'll just log
    logging.info(f"Would save {len(asset_dict)} assets to external storage")
    return True

def format_asset_message(asset_data):
    """Format asset information for Telegram message"""
    message = f"""🆕 New Asset Found
🔍 Asset: {asset_data['asset']}
🏢 Program: {asset_data['program']}
🌐 Platform: {asset_data['platform']}
📋 Type: {asset_data['asset_type'].upper()}
💸 Bounty Eligible: YES
Found at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
    
    return message

def run_monitor():
    """Main monitoring function"""
    try:
        logging.info("Starting bounty asset monitoring...")
        
        # Fetch current assets
        current_assets = fetch_assets()
        if not current_assets:
            logging.error("Failed to fetch asset data")
            return {"status": "error", "message": "Failed to fetch asset data"}
        
        # Load previous state
        last_assets = load_last_assets()
        
        # Find new assets
        new_asset_keys = set(current_assets.keys()) - set(last_assets.keys())
        
        if new_asset_keys:
            logging.info(f"Found {len(new_asset_keys)} new assets")
            
            # Extract URLs for new assets
            all_urls = []
            for asset_key in new_asset_keys:
                asset_data = current_assets[asset_key]
                urls = extract_urls_from_asset(asset_data['asset'], asset_data['asset_type'])
                for url in urls:
                    all_urls.append({
                        "url": url,
                        "program": asset_data['program'],
                        "asset_type": asset_data['asset_type'],
                        "platform": asset_data['platform']
                    })
            
            # Send notifications if configured
            telegram_count = 0
            if TELEGRAM_BOT_TOKEN and TELEGRAM_USER_ID:
                for asset_key in new_asset_keys:
                    asset_data = current_assets[asset_key]
                    message = format_asset_message(asset_data)
                    
                    if send_telegram(message):
                        telegram_count += 1
                        logging.info(f"Sent alert for: {asset_data['asset']}")
                    else:
                        logging.error(f"Failed to send alert for: {asset_data['asset']}")
            
            # Save updated state
            save_assets(current_assets)
            
            return {
                "status": "success",
                "message": f"Found {len(new_asset_keys)} new assets",
                "new_assets": len(new_asset_keys),
                "extracted_urls": all_urls,
                "telegram_sent": telegram_count
            }
        else:
            logging.info("No new assets found")
            save_assets(current_assets)
            return {
                "status": "success",
                "message": "No new assets found",
                "new_assets": 0
            }
            
    except Exception as e:
        logging.error(f"Monitor run failed: {e}")
        return {"status": "error", "message": str(e)}

@app.route('/')
def home():
    """Home page with instructions"""
    telegram_status = "✅ Configured" if (TELEGRAM_BOT_TOKEN and TELEGRAM_USER_ID) else "❌ Not Configured"
    
    return f"""
    <html>
    <head><title>🎯 Bug Bounty Monitor - Vercel</title></head>
    <body style="font-family: Arial; margin: 40px; background: #f5f5f5;">
        <div style="background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
            <h1>🎯 Bug Bounty Monitor (Vercel)</h1>
            <p><strong>Status:</strong> <span style="color: green;">Online and Ready</span></p>
            <p><strong>Last Check:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            <p><strong>Telegram:</strong> {telegram_status}</p>
            
            <h3>🔧 Available Endpoints:</h3>
            <ul>
                <li><a href="/api/trigger" style="color: #007bff;">🔄 Manual Trigger</a></li>
                <li><a href="/api/health" style="color: #28a745;">❤️ Health Check</a></li>
                <li><a href="/api/run-now" style="color: #6f42c1;">▶️ Run Now (with results)</a></li>
            </ul>
            
            <h3>⏰ For Cron Jobs:</h3>
            <div style="background: #f8f9fa; padding: 15px; border-radius: 5px; margin: 10px 0;">
                <p><strong>Trigger URL:</strong><br><code>https://your-domain.vercel.app/api/trigger</code></p>
            </div>
            
            <h3>📊 Monitoring Settings:</h3>
            <ul>
                <li><strong>Platforms:</strong> HackerOne & Bugcrowd</li>
                <li><strong>Filter:</strong> Bounty eligible only</li>
                <li><strong>Types:</strong> URL, Wildcard</li>
                <li><strong>Runtime:</strong> Serverless (30 second timeout)</li>
            </ul>
            
            <div style="background: #fff3cd; padding: 15px; border-radius: 5px; margin-top: 20px;">
                <h4>⚠️ Important Notes:</h4>
                <ul>
                    <li>This is running on Vercel serverless functions</li>
                    <li>No persistent file storage - implement external storage for production</li>
                    <li>30-second execution timeout</li>
                    <li>Configure environment variables in Vercel dashboard</li>
                </ul>
            </div>
        </div>
    </body>
    </html>
    """

@app.route('/api/trigger')
def trigger_monitor():
    """Endpoint to trigger the monitor (for cron jobs)"""
    try:
        result = run_monitor()
        return jsonify({
            "status": "success",
            "message": "Monitor completed",
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "telegram_configured": bool(TELEGRAM_BOT_TOKEN and TELEGRAM_USER_ID),
            "result": result
        })
    
    except Exception as e:
        logging.error(f"Failed to trigger monitor: {e}")
        return jsonify({
            "status": "error",
            "message": f"Failed to trigger monitor: {str(e)}",
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }), 500

@app.route('/api/health')
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "service": "bounty-monitor-vercel",
        "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "telegram_configured": bool(TELEGRAM_BOT_TOKEN and TELEGRAM_USER_ID),
        "platform": "vercel-serverless"
    })

@app.route('/api/run-now')
def run_now():
    """Run monitor immediately and return results"""
    try:
        result = run_monitor()
        return jsonify({
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "result": result
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e),
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }), 500

# Vercel serverless function handler
def handler(request):
    return app(request.environ, lambda *args: None)
