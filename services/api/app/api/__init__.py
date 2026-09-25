from .documents import router as documents_router
from .onboarding import router as onboarding_router
from .push import router as push_router
from .routes import router as plan_router

#: Os routers da API, na ordem em que entram no app.
routers = [plan_router, onboarding_router, documents_router, push_router]

__all__ = [
    "documents_router",
    "onboarding_router",
    "plan_router",
    "push_router",
    "routers",
]
