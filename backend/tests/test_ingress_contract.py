import os
import re
import fnmatch
from backend.app.api.public import router as public_router


def test_ingress_contract_routing_matches_all_public_api_endpoints():
    """
    Guarantees that every endpoint registered on FastAPI public router
    is matched by the ingress contract and routed to dearbot-backend:8000.
    """
    # Sample token used for testing routing patterns
    sample_token = "5c1a7d2b8e3f4a1c9d2e3f4a5b6c7d8e"
    
    # Read Caddyfile.snippet
    snippet_path = os.path.join(os.path.dirname(__file__), "..", "..", "deploy", "Caddyfile.snippet")
    assert os.path.exists(snippet_path), "deploy/Caddyfile.snippet must exist"
    
    with open(snippet_path, "r") as f:
        snippet_content = f.read()

    # Ingress matchers configured to proxy to dearbot-backend:8000
    backend_matchers = ["/a/*/*", "/mcp/*", "/health"]
    for m in backend_matchers:
        assert m in snippet_content, f"Expected matcher '{m}' in deploy/Caddyfile.snippet"

    # Verify all routes in public_router are matched by /a/*/*
    for route in public_router.routes:
        path = route.path  # e.g. '/{token}/info', '/{token}/ask', etc.
        concrete_path = f"/a{path.replace('{token}', sample_token).replace('{doc_id}', 'test_doc_id')}"
        
        # Verify concrete_path matches /a/*/*
        matched = fnmatch.fnmatch(concrete_path, "/a/*/*")
        assert matched, f"FastAPI route '{concrete_path}' must match backend ingress pattern '/a/*/*'"

    # Verify that the recruiter landing page UI route DOES NOT match /a/*/* (so it goes to Next.js)
    frontend_page_route = f"/a/{sample_token}"
    assert not fnmatch.fnmatch(frontend_page_route, "/a/*/*"), (
        f"Frontend UI route '{frontend_page_route}' must NOT match '/a/*/*', so it falls through to dearbot-frontend:3000"
    )
