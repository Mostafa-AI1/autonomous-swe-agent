def normalize_route(route: str) -> str:
    """Normalize route path by removing redundant trailing slashes.
    
    Root path '/' must remain unchanged.
    Non-root paths like '/users/profile/' should become '/users/profile'.
    """
    # BUG: Does not strip trailing slash for non-root routes
    return route
