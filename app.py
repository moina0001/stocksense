from flask import Flask, jsonify, render_template_string
from flask_cors import CORS
import requests
import pandas as pd
from io import StringIO
from datetime import datetime, date
import json

app = Flask(__name__)
CORS(app)

def get_nse_bhavcopy():
    try:
        today = date.today()
        date_str = today.strftime("%d%b%Y").upper()
        url = f"https://nsearchives.nseindia.com/content/historical/EQUITIES/{today.year}/{today.strftime('%b').upper()}/cm{date_str}bhav.csv.zip"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://www.nseindia.com'
        }
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            import zipfile
            import io
            z = zipfile.ZipFile(io.BytesIO(response.content))
            csv_data = z.read(z.namelist()[0]).decode('utf-8')
            df = pd.read_csv(StringIO(csv_data))
            return df
        return None
    except Exception as e:
        print(f"Bhavcopy error: {e}")
        return None

def get_yahoo_data(symbol):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}.NS?interval=1d&range=6mo"
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, timeout=10)
        data = res.json()
        result = data['chart']['result'][0]
        meta = result['meta']
        closes = result['indicators']['quote'][0].get('close', [])
        def calc_perf(days):
            if len(closes) >= days:
                old = closes[-days]
                cur = closes[-1]
                if old and cur:
                    return round((cur - old) / old * 100, 2)
            return None
        return {
            'symbol': symbol,
            'name': meta.get('shortName', symbol),
            'price': meta.get('regularMarketPrice'),
            'prevClose': meta.get('previousClose') or meta.get('chartPreviousClose'),
            'change': round(((meta.get('regularMarketPrice', 0) - (meta.get('previousClose') or meta.get('chartPreviousClose', 0))) / (meta.get('previousClose') or meta.get('chartPreviousClose', 1))) * 100, 2),
            'high52': meta.get('fiftyTwoWeekHigh'),
            'low52': meta.get('fiftyTwoWeekLow'),
            'volume': meta.get('regularMarketVolume'),
            'avgVolume': meta.get('averageDailyVolume3Month'),
            'perf_1w': calc_perf(5),
            'perf_1m': calc_perf(21),
            'perf_3m': calc_perf(63),
            'perf_6m': calc_perf(126),
        }
    except Exception as e:
        print(f"Yahoo error for {symbol}: {e}")
        return None

@app.route('/')
def index():
    with open('index.html') as f:
        return render_template_string(f.read())

@app.route('/api/scan/losers')
def scan_losers():
    try:
        df = get_nse_bhavcopy()
        if df is None:
            return jsonify({'error': 'NSE data abhi available nahi. Market close ke baad try karo (3:30 PM ke baad)', 'data': []})
        df.columns = df.columns.str.strip()
        if 'SERIES' in df.columns:
            df = df[df['SERIES'] == 'EQ']
        if 'PREVCLOSE' in df.columns and 'CLOSE' in df.columns:
            df['CHANGE_PCT'] = ((df['CLOSE'] - df['PREVCLOSE']) / df['PREVCLOSE'] * 100).round(2)
        elif 'OPEN' in df.columns and 'CLOSE' in df.columns:
            df['CHANGE_PCT'] = ((df['CLOSE'] - df['OPEN']) / df['OPEN'] * 100).round(2)
        losers = df[df['CHANGE_PCT'] <= -20].copy()
        losers = losers.sort_values('CHANGE_PCT')
        result = []
        for _, row in losers.iterrows():
            result.append({
                'symbol': str(row.get('SYMBOL', '')),
                'open': float(row.get('OPEN', 0)),
                'close': float(row.get('CLOSE', 0)),
                'prev_close': float(row.get('PREVCLOSE', 0)),
                'change_pct': float(row.get('CHANGE_PCT', 0)),
                'volume': int(row.get('TOTTRDQTY', 0)),
            })
        return jsonify({'data': result, 'total': len(result), 'date': str(date.today())})
    except Exception as e:
        return jsonify({'error': str(e), 'data': []})

@app.route('/api/scan/breakouts')
def scan_breakouts():
    try:
        df = get_nse_bhavcopy()
        if df is None:
            return jsonify({'error': 'NSE data abhi available nahi', 'week52': [], 'box': []})
        df.columns = df.columns.str.strip()
        if 'SERIES' in df.columns:
            df = df[df['SERIES'] == 'EQ']
        if 'PREVCLOSE' in df.columns and 'CLOSE' in df.columns:
            df['CHANGE_PCT'] = ((df['CLOSE'] - df['PREVCLOSE']) / df['PREVCLOSE'] * 100).round(2)
        week52_breaks = []
        box_breaks = []
        if '52WH' in df.columns:
            w52 = df[df['CLOSE'] >= df['52WH'] * 0.99]
            for _, row in w52.iterrows():
                week52_breaks.append({'symbol': str(row.get('SYMBOL', '')), 'close': float(row.get('CLOSE', 0)), 'high52': float(row.get('52WH', 0)), 'change_pct': float(row.get('CHANGE_PCT', 0)), 'volume': int(row.get('TOTTRDQTY', 0))})
        if 'HIGH' in df.columns and 'CLOSE' in df.columns:
            box = df[(df['CLOSE'] >= df['HIGH'] * 0.998) & (df['CHANGE_PCT'] >= 2)]
            for _, row in box.iterrows():
                box_breaks.append({'symbol': str(row.get('SYMBOL', '')), 'close': float(row.get('CLOSE', 0)), 'high': float(row.get('HIGH', 0)), 'change_pct': float(row.get('CHANGE_PCT', 0)), 'volume': int(row.get('TOTTRDQTY', 0))})
        return jsonify({'week52': week52_breaks, 'box': box_breaks, 'date': str(date.today())})
    except Exception as e:
        return jsonify({'error': str(e), 'week52': [], 'box': []})

@app.route('/api/stock/<symbol>')
def stock_detail(symbol):
    data = get_yahoo_data(symbol.upper())
    if data:
        return jsonify(data)
    return jsonify({'error': f'{symbol} ka data nahi mila'})

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=10000)
