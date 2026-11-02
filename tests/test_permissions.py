from datetime import timedelta
from unittest.mock import MagicMock
import pytest
from fastapi import HTTPException

from core.permissions import (
    DEFAULT_ROLE_WEIGHTS,
    DiscordPermissions,
    get_role_weight,
    has_discord_permission,
    has_sufficient_role,
    require_permission,
    require_role,
)
from core.security import (
    InvalidTokenError,
    TokenExpiredError,
    create_access_token,
    decode_and_verify_token,
)


def test_jwt_create_and_decode_valid():
    """Verify cryptographic token generation, issuer, and claim decoding."""
    claims = {
        "sub": "987654321098765432",
        "guild_id": "111222333444555666",
        "roles": ["officer", "member"],
        "permissions": int(DiscordPermissions.MANAGE_GUILD),
    }
    token = create_access_token(claims)
    decoded = decode_and_verify_token(token)

    assert decoded["sub"] == claims["sub"]
    assert decoded["guild_id"] == claims["guild_id"]
    assert decoded["roles"] == claims["roles"]
    assert decoded["permissions"] == claims["permissions"]
    assert decoded["iss"] == "ryujin-auth"
    assert "exp" in decoded
    assert "iat" in decoded


def test_jwt_expired_token():
    """Verify that an expired token raises TokenExpiredError."""
    claims = {"sub": "123456"}
    # Token expired 10 minutes ago
    token = create_access_token(claims, expires_delta=timedelta(minutes=-10))
    with pytest.raises(TokenExpiredError):
        decode_and_verify_token(token)


def test_jwt_tampered_signature():
    """Verify that a tampered signature raises InvalidTokenError."""
    claims = {"sub": "123456"}
    token = create_access_token(claims)
    tampered = token[:-5] + "aaaaa"
    with pytest.raises(InvalidTokenError):
        decode_and_verify_token(tampered)


def test_bitwise_permission_checks():
    """Verify bitwise permission evaluation and ADMINISTRATOR override."""
    manage_guild = DiscordPermissions.MANAGE_GUILD.value
    ban_members = DiscordPermissions.BAN_MEMBERS.value
    admin = DiscordPermissions.ADMINISTRATOR.value

    user_bits = manage_guild | DiscordPermissions.SEND_MESSAGES.value

    # Exact bit check
    assert has_discord_permission(user_bits, DiscordPermissions.MANAGE_GUILD) is True
    assert has_discord_permission(user_bits, DiscordPermissions.BAN_MEMBERS) is False

    # Administrator bit check override: admin flag satisfies ANY required permission
    admin_user_bits = admin
    assert has_discord_permission(admin_user_bits, DiscordPermissions.BAN_MEMBERS) is True
    assert has_discord_permission(admin_user_bits, DiscordPermissions.MANAGE_ROLES) is True
    assert has_discord_permission(admin_user_bits, DiscordPermissions.MODERATE_MEMBERS) is True


def test_role_hierarchy_weights():
    """Verify role weight lookups and hierarchical threshold checks."""
    assert get_role_weight("owner") == 100
    assert get_role_weight("admin") == 80
    assert get_role_weight("officer") == 60
    assert get_role_weight("captain") == 40
    assert get_role_weight("member") == 20
    assert get_role_weight("guest") == 10
    assert get_role_weight("unknown_role") == 0

    # Owner satisfies all
    assert has_sufficient_role(["owner"], "admin") is True
    assert has_sufficient_role(["owner"], "officer") is True
    assert has_sufficient_role(["owner"], "member") is True

    # Admin satisfies officer and member, but not owner
    assert has_sufficient_role(["admin"], "officer") is True
    assert has_sufficient_role(["admin"], "member") is True
    assert has_sufficient_role(["admin"], "owner") is False

    # Officer satisfies captain & officer, not admin
    assert has_sufficient_role(["officer"], "captain") is True
    assert has_sufficient_role(["officer"], "officer") is True
    assert has_sufficient_role(["officer"], "admin") is False

    # Multi-role user resolves to highest weight
    assert has_sufficient_role(["guest", "captain", "member"], "captain") is True
    assert has_sufficient_role(["guest", "captain", "member"], "officer") is False


@pytest.mark.asyncio
async def test_fastapi_require_role_dependency():
    """Verify require_role FastAPI dependency behavior."""
    officer_checker = require_role("officer")

    # Satisfied
    valid_claims = {"sub": "123", "roles": ["admin"]}
    res = await officer_checker(claims=valid_claims)
    assert res == valid_claims

    # Insufficient role -> 403 Forbidden
    insufficient_claims = {"sub": "123", "roles": ["member"]}
    with pytest.raises(HTTPException) as exc_info:
        await officer_checker(claims=insufficient_claims)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_fastapi_require_permission_dependency():
    """Verify require_permission FastAPI dependency behavior."""
    ban_checker = require_permission(DiscordPermissions.BAN_MEMBERS)

    # Has permission
    valid_claims = {"sub": "123", "permissions": DiscordPermissions.BAN_MEMBERS.value}
    res = await ban_checker(claims=valid_claims)
    assert res == valid_claims

    # Administrator bit set
    admin_claims = {"sub": "123", "permissions": DiscordPermissions.ADMINISTRATOR.value}
    res_admin = await ban_checker(claims=admin_claims)
    assert res_admin == admin_claims

    # Missing permission -> 403 Forbidden
    invalid_claims = {"sub": "123", "permissions": DiscordPermissions.SEND_MESSAGES.value}
    with pytest.raises(HTTPException) as exc_info:
        await ban_checker(claims=invalid_claims)
    assert exc_info.value.status_code == 403

