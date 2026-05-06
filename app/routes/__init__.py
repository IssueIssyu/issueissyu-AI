from app.routes.DbCheckRoute import router as db_check_router
from app.routes.UserRoute import router as user_router
from app.routes.TestRoute import router as test_router
from app.routes.VectorTestRoute import router as vector_test_router
from app.core.config import settings

ROUTER_REGISTRY = (
    {"router": user_router, "disabled_envs": set()},
    {"router": db_check_router, "disabled_envs": set()},
    {"router": test_router, "disabled_envs": {"dev", "prod"}},
    {"router": vector_test_router, "disabled_envs": {"dev", "prod"}},
)


def get_enabled_routers(env: str):
    return tuple(
        entry["router"]
        for entry in ROUTER_REGISTRY
        if env not in entry["disabled_envs"]
    )


enabled_routers = get_enabled_routers(settings.env)

__all__ = ["enabled_routers", "get_enabled_routers"]
