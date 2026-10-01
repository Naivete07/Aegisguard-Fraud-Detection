"""FastAPI Application for AegisGuard Credit Card Fraud Detection System.

Hybrid XGBoost + Isolation Forest Anomaly Detection with SHAP Explainability (PRD v1.0).
"""
import os
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

# Ensure project root is in sys.path regardless of where the script is executed from
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.db import get_db
from app.routes.alerts import router as alerts_router
from app.routes.retrain import router as retrain_router
from app.routes.score import router as score_router
from app.routes.simulate import router as simulate_router
from app.routes.stats import router as stats_router
from app.schemas import HealthResponse
from src.config import ROOT
from src.models.registry import ModelRegistry

START_TIME = time.time()
STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize Database schema
    print("[Startup] Initializing database schema...")
    db = get_db()
    
    # Load or train default production model
    print("[Startup] Initializing Model Registry...")
    registry = ModelRegistry.get_instance()
    
    # Register active model in DB if not present
    if registry.is_loaded and registry.bundle:
        db.register_model_version(
            model_version=registry.model_version,
            model_type=registry.bundle.get("model_type", "hybrid_xgboost_isolation_forest"),
            dataset=registry.bundle.get("dataset", "sparkov"),
            metrics_dict=registry.bundle.get("metrics", {}),
            artefact_path=str(registry.model_path)
        )

    # Seed initial demo transactions if database is completely empty (e.g. on fresh clone / cloud boot)
    try:
        stats = db.get_summary_stats()
        if stats["total_transactions"] == 0:
            print("[Startup] Empty database detected. Seeding initial demo transactions...")
            from app.routes.simulate import simulate_batch, SimulationScenarioRequest
            simulate_batch(req=SimulationScenarioRequest(scenario_type="random", count=15), db=db)
            print("[Startup] Initial demo transactions seeded successfully.")
    except Exception as e:
        print(f"[Startup] Demo seeding skipped: {e}")

    print(f"[Startup] AegisGuard ready with active model: {registry.model_version}")
    yield
    print("[Shutdown] AegisGuard shutting down.")


app = FastAPI(
    title="AegisGuard Fraud Detection Service",
    version="1.0.0",
    description="Real-time hybrid fraud detection (XGBoost + Isolation Forest) with SHAP explainability",
    lifespan=lifespan
)

# Enable CORS for UI integrations
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static assets for frontend dashboard
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Include API route modules
app.include_router(score_router)
app.include_router(alerts_router)
app.include_router(stats_router)
app.include_router(retrain_router)
app.include_router(simulate_router)


@app.get("/", include_in_schema=False)
@app.get("/dashboard", include_in_schema=False)
def serve_dashboard():
    """Serve the Analyst Dashboard UI."""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health", response_model=HealthResponse, tags=["Health"])
def health_check():
    """Liveness & readiness probe for Docker Compose, Kubernetes, and Locust load tests (PRD Table 1)."""
    db_status = "ok"
    redis_status = "ok"
    
    # Test DB
    try:
        db = get_db()
        with db.get_conn() as conn:
            conn.execute("SELECT 1")
    except Exception as e:
        db_status = f"down ({str(e)})"

    # Test Redis
    redis_url = os.environ.get("REDIS_URL")
    if redis_url:
        try:
            import redis
            client = redis.from_url(redis_url, socket_timeout=1.0)
            client.ping()
        except Exception:
            redis_status = "unreachable (standalone fallback active)"
    else:
        redis_status = "standalone_in_memory"

    registry = ModelRegistry.get_instance()
    uptime = time.time() - START_TIME

    return HealthResponse(
        status="HEALTHY" if ("ok" in db_status) else "DEGRADED",
        api="ok",
        database=db_status,
        redis=redis_status,
        active_model_version=registry.model_version,
        uptime_seconds=round(uptime, 1)
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)

