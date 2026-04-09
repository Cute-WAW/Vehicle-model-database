import sys, os, json
from pathlib import Path
sys.path.insert(0, str(Path('d:/BaiduNetdiskDownload/车型库映射/车型库映射/src')))
sys.path.insert(0, str(Path('d:/BaiduNetdiskDownload/车型库映射/车型库映射')))

import db_supabase
from db_supabase import create_wechat_user_if_not_exists, add_history_record

result = {}
result['supabase_client'] = db_supabase.get_supabase_client() is not None

# Force create user
success, user, msg = create_wechat_user_if_not_exists('test_real_openid_999', '真机测试号', 'http://avatar')
result['user_create_success'] = success
result['user'] = user
result['msg'] = msg

# Force history
if success and user:
    db_username = user.get('username')
    v_info = {'test': 'data'}
    p_info = {'price': '100'}
    s2, rid, m2 = add_history_record(db_username, v_info, p_info)
    result['history_success'] = s2
    result['history_rid'] = str(rid)
    result['history_msg'] = m2

with open('db_test.json', 'w', encoding='utf-8') as f:
    json.dump(result, f, indent=2, ensure_ascii=False)
