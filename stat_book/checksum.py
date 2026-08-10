"""Basketball validation for spiral scorebook rows (not file-hash checksums)."""

from __future__ import annotations

from typing import Any

from .schema import normalize_player


def _issue(code: str, message: str, path: str | None = None) -> dict:
    item = {"code": code, "message": message}
    if path:
        item["path"] = path
    return item


def _fg2_fg3(player: dict) -> tuple[int | None, int | None]:
    extras = player.get("extras") if isinstance(player.get("extras"), dict) else {}
    fg2 = extras.get("fg2")
    fg3 = extras.get("fg3")
    if fg2 is None and player.get("fgm") is not None and player.get("tpm") is not None:
        fg2 = player["fgm"] - player["tpm"]
        fg3 = player["tpm"]
    elif fg3 is None and player.get("tpm") is not None:
        fg3 = player["tpm"]
    return fg2, fg3


def run_validation(box: dict[str, Any]) -> dict:
    """Return {ok, issues}. Primary rule: pts == 2*fg2 + 3*fg3 + ftm."""
    issues: list[dict] = []
    players = [normalize_player(p) for p in (box.get("players") or [])]

    for i, player in enumerate(players):
        path = f"players[{i}]"
        fg2, fg3 = _fg2_fg3(player)
        ftm = player.get("ftm")
        fta = player.get("fta")
        pts = player.get("pts")

        if ftm is not None and fta is not None and ftm > fta:
            issues.append(_issue("makes_lte_attempts", f"ftm ({ftm}) > fta ({fta})", f"{path}.ftm"))

        if None not in (fg2, fg3, ftm, pts):
            expected = 2 * fg2 + 3 * fg3 + ftm
            if pts != expected:
                issues.append(
                    _issue(
                        "pts_identity",
                        f"pts ({pts}) != 2*fg2 + 3*fg3 + ftm ({expected})",
                        f"{path}.pts",
                    )
                )

        # Skip empty rows (no jersey and no pts)
        if player.get("jersey") is None and pts is None and fg2 is None and fg3 is None:
            continue

    home_pts = [p.get("pts") for p in players if p.get("team") == "home" and p.get("pts") is not None]
    away_pts = [p.get("pts") for p in players if p.get("team") == "away" and p.get("pts") is not None]
    if home_pts and box.get("final_score_home") is not None:
        summed = sum(home_pts)
        if box["final_score_home"] != summed:
            issues.append(
                _issue(
                    "final_score_home_sum",
                    f"final_score_home ({box['final_score_home']}) != sum home pts ({summed})",
                    "final_score_home",
                )
            )
    if away_pts and box.get("final_score_away") is not None:
        summed = sum(away_pts)
        if box["final_score_away"] != summed:
            issues.append(
                _issue(
                    "final_score_away_sum",
                    f"final_score_away ({box['final_score_away']}) != sum away pts ({summed})",
                    "final_score_away",
                )
            )

    return {"ok": len(issues) == 0, "issues": issues}


def apply_validation(box: dict[str, Any]) -> dict[str, Any]:
    out = dict(box)
    out["validation"] = run_validation(out)
    return out


# Alias used by older call sites
run_checksums = run_validation
apply_checksums = apply_validation
