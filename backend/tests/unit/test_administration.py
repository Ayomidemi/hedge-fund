from unittest import TestCase

from app.main import app


class AdministrationRouteTests(TestCase):
    def test_administration_routes_are_registered(self) -> None:
        paths = app.openapi()["paths"]

        self.assertIn("/api/administration/overview", paths)
        self.assertIn("get", paths["/api/administration/overview"])
