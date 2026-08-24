import sys
import os
from pathlib import Path

# Add parent directory (Code/backend) to Python path so imports work from any directory
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.v1.endpoints import auth, superadmin, users, iam_policies, meetings

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    description="RoSense AI Multi-Tenant Backend API with AWS IAM-Style Policy Engine"
)

# Set up CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API v1 Routers
app.include_router(auth.router, prefix=f"{settings.API_V1_STR}/auth", tags=["Authentication"])
app.include_router(superadmin.router, prefix=f"{settings.API_V1_STR}/superadmin", tags=["Superadmin Management"])
app.include_router(users.router, prefix=f"{settings.API_V1_STR}/users", tags=["User Management"])
app.include_router(iam_policies.router, prefix=f"{settings.API_V1_STR}/policies", tags=["IAM Policy Engine"])
app.include_router(meetings.router, prefix=f"{settings.API_V1_STR}/meetings", tags=["Meeting Management & STT Pipeline"])

@app.get("/")
def root_health_check():
    return {
        "status": "online",
        "service": settings.PROJECT_NAME,
        "environment": settings.SUPABASE_ENV,
        "docs": "/docs"
    }

if __name__ == "__main__":
    import uvicorn
    # Use app instance directly to support running from any working directory
    uvicorn.run(app, host="0.0.0.0", port=8000)
