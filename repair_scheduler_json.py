import json
import re
import datetime
import sys
from pathlib import Path

def repair_scheduler_json(input_file: str, output_file: str) -> None:
    """
    Repairs malformed scheduler JSON files by:
    1. Ensuring arena slots include 'start' and 'end' fields (in addition to 'time').
    2. Validating root structure: ensures 'teams', 'arenas', and 'rules' exist.
    3. Validating teams: ensures required defaults (practice/game duration, shared_ice, etc).
    4. Normalizing blackout dates and preferred days/times.
    Saves corrected JSON to output_file.
    """

    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # --- Root structure validation ---
    if not isinstance(data, dict):
        raise ValueError("Root of JSON must be an object/dictionary.")

    if "teams" not in data:
        data["teams"] = {}
    if "arenas" not in data:
        data["arenas"] = {}
    if "rules" not in data:
        data["rules"] = {
            "default_ice_time_type": "practice",
            "ice_times_per_week": {}
        }

    # --- Fix arena slots ---
    def fix_slots(arenas: dict) -> dict:
        for arena, blocks in arenas.items():
            for block in blocks:
                slots = block.get("slots", {})
                for day, slot_list in slots.items():
                    for slot in slot_list:
                        # Fix missing start/end
                        if "time" in slot and ("start" not in slot or "end" not in slot):
                            time_val = slot["time"]
                            match = re.match(r"(\d{1,2}:\d{2})-(\d{1,2}:\d{2})", time_val)
                            if match:
                                slot["start"], slot["end"] = match.groups()
                        # Ensure type exists
                        slot.setdefault("type", "practice")
        return arenas

    data["arenas"] = fix_slots(data["arenas"])

    # --- Fix team defaults ---
    def _is_valid_date(d: str) -> bool:
        try:
            datetime.date.fromisoformat(str(d))
            return True
        except Exception:
            return False

    def fix_teams(teams: dict) -> dict:
        for name, team in teams.items():
            team.setdefault("age", "")
            team.setdefault("type", "house")
            team.setdefault("game_duration", 60)
            team.setdefault("practice_duration", 60)
            team.setdefault("allow_multiple_per_day", False)
            team.setdefault("late_ice_cutoff", None)
            team.setdefault("preferred_days_and_times", {})
            team.setdefault("blackouts", {"tournament": []})
            team.setdefault("shared_ice", True)
            team.setdefault("mandatory_shared_ice", False)

            # Normalize blackout_dates
            if isinstance(team.get("blackouts"), dict):
                for k, arr in team["blackouts"].items():
                    if isinstance(arr, list):
                        team["blackouts"][k] = [
                            d for d in arr if _is_valid_date(d)
                        ]
            elif isinstance(team.get("blackouts"), list):
                team["blackouts"] = {"tournament": [
                    d for d in team["blackouts"] if _is_valid_date(d)
                ]}

            # Normalize preferred_days_and_times
            prefs = team.get("preferred_days_and_times", {})
            if not isinstance(prefs, dict):
                team["preferred_days_and_times"] = {}
            else:
                fixed_prefs = {}
                for day, val in prefs.items():
                    if isinstance(val, list):
                        fixed_prefs[day] = [str(v) for v in val]
                    elif isinstance(val, str):
                        fixed_prefs[day] = [val]
                    else:
                        fixed_prefs[day] = []
                team["preferred_days_and_times"] = fixed_prefs

        return teams

    data["teams"] = fix_teams(data["teams"])

    # --- Fix rules ---
    rules = data["rules"]
    rules.setdefault("default_ice_time_type", "practice")
    rules.setdefault("ice_times_per_week", {})

    # Save corrected JSON
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

    print(f"Corrected and validated JSON saved to {output_file}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python fix_json.py <input.json> <output.json>")
        sys.exit(1)

    repair_scheduler_json(sys.argv[1], sys.argv[2])
