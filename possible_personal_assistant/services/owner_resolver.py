import re


def resolve_user(env, owner_text):
    """Return an active user only when its normalized name is unambiguous."""
    if not owner_text:
        return env["res.users"]
    normalized = re.sub(r"\s+", " ", owner_text.strip()).casefold()
    matches = env["res.users"].search([("active", "=", True)]).filtered(lambda user: re.sub(r"\s+", " ", (user.name or "").strip()).casefold() == normalized)
    return matches if len(matches) == 1 else env["res.users"]
