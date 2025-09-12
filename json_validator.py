import json
import re
import datetime
from typing import Dict, Any, List
import copy

def repair_scheduler_json_object(data: dict) -> dict:
    """
    Comprehensive repair and validation of scheduler JSON (in-memory).
    Fixes common issues with legacy files and ensures compatibility.
    Returns the corrected object.
    """
    if not isinstance(data, dict):
        raise ValueError("Root of JSON must be an object/dictionary.")

    # Create a deep copy to avoid modifying the original
    repaired_data = copy.deepcopy(data)

    # --- Root structure validation ---
    repaired_data.setdefault("teams", {})
    repaired_data.setdefault("arenas", {})
    repaired_data.setdefault("rules", {
        "default_ice_time_type": "practice", 
        "ice_times_per_week": {}
    })

    # --- Repair teams data ---
    repaired_data["teams"] = _repair_teams(repaired_data["teams"])
    
    # --- Repair arenas data ---
    repaired_data["arenas"] = _repair_arenas(repaired_data["arenas"])
    
    # --- Repair rules data ---
    repaired_data["rules"] = _repair_rules(repaired_data["rules"])

    return repaired_data


def _repair_teams(teams: dict) -> dict:
    """Repair and normalize team data structures."""
    if not isinstance(teams, dict):
        return {}
    
    repaired_teams = {}
    
    for team_name, team_data in teams.items():
        if not isinstance(team_data, dict):
            # Skip invalid team entries
            continue
            
        repaired_team = _repair_single_team(team_data)
        repaired_teams[str(team_name)] = repaired_team
    
    return repaired_teams


def _repair_single_team(team: dict) -> dict:
    """Repair a single team's data structure."""
    repaired = {}
    
    # Basic team info with defaults
    repaired["age"] = str(team.get("age", "")).strip() or "U9"
    repaired["type"] = team.get("type", "house")
    if repaired["type"] not in ["house", "competitive"]:
        repaired["type"] = "house"
    
    # Durations
    repaired["practice_duration"] = _safe_int(team.get("practice_duration"), 60)
    repaired["game_duration"] = _safe_int(team.get("game_duration"), 60)
    
    # Boolean settings
    repaired["allow_multiple_per_day"] = bool(team.get("allow_multiple_per_day", False))
    
    # Shared ice settings - this is crucial for fixing shared ice issues
    repaired["allow_shared_ice"] = _repair_shared_ice_setting(team)
    repaired["mandatory_shared_ice"] = bool(team.get("mandatory_shared_ice", False))
    
    # If mandatory shared ice is true, ensure allow_shared_ice is also true
    if repaired["mandatory_shared_ice"]:
        repaired["allow_shared_ice"] = True
    
    # Late ice cutoff
    repaired["late_ice_cutoff_enabled"] = bool(team.get("late_ice_cutoff_enabled", False))
    repaired["late_ice_cutoff_time"] = _repair_late_cutoff_time(team)
    
    # Preferred days and times
    repaired["preferred_days_and_times"] = _repair_preferred_days(team)
    
    # Calculate strict_preferred flag
    prefs = repaired["preferred_days_and_times"]
    repaired["strict_preferred"] = any(
        key.endswith("_strict") and value for key, value in prefs.items()
    )
    
    # Blackout dates
    repaired["blackout_dates"] = _repair_blackout_dates(team)
    
    return repaired


def _repair_shared_ice_setting(team: dict) -> bool:
    """Repair shared ice setting from various legacy formats."""
    # Check new format first
    if "allow_shared_ice" in team:
        return bool(team["allow_shared_ice"])
    
    # Check legacy "shared_ice" format
    shared_ice = team.get("shared_ice")
    if isinstance(shared_ice, dict):
        return bool(shared_ice.get("enabled", True))
    elif isinstance(shared_ice, bool):
        return shared_ice
    elif isinstance(shared_ice, str):
        return shared_ice.lower() in ["true", "yes", "1", "enabled"]
    
    # Default to True for shared ice
    return True


def _repair_late_cutoff_time(team: dict) -> str:
    """Repair late cutoff time setting."""
    # Check new format first
    if team.get("late_ice_cutoff_enabled") and team.get("late_ice_cutoff_time"):
        time_str = str(team["late_ice_cutoff_time"]).strip()
        if _is_valid_time_format(time_str):
            return time_str
    
    # Check legacy format
    legacy_cutoff = team.get("late_ice_cutoff")
    if legacy_cutoff:
        time_str = str(legacy_cutoff).strip()
        if _is_valid_time_format(time_str):
            return time_str
    
    return "21:00"  # Default cutoff time


def _repair_preferred_days(team: dict) -> dict:
    """Repair preferred days and times structure."""
    repaired_prefs = {}
    prefs = team.get("preferred_days_and_times", {})
    
    if not isinstance(prefs, dict):
        return {}
    
    # Valid day names
    valid_days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun",
                  "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    
    for key, value in prefs.items():
        # Handle strict flags
        if key.endswith("_strict"):
            repaired_prefs[key] = bool(value)
            continue
        
        # Normalize day names
        normalized_key = _normalize_day_name(key)
        if not normalized_key:
            continue
        
        # Repair time format
        if isinstance(value, list):
            # Legacy format: ["17:00", "19:00"] -> "17:00-19:00"
            if len(value) >= 2:
                try:
                    start_time = _normalize_time(str(value[0]))
                    end_time = _normalize_time(str(value[1]))
                    if start_time and end_time:
                        repaired_prefs[normalized_key] = f"{start_time}-{end_time}"
                except (IndexError, ValueError):
                    continue
            elif len(value) == 1:
                # Single time - assume 1 hour duration
                try:
                    start_time = _normalize_time(str(value[0]))
                    if start_time:
                        start_dt = datetime.datetime.strptime(start_time, "%H:%M")
                        end_dt = start_dt + datetime.timedelta(hours=1)
                        end_time = end_dt.strftime("%H:%M")
                        repaired_prefs[normalized_key] = f"{start_time}-{end_time}"
                except (ValueError, IndexError):
                    continue
        elif isinstance(value, str) and value.strip():
            # String format - could be "17:00-19:00" or just "17:00"
            value = value.strip()
            if "-" in value:
                # Already in correct format, just validate
                parts = value.split("-", 1)
                if len(parts) == 2:
                    start_time = _normalize_time(parts[0].strip())
                    end_time = _normalize_time(parts[1].strip())
                    if start_time and end_time:
                        repaired_prefs[normalized_key] = f"{start_time}-{end_time}"
            else:
                # Single time
                start_time = _normalize_time(value)
                if start_time:
                    start_dt = datetime.datetime.strptime(start_time, "%H:%M")
                    end_dt = start_dt + datetime.timedelta(hours=1)
                    end_time = end_dt.strftime("%H:%M")
                    repaired_prefs[normalized_key] = f"{start_time}-{end_time}"
        
        # Copy over strict flag if it exists
        strict_key = f"{key}_strict"
        if strict_key in prefs:
            repaired_strict_key = f"{normalized_key}_strict"
            repaired_prefs[repaired_strict_key] = bool(prefs[strict_key])
    
    return repaired_prefs


def _repair_blackout_dates(team: dict) -> List[str]:
    """Repair blackout dates from various legacy formats."""
    blackouts = []
    
    # Check new format first
    if "blackout_dates" in team:
        blackout_data = team["blackout_dates"]
        if isinstance(blackout_data, list):
            blackouts.extend(blackout_data)
        elif isinstance(blackout_data, dict):
            # Flatten dictionary of blackout lists
            for category_blackouts in blackout_data.values():
                if isinstance(category_blackouts, list):
                    blackouts.extend(category_blackouts)
    
    # Check legacy "blackouts" format
    if "blackouts" in team:
        legacy_blackouts = team["blackouts"]
        if isinstance(legacy_blackouts, list):
            blackouts.extend(legacy_blackouts)
        elif isinstance(legacy_blackouts, dict):
            # Extract from categorized blackouts
            for category_blackouts in legacy_blackouts.values():
                if isinstance(category_blackouts, list):
                    blackouts.extend(category_blackouts)
    
    # Validate and normalize dates
    valid_blackouts = []
    for date_str in blackouts:
        if _is_valid_date(str(date_str)):
            # Normalize date format to YYYY-MM-DD
            try:
                if isinstance(date_str, datetime.date):
                    valid_blackouts.append(date_str.isoformat())
                else:
                    # Try to parse and reformat
                    parsed_date = datetime.date.fromisoformat(str(date_str))
                    valid_blackouts.append(parsed_date.isoformat())
            except ValueError:
                # Skip invalid dates
                continue
    
    return sorted(list(set(valid_blackouts)))  # Remove duplicates and sort


def _repair_arenas(arenas: dict) -> dict:
    """Repair and normalize arena data structures."""
    if not isinstance(arenas, dict):
        return {}
    
    repaired_arenas = {}
    
    for arena_name, arena_blocks in arenas.items():
        if not isinstance(arena_blocks, list):
            continue
        
        repaired_blocks = []
        for block in arena_blocks:
            if isinstance(block, dict):
                repaired_block = _repair_arena_block(block)
                if repaired_block:
                    repaired_blocks.append(repaired_block)
        
        repaired_arenas[str(arena_name)] = repaired_blocks
    
    return repaired_arenas


def _repair_arena_block(block: dict) -> dict:
    """Repair a single arena block."""
    repaired_block = {}
    
    # Date validation and repair
    start_date = _repair_date(block.get("start"))
    end_date = _repair_date(block.get("end"))
    
    if not start_date or not end_date:
        return None  # Invalid block
    
    repaired_block["start"] = start_date
    repaired_block["end"] = end_date
    
    # Repair slots
    slots = block.get("slots", {})
    repaired_slots = {}
    
    for day_num, day_slots in slots.items():
        # Ensure day_num is string
        day_key = str(day_num)
        if day_key not in ["0", "1", "2", "3", "4", "5", "6"]:
            continue
        
        if not isinstance(day_slots, list):
            continue
        
        repaired_day_slots = []
        for slot in day_slots:
            repaired_slot = _repair_arena_slot(slot)
            if repaired_slot:
                repaired_day_slots.append(repaired_slot)
        
        if repaired_day_slots:
            repaired_slots[day_key] = repaired_day_slots
    
    repaired_block["slots"] = repaired_slots
    return repaired_block


def _repair_arena_slot(slot: dict) -> dict:
    """Repair a single arena time slot."""
    if not isinstance(slot, dict):
        return None
    
    repaired_slot = {}
    
    # Time validation - this is critical
    time_str = slot.get("time", "")
    if not time_str or "-" not in time_str:
        return None
    
    try:
        start_str, end_str = time_str.split("-", 1)
        start_time = _normalize_time(start_str.strip())
        end_time = _normalize_time(end_str.strip())
        
        if not start_time or not end_time:
            return None
        
        repaired_slot["time"] = f"{start_time}-{end_time}"
    except ValueError:
        return None
    
    # Slot type
    repaired_slot["type"] = slot.get("type", "practice")
    if repaired_slot["type"] not in ["practice", "game"]:
        repaired_slot["type"] = "practice"
    
    # Duration
    if "duration" in slot:
        repaired_slot["duration"] = _safe_int(slot["duration"], 60)
    
    # Pre-assigned team/game info
    if slot.get("pre_assigned_team"):
        repaired_slot["pre_assigned_team"] = str(slot["pre_assigned_team"])
    
    if slot.get("team"):  # Legacy format
        repaired_slot["pre_assigned_team"] = str(slot["team"])
    
    if slot.get("pre_assigned_date"):
        if _is_valid_date(slot["pre_assigned_date"]):
            repaired_slot["pre_assigned_date"] = str(slot["pre_assigned_date"])
    
    if slot.get("pre_assigned_time"):
        time_val = _normalize_time(str(slot["pre_assigned_time"]))
        if time_val:
            repaired_slot["pre_assigned_time"] = time_val
    
    if slot.get("pre_assigned_opponent"):
        repaired_slot["pre_assigned_opponent"] = str(slot["pre_assigned_opponent"])
    
    return repaired_slot


def _repair_rules(rules: dict) -> dict:
    """Repair rules data structure."""
    if not isinstance(rules, dict):
        return {
            "default_ice_time_type": "practice",
            "ice_times_per_week": {}
        }
    
    repaired_rules = {}
    
    # Default ice time type
    default_type = rules.get("default_ice_time_type", "practice")
    if default_type not in ["practice", "game"]:
        default_type = "practice"
    repaired_rules["default_ice_time_type"] = default_type
    
    # Ice times per week
    ice_times = rules.get("ice_times_per_week", {})
    repaired_ice_times = {}
    
    if isinstance(ice_times, dict):
        for team_type, age_data in ice_times.items():
            if team_type not in ["house", "competitive"]:
                continue
            
            if isinstance(age_data, dict):
                repaired_age_data = {}
                for age_group, times in age_data.items():
                    times_int = _safe_int(times, 0)
                    if times_int >= 0:
                        repaired_age_data[str(age_group)] = times_int
                
                if repaired_age_data:
                    repaired_ice_times[team_type] = repaired_age_data
    
    repaired_rules["ice_times_per_week"] = repaired_ice_times
    
    return repaired_rules


def _normalize_day_name(day: str) -> str:
    """Normalize day name to 3-letter format."""
    day_mapping = {
        "monday": "Mon", "mon": "Mon",
        "tuesday": "Tue", "tue": "Tue", "tues": "Tue",
        "wednesday": "Wed", "wed": "Wed",
        "thursday": "Thu", "thu": "Thu", "thur": "Thu", "thurs": "Thu",
        "friday": "Fri", "fri": "Fri",
        "saturday": "Sat", "sat": "Sat",
        "sunday": "Sun", "sun": "Sun"
    }
    
    normalized = day_mapping.get(day.lower())
    if normalized:
        return normalized
    
    # If already in correct format
    if day in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]:
        return day
    
    return None


def _normalize_time(time_str: str) -> str:
    """Normalize time string to HH:MM format."""
    if not time_str:
        return None
    
    time_str = str(time_str).strip()
    
    # Try direct parsing first
    try:
        parsed_time = datetime.datetime.strptime(time_str, "%H:%M")
        return parsed_time.strftime("%H:%M")
    except ValueError:
        pass
    
    # Try with seconds
    try:
        parsed_time = datetime.datetime.strptime(time_str, "%H:%M:%S")
        return parsed_time.strftime("%H:%M")
    except ValueError:
        pass
    
    # Try 12-hour format
    for fmt in ["%I:%M %p", "%I:%M%p", "%I%p"]:
        try:
            parsed_time = datetime.datetime.strptime(time_str.upper(), fmt)
            return parsed_time.strftime("%H:%M")
        except ValueError:
            continue
    
    # Try to parse just numbers
    if time_str.isdigit():
        try:
            hour = int(time_str)
            if 0 <= hour <= 23:
                return f"{hour:02d}:00"
        except ValueError:
            pass
    
    return None


def _is_valid_time_format(time_str: str) -> bool:
    """Check if time string is in valid HH:MM format."""
    if not time_str:
        return False
    
    try:
        datetime.datetime.strptime(str(time_str).strip(), "%H:%M")
        return True
    except ValueError:
        return False


def _is_valid_date(date_str: str) -> bool:
    """Check if date string is valid."""
    if not date_str:
        return False
    
    try:
        if isinstance(date_str, datetime.date):
            return True
        datetime.date.fromisoformat(str(date_str))
        return True
    except (ValueError, TypeError):
        return False


def _repair_date(date_value) -> str:
    """Repair and normalize date to YYYY-MM-DD format."""
    if not date_value:
        return None
    
    if isinstance(date_value, datetime.date):
        return date_value.isoformat()
    
    try:
        parsed_date = datetime.date.fromisoformat(str(date_value))
        return parsed_date.isoformat()
    except ValueError:
        return None


def _safe_int(value, default: int) -> int:
    """Safely convert value to integer with default."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def validate_json_structure(data: dict) -> List[str]:
    """
    Validate JSON structure and return list of issues found.
    This can be used for diagnostics.
    """
    issues = []
    
    if not isinstance(data, dict):
        issues.append("Root data must be a dictionary")
        return issues
    
    # Check required sections
    required_sections = ["teams", "arenas", "rules"]
    for section in required_sections:
        if section not in data:
            issues.append(f"Missing required section: {section}")
    
    # Validate teams
    teams = data.get("teams", {})
    if isinstance(teams, dict):
        for team_name, team_data in teams.items():
            if not isinstance(team_data, dict):
                issues.append(f"Team '{team_name}' data is not a dictionary")
                continue
            
            # Check shared ice settings
            shared_ice = team_data.get("allow_shared_ice")
            mandatory_shared = team_data.get("mandatory_shared_ice")
            
            if mandatory_shared and not shared_ice:
                issues.append(f"Team '{team_name}' has mandatory shared ice but allow_shared_ice is False")
    
    # Validate arenas
    arenas = data.get("arenas", {})
    if isinstance(arenas, dict):
        for arena_name, blocks in arenas.items():
            if not isinstance(blocks, list):
                issues.append(f"Arena '{arena_name}' blocks must be a list")
                continue
            
            for i, block in enumerate(blocks):
                if not isinstance(block, dict):
                    issues.append(f"Arena '{arena_name}' block {i} is not a dictionary")
                    continue
                
                # Check dates
                if not _is_valid_date(block.get("start")):
                    issues.append(f"Arena '{arena_name}' block {i} has invalid start date")
                
                if not _is_valid_date(block.get("end")):
                    issues.append(f"Arena '{arena_name}' block {i} has invalid end date")
    
    return issues