from supabase import create_client, Client
from app.core.config import settings

def get_supabase_admin_client() -> Client:
    """
    Returns an administrative Supabase client using the Service Role Key.
    Used exclusively for system-level operations (Superadmin provisioning,
    initial user creation, system audit log inserts).
    """
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

def get_supabase_client(user_jwt: str = None) -> Client:
    """
    Returns a standard Supabase client. If a user_jwt is provided,
    requests will be executed under that user's security context,
    enforcing PostgreSQL Row Level Security (RLS) policies.
    """
    client = create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)
    if user_jwt:
        client.postgrest.auth(user_jwt)
    return client
