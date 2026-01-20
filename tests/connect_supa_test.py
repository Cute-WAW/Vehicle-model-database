import os
from sqlalchemy import table
from supabase import create_client,Client

url: str = "https://pvfjiwbycsydurtvmjdj.supabase.co"
key: str = "sb_secret_y5yRwQcNNycbY98_A4ZczQ_na3d33Im"
supabase: Client = create_client(url, key)

response = (
    supabase.table("users")
    .select("*")
    .execute()
)
print(response)
