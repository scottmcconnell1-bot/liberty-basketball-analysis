"""Tests for Adrian jersey lookaround matching."""

from adrian_identity import match_scorebook_player, scorebook_roster_index


def test_unique_jersey_matches_scorebook():
    idx = scorebook_roster_index()
    # Dayley #40 is Liberty (away) only
    hit = match_scorebook_player(40, idx)
    assert hit is not None
    assert hit["jersey"] == "40"
    assert "Dayley" in (hit.get("name") or "")
    assert hit["team_name"] == "Liberty"


def test_ambiguous_jersey_skipped():
    idx = scorebook_roster_index()
    # #11 appears on both Adrian and Liberty in this book
    assert match_scorebook_player(11, idx) is None
