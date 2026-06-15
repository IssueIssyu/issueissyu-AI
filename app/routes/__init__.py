from app.routes.ComplaintEmailRoute import router as complaint_email_router
from app.routes.ComplaintApplyRoute import router as complaint_apply_router
from app.routes.ImageGeoRoute import router as image_geo_router
from app.routes.IssueRoute import router as issue_router
from app.routes.UserRoute import router as user_router
from app.routes.TestRoute import router as test_router
from app.routes.VectorTestRoute import router as vector_test_router
from app.routes.ContestPinRoute import router as contest_pin_router
from app.routes.ContestAdminRoute import router as contest_admin_router
from app.routes.FestivalPinRoute import router as festival_pin_router
from app.routes.FestivalAdminRoute import router as festival_admin_router
from app.routes.PolicyAdminRoute import router as policy_admin_router
from app.routes.PolicyPinRoute import router as policy_pin_router
from app.core.config import settings

ROUTER_REGISTRY = (
    {"router": user_router, "disabled_envs": set()},
    {"router": issue_router, "disabled_envs": set()},
    {"router": complaint_email_router, "disabled_envs": {"prod"}},
    {"router": complaint_apply_router, "disabled_envs": set()},
    {"router": image_geo_router, "disabled_envs": {"prod"}},
    {"router": test_router, "disabled_envs": {"dev", "prod"}},
    {"router": vector_test_router, "disabled_envs": {"dev", "prod"}},
    {"router": festival_pin_router, "disabled_envs": {"prod"}},
    {"router": festival_admin_router, "disabled_envs": set()},
    {"router": contest_pin_router, "disabled_envs": {"prod"}},
    {"router": contest_admin_router, "disabled_envs": set()},
    {"router": policy_pin_router, "disabled_envs": {"prod"}},
    {"router": policy_admin_router, "disabled_envs": set()},
)


def get_enabled_routers(env: str):
    return tuple(
        entry["router"]
        for entry in ROUTER_REGISTRY
        if env not in entry["disabled_envs"]
    )


enabled_routers = get_enabled_routers(settings.env)

__all__ = ["enabled_routers", "get_enabled_routers"]
