import sys
import os
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(backend_dir))

from app.core.config import settings
from app.core.supabase_client import get_supabase_admin_client, get_supabase_client

def create_and_test_superadmin(
    email: str = "superadmin@rosense.ai",
    password: str = "SuperAdminRoSense2026!"
):
    print(f"=== Creating & Testing RoSense AI Superadmin User ===")
    print(f"Target Email: {email}")
    admin_supabase = get_supabase_admin_client()

    try:
        # 1. Check if user already exists or create in Supabase Auth
        print(f"\n[1/3] Creating/Updating Superadmin Auth user ({email})...")
        
        # Check existing profiles
        existing_profile = admin_supabase.table("profiles").select("*").eq("email", email).execute()
        
        user_id = None
        if existing_profile.data:
            user_id = existing_profile.data[0]["id"]
            print(f"[INFO] Superadmin profile exists (User ID: {user_id}). Updating password...")
            admin_supabase.auth.admin.update_user_by_id(user_id, {"password": password})
        else:
            auth_res = admin_supabase.auth.admin.create_user({
                "email": email,
                "password": password,
                "email_confirm": True,
                "user_metadata": {
                    "full_name": "RoSense AI Superadmin",
                    "role": "superadmin"
                }
            })
            user_id = auth_res.user.id
            print(f"[SUCCESS] Auth user created! User ID: {user_id}")

        # 2. Assign Superadmin Role in user_roles table
        print(f"\n[2/3] Assigning 'superadmin' role in database...")
        admin_supabase.table("user_roles").upsert({
            "user_id": user_id,
            "role": "superadmin"
        }, on_conflict="user_id,org_id").execute()
        print("[SUCCESS] Superadmin role assigned!")

        # 3. Test Authentication Login via Supabase Client
        print(f"\n[3/3] Testing Login with Superadmin Credentials...")
        supabase = get_supabase_client()
        login_res = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })

        if login_res.session and login_res.user:
            print("\n========================================================")
            print("LOGIN SUCCESSFUL!")
            print(f"   User Email  : {login_res.user.email}")
            print(f"   User ID     : {login_res.user.id}")
            print(f"   Access Token: {login_res.session.access_token[:35]}...")
            print("========================================================")
            return True
        else:
            print("[FAIL] Login failed - No session returned.")
            return False

    except Exception as e:
        print(f"[ERROR] Failed to create or test superadmin: {e}")
        return False

if __name__ == "__main__":
    email = sys.argv[1] if len(sys.argv) > 1 else "superadmin@rosense.ai"
    password = sys.argv[2] if len(sys.argv) > 2 else "SuperAdminRoSense2026!"
    create_and_test_superadmin(email, password)
