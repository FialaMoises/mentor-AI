from .admin import router as admin_router
from .auth import router as auth_router
from .billing import router as billing_router
from .documents import router as documents_router
from .onboarding import router as onboarding_router
from .push import router as push_router
from .routes import router as plan_router

#: Os routers da API, na ordem em que entram no app.
routers = [
    plan_router,
    auth_router,
    onboarding_router,
    documents_router,
    push_router,
    billing_router,
    admin_router,
]

__all__ = [
    "admin_router",
    "auth_router",
    "billing_router",
    "documents_router",
    "onboarding_router",
    "plan_router",
    "push_router",
    "routers",
]
