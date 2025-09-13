import json
import re
import os
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional, Set
import datetime


# =============================================================================
# SECTION 1: CORE DATA STRUCTURES
# =============================================================================

class ScheduleConflictValidator:
    """Integrated conflict validation for the scheduler."""
    
    def __init__(self):
        self.team_bookings = defaultdict(list)  # team -> [(date, time_slot, arena), ...]
        self.arena_bookings = defaultdict(list)  # arena -> [(date, time_slot, team), ...]
    
    def clear(self):
        """Clear all tracking data."""
        self.team_bookings.clear()
        self.arena_bookings.clear()
    
    def add_existing_schedule(self, schedule: List[Dict]):
        """Initialize with existing schedule entries."""
        self.clear()
        for entry in schedule:
            team = entry.get("team", "")
            arena = entry.get("arena", "")
            date = entry.get("date", "")
            time_slot = entry.get("time_slot", "")
            
            if all([team, arena, date, time_slot]):
                self.team_bookings[team].append((date, time_slot, arena))
                self.arena_bookings[arena].append((date, time_slot, team))
    
    def validate_booking(self, team: str, arena: str, date: str, time_slot: str, 
                        allow_force: bool = False) -> Tuple[bool, List[str]]:
        """Validate a booking attempt. Returns (is_valid, list_of_conflicts)"""
        conflicts = []
        
        # Check 1: Team double-booking
        if team in self.team_bookings:
            for existing_date, existing_time, existing_arena in self.team_bookings[team]:
                if existing_date == date and existing_time == time_slot:
                    if existing_arena != arena:
                        conflicts.append(f"Team {team} already booked at {existing_arena} for {time_slot} on {date}")
                    else:
                        conflicts.append(f"Duplicate booking: Team {team} already has this exact slot")
        
        # Check 2: Arena double-booking
        if arena in self.arena_bookings:
            for existing_date, existing_time, existing_team in self.arena_bookings[arena]:
                if (existing_date == date and existing_time == time_slot and existing_team != team):
                    if not allow_force:
                        conflicts.append(f"Arena {arena} already booked by {existing_team} for {time_slot} on {date}")
        
        return len(conflicts) == 0, conflicts
    
    def add_booking(self, team: str, arena: str, date: str, time_slot: str) -> bool:
        """Add a validated booking to tracking."""
        is_valid, _ = self.validate_booking(team, arena, date, time_slot)
        if is_valid:
            self.team_bookings[team].append((date, time_slot, arena))
            self.arena_bookings[arena].append((date, time_slot, team))
            return True
        return False


@dataclass
class AvailableBlock:
    """Represents an available time block in an arena with booking tracking"""
    arena: str
    date: datetime.date
    start_time: datetime.time
    end_time: datetime.time
    weekday: int
    slot_type: str = "practice"
    bookings: List = None
    
    def __post_init__(self):
        if self.bookings is None:
            self.bookings = []
    
    def __lt__(self, other):
        if not isinstance(other, AvailableBlock):
            return NotImplemented
        return (self.date, self.start_time) < (other.date, other.start_time)
    
    def __eq__(self, other):
        if not isinstance(other, AvailableBlock):
            return NotImplemented
        return (self.arena, self.date, self.start_time, self.end_time) == (other.arena, other.date, other.start_time, other.end_time)
    
    def __hash__(self):
        return hash((self.arena, self.date, self.start_time, self.end_time))
    
    def duration_minutes(self) -> int:
        """Calculate the total duration of this block in minutes"""
        start_dt = datetime.datetime.combine(datetime.date.min, self.start_time)
        end_dt = datetime.datetime.combine(datetime.date.min, self.end_time)
        return int((end_dt - start_dt).total_seconds() / 60)
    
    def remaining_minutes(self) -> int:
        """Calculate remaining unbooked time in this block"""
        used_minutes = sum(booking['duration'] for booking in self.bookings)
        return self.duration_minutes() - used_minutes
    
    def can_fit_duration(self, required_minutes: int) -> bool:
        """Check if a required duration can fit in the remaining time"""
        return self.remaining_minutes() >= required_minutes
    
    def add_booking(self, team_name: str, duration: int, booking_type: str = "practice") -> Tuple[datetime.time, datetime.time]:
        """Add a booking to this block and return the actual start/end times"""
        if not self.can_fit_duration(duration):
            raise ValueError(f"Cannot fit {duration} minutes in remaining {self.remaining_minutes()} minutes")
        
        used_minutes = sum(booking['duration'] for booking in self.bookings)
        start_dt = datetime.datetime.combine(datetime.date.min, self.start_time)
        booking_start_dt = start_dt + datetime.timedelta(minutes=used_minutes)
        booking_end_dt = booking_start_dt + datetime.timedelta(minutes=duration)
        
        booking = {
            'team': team_name,
            'duration': duration,
            'start_time': booking_start_dt.time(),
            'end_time': booking_end_dt.time(),
            'type': booking_type
        }
        self.bookings.append(booking)
        
        return booking_start_dt.time(), booking_end_dt.time()


# =============================================================================
# SECTION 2: UTILITY FUNCTIONS
# =============================================================================

def normalize_team_info(raw: dict) -> dict:
    """Convert legacy JSON structures into new scheduler format."""
    out = dict(raw or {})

    # Preferred days normalization
    pref = out.get("preferred_days_and_times", {})
    norm_pref = {}
    strict_flag = False
    
    if isinstance(pref, dict):
        for day, val in pref.items():
            if day.endswith("_strict"):
                norm_pref[day] = bool(val)
                if val:
                    strict_flag = True
                continue
                
            if isinstance(val, list):
                if len(val) >= 2:
                    norm_pref[day] = f"{val[0]}-{val[1]}"
                elif len(val) == 1:
                    t = str(val[0])
                    try:
                        hh, mm = [int(x) for x in t.split(":")]
                        end_hh, end_mm = hh + 1, mm
                        if end_hh >= 24:
                            end_hh = 23
                            end_mm = 59
                        norm_pref[day] = f"{hh:02d}:{mm:02d}-{end_hh:02d}:{end_mm:02d}"
                    except Exception:
                        norm_pref[day] = f"{t}-{t}"
                else:
                    norm_pref[day] = ""
            elif isinstance(val, str) and val.strip():
                norm_pref[day] = val.strip()
            else:
                norm_pref[day] = ""
    
    out["preferred_days_and_times"] = norm_pref
    out["strict_preferred"] = strict_flag

    # Blackouts normalization
    bl = []
    if isinstance(out.get("blackout_dates"), list):
        bl = list(out.get("blackout_dates"))
    else:
        b2 = out.get("blackouts")
        if isinstance(b2, dict):
            for arr in b2.values():
                if isinstance(arr, list):
                    bl.extend(arr)
        elif isinstance(b2, list):
            bl.extend(b2)
    out["blackout_dates"] = bl

    # Shared ice normalization
    s = out.get("shared_ice", None)
    if isinstance(s, dict):
        out["allow_shared_ice"] = bool(s.get("enabled", True))
    elif isinstance(s, bool):
        out["allow_shared_ice"] = s
    else:
        out.setdefault("allow_shared_ice", True)
    
    out.setdefault("mandatory_shared_ice", False)
    
    if out.get("mandatory_shared_ice", False):
        out["allow_shared_ice"] = True

    # Duration defaults
    try:
        out["practice_duration"] = int(out.get("practice_duration", 60))
    except Exception:
        out["practice_duration"] = 60
    try:
        out["game_duration"] = int(out.get("game_duration", 60))
    except Exception:
        out["game_duration"] = 60

    # Late cutoff
    if out.get("late_ice_cutoff_enabled") and out.get("late_ice_cutoff_time"):
        pass
    else:
        legacy = out.get("late_ice_cutoff")
        if legacy:
            out["late_ice_cutoff_enabled"] = True
            out["late_ice_cutoff_time"] = legacy

    # Clean legacy
    if "blackouts" in out:
        del out["blackouts"]
    if "shared_ice" in out:
        del out["shared_ice"]

    return out


def _parse_date(value) -> datetime.date:
    if isinstance(value, datetime.date):
        return value
    return datetime.date.fromisoformat(str(value))


def _get_age_numeric(age_str: str) -> Optional[int]:
    if not age_str:
        return None
    match = re.search(r"\d+", age_str)
    if match:
        return int(match.group())
    return None


def get_week_number(date: datetime.date, start_date: datetime.date) -> int:
    """Calculate week number from start date."""
    days_diff = (date - start_date).days
    return (days_diff // 7) + 1


def get_sessions_on_date_count(team_data: dict, check_date: datetime.date) -> int:
    """Get count of sessions a team has on a specific date."""
    return len([d for d in team_data["scheduled_dates"] if d == check_date])


def is_consecutive_with_existing_session(team_name: str, team_data: dict, new_block: AvailableBlock, 
                                       schedule: List[dict]) -> bool:
    """Check if a new booking would be consecutive with existing session on same date."""
    existing_sessions = [
        event for event in schedule 
        if ((event.get("team") == team_name and event.get("date") == new_block.date.isoformat()) or
            (event.get("type") == "shared practice" and event.get("opponent") == team_name and 
             event.get("date") == new_block.date.isoformat()))
    ]
    
    if not existing_sessions:
        return True
    
    for session in existing_sessions:
        try:
            existing_start_str, existing_end_str = session["time_slot"].split("-")
            existing_start = datetime.datetime.strptime(existing_start_str, "%H:%M").time()
            existing_end = datetime.datetime.strptime(existing_end_str, "%H:%M").time()
            
            # Check if consecutive
            if (new_block.start_time == existing_end or new_block.end_time == existing_start):
                return True
                
        except Exception as e:
            print(f"    DEBUG: Error parsing time slot {session.get('time_slot', '')}: {e}")
            continue
    
    return False


def block_would_exceed_daily_limit(team_name: str, team_data: dict, block: AvailableBlock, 
                                 schedule: List[dict]) -> bool:
    """Check if booking would exceed reasonable daily limits (max 3 sessions per day)."""
    sessions_on_date = get_sessions_on_date_count(team_data, block.date)
    
    # Hard limit: no more than 3 sessions per day even for utilization
    if sessions_on_date >= 3:
        return True
    
    # If 2+ sessions, must be consecutive
    if sessions_on_date >= 2:
        return not is_consecutive_with_existing_session(team_name, team_data, block, schedule)
    
    return False


# =============================================================================
# SECTION 3: STRICT PREFERENCE FUNCTIONS
# =============================================================================

def has_strict_preferences(team_info: dict) -> bool:
    """Check if team has strict time preferences."""
    if team_info.get("strict_preferred", False):
        return True
    
    prefs = team_info.get("preferred_days_and_times", {})
    for key, value in prefs.items():
        if key.endswith("_strict") and value:
            return True
    
    return False


def _parse_preferred_windows(team_info: dict) -> dict:
    """Parse preferred days/times into structured windows with strict flags."""
    windows = defaultdict(list)
    prefs = team_info.get("preferred_days_and_times", {})
    
    day_mapping = {
        "Mon": "Monday", "Tue": "Tuesday", "Wed": "Wednesday", 
        "Thu": "Thursday", "Fri": "Friday", "Sat": "Saturday", "Sun": "Sunday",
        "Monday": "Monday", "Tuesday": "Tuesday", "Wednesday": "Wednesday",
        "Thursday": "Thursday", "Friday": "Friday", "Saturday": "Saturday", "Sunday": "Sunday"
    }
    
    for key, value in prefs.items():
        if key.endswith("_strict"):
            continue
            
        day_name = day_mapping.get(key)
        if not day_name or not value:
            continue
            
        is_strict = bool(prefs.get(f"{key}_strict", False))
        
        try:
            if "-" in str(value):
                start_str, end_str = str(value).split("-", 1)
                start_time = datetime.datetime.strptime(start_str.strip(), "%H:%M").time()
                end_time = datetime.datetime.strptime(end_str.strip(), "%H:%M").time()
                windows[day_name].append((start_time, end_time, is_strict))
        except (ValueError, AttributeError):
            print(f"DEBUG: Could not parse time preference for {key}: {value}")
            continue
    
    return windows


def find_exact_strict_preference_matches(team_info: dict, available_blocks: List[AvailableBlock]) -> List[AvailableBlock]:
    """Find blocks that exactly match team's STRICT preferences only."""
    exact_matches = []
    windows = _parse_preferred_windows(team_info)
    
    for block in available_blocks:
        block_day = block.date.strftime("%A")
        
        if block_day in windows:
            for start_pref, end_pref, is_strict_window in windows[block_day]:
                if is_strict_window:
                    if (block.start_time <= start_pref and block.end_time >= end_pref):
                        exact_matches.append(block)
                        break
    
    return exact_matches


def find_preferred_time_matches(team_info: dict, available_blocks: List[AvailableBlock], strict_only: bool = False) -> List[AvailableBlock]:
    """Find blocks that match team's preferences (strict or non-strict)."""
    matches = []
    windows = _parse_preferred_windows(team_info)
    
    for block in available_blocks:
        block_day = block.date.strftime("%A")
        
        if block_day in windows:
            for start_pref, end_pref, is_strict_window in windows[block_day]:
                if strict_only and not is_strict_window:
                    continue
                if (block.start_time <= start_pref and block.end_time >= end_pref):
                    matches.append(block)
                    break
    
    return matches


def find_mutual_preference_matches(team1_info: dict, team2_info: dict, available_blocks: List[AvailableBlock], strict_only: bool = False) -> List[AvailableBlock]:
    """Find blocks that match BOTH teams' preferences for shared ice."""
    team1_matches = find_preferred_time_matches(team1_info, available_blocks, strict_only)
    team2_matches = find_preferred_time_matches(team2_info, available_blocks, strict_only)
    
    mutual_matches = []
    for block in team1_matches:
        if block in team2_matches:
            mutual_matches.append(block)
    
    return mutual_matches


def get_block_preference_score(block: AvailableBlock, team_info: dict) -> int:
    """Score block based on preferences - MODIFIED to not penalize early times."""
    windows = _parse_preferred_windows(team_info)
    block_day = block.date.strftime("%A")
    
    if block_day not in windows:
        return 10  # Small positive score for any available time instead of 0
    
    best_score = 10  # Base score for available time
    for start_pref, end_pref, is_strict_window in windows[block_day]:
        if block.start_time < end_pref and block.end_time > start_pref:
            if is_strict_window:
                overlap_start = max(block.start_time, start_pref)
                overlap_end = min(block.end_time, end_pref)
                
                block_duration = (datetime.datetime.combine(datetime.date.min, block.end_time) - 
                                datetime.datetime.combine(datetime.date.min, block.start_time)).total_seconds()
                overlap_duration = (datetime.datetime.combine(datetime.date.min, overlap_end) - 
                                  datetime.datetime.combine(datetime.date.min, overlap_start)).total_seconds()
                
                if overlap_duration >= block_duration * 0.8:
                    return 1000
                elif overlap_duration >= block_duration * 0.5:
                    return 800
                else:
                    return 600
            else:
                overlap_start = max(block.start_time, start_pref)
                overlap_end = min(block.end_time, end_pref)
                
                block_duration = (datetime.datetime.combine(datetime.date.min, block.end_time) - 
                                datetime.datetime.combine(datetime.date.min, block.start_time)).total_seconds()
                overlap_duration = (datetime.datetime.combine(datetime.date.min, overlap_end) - 
                                  datetime.datetime.combine(datetime.date.min, overlap_start)).total_seconds()
                
                if overlap_duration >= block_duration * 0.8:
                    best_score = max(best_score, 50)
                else:
                    best_score = max(best_score, 30)
    
    return best_score


# =============================================================================
# SECTION 4: TEAM PROPERTY HELPERS
# =============================================================================

def has_mandatory_shared_ice(team_info: dict) -> bool:
    """Check if a team has mandatory shared ice enabled."""
    return bool(team_info.get("mandatory_shared_ice", False)) and bool(team_info.get("allow_shared_ice", True))


def calculate_team_priority(team_info: dict, team_name: str) -> int:
    """Calculate allocation priority for teams (lower = higher priority)."""
    priority = 0
    
    age = _get_age_numeric(team_info.get("age", ""))
    if age:
        priority += age // 2
    else:
        priority += 25
    
    team_type = team_info.get("type", "house")
    if team_type == "competitive":
        priority += 0
    else:
        priority += 3
    
    if team_type == "competitive":
        tier = _get_team_tier(team_name, team_info)
        tier_values = {"AA": 0, "A": 1, "BB": 2, "B": 3, "C": 4}
        priority += tier_values.get(tier, 5)
    
    if has_mandatory_shared_ice(team_info):
        priority -= 10
    
    if has_strict_preferences(team_info):
        priority -= 8
    
    return priority


def calculate_constraint_complexity(team_info: dict, team_name: str) -> int:
    """Calculate how constrained a team is for allocation order."""
    complexity = 0
    
    if has_mandatory_shared_ice(team_info):
        complexity += 100
    
    if has_strict_preferences(team_info):
        complexity += 50
    
    blackouts = team_info.get("blackout_dates", [])
    complexity += len(blackouts) * 2
    
    age = _get_age_numeric(team_info.get("age", ""))
    if age and age <= 9:
        complexity += 20
    
    if not team_info.get("allow_shared_ice", True):
        complexity += 30
    
    return complexity


def _get_team_tier(team_name: str, team_info: dict = None) -> str:
    """Extract team tier from team name or info"""
    if team_info and team_info.get("type") == "house":
        return "HOUSE"
    
    tier_patterns = [r"U\d+(AA|A|BB|B|C)\b", r"U\d+\s+(AA|A|BB|B|C)\b"]
    for pattern in tier_patterns:
        match = re.search(pattern, team_name, re.IGNORECASE)
        if match:
            return match.group(1).upper()
    
    return "HOUSE" if "House" in team_name or "house" in team_name else "C"


def _safe_blackout_dates(team_info: dict):
    bl = team_info.get("blackout_dates")
    if isinstance(bl, list):
        return bl
    b = team_info.get("blackouts")
    if isinstance(b, dict):
        out = []
        for v in b.values():
            if isinstance(v, list):
                out.extend(v)
        return out
    if isinstance(b, list):
        return b
    return []


def _safe_allow_multiple(team_info: dict) -> bool:
    return bool(team_info.get("allow_multiple_per_day", False))


def has_blackout_on_date(team_info: dict, check_date: datetime.date) -> bool:
    """Check if team has a blackout on a specific date"""
    blackout_dates = _safe_blackout_dates(team_info)
    for blackout_str in blackout_dates:
        try:
            blackout_date = _parse_date(blackout_str)
            if blackout_date == check_date:
                return True
        except:
            continue
    return False


# =============================================================================
# SECTION 5: SAME-DAY SESSION RULES
# =============================================================================

def should_allow_same_day_booking(team_name: str, team_data: dict, new_block: AvailableBlock, 
                                schedule: List[dict], booking_type: str, allow_multiple: bool) -> bool:
    """Same-day booking rules with utilization priority in Phase 3."""
    sessions_on_date = get_sessions_on_date_count(team_data, new_block.date)
    
    # Phase 3 (utilization): More relaxed rules
    if booking_type in ["extended utilization"]:
        return not block_would_exceed_daily_limit(team_name, team_data, new_block, schedule)
    
    # Standard phases: Max 2 sessions per day, must be consecutive
    if sessions_on_date >= 2:
        print(f"    HARD LIMIT: {team_name} already has {sessions_on_date} sessions on {new_block.date} - BLOCKING")
        return False
    
    if sessions_on_date == 1:
        if not is_consecutive_with_existing_session(team_name, team_data, new_block, schedule):
            print(f"    CONSECUTIVE RULE: {team_name} 2nd session on {new_block.date} would not be consecutive - BLOCKING")
            return False
        
        if (not allow_multiple and 
            booking_type not in ["shared practice", "minimum guarantee"] and 
            team_data.get("needed", 0) < 2):
            print(f"    TEAM POLICY: {team_name} doesn't allow multiple per day - BLOCKING")
            return False
    
    return True


# =============================================================================
# SECTION 6: ENHANCED SHARED ICE FUNCTIONS
# =============================================================================

def has_mutual_preferences(team1_info: dict, team2_info: dict) -> bool:
    """Check if two teams have overlapping preferred days/times."""
    windows1 = _parse_preferred_windows(team1_info)
    windows2 = _parse_preferred_windows(team2_info)
    
    for day in windows1:
        if day in windows2:
            return True
    
    return False


def can_teams_share_ice(team1_info: dict, team2_info: dict, team1_name: str = "", 
                       team2_name: str = "") -> bool:
    """Check if two teams can share ice time."""
    age1 = _get_age_numeric(team1_info.get("age", ""))
    age2 = _get_age_numeric(team2_info.get("age", ""))
    
    if age1 is None or age2 is None:
        return False
    
    age_diff = abs(age1 - age2)
    
    allow1 = team1_info.get("allow_shared_ice", True)
    allow2 = team2_info.get("allow_shared_ice", True)
    
    if not allow1 or not allow2:
        return False
    
    if age_diff > 3:
        return False
    
    return True


def try_shared_ice_for_any_team(team_name: str, team_data: dict, teams_needing_slots: Dict,
                               available_blocks: List[AvailableBlock], start_date: datetime.date,
                               schedule: List[Dict], rules_data: Dict, 
                               validator: ScheduleConflictValidator, booking_type: str = "shared") -> bool:
    """Try shared ice for ANY team that allows it."""
    team_info = team_data["info"]
    
    if not team_info.get("allow_shared_ice", True):
        return False
    
    # Find compatible partners, prioritized by need
    compatible_partners = []
    for other_name, other_data in teams_needing_slots.items():
        if (other_name != team_name and 
            other_data["needed"] > 0 and
            can_teams_share_ice(team_info, other_data["info"], team_name, other_name)):
            
            partner_priority = other_data["needed"] * 100
            if has_mutual_preferences(team_info, other_data["info"]):
                partner_priority += 50
            if other_data["info"].get("allow_shared_ice", True):
                partner_priority += 25
                
            compatible_partners.append((partner_priority, other_name, other_data))
    
    if not compatible_partners:
        return False
    
    compatible_partners.sort(reverse=True)
    
    # Try to find blocks that work for both teams
    for priority, partner_name, partner_data in compatible_partners:
        partner_info = partner_data["info"]
        
        # First try blocks that match both teams' preferences
        mutual_pref_blocks = find_mutual_preference_matches(team_info, partner_info, available_blocks, strict_only=False)
        if mutual_pref_blocks:
            best_block = find_best_block_for_teams_with_distribution(mutual_pref_blocks, team_info, partner_info, 
                                                                   team_data, partner_data, rules_data, start_date)
            if best_block and book_shared_practice(team_name, partner_name, team_data, partner_data, 
                                                 best_block, start_date, schedule, validator):
                print(f"    SHARED (with prefs): {team_name} + {partner_name}")
                return True
        
        # Try any available block that works for both teams
        for block in available_blocks:
            if (is_block_available_for_team(block, team_info, team_data, rules_data, start_date) and
                is_block_available_for_team(block, partner_info, partner_data, rules_data, start_date)):
                
                if book_shared_practice(team_name, partner_name, team_data, partner_data, 
                                      block, start_date, schedule, validator):
                    print(f"    SHARED (any available): {team_name} + {partner_name}")
                    return True
    
    return False


# =============================================================================
# SECTION 7: AVAILABILITY CHECKING
# =============================================================================

def is_block_available_for_team(block: AvailableBlock, team_info: Dict, team_data: Dict, 
                               rules_data: Dict, start_date: datetime.date) -> bool:
    """Check if a block is available for a specific team."""
    required_duration = team_info.get("practice_duration", 60)
    
    if not block.can_fit_duration(required_duration):
        return False
    
    if has_blackout_on_date(team_info, block.date):
        return False
    
    week_num = get_week_number(block.date, start_date)
    current_weekly_count = team_data["weekly_count"][week_num]
    
    team_type = team_info.get("type")
    team_age = team_info.get("age")
    max_per_week = (rules_data.get("ice_times_per_week", {})
                   .get(team_type, {}).get(team_age, 0))
    
    if current_weekly_count >= max_per_week:
        return False
    
    return True


def find_best_block_with_distribution(blocks: List[AvailableBlock], team_info: dict, team_data: dict,
                                    rules_data: Dict, start_date: datetime.date) -> Optional[AvailableBlock]:
    """Find best block considering preferences AND day distribution."""
    best_block = None
    best_score = -999999
    
    print(f"    DEBUG: Looking for blocks for team, currently scheduled on: {sorted(team_data['scheduled_dates'])}")
    
    for block in blocks:
        if is_block_available_for_team(block, team_info, team_data, rules_data, start_date):
            # Base preference score
            pref_score = get_block_preference_score(block, team_info)
                       
            # Reduced same-day penalty since consecutive sessions are now allowed
            sessions_on_date = get_sessions_on_date_count(team_data, block.date)
            
            if sessions_on_date == 0:
                same_day_penalty = 0
            elif sessions_on_date == 1:
                # Check if this would be consecutive - much lower penalty if so
                if is_consecutive_with_existing_session("temp_team", team_data, block, []):
                    same_day_penalty = 50   # Small penalty for consecutive sessions
                else:
                    same_day_penalty = 500  # Higher penalty for non-consecutive
            else:
                same_day_penalty = 2000     # High penalty for 3+ sessions
            
            # Final score encourages day diversity but allows consecutive sessions
            final_score = pref_score - same_day_penalty
            
            print(f"    DEBUG: Block {block.arena} {block.date} {block.start_time}-{block.end_time}: pref={pref_score}, penalty={same_day_penalty}, final={final_score}")
            
            if final_score > best_score:
                best_score = final_score
                best_block = block
    
    if best_block:
        print(f"    DEBUG: Selected block {best_block.arena} {best_block.date} {best_block.start_time}-{best_block.end_time} with score {best_score}")
    else:
        print(f"    DEBUG: No suitable blocks found")
    
    return best_block


def find_best_block_for_teams_with_distribution(blocks: List[AvailableBlock], team1_info: dict, team2_info: dict,
                                              team1_data: dict, team2_data: dict, rules_data: Dict, 
                                              start_date: datetime.date) -> Optional[AvailableBlock]:
    """Find the best block for two teams considering preferences AND day distribution."""
    best_block = None
    best_score = -999999
    
    for block in blocks:
        if (is_block_available_for_team(block, team1_info, team1_data, rules_data, start_date) and
            is_block_available_for_team(block, team2_info, team2_data, rules_data, start_date)):
            
            # Base preference scores
            score1 = get_block_preference_score(block, team1_info)
            score2 = get_block_preference_score(block, team2_info)
            combined_pref_score = score1 + score2
            
            # Same-day penalties for both teams (reduced for consecutive sessions)
            sessions1 = get_sessions_on_date_count(team1_data, block.date)
            sessions2 = get_sessions_on_date_count(team2_data, block.date)
            
            penalty1 = 50 if sessions1 == 1 else 0
            penalty2 = 50 if sessions2 == 1 else 0
            combined_penalty = penalty1 + penalty2
            
            final_score = combined_pref_score - combined_penalty
            
            if final_score > best_score:
                best_score = final_score
                best_block = block
    
    return best_block


# =============================================================================
# SECTION 8: BOOKING FUNCTIONS (ENHANCED)
# =============================================================================

def book_team_practice(team_name: str, team_data: dict, block: AvailableBlock, 
                      start_date: datetime.date, schedule: List[dict], 
                      validator: ScheduleConflictValidator, booking_type: str = "practice") -> bool:
    """Enhanced team practice booking with consecutive session rules."""
    required_duration = team_data["info"].get("practice_duration", 60)
    
    if not block.can_fit_duration(required_duration):
        return False
    
    # Apply same-day rules
    allow_multiple = _safe_allow_multiple(team_data["info"])
    
    if not should_allow_same_day_booking(team_name, team_data, block, schedule, booking_type, allow_multiple):
        return False
    
    try:
        booking_start, booking_end = block.add_booking(team_name, required_duration, booking_type)
    except ValueError:
        return False
    
    # Validate the booking
    date_str = block.date.isoformat()
    time_slot_str = f"{booking_start.strftime('%H:%M')}-{booking_end.strftime('%H:%M')}"
    
    is_valid, conflicts = validator.validate_booking(team_name, block.arena, date_str, time_slot_str)
    
    if not is_valid:
        block.bookings.pop()
        return False
    
    # Booking is valid, create schedule entry
    booking = {
        "team": team_name,
        "opponent": "Practice",
        "arena": block.arena,
        "date": date_str,
        "time_slot": time_slot_str,
        "type": f"practice ({booking_type})"
    }
    
    # Update tracking
    week_num = get_week_number(block.date, start_date)
    schedule.append(booking)
    validator.add_booking(team_name, block.arena, date_str, time_slot_str)
    team_data["needed"] -= 1
    team_data["weekly_count"][week_num] += 1
    team_data["scheduled_dates"].add(block.date)
    
    new_sessions_on_date = len([d for d in team_data["scheduled_dates"] if d == block.date])
    print(f"    BOOKED: {team_name} on {block.date} {booking_start}-{booking_end} (sessions on this date: {new_sessions_on_date})")
    
    return True


def book_shared_practice(team1_name: str, team2_name: str, team1_data: dict, 
                        team2_data: dict, block: AvailableBlock, start_date: datetime.date, 
                        schedule: List[dict], validator: ScheduleConflictValidator) -> bool:
    """Enhanced shared practice booking with consecutive session rules."""
    team1_duration = team1_data["info"].get("practice_duration", 60)
    team2_duration = team2_data["info"].get("practice_duration", 60)
    required_duration = max(team1_duration, team2_duration)
    
    if not block.can_fit_duration(required_duration):
        return False
    
    # Check same-day restrictions for both teams
    allow_multiple1 = _safe_allow_multiple(team1_data["info"])
    allow_multiple2 = _safe_allow_multiple(team2_data["info"])
    
    if not should_allow_same_day_booking(team1_name, team1_data, block, schedule, "shared practice", allow_multiple1):
        return False
    if not should_allow_same_day_booking(team2_name, team2_data, block, schedule, "shared practice", allow_multiple2):
        return False
    
    try:
        booking_start, booking_end = block.add_booking(f"{team1_name} & {team2_name}", required_duration, "shared practice")
    except ValueError:
        return False
    
    # Validate both teams
    date_str = block.date.isoformat()
    time_slot_str = f"{booking_start.strftime('%H:%M')}-{booking_end.strftime('%H:%M')}"
    
    is_valid1, _ = validator.validate_booking(team1_name, block.arena, date_str, time_slot_str)
    is_valid2, _ = validator.validate_booking(team2_name, block.arena, date_str, time_slot_str)
    
    if not is_valid1 or not is_valid2:
        block.bookings.pop()
        return False
    
    # Create shared booking
    booking = {
        "team": team1_name,
        "opponent": team2_name,
        "arena": block.arena,
        "date": date_str,
        "time_slot": time_slot_str,
        "type": "shared practice"
    }
    
    # Update tracking
    week_num = get_week_number(block.date, start_date)
    schedule.append(booking)
    validator.add_booking(team1_name, block.arena, date_str, time_slot_str)
    validator.add_booking(team2_name, block.arena, date_str, time_slot_str)
    
    team1_data["needed"] -= 1
    team2_data["needed"] -= 1
    team1_data["weekly_count"][week_num] += 1
    team2_data["weekly_count"][week_num] += 1
    team1_data["scheduled_dates"].add(block.date)
    team2_data["scheduled_dates"].add(block.date)
    
    return True


def book_extended_practice(team_name: str, team_data: dict, block: AvailableBlock, 
                         duration: int, start_date: datetime.date, schedule: List[dict], 
                         validator: ScheduleConflictValidator) -> bool:
    """Book practice using specified duration (can exceed team's normal practice time)."""
    
    if not block.can_fit_duration(duration):
        return False
    
    try:
        booking_start, booking_end = block.add_booking(team_name, duration, "extended utilization")
    except ValueError:
        return False
    
    # Validate booking
    date_str = block.date.isoformat()
    time_slot_str = f"{booking_start.strftime('%H:%M')}-{booking_end.strftime('%H:%M')}"
    
    is_valid, _ = validator.validate_booking(team_name, block.arena, date_str, time_slot_str)
    if not is_valid:
        block.bookings.pop()
        return False
    
    # Create schedule entry
    booking = {
        "team": team_name,
        "opponent": "Practice",
        "arena": block.arena,
        "date": date_str,
        "time_slot": time_slot_str,
        "type": f"practice (extended utilization - {duration}min)"
    }
    
    # Update tracking (but don't count against weekly quota since this is extra)
    schedule.append(booking)
    validator.add_booking(team_name, block.arena, date_str, time_slot_str)
    team_data["scheduled_dates"].add(block.date)
    
    return True


# =============================================================================
# SECTION 9: ALLOCATION STRATEGIES (ENHANCED)
# =============================================================================

def try_strict_preference_allocation(team_name: str, team_data: dict, available_blocks: List[AvailableBlock],
                                   start_date: datetime.date, schedule: List[Dict], rules_data: Dict,
                                   validator: ScheduleConflictValidator) -> bool:
    """Try to allocate individual session matching strict preferences."""
    team_info = team_data["info"]
    
    strict_matches = find_exact_strict_preference_matches(team_info, available_blocks)
    
    for block in strict_matches:
        if is_block_available_for_team(block, team_info, team_data, rules_data, start_date):
            if book_team_practice(team_name, team_data, block, start_date, schedule, validator, "strict preference"):
                print(f"    INDIVIDUAL (strict): {team_name}")
                return True
    
    return False


def try_preferred_time_allocation(team_name: str, team_data: dict, teams_needing_slots: Dict,
                                available_blocks: List[AvailableBlock], start_date: datetime.date, 
                                schedule: List[Dict], rules_data: Dict,
                                validator: ScheduleConflictValidator) -> bool:
    """Enhanced preferred time allocation that tries shared ice if individual fails."""
    team_info = team_data["info"]
    
    # First try individual allocation with preferences
    preferred_matches = find_preferred_time_matches(team_info, available_blocks, strict_only=False)
    
    for block in preferred_matches:
        if is_block_available_for_team(block, team_info, team_data, rules_data, start_date):
            if book_team_practice(team_name, team_data, block, start_date, schedule, validator, "preferred time"):
                print(f"    INDIVIDUAL (preferred): {team_name}")
                return True
    
    # If individual preferred allocation failed, try shared ice
    if team_info.get("allow_shared_ice", True):
        return try_shared_ice_for_any_team(team_name, team_data, teams_needing_slots, available_blocks, 
                                         start_date, schedule, rules_data, validator, "preferred shared")
    
    return False


def try_any_preference_allocation(team_name: str, team_data: dict, teams_needing_slots: Dict,
                                available_blocks: List[AvailableBlock], start_date: datetime.date, 
                                schedule: List[Dict], rules_data: Dict,
                                validator: ScheduleConflictValidator) -> bool:
    """Try to allocate individual session in any preferred time (relaxed)."""
    return try_preferred_time_allocation(team_name, team_data, teams_needing_slots, available_blocks, start_date, schedule, rules_data, validator)


def force_any_available_allocation(team_name: str, team_data: dict, teams_needing_slots: Dict,
                                 available_blocks: List[AvailableBlock], start_date: datetime.date, 
                                 schedule: List[Dict], rules_data: Dict,
                                 validator: ScheduleConflictValidator) -> bool:
    """Enhanced force allocation that tries shared ice before giving up."""
    team_info = team_data["info"]
    
    # First try any individual block
    for block in available_blocks:
        if is_block_available_for_team(block, team_info, team_data, rules_data, start_date):
            if book_team_practice(team_name, team_data, block, start_date, schedule, validator, "forced minimum"):
                print(f"    INDIVIDUAL (forced): {team_name}")
                return True
    
    # If no individual blocks work, try shared ice as last resort
    if team_info.get("allow_shared_ice", True):
        if try_shared_ice_for_any_team(team_name, team_data, teams_needing_slots, available_blocks, 
                                     start_date, schedule, rules_data, validator, "forced shared"):
            print(f"    SHARED (forced): {team_name}")
            return True
    
    return False


def try_mandatory_shared_with_preferences(team_name: str, team_data: dict, teams_needing_slots: Dict,
                                        available_blocks: List[AvailableBlock], start_date: datetime.date,
                                        schedule: List[Dict], rules_data: Dict, 
                                        validator: ScheduleConflictValidator) -> bool:
    """Try to allocate mandatory shared ice while respecting preferences."""
    team_info = team_data["info"]
    
    # Find compatible partners
    compatible_partners = []
    for other_name, other_data in teams_needing_slots.items():
        if (other_name != team_name and 
            other_data["needed"] > 0 and
            can_teams_share_ice(team_info, other_data["info"], team_name, other_name)):
            compatible_partners.append((other_name, other_data))
    
    if not compatible_partners:
        return False
    
    # Try to find blocks that work for both teams with preferences
    for partner_name, partner_data in compatible_partners:
        partner_info = partner_data["info"]
        
        # First try strict preference matches if both have them
        if has_strict_preferences(team_info) and has_strict_preferences(partner_info):
            mutual_blocks = find_mutual_preference_matches(team_info, partner_info, available_blocks, strict_only=True)
            if mutual_blocks:
                best_block = find_best_block_for_teams_with_distribution(mutual_blocks, team_info, partner_info, 
                                                     team_data, partner_data, rules_data, start_date)
                if best_block and book_shared_practice(team_name, partner_name, team_data, partner_data, 
                                                     best_block, start_date, schedule, validator):
                    print(f"    SHARED (strict prefs): {team_name} + {partner_name}")
                    return True
        
        # Try any preference matches
        mutual_blocks = find_mutual_preference_matches(team_info, partner_info, available_blocks, strict_only=False)
        if mutual_blocks:
            best_block = find_best_block_for_teams_with_distribution(mutual_blocks, team_info, partner_info, 
                                                 team_data, partner_data, rules_data, start_date)
            if best_block and book_shared_practice(team_name, partner_name, team_data, partner_data, 
                                                 best_block, start_date, schedule, validator):
                print(f"    SHARED (any prefs): {team_name} + {partner_name}")
                return True
    
    return False


def try_mandatory_shared_relaxed(team_name: str, team_data: dict, teams_needing_slots: Dict,
                               available_blocks: List[AvailableBlock], start_date: datetime.date,
                               schedule: List[Dict], rules_data: Dict, 
                               validator: ScheduleConflictValidator) -> bool:
    """Try to allocate mandatory shared ice ignoring preferences."""
    team_info = team_data["info"]
    
    # Find compatible partners
    compatible_partners = []
    for other_name, other_data in teams_needing_slots.items():
        if (other_name != team_name and 
            other_data["needed"] > 0 and
            can_teams_share_ice(team_info, other_data["info"], team_name, other_name)):
            compatible_partners.append((other_name, other_data))
    
    if not compatible_partners:
        return False
    
    # Try any available block that works for both teams
    for partner_name, partner_data in compatible_partners:
        partner_info = partner_data["info"]
        
        for block in available_blocks:
            if (is_block_available_for_team(block, team_info, team_data, rules_data, start_date) and
                is_block_available_for_team(block, partner_info, partner_data, rules_data, start_date)):
                
                if book_shared_practice(team_name, partner_name, team_data, partner_data, 
                                      block, start_date, schedule, validator):
                    print(f"    SHARED (no prefs): {team_name} + {partner_name}")
                    return True
    
    return False


# =============================================================================
# SECTION 10: PHASE ALLOCATION FUNCTIONS
# =============================================================================

def allocate_smart_minimum_guarantee(teams_needing_slots: Dict, available_blocks: List[AvailableBlock],
                                   start_date: datetime.date, schedule: List[Dict],
                                   rules_data: Dict, validator: ScheduleConflictValidator) -> int:
    """
    PHASE 0: Smart Minimum Guarantee with enhanced shared ice support.
    """
    allocated_count = 0
    
    print("\n" + "="*80)
    print("PHASE 0: SMART MINIMUM GUARANTEE ALLOCATION")
    print("="*80)
    print("Strategy: Everyone gets 1+ session, enhanced shared ice, consecutive sessions allowed")
    
    # Sort teams by constraint complexity (most constrained first)
    teams_by_complexity = []
    for team_name, team_data in teams_needing_slots.items():
        if team_data["needed"] > 0:
            complexity = calculate_constraint_complexity(team_data["info"], team_name)
            teams_by_complexity.append((complexity, team_name, team_data))
    
    teams_by_complexity.sort(reverse=True)
    
    print(f"Processing {len(teams_by_complexity)} teams needing ice (by constraint complexity)")
    
    for complexity, team_name, team_data in teams_by_complexity:
        team_info = team_data["info"]
        
        if team_data["needed"] <= 0:
            continue
        
        print(f"\n--- {team_name} (complexity: {complexity}, needs: {team_data['needed']}) ---")
        
        allocated = False
        
        # STRATEGY 1: Try optimal allocation
        if has_mandatory_shared_ice(team_info):
            print(f"  Trying mandatory shared ice...")
            allocated = try_mandatory_shared_with_preferences(team_name, team_data, teams_needing_slots,
                                                             available_blocks, start_date, schedule, 
                                                             rules_data, validator)
        elif has_strict_preferences(team_info):
            print(f"  Trying strict preference allocation...")
            allocated = try_strict_preference_allocation(team_name, team_data, available_blocks, 
                                                       start_date, schedule, rules_data, validator)
        else:
            print(f"  Trying preferred time allocation...")
            allocated = try_preferred_time_allocation(team_name, team_data, teams_needing_slots,
                                                    available_blocks, start_date, schedule, 
                                                    rules_data, validator)
        
        if allocated:
            allocated_count += 1
            print(f"  SUCCESS: Optimal allocation achieved")
            continue
        
        # STRATEGY 2: Try relaxed allocation
        print(f"  Optimal failed, trying relaxed allocation...")
        if has_mandatory_shared_ice(team_info):
            allocated = try_mandatory_shared_relaxed(team_name, team_data, teams_needing_slots,
                                                   available_blocks, start_date, schedule, 
                                                   rules_data, validator)
        else:
            allocated = try_any_preference_allocation(team_name, team_data, teams_needing_slots,
                                                    available_blocks, start_date, schedule, 
                                                    rules_data, validator)
        
        if allocated:
            allocated_count += 1
            print(f"  SUCCESS: Relaxed allocation achieved")
            continue
        
        # STRATEGY 3: Force any available allocation
        print(f"  Relaxed failed, forcing any available slot...")
        allocated = force_any_available_allocation(team_name, team_data, teams_needing_slots,
                                                 available_blocks, start_date, schedule, 
                                                 rules_data, validator)
        
        if allocated:
            allocated_count += 1
            print(f"  SUCCESS: Minimum guarantee met")
        else:
            print(f"  FAILED: No available slots found")
    
    print(f"\nPHASE 0 COMPLETE: {allocated_count} minimum guarantee allocations")
    print("="*80)
    return allocated_count


def allocate_preference_optimization(teams_needing_slots: Dict, available_blocks: List[AvailableBlock],
                                   start_date: datetime.date, schedule: List[Dict],
                                   rules_data: Dict, validator: ScheduleConflictValidator) -> int:
    """
    PHASE 1: Enhanced Preference Optimization with aggressive shared ice usage.
    """
    allocated_count = 0
    
    print("\n" + "="*80)
    print("PHASE 1: PREFERENCE OPTIMIZATION ALLOCATION (ENHANCED)")
    print("="*80)
    print("Strategy: Preferences + aggressive shared ice usage for full allocation")
    
    max_iterations = 30
    iteration = 0
    
    while iteration < max_iterations:
        iteration += 1
        progress_made = False
        
        # Get teams still needing slots, sorted by priority
        teams_needing = []
        for team_name, team_data in teams_needing_slots.items():
            if team_data["needed"] > 0:
                priority = calculate_team_priority(team_data["info"], team_name)
                # Boost priority for teams missing 2+ sessions
                if team_data["needed"] >= 2:
                    priority -= 50
                teams_needing.append((priority, team_name, team_data))
        
        if not teams_needing:
            print(f"All teams satisfied after {iteration-1} iterations")
            break
        
        teams_needing.sort()
        
        print(f"\nIteration {iteration}: {len(teams_needing)} teams need more sessions")
        
        # Round robin: only one allocation per iteration
        allocation_made_this_iteration = False
        
        # Strategy 1: Try shared ice for ANY team that allows it
        for priority, team_name, team_data in teams_needing:
            if team_data["needed"] <= 0 or allocation_made_this_iteration:
                continue
            
            if try_shared_ice_for_any_team(team_name, team_data, teams_needing_slots,
                                         available_blocks, start_date, schedule, 
                                         rules_data, validator, "preference shared"):
                allocated_count += 1
                progress_made = True
                allocation_made_this_iteration = True
                print(f"  ENHANCED SHARED ICE: {team_name}")
                break
        
        if allocation_made_this_iteration:
            continue
        
        # Strategy 2: Try individual allocations with distribution awareness
        for priority, team_name, team_data in teams_needing:
            if team_data["needed"] <= 0 or allocation_made_this_iteration:
                continue
            
            team_info = team_data["info"]
            individual_blocks = [block for block in available_blocks 
                               if is_block_available_for_team(block, team_info, team_data, rules_data, start_date)]
            
            if individual_blocks:
                best_block = find_best_block_with_distribution(individual_blocks, team_info, team_data, rules_data, start_date)
                if best_block and book_team_practice(team_name, team_data, best_block, start_date, schedule, validator, "relaxed"):
                    allocated_count += 1
                    progress_made = True
                    allocation_made_this_iteration = True
                    print(f"  ANY AVAILABLE: {team_name}")
                    break
        
        if not progress_made:
            print(f"  No progress in iteration {iteration}, stopping")
            break
    
    print(f"\nPHASE 1 ENHANCED COMPLETE: {allocated_count} allocations")
    print("="*80)
    return allocated_count


def allocate_capacity_maximization(teams_needing_slots: Dict, available_blocks: List[AvailableBlock],
                                 start_date: datetime.date, schedule: List[Dict],
                                 rules_data: Dict, validator: ScheduleConflictValidator) -> int:
    """
    PHASE 2: Capacity Maximization with consecutive session rules.
    """
    allocated_count = 0
    
    print("\n" + "="*80)
    print("PHASE 2: CAPACITY MAXIMIZATION")
    print("="*80)
    print("Strategy: Fill remaining slots, allow consecutive sessions")
    
    max_iterations = 15
    iteration = 0
    
    while iteration < max_iterations:
        iteration += 1
        progress_made = False
        
        # Get all teams that could use more ice
        teams_wanting_more = []
        for team_name, team_data in teams_needing_slots.items():
            if team_data["needed"] > 0:
                priority = 0
                teams_wanting_more.append((priority, team_name, team_data))
            else:
                # Teams that are satisfied but could take extra ice
                team_type = team_data["info"].get("type")
                team_age = team_data["info"].get("age")
                max_per_week = (rules_data.get("ice_times_per_week", {})
                               .get(team_type, {}).get(team_age, 0))
                
                total_weeks = max(1, len(team_data["weekly_count"]))
                for week_num in range(1, total_weeks + 1):
                    if team_data["weekly_count"][week_num] < max_per_week:
                        priority = 100
                        teams_wanting_more.append((priority, team_name, team_data))
                        break
        
        if not teams_wanting_more:
            print(f"No teams want more ice after {iteration-1} iterations")
            break
        
        teams_wanting_more.sort()
        
        print(f"\nIteration {iteration}: {len(teams_wanting_more)} teams want more ice")
        
        allocation_made = False
        
        # Try to fill any remaining capacity
        for priority, team_name, team_data in teams_wanting_more:
            if allocation_made:
                break
                
            team_info = team_data["info"]
            
            # Try shared ice first
            if team_info.get("allow_shared_ice", True):
                if try_shared_ice_for_any_team(team_name, team_data, teams_needing_slots,
                                             available_blocks, start_date, schedule, 
                                             rules_data, validator, "capacity shared"):
                    allocated_count += 1
                    progress_made = True
                    allocation_made = True
                    print(f"  CAPACITY SHARED: {team_name}")
                    break
            
            # Try individual allocation
            individual_blocks = [block for block in available_blocks 
                               if is_block_available_for_team(block, team_info, team_data, rules_data, start_date)]
            
            if individual_blocks:
                best_block = find_best_block_with_distribution(individual_blocks, team_info, team_data, rules_data, start_date)
                if best_block and book_team_practice(team_name, team_data, best_block, start_date, schedule, validator, "capacity fill"):
                    allocated_count += 1
                    progress_made = True
                    allocation_made = True
                    print(f"  CAPACITY INDIVIDUAL: {team_name}")
                    
                    if best_block.remaining_minutes() < 30:
                        available_blocks.remove(best_block)
                    break
        
        if not progress_made:
            print(f"  No progress in iteration {iteration}, stopping")
            break
    
    print(f"\nPHASE 2 COMPLETE: {allocated_count} capacity maximization allocations")
    print("="*80)
    return allocated_count


def allocate_maximum_utilization(teams_needing_slots: Dict, available_blocks: List[AvailableBlock],
                               start_date: datetime.date, schedule: List[Dict],
                               rules_data: Dict, validator: ScheduleConflictValidator) -> int:
    """
    PHASE 3: Maximum Utilization - Fill every remaining minute of ice.
    Ignores quotas, preferences, and distribution - just fills ice.
    """
    allocated_count = 0
    
    print("\n" + "="*80)
    print("PHASE 3: MAXIMUM UTILIZATION")
    print("="*80)
    print("Strategy: Fill every remaining minute - preferences ignored, maximum ice usage")
    
    iteration = 0
    while any(block.remaining_minutes() >= 60 for block in available_blocks) and iteration < 50:
        iteration += 1
        progress_made = False
        
        # Sort blocks by remaining time (most remaining first)
        blocks_with_time = [b for b in available_blocks if b.remaining_minutes() >= 60]
        blocks_with_time.sort(key=lambda b: b.remaining_minutes(), reverse=True)
        
        print(f"\nUtilization Iteration {iteration}: {len(blocks_with_time)} blocks with 60+ minutes remaining")
        
        for block in blocks_with_time:
            remaining = block.remaining_minutes()
            
            # Find ANY team that can physically use this block (ignore quotas)
            for team_name, team_data in teams_needing_slots.items():
                team_info = team_data["info"]
                
                # Only check essential constraints (blackouts, same-day limits)
                if (not has_blackout_on_date(team_info, block.date) and
                    not block_would_exceed_daily_limit(team_name, team_data, block, schedule)):
                    
                    # Use ALL remaining time in block (with minimum 60 minutes)
                    duration_to_use = max(60, remaining)
                    
                    if book_extended_practice(team_name, team_data, block, duration_to_use, 
                                            start_date, schedule, validator):
                        allocated_count += 1
                        progress_made = True
                        new_remaining = block.remaining_minutes()
                        print(f"  UTILIZATION: {team_name} gets {duration_to_use}min (block now has {new_remaining}min remaining)")
                        break
            
            if progress_made:
                break
        
        if not progress_made:
            print(f"  No more teams can use remaining ice")
            break
    
    # Report remaining unused ice
    total_unused = sum(block.remaining_minutes() for block in available_blocks)
    print(f"\nFinal unused ice time: {total_unused} minutes across {len(available_blocks)} blocks")
    
    print(f"\nPHASE 3 COMPLETE: {allocated_count} utilization allocations")
    print("="*80)
    return allocated_count


# =============================================================================
# SECTION 11: VALIDATION FUNCTIONS
# =============================================================================

def validate_consecutive_sessions(schedule: List[Dict]) -> List[str]:
    """Validate that all teams with 2+ sessions on same day have consecutive sessions."""
    violations = []
    
    # Group sessions by team and date
    team_date_sessions = defaultdict(list)
    for event in schedule:
        team = event.get("team")
        date = event.get("date")
        time_slot = event.get("time_slot")
        
        if team and date and time_slot:
            team_date_sessions[(team, date)].append(time_slot)
            
        # Also check shared practice opponent
        if event.get("type") == "shared practice":
            opponent = event.get("opponent")
            if opponent and opponent not in ("Practice", "TBD"):
                team_date_sessions[(opponent, date)].append(time_slot)
    
    # Check each team-date combination with 2+ sessions
    for (team, date), time_slots in team_date_sessions.items():
        if len(time_slots) > 3:
            violations.append(f"{team} has {len(time_slots)} sessions on {date}: {time_slots}")
        elif len(time_slots) == 2:
            # Check if consecutive
            try:
                times = []
                for slot in time_slots:
                    start_str, end_str = slot.split("-")
                    start_time = datetime.datetime.strptime(start_str, "%H:%M").time()
                    end_time = datetime.datetime.strptime(end_str, "%H:%M").time()
                    times.append((start_time, end_time))
                
                times.sort()
                
                # Check if first session's end time equals second session's start time
                if times[0][1] != times[1][0]:
                    violations.append(f"{team} has non-consecutive sessions on {date}: {time_slots}")
                    
            except Exception as e:
                violations.append(f"{team} has unparseable time slots on {date}: {time_slots} ({e})")
    
    return violations


def clean_schedule_duplicates(schedule: List[Dict]) -> List[Dict]:
    """Remove exact duplicate entries from the schedule."""
    seen = set()
    cleaned = []
    
    for entry in schedule:
        key = (
            entry.get("team", ""),
            entry.get("opponent", ""),
            entry.get("arena", ""),
            entry.get("date", ""),
            entry.get("time_slot", ""),
            entry.get("type", "")
        )
        
        if key not in seen:
            seen.add(key)
            cleaned.append(entry)
    
    return cleaned


# =============================================================================
# SECTION 12: MAIN SCHEDULER FUNCTION
# =============================================================================

def generate_schedule_enhanced_FIXED(
    season_dates: Tuple[datetime.date, datetime.date],
    teams_data: Dict,
    arenas_data: Dict,
    rules_data: Dict,
):
    """
    MAXIMUM UTILIZATION HOCKEY SCHEDULER:
    
    Phase 0: Smart Minimum Guarantee - Everyone gets 1+ session, enhanced shared ice support
    Phase 1: Preference Optimization - Aggressive shared ice usage for full allocation  
    Phase 2: Capacity Maximization - Fill remaining slots with consecutive session rules
    Phase 3: Maximum Utilization - Fill every remaining minute of ice time
    
    Key features:
    1. Maximum 2 sessions per day per team (3 in utilization phase)
    2. If 2+ sessions on same day, they MUST be consecutive
    3. Enhanced shared ice for ALL teams that allow it (not just mandatory)
    4. Prioritize teams missing 2+ sessions for shared ice partnerships
    5. Extended sessions to use all remaining ice time
    6. No ice time is wasted
    """
    
    print("=== MAXIMUM UTILIZATION HOCKEY SCHEDULER ===")
    print("Strategy: Full allocation + enhanced shared ice + maximum utilization")
    
    # Initialize
    validator = ScheduleConflictValidator()
    start_date, end_date = season_dates
    teams_data = {k: normalize_team_info(v) for k, v in (teams_data or {}).items()}
    schedule = []
    available_blocks = []

    # Generate all available blocks
    for arena, blocks in arenas_data.items():
        for block in blocks:
            block_start = max(_parse_date(block["start"]), start_date)
            block_end = min(_parse_date(block["end"]), end_date)
            if block_start > block_end:
                continue
                
            current_date = block_start
            while current_date <= block_end:
                weekday_index = str(current_date.weekday())
                if weekday_index in block.get("slots", {}):
                    for slot in block["slots"][weekday_index]:
                        try:
                            start_time = datetime.datetime.strptime(slot["time"].split("-")[0], "%H:%M").time()
                            end_time = datetime.datetime.strptime(slot["time"].split("-")[1], "%H:%M").time()
                            weekday = current_date.weekday()

                            team_name = slot.get("team") or slot.get("pre_assigned_team")
                            if team_name:
                                team_info = teams_data.get(team_name, {})
                                slot_type = slot.get("type")

                                if slot_type == "game" or (not slot_type and team_info.get("game_duration")):
                                    game_duration = slot.get("duration", team_info.get("game_duration", 60))
                                    game_end_dt = datetime.datetime.combine(current_date, start_time) + datetime.timedelta(minutes=game_duration)
                                    game_end = game_end_dt.time()

                                    opponent = slot.get("opponent") or slot.get("pre_assigned_opponent", "TBD")
                                    schedule.append({
                                        "team": team_name,
                                        "opponent": opponent,
                                        "arena": arena,
                                        "date": current_date.isoformat(),
                                        "time_slot": f"{start_time.strftime('%H:%M')}-{game_end.strftime('%H:%M')}",
                                        "type": "game",
                                    })

                                    if game_end < end_time:
                                        available_blocks.append(AvailableBlock(
                                            arena=arena,
                                            date=current_date,
                                            start_time=game_end,
                                            end_time=end_time,
                                            weekday=weekday,
                                            slot_type="practice"
                                        ))
                                else:
                                    schedule.append({
                                        "team": team_name,
                                        "opponent": "Practice",
                                        "arena": arena,
                                        "date": current_date.isoformat(),
                                        "time_slot": f"{start_time.strftime('%H:%M')}-{end_time.strftime('%H:%M')}",
                                        "type": "practice",
                                    })
                            else:
                                available_blocks.append(AvailableBlock(
                                    arena=arena,
                                    date=current_date,
                                    start_time=start_time,
                                    end_time=end_time,
                                    weekday=weekday,
                                    slot_type="practice"
                                ))

                        except Exception as e:
                            print(f"Skipping invalid slot in {arena}: {slot} ({e})")
                current_date += datetime.timedelta(days=1)

    # Build team needs
    teams_needing_slots = {}
    total_weeks = max(1, (end_date - start_date).days // 7)
    
    for team_name, team_info in teams_data.items():
        team_type = team_info.get("type")
        team_age = team_info.get("age")
        expected_per_week = (rules_data.get("ice_times_per_week", {})
                           .get(team_type, {}).get(team_age, 0))
        needed_total = expected_per_week * total_weeks
        
        existing_count = sum(1 for event in schedule 
                           if (event.get("team") == team_name or 
                               (event.get("type") == "shared practice" and event.get("opponent") == team_name)))
        
        teams_needing_slots[team_name] = {
            "info": team_info,
            "needed": max(0, needed_total - existing_count),
            "weekly_count": defaultdict(int),
            "scheduled_dates": set(),
            "expected_per_week": expected_per_week,
            "total_target": needed_total,
            "allocation_priority": calculate_team_priority(team_info, team_name),
        }

    # Update scheduled dates and weekly counts for existing schedule
    for event in schedule:
        team = event.get("team")
        opponent = event.get("opponent")
        date_str = event.get("date")
        
        if date_str:
            try:
                event_date = _parse_date(date_str)
                week_num = get_week_number(event_date, start_date)
                
                if team in teams_needing_slots:
                    teams_needing_slots[team]["scheduled_dates"].add(event_date)
                    teams_needing_slots[team]["weekly_count"][week_num] += 1
                    
                if (event.get("type") == "shared practice" and 
                    opponent in teams_needing_slots and 
                    opponent not in ("Practice", "TBD")):
                    teams_needing_slots[opponent]["scheduled_dates"].add(event_date)
                    teams_needing_slots[opponent]["weekly_count"][week_num] += 1
            except:
                continue

    # Calculate initial metrics
    total_supply_hours = sum(block.duration_minutes() for block in available_blocks) // 60
    remaining_demand = sum(t["needed"] for t in teams_needing_slots.values())
    
    print(f"ANALYSIS: Demand: {remaining_demand} sessions, Supply: ~{total_supply_hours} hours")
    print(f"Available blocks: {len(available_blocks)}")
    
    # Show constraint complexity
    teams_with_constraints = []
    for team_name, team_data in teams_needing_slots.items():
        if team_data["needed"] > 0:
            complexity = calculate_constraint_complexity(team_data["info"], team_name)
            mandatory_shared = has_mandatory_shared_ice(team_data["info"])
            strict_prefs = has_strict_preferences(team_data["info"])
            allow_shared = team_data["info"].get("allow_shared_ice", True)
            teams_with_constraints.append((complexity, team_name, mandatory_shared, strict_prefs, allow_shared))
    
    teams_with_constraints.sort(reverse=True)
    print(f"Teams by constraint complexity:")
    for complexity, team_name, mandatory, strict, allow_shared in teams_with_constraints[:5]:
        flags = []
        if mandatory: flags.append("mandatory_shared")
        if strict: flags.append("strict_prefs")
        if allow_shared: flags.append("allows_shared")
        print(f"  {team_name}: {complexity} ({', '.join(flags) if flags else 'no_sharing'})")

    # 4-PHASE MAXIMUM UTILIZATION STRATEGY
    print("\n=== 4-PHASE MAXIMUM UTILIZATION STRATEGY ===")
    
    # PHASE 0: SMART MINIMUM GUARANTEE
    phase0_allocated = allocate_smart_minimum_guarantee(
        teams_needing_slots, available_blocks, start_date, schedule, rules_data, validator
    )
    
    # PHASE 1: PREFERENCE OPTIMIZATION
    phase1_allocated = allocate_preference_optimization(
        teams_needing_slots, available_blocks, start_date, schedule, rules_data, validator
    )
    
    # PHASE 2: CAPACITY MAXIMIZATION
    phase2_allocated = allocate_capacity_maximization(
        teams_needing_slots, available_blocks, start_date, schedule, rules_data, validator
    )
    
    # PHASE 3: MAXIMUM UTILIZATION (NEW)
    phase3_allocated = allocate_maximum_utilization(
        teams_needing_slots, available_blocks, start_date, schedule, rules_data, validator
    )

    # Generate final analysis
    print("\n=== FINAL ANALYSIS ===")
    total_allocated = 0
    total_target = 0
    underallocated = []
    zero_allocations = []
    perfect_allocations = []
    consecutive_violations = []
    
    for team_name, team_data in teams_needing_slots.items():
        target = team_data["total_target"]
        allocated = target - team_data["needed"]
        total_allocated += allocated
        total_target += target
        
        percentage = (allocated / target * 100) if target > 0 else 100
        
        if allocated == 0:
            zero_allocations.append(team_name)
        elif allocated == target:
            perfect_allocations.append(team_name)
        elif team_data["needed"] > 0:
            underallocated.append((team_name, allocated, target, team_data["needed"]))
        
        print(f"{team_name}: {allocated}/{target} ({percentage:.1f}%)")
    
    overall_percentage = (total_allocated / total_target * 100) if total_target > 0 else 100
    print(f"\nOVERALL ALLOCATION: {total_allocated}/{total_target} ({overall_percentage:.1f}%)")
    
    print(f"\nPhase Results:")
    print(f"  Phase 0 (Smart Minimum): {phase0_allocated} sessions")
    print(f"  Phase 1 (Preference Optimization): {phase1_allocated} sessions")
    print(f"  Phase 2 (Capacity Maximization): {phase2_allocated} sessions")
    print(f"  Phase 3 (Maximum Utilization): {phase3_allocated} sessions")
    print(f"  Total: {phase0_allocated + phase1_allocated + phase2_allocated + phase3_allocated} sessions")
    
    # Validate consecutive sessions
    consecutive_violations = validate_consecutive_sessions(schedule)
    if consecutive_violations:
        print(f"\n⚠️  CONSECUTIVE SESSION VIOLATIONS ({len(consecutive_violations)}):")
        for violation in consecutive_violations:
            print(f"  {violation}")
    else:
        print(f"\n✅ CONSECUTIVE SESSION VALIDATION: All multi-session days are consecutive")
    
    # Ice utilization analysis
    total_available_minutes = sum(block.duration_minutes() for block in available_blocks)
    total_unused_minutes = sum(block.remaining_minutes() for block in available_blocks)
    utilization_percentage = ((total_available_minutes - total_unused_minutes) / total_available_minutes * 100) if total_available_minutes > 0 else 0
    
    print(f"\nICE UTILIZATION ANALYSIS:")
    print(f"  Total available ice: {total_available_minutes} minutes ({total_available_minutes//60:.1f} hours)")
    print(f"  Ice time used: {total_available_minutes - total_unused_minutes} minutes ({(total_available_minutes - total_unused_minutes)//60:.1f} hours)")
    print(f"  Ice time unused: {total_unused_minutes} minutes ({total_unused_minutes//60:.1f} hours)")
    print(f"  Utilization rate: {utilization_percentage:.1f}%")
    
    # Allocation categories
    if perfect_allocations:
        print(f"\nPERFECT ALLOCATIONS ({len(perfect_allocations)}):")
        for team in perfect_allocations:
            print(f"  {team}")
    
    if zero_allocations:
        print(f"\nZERO ALLOCATIONS ({len(zero_allocations)}) - NEEDS INVESTIGATION:")
        for team in zero_allocations:
            team_info = teams_needing_slots[team]["info"]
            blackouts = len(team_info.get("blackout_dates", []))
            allows_shared = team_info.get("allow_shared_ice", True)
            print(f"  {team} (blackouts: {blackouts}, allows_shared: {allows_shared})")
    
    if underallocated:
        print(f"\nUNDERALLOCATED TEAMS ({len(underallocated)}):")
        for team, allocated, target, remaining in sorted(underallocated, key=lambda x: x[3], reverse=True):
            team_info = teams_needing_slots[team]["info"]
            allows_shared = team_info.get("allow_shared_ice", True)
            blackouts = len(team_info.get("blackout_dates", []))
            print(f"  {team}: {allocated}/{target} (missing {remaining}) - shared_ice: {allows_shared}, blackouts: {blackouts}")

    # Analyze shared ice success
    shared_sessions = [event for event in schedule if event.get("type") == "shared practice"]
    teams_with_shared_ice = set()
    teams_allowing_shared = [name for name, data in teams_needing_slots.items() 
                           if data["info"].get("allow_shared_ice", True)]
    
    for event in shared_sessions:
        teams_with_shared_ice.add(event.get("team"))
        opponent = event.get("opponent")
        if opponent and opponent not in ("Practice", "TBD"):
            teams_with_shared_ice.add(opponent)
    
    print(f"\nSHARED ICE ANALYSIS:")
    print(f"  Total shared sessions: {len(shared_sessions)}")
    print(f"  Teams allowing shared ice: {len(teams_allowing_shared)}")
    print(f"  Teams that got shared ice: {len(teams_with_shared_ice)}")
    print(f"  Shared ice utilization: {len(teams_with_shared_ice)}/{len(teams_allowing_shared)} ({len(teams_with_shared_ice)/max(1,len(teams_allowing_shared))*100:.1f}%)")
    
    # Show specific shared ice examples
    if shared_sessions:
        print(f"  Sample shared sessions:")
        for i, session in enumerate(shared_sessions[:3]):
            team1 = session.get("team")
            team2 = session.get("opponent")
            date = session.get("date")
            time = session.get("time_slot")
            print(f"    {team1} + {team2} on {date} at {time}")
        if len(shared_sessions) > 3:
            print(f"    ... and {len(shared_sessions) - 3} more")

    # Final success assessment
    if utilization_percentage >= 95:
        print("\n✅ EXCELLENT: Maximum utilization achieved - minimal ice waste")
    elif utilization_percentage >= 85:
        print("\n✅ SUCCESS: High utilization achieved - most ice time used")
    elif utilization_percentage >= 75:
        print("\n⚠️  GOOD: Reasonable utilization - some ice time unused")
    else:
        print("\n❌ POOR: Low utilization - significant ice time wasted")
    
    if len(underallocated) <= 2 and all(remaining <= 1 for _, _, _, remaining in underallocated):
        print("✅ ALLOCATION SUCCESS: All teams received required ice with minimal shortfalls")
    elif len(underallocated) <= 5:
        print("⚠️  PARTIAL SUCCESS: Most teams allocated, some minor shortfalls remain")
    else:
        print("❌ ALLOCATION ISSUES: Multiple teams significantly under-allocated")
    
    # Clean and validate final schedule
    schedule = clean_schedule_duplicates(schedule)
    
    return {
        "schedule": schedule, 
        "phase0_allocated": phase0_allocated, 
        "phase1_allocated": phase1_allocated,
        "phase2_allocated": phase2_allocated,
        "phase3_allocated": phase3_allocated,
        "zero_allocations": zero_allocations,
        "perfect_allocations": perfect_allocations,
        "underallocated": underallocated,
        "consecutive_violations": consecutive_violations,
        "shared_sessions_count": len(shared_sessions),
        "teams_with_shared_ice": len(teams_with_shared_ice),
        "ice_utilization_percentage": utilization_percentage,
        "total_unused_minutes": total_unused_minutes
    }


# =============================================================================
# SECTION 13: BACKWARD COMPATIBILITY & MAIN INTERFACE
# =============================================================================

def generate_schedule(*args, **kwargs):
    """Main interface for the maximum utilization hockey scheduler."""
    return generate_schedule_enhanced_FIXED(*args, **kwargs)


def generate_schedule_enhanced(*args, **kwargs):
    """Legacy function name compatibility."""
    return generate_schedule_enhanced_FIXED(*args, **kwargs)


if __name__ == "__main__":
    print("Maximum Utilization Hockey Scheduler")
    print("Key features:")
    print("✅ Maximum 2 sessions per day, must be consecutive (3 max in utilization phase)")
    print("✅ Enhanced shared ice for ALL teams that allow it")  
    print("✅ Priority matching based on need and preferences")
    print("✅ Extended sessions to use all remaining ice time")
    print("✅ 4-phase allocation for maximum utilization")
    print("✅ Comprehensive ice usage analysis")
    