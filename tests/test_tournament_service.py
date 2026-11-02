import pytest
from services.tournament_service import (
    DuplicateRegistrationError,
    MatchDisputeError,
    TournamentFullError,
    TournamentPermissionError,
    TournamentService,
    TournamentStateError,
)


@pytest.mark.asyncio
async def test_tournament_registration_and_caps(db_session):
    """Test tournament registration respects participant caps and prevents duplicates."""
    service = TournamentService(db_session)
    guild_id = 888001
    officer_id = 999001

    tourney = await service.create_tournament(
        guild_id=guild_id,
        creator_id=officer_id,
        creator_roles=["officer"],
        title="Ryujin 1v1 Invitational",
        max_participants=2,
    )

    # Register player 1
    p1 = await service.register_participant(tourney.id, 101)
    assert p1.seed == 1

    # Duplicate registration -> raises DuplicateRegistrationError
    with pytest.raises(DuplicateRegistrationError):
        await service.register_participant(tourney.id, 101)

    # Register player 2
    p2 = await service.register_participant(tourney.id, 102)
    assert p2.seed == 2

    # Register player 3 -> exceeds cap
    with pytest.raises(TournamentFullError):
        await service.register_participant(tourney.id, 103)


@pytest.mark.asyncio
async def test_bracket_generation_with_byes_and_match_flow(db_session):
    """
    Test single-elimination bracket generation with 3 participants (non-power-of-2).
    Generates a 4-player bracket where slot 2 has a bye (automatically advances).
    """
    service = TournamentService(db_session)
    guild_id = 888002
    officer_id = 999002

    tourney = await service.create_tournament(
        guild_id=guild_id,
        creator_id=officer_id,
        creator_roles=["officer"],
        title="3-Player Showdown",
        max_participants=8,
    )

    # Register 3 players: 201, 202, 203
    await service.register_participant(tourney.id, 201)
    await service.register_participant(tourney.id, 202)
    await service.register_participant(tourney.id, 203)

    # Generate bracket
    matches = await service.generate_single_elimination_bracket(
        tournament_id=tourney.id,
        initiator_id=officer_id,
        initiator_roles=["officer"],
    )

    # With 3 players, bracket size is 4 (2 rounds total: Round 1 has 2 matches, Round 2 is Finals)
    assert len(matches) == 3
    r1_matches = [m for m in matches if m.round_number == 1]
    assert len(r1_matches) == 2

    # Match 1 is 201 vs 202 (pending)
    m1 = r1_matches[0]
    assert m1.participant1_id == 201
    assert m1.participant2_id == 202
    assert m1.status == "pending"

    # Match 2 is 203 vs BYE (None) -> automatically completed with 203 advancing to Finals
    m2 = r1_matches[1]
    assert m2.participant1_id == 203
    assert m2.participant2_id is None
    assert m2.status == "completed"
    assert m2.winner_id == 203

    # Finals match should already have participant2 set to 203!
    finals = next(m for m in matches if m.round_number == 2)
    assert finals.participant2_id == 203

    # Report score for Match 1: 201 beats 202 (2 - 1)
    await service.report_match_score(
        match_id=m1.id,
        reporter_id=201,
        reporter_roles=["member"],
        score1=2,
        score2=1,
    )

    # 201 advances to Finals as participant1
    await db_session.refresh(finals)
    assert finals.participant1_id == 201
    assert finals.participant2_id == 203

    # Report Finals score: 203 beats 201 (3 - 2)
    await service.report_match_score(
        match_id=finals.id,
        reporter_id=officer_id,
        reporter_roles=["officer"],
        score1=2,
        score2=3,
    )

    # Verify tournament completed and standings
    await db_session.refresh(tourney)
    assert tourney.status == "completed"

    standings = await service.calculate_standings(tourney.id)
    assert len(standings) >= 2
    assert standings[0]["discord_user_id"] == "203"
    assert standings[0]["status"] == "Champion"
    assert standings[1]["discord_user_id"] == "201"
    assert standings[1]["status"] == "Runner-Up"


@pytest.mark.asyncio
async def test_dispute_and_resolution(db_session):
    """Test match dispute raising by participant and resolution by officer."""
    service = TournamentService(db_session)
    guild_id = 888003
    officer_id = 999003

    tourney = await service.create_tournament(
        guild_id=guild_id,
        creator_id=officer_id,
        creator_roles=["officer"],
        title="Dispute Cup",
        max_participants=4,
    )
    await service.register_participant(tourney.id, 301)
    await service.register_participant(tourney.id, 302)

    matches = await service.generate_single_elimination_bracket(
        tournament_id=tourney.id,
        initiator_id=officer_id,
        initiator_roles=["officer"],
    )
    m = matches[0]

    # Participant 302 raises dispute
    dispute = await service.raise_dispute(
        match_id=m.id,
        user_id=302,
        reason="Opponent disconnected during the decider round.",
    )
    assert dispute.id is not None
    assert dispute.status == "open"

    await db_session.refresh(m)
    assert m.status == "disputed"

    # Officer resolves dispute in favor of 302
    resolved_disp = await service.resolve_dispute(
        dispute_id=dispute.id,
        officer_id=officer_id,
        officer_roles=["officer"],
        winner_id=302,
        officer_notes="Verified disconnect logs. Awarded win to 302.",
    )
    assert resolved_disp.status == "resolved"

    await db_session.refresh(m)
    assert m.status == "completed"
    assert m.winner_id == 302

