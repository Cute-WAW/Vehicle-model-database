import json, os, sys
import urllib.request
sys.path.insert(0, 'src')
os.chdir(r'd:\BaiduNetdiskDownload\车型库映射\车型库映射')
from dotenv import load_dotenv
load_dotenv('.env')

URL = os.getenv('SUPABASE_URL')
KEY = os.getenv('SUPABASE_KEY')

def query(path):
    req = urllib.request.Request(
        f'{URL}/rest/v1/{path}',
        headers={
            'apikey': KEY,
            'Authorization': f'Bearer {KEY}',
            'Accept': 'application/json'
        }
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())

result = {}
try:
    users = query('users?limit=1')
    if users:
        result['users_columns'] = list(users[0].keys())
    else:
        result['users_columns'] = []
except Exception as e:
    result['users_error'] = str(e)

try:
    history = query('prediction_history?limit=1')
    if history:
        result['history_columns'] = list(history[0].keys())
    else:
        result['history_columns'] = []
except Exception as e:
    result['history_error'] = str(e)

with open('supabase_fields.json', 'w', encoding='utf-8') as f:
    json.dump(result, f, indent=2, ensure_ascii=False)
