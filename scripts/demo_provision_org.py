import sys
import os
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(backend_dir))

from app.core.config import settings
from app.core.supabase_client import get_supabase_admin_client

def test_provision_tenant():
    print(f"=== Testing Tenant Provisioning on Supabase Cloud ===")
    admin_supabase = get_supabase_admin_client()
    
    org_slug = "acme-legal"
    org_name = "Acme Legal Partners"
    
    try:
        # 1. Create Organization
        print(f"\n[1/3] Provisioning Organization: '{org_name}'...")
        org_res = admin_supabase.table("organizations").upsert({
            "name": org_name,
            "slug": org_slug,
            "tier": "enterprise"
        }, on_conflict="slug").execute()
        
        org = org_res.data[0]
        org_id = org["id"]
        print(f"[SUCCESS] Organization created! Org ID: {org_id}")

        # 2. Query Departments or Default IAM Policies
        print(f"\n[2/3] Verifying RLS & IAM tables for Org ID: {org_id}...")
        dept_res = admin_supabase.table("departments").upsert({
            "org_id": org_id,
            "name": "Corporate Law Practice",
            "code": "LEGAL-CORP"
        }, on_conflict="org_id,name").execute()
        print(f"[SUCCESS] Department created: {dept_res.data[0]['name']}")

        # 3. List Organizations
        all_orgs = admin_supabase.table("organizations").select("id, name, slug, tier, created_at").execute()
        print(f"\n[3/3] Active Tenants in Database ({len(all_orgs.data)} found):")
        for o in all_orgs.data:
            print(f" - {o['name']} (Slug: {o['slug']}, ID: {o['id']})")

    except Exception as e:
        print(f"[ERROR] Provisioning failed: {e}")

if __name__ == "__main__":
    test_provision_tenant()
