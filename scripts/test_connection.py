import sys
import os
from pathlib import Path

# Add parent directory to python path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(backend_dir))

# Try loading .env explicitly
env_file = backend_dir / ".env"
if env_file.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=env_file)
    except ImportError:
        pass

from app.core.config import settings
from app.core.supabase_client import get_supabase_admin_client, get_supabase_client

def test_supabase_connection():
    print(f"=== Testing Connection for Project: {settings.PROJECT_NAME} ===")
    print(f"Environment Mode : {settings.SUPABASE_ENV}")
    print(f"Supabase URL     : {settings.SUPABASE_URL}")
    
    if "your-project-ref" in settings.SUPABASE_URL:
        print("\n[!] ERROR: .env file is missing or still contains placeholder 'your-project-ref'.")
        print("Please create 'Code/backend/.env' with your real Supabase credentials.")
        return

    # 1. Test Supabase Client API Connection
    try:
        admin_client = get_supabase_admin_client()
        print("\n[1/2] Connecting to Supabase API with Service Role Key...")
        
        # Test query to check if database tables respond
        response = admin_client.table("organizations").select("count", count="exact").limit(0).execute()
        print("[SUCCESS] Connected to Supabase API successfully!")
        print(f"   Database query response: {response}")
        
    except Exception as e:
        print(f"[API ERROR] {e}")
        print("\nTroubleshooting Tips:")
        print(" 1. Ensure you ran 001_multi_tenant_iam_schema.sql & 002_rls_security_policies.sql in your Supabase SQL Editor.")
        print(" 2. Double check SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env.")

    # 2. Test Direct Database URL Connection string
    try:
        print(f"\n[2/2] Checking Configured Direct DATABASE_URL...")
        db_url = settings.DATABASE_URL
        if "YOUR_DATABASE_PASSWORD" in db_url or "postgres:postgres@localhost" in db_url:
            print("[INFO] DATABASE_URL is set to default/local. Update password in .env if direct PostgreSQL connection is required.")
        else:
            print("[SUCCESS] DATABASE_URL is configured.")
    except Exception as e:
        print(f"[DB URL ERROR] {e}")

if __name__ == "__main__":
    test_supabase_connection()
