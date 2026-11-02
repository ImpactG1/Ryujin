from enum import IntFlag
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Union

import discord
from discord import app_commands
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core.security import decode_and_verify_token


class DiscordPermissions(IntFlag):
    CREATE_INSTANT_INVITE = 1 << 0
    KICK_MEMBERS = 1 << 1
    BAN_MEMBERS = 1 << 2
    ADMINISTRATOR = 1 << 3
    MANAGE_CHANNELS = 1 << 4
    MANAGE_GUILD = 1 << 5
    ADD_REACTIONS = 1 << 6
    VIEW_AUDIT_LOG = 1 << 7
    VIEW_CHANNEL = 1 << 10
    SEND_MESSAGES = 1 << 11
    MANAGE_MESSAGES = 1 << 13
    EMBED_LINKS = 1 << 14
    ATTACH_FILES = 1 << 15
    READ_MESSAGE_HISTORY = 1 << 16
    MENTION_EVERYONE = 1 << 17
    MANAGE_ROLES = 1 << 28
    MODERATE_MEMBERS = 1 << 40


DEFAULT_ROLE_WEIGHTS: Dict[str, int] = {
    "owner": 100,
    "admin": 80,
    "officer": 60,
    "captain": 40,
    "member": 20,
    "guest": 10,
}


def has_discord_permission(user_perms_bitfield: int, required_flag: Union[int, DiscordPermissions]) -> bool:
    """
    Check if a user bitfield contains the required permission flag.
    If the user has ADMINISTRATOR (1 << 3), it automatically satisfies all checks.
    """
    admin_flag = DiscordPermissions.ADMINISTRATOR.value
    flag_val = int(required_flag)

    if (user_perms_bitfield & admin_flag) == admin_flag:
        return True

    return (user_perms_bitfield & flag_val) == flag_val


def get_role_weight(role_name: str, custom_weights: Optional[Dict[str, int]] = None) -> int:
    weights = custom_weights or DEFAULT_ROLE_WEIGHTS
    return weights.get(role_name.strip().lower(), 0)


def has_sufficient_role(
    user_roles: Union[str, List[str]],
    required_role: str,
    custom_weights: Optional[Dict[str, int]] = None,
) -> bool:
    """
    Verify if the highest weight of the user's roles is greater than or equal to required_role.
    """
    weights = custom_weights or DEFAULT_ROLE_WEIGHTS
    target_weight = get_role_weight(required_role, weights)

    if isinstance(user_roles, str):
        roles_list = [user_roles]
    else:
        roles_list = list(user_roles)

    highest_user_weight = max([get_role_weight(r, weights) for r in roles_list], default=0)
    return highest_user_weight >= target_weight


# --- FastAPI Auth & RBAC Dependencies ---
security_scheme = HTTPBearer(auto_error=False)


async def get_current_user_claims(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security_scheme),
) -> Dict[str, Any]:
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        claims = decode_and_verify_token(credentials.credentials)
        return claims
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_role(required_role: str, custom_weights: Optional[Dict[str, int]] = None) -> Callable:
    """
    FastAPI dependency ensuring the authenticated user has at least the required role weight.
    """
    async def role_checker(claims: Dict[str, Any] = Depends(get_current_user_claims)) -> Dict[str, Any]:
        user_roles = claims.get("roles", ["guest"])
        if isinstance(user_roles, str):
            user_roles = [user_roles]

        if not has_sufficient_role(user_roles, required_role, custom_weights):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden: requires role '{required_role}' or higher",
            )
        return claims

    return role_checker


def require_permission(required_perm: Union[int, DiscordPermissions]) -> Callable:
    """
    FastAPI dependency ensuring the user's bitwise Discord permission is satisfied.
    """
    async def perm_checker(claims: Dict[str, Any] = Depends(get_current_user_claims)) -> Dict[str, Any]:
        user_perms = int(claims.get("permissions", 0))
        if not has_discord_permission(user_perms, required_perm):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden: missing required Discord permission bit {int(required_perm)}",
            )
        return claims

    return perm_checker


# --- Discord.py Cog Slash Command Checks ---
class DiscordPermissionError(app_commands.AppCommandError):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def require_discord_role(required_role: str):
    """
    Discord slash command check: checks interaction.user roles against the required role hierarchy.
    """
    async def predicate(interaction: discord.Interaction) -> bool:
        if not interaction.guild:
            raise DiscordPermissionError("This command can only be used in a server.")

        user = interaction.user
        role_names = [r.name.lower() for r in getattr(user, "roles", [])]
        # Also include 'owner' if user is guild owner
        if getattr(interaction.guild, "owner_id", None) == user.id:
            role_names.append("owner")

        if not has_sufficient_role(role_names, required_role):
            raise DiscordPermissionError(f"You require '{required_role}' or higher to use this command.")
        return True

    return app_commands.check(predicate)


def require_discord_bitwise_perm(required_flag: Union[int, DiscordPermissions]):
    """
    Discord slash command check: checks interaction.permissions against the required bitwise flag.
    """
    async def predicate(interaction: discord.Interaction) -> bool:
        user_perms_val = getattr(interaction.permissions, "value", 0)
        if not has_discord_permission(user_perms_val, required_flag):
            raise DiscordPermissionError("You lack the required Discord permissions to run this command.")
        return True

    return app_commands.check(predicate)

