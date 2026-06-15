from __future__ import annotations

import unittest

from app.routes import get_enabled_routers


def _router_tags(env: str) -> set[str]:
    return {router.tags[0] for router in get_enabled_routers(env) if router.tags}


class RouterRegistryTest(unittest.TestCase):
    def test_prod_excludes_pipeline_and_debug_routes(self) -> None:
        tags = _router_tags("prod")

        self.assertNotIn("complaint-email", tags)
        self.assertNotIn("geo", tags)
        self.assertNotIn("festival-pins", tags)
        self.assertNotIn("contest-pins", tags)
        self.assertNotIn("policy-pins", tags)
        self.assertNotIn("test", tags)
        self.assertNotIn("vector-test", tags)

    def test_prod_includes_core_and_admin_routes(self) -> None:
        tags = _router_tags("prod")

        self.assertIn("issue", tags)
        self.assertIn("complaint-apply", tags)
        self.assertIn("festival-admin", tags)
        self.assertIn("contest-admin", tags)
        self.assertIn("policy-admin", tags)
        self.assertIn("users", tags)

    def test_dev_includes_complaint_email_and_geo(self) -> None:
        tags = _router_tags("dev")

        self.assertIn("complaint-email", tags)
        self.assertIn("geo", tags)
        self.assertIn("festival-pins", tags)
        self.assertIn("contest-admin", tags)
        self.assertIn("policy-admin", tags)
