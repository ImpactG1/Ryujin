import pytest
from core.scheduler import scheduler
from services.moderation_service import ModerationPermissionError, ModerationService


@pytest.mark.asyncio
async def test_apply_sanctions_and_mute_expiry(db_session):
    """Test applying sanctions (warn, mute, kick, ban) and automatic mute expiration."""
    service = ModerationService(db_session)
    guild_id = 333001
    moderator_id = 444001
    target_id = 555001

    # 1. Non-officer cannot warn
    with pytest.raises(ModerationPermissionError):
        await service.apply_sanction(
            guild_id=guild_id,
            moderator_id=moderator_id,
            moderator_roles=["member"],
            target_user_id=target_id,
            sanction_type="warn",
            reason="Uncivil banter",
        )

    # 2. Officer applies warn
    warn = await service.apply_sanction(
        guild_id=guild_id,
        moderator_id=moderator_id,
        moderator_roles=["officer"],
        target_user_id=target_id,
        sanction_type="warn",
        reason="Warning for spamming links",
    )
    assert warn.id is not None
    assert warn.sanction_type == "warn"
    assert warn.is_active is True

    # 3. Officer applies mute with duration
    mute = await service.apply_sanction(
        guild_id=guild_id,
        moderator_id=moderator_id,
        moderator_roles=["officer"],
        target_user_id=target_id,
        sanction_type="mute",
        reason="Repeated spam",
        duration_minutes=30,
    )
    assert mute.id is not None
    assert mute.sanction_type == "mute"
    assert mute.expires_at is not None

    # Verify mute expiration execution
    await service.expire_mute(mute.id)
    await db_session.refresh(mute)
    assert mute.is_active is False


@pytest.mark.asyncio
async def test_audit_log_role_based_pii_masking(db_session):
    """
    Test role-based PII masking in audit logs:
    - Admins see full data (unmasked PII).
    - Officers/Moderators see partial data (masked PII).
    """
    service = ModerationService(db_session)
    guild_id = 333002

    # Log an action with sensitive PII in details
    await service.audit_repo.log_action(
        guild_id=guild_id,
        actor_id=111,
        action="USER_REGISTRATION",
        target_entity="member",
        target_id="222",
        details={
            "email": "private.user@gmail.com",
            "phone": "+1-555-123-4567",
            "full_name": "Alice Walker",
            "token": "Bearer secret_test_token_123",
            "public_role": "Duelist",
        },
    )

    # 1. Officer/Mod view -> PII is masked
    officer_logs = await service.get_audit_logs_with_role_pii_masking(
        guild_id=guild_id,
        viewer_roles=["officer"],
    )
    assert len(officer_logs) == 1
    mod_details = officer_logs[0]["details"]
    assert "private.user@gmail.com" not in mod_details["email"]
    assert "@gmail.com" in mod_details["email"]
    assert "Alice Walker" not in mod_details["full_name"] or "[PROTECTED" in mod_details["full_name"] or "*" in mod_details["full_name"]
    assert "secret_test_token_123" not in mod_details["token"]
    assert mod_details["public_role"] == "Duelist"

    # 2. Admin view -> Non-secret PII is visible, secret tokens are always protected
    admin_logs = await service.get_audit_logs_with_role_pii_masking(
        guild_id=guild_id,
        viewer_roles=["admin"],
    )
    admin_details = admin_logs[0]["details"]
    assert admin_details["email"] == "private.user@gmail.com"
    assert admin_details["full_name"] == "Alice Walker"
    assert admin_details["token"] == "********"  # Secrets are always masked


@pytest.mark.asyncio
async def test_anti_abuse_anomaly_detection_flags_for_human_review(db_session):
    """
    Test anti-abuse engine detects repeated sanctions and flags for human review.
    CRITICAL RULE: MUST NEVER AUTO-BAN.
    """
    service = ModerationService(db_session)
    guild_id = 333003
    officer_id = 444003
    spammer_id = 555003

    # Apply 3 sanctions to same user
    for i in range(3):
        await service.apply_sanction(
            guild_id=guild_id,
            moderator_id=officer_id,
            moderator_roles=["officer"],
            target_user_id=spammer_id,
            sanction_type="warn",
            reason=f"Infraction #{i+1}",
        )

    # Run anomaly detection
    anomalies = await service.detect_anti_abuse_anomalies(guild_id)
    assert len(anomalies) >= 1

    sanction_anomaly = next(a for a in anomalies if a["anomaly_type"] == "REPEATED_SANCTIONS_SPIKE")
    assert sanction_anomaly["target_user_id"] == str(spammer_id)
    assert sanction_anomaly["flagged_for_human_review"] is True
    assert sanction_anomaly["action_taken"] == "FLAGGED_FOR_OFFICER_REVIEW"
    # Verify no auto-ban happened
    sanctions = await service.moderation_repo.list_sanctions(guild_id, target_user_id=spammer_id)
    ban_sanctions = [s for s in sanctions if s.sanction_type == "ban"]
    assert len(ban_sanctions) == 0, "Anti-abuse must NEVER auto-ban!"

