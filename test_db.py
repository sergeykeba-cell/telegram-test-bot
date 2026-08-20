import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
supabase = create_client(url, key)

try:
    # Спробуємо отримати список таблиць або один запис
    response = supabase.table("tokens").select("*").limit(1).execute()
    print("✅ Підключення до Supabase успішне!")
except Exception as e:
    print(f"❌ Помилка підключення: {e}")