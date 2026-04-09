import urllib.request, json, os, sys
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

# === users 表字段 ===
print("=== USERS TABLE ===")
rows = query('users?limit=1')
if rows:
    print("字段列表:")
    for col, val in rows[0].items():
        display = str(val)[:50] if val is not None else 'null'
        print(f"  {col:25s}: {display}")
else:
    print("  (表存在但为空)")

# === prediction_history 表字段 ===
print()
print("=== PREDICTION_HISTORY TABLE ===")
rows2 = query('prediction_history?limit=1')
if rows2:
    print("字段列表:")
    for col, val in rows2[0].items():
        display = str(val)[:60] if val is not None else 'null'
        print(f"  {col:25s}: {display}")
else:
    print("  (表存在但为空)")

# === 已通过微信登录的用户 ===
print()
print("=== 已绑定微信OpenID的用户 ===")
wx_users = query('users?wechat_openid=not.is.null&select=id,username,wechat_openid,nickname,created_at&limit=10')
print(f"共 {len(wx_users)} 个微信登录用户：")
for u in wx_users:
    openid = str(u.get('wechat_openid', ''))
    masked = openid[:12] + '...' if len(openid) > 12 else openid
    print(f"  id={u['id']}  username={u['username']}  openid={masked}  nickname={u.get('nickname')}")
