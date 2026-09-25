from .documents import router as documents_router
from .onboarding import router as onboarding_router
from .routes import router as plan_router

#: Os três routers da API, na ordem em que entram no app.
routers = [plan_router, onboarding_router, documents_router]

__all__ = ["documents_router", "onboarding_router", "plan_router", "routers"]
