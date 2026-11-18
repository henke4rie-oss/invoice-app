from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from .config import settings
from .db import init_db, get_db
from .services.scheduler import start_scheduler, stop_scheduler
from pathlib import Path
from fastapi.staticfiles import StaticFiles
import logging
import time
from contextlib import asynccontextmanager

# Import routers after app initialization to avoid circular imports
from .routers.auth import router as auth_router
from .routers.clients import router as clients_router
from .routers.invoices import router as invoices_router
from .routers.reminders import router as reminders_router
from .routers.dashboard import router as dashboard_router
from .routers.profile import router as profile_router

# Configure logging
logging.basicConfig(level=logging.INFO)

# Parse CORS origins from comma-separated string
origins = [origin.strip() for origin in settings.cors_origins.split(",")] if settings.cors_origins else []

# Security CORS filtering
if not settings.debug:
    origins = [o for o in origins if o not in ("null", "*")]

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Production secret key validation
    if not settings.debug and (settings.secret_key == "dev-secret-change-in-production" or len(settings.secret_key) < 32):
        raise RuntimeError("SECRET_KEY must be set to a strong value in production")

    # Create logos directory
    logos_dir = Path(__file__).resolve().parent.parent / "data" / "logos"
    logos_dir.mkdir(parents=True, exist_ok=True)

    init_db()
    if settings.scheduler_enabled:
        start_scheduler()
    yield
    if settings.scheduler_enabled:
        stop_scheduler()


app = FastAPI(
    lifespan=lifespan,
    title="Invoice App API",
    version="1.0.0",
    description="API for managing invoices, clients, and reminders",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    openapi_url="/openapi.json" if settings.debug else None,
)

# Configure CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security headers and rate limiting middleware
rate_limit_data = {}

class SecurityAndRateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        # Rate limiting for auth endpoints (disabled in debug mode)
        if not settings.debug and request.url.path in ("/api/auth/login", "/api/auth/register"):
            client_ip = request.client.host if request.client else "unknown"
            now = time.time()
            
            # Drop expired IPs so the dict cannot grow without bound
            for ip in [ip for ip, stamps in rate_limit_data.items() if not stamps or now - stamps[-1] >= settings.auth_rate_window]:
                del rate_limit_data[ip]

            # Clean old timestamps (outside the window) for this IP
            rate_limit_data[client_ip] = [ts for ts in rate_limit_data.get(client_ip, []) if now - ts < settings.auth_rate_window]

            if len(rate_limit_data[client_ip]) >= settings.auth_rate_limit:
                # Calculate retry-after: seconds until oldest request expires
                oldest_ts = min(rate_limit_data[client_ip])
                retry_after = int(oldest_ts + settings.auth_rate_window - now)
                retry_after = max(1, retry_after)
                
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too many requests"},
                    headers={"Retry-After": str(retry_after)}
                )
            
            rate_limit_data[client_ip].append(now)
        
        response = await call_next(request)
        
        # Add security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data: blob:; connect-src 'self'; frame-ancestors 'none'"
        
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        return response

app.add_middleware(SecurityAndRateLimitMiddleware)

# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logging.exception("Unhandled exception occurred")
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})

# Include routers with specified prefixes
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(clients_router, prefix="/api/clients", tags=["clients"])
app.include_router(invoices_router, prefix="/api/invoices", tags=["invoices"])
app.include_router(reminders_router, prefix="/api", tags=["reminders"])
app.include_router(dashboard_router, prefix="/api/dashboard", tags=["dashboard"])
app.include_router(profile_router, prefix="/api/profile", tags=["profile"])

# Health endpoint
@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "Invoice App API"}

# Serve frontend as static files
FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
