PERMISSIONS = {
    "super_admin": ["all"],
    "admin": [
        "manage_users",
        "ban_user",
        "unban_user",
        "assign_roles",
        "edit_profile",
        "view_premium_users",
        "access_ai"
    ],
    "user": [
        "edit_own_profile",
        "use_ai"
    ]
}

def has_permission(user_roles: list, permission: str) -> bool:
    if not user_roles:
        return False
    for role in user_roles:
        perms = PERMISSIONS.get(role, [])
        if "all" in perms or permission in perms:
            return True
    return False