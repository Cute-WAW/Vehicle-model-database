import sys, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import db_supabase
from db_supabase import create_wechat_user_if_not_exists, add_history_record

print(f"Supabase Client Loaded: {db_supabase.get_supabase_client() is not None}")

# 强制测试插入一个用户
success, user, msg = create_wechat_user_if_not_exists("test_real_openid_999", "真机测试号", "http://avatar")
print(f"User Create Result: {success}, {user}, {msg}")

# 测试加入历史记录 (带正确的 username)
if success and user:
    db_username = user.get('username')
    v_info = {"test": "data"}
    p_info = {"price": "100"}
    s2, rid, m2 = add_history_record(db_username, v_info, p_info)
    print(f"History Create Result: {s2}, {rid}, {m2}")
