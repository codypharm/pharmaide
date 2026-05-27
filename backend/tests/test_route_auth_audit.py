"""Route-level auth/scoping guard audit.

This test is intentionally structural: it catches new routes that are added
without the correct identity boundary. Behavior-level scope tests live beside
the individual route/service tests.
"""

from collections.abc import Callable

from fastapi.routing import APIRoute
from fastapi.security.base import SecurityBase
from starlette.routing import BaseRoute

from app.api.internal import require_internal_worker_auth
from app.auth import get_current_actor
from app.config import Settings
from app.main import create_app

_PUBLIC_PATHS = {"/health", "/health/ready"}
_EXTERNAL_WEBHOOK_PREFIXES = ("/webhooks/",)
_INTERNAL_PREFIXES = ("/internal/",)


def test_pharmacist_routes_require_actor_identity() -> None:
    app = create_app(Settings(_env_file=None))

    unguarded_paths = [
        _route_signature(route)
        for route in _api_routes(app.routes)
        if _requires_actor_guard(route)
        and get_current_actor not in _dependency_calls(route)
    ]

    assert unguarded_paths == []


def test_internal_routes_require_worker_identity_guard() -> None:
    app = create_app(Settings(_env_file=None))

    unguarded_paths = [
        _route_signature(route)
        for route in _api_routes(app.routes)
        if route.path.startswith(_INTERNAL_PREFIXES)
        and require_internal_worker_auth not in _dependency_calls(route)
    ]

    assert unguarded_paths == []


def _api_routes(routes: list[BaseRoute]) -> list[APIRoute]:
    return [route for route in routes if isinstance(route, APIRoute)]


def _requires_actor_guard(route: APIRoute) -> bool:
    if route.path in _PUBLIC_PATHS:
        return False
    if route.path.startswith(_EXTERNAL_WEBHOOK_PREFIXES):
        return False
    return not route.path.startswith(_INTERNAL_PREFIXES)


def _dependency_calls(route: APIRoute) -> set[Callable[..., object]]:
    calls: set[Callable[..., object]] = set()

    def visit(dependant: object) -> None:
        for dependency in getattr(dependant, "dependencies", []):
            call = getattr(dependency, "call", None)
            if callable(call) and not isinstance(call, SecurityBase):
                calls.add(call)
            visit(dependency)

    visit(route.dependant)
    return calls


def _route_signature(route: APIRoute) -> str:
    methods = ",".join(sorted(route.methods or []))
    return f"{methods} {route.path}"
