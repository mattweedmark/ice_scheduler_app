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
    
    def parse_time_slot(self, time_slot: str) -> Tuple[datetime.time, datetime.time]:
        """Parse time slot string into start and end times."""
        try:
            start_str, end_str = time_slot.split("-")
            start_time = datetime.datetime.strptime(start_str.strip(), "%H:%M").time()
            end_time = datetime.datetime.strptime(end_str.strip(), "%H:%M").time()
            return start_time, end_time
        except (ValueError, AttributeError):
            return datetime.time(0, 0), datetime.time(0, 0)
    
    def are_consecutive_times(self, time1: str, time2: str) -> bool:
        """Check if two time slots are consecutive."""
        start1, end1 = self.parse_time_slot(time1)
        start2, end2 = self.parse_time_slot(time2)
        return end1 == start2 or end2 == start1
    
    def count_consecutive_bookings(self, team: str, date: str, new_time_slot: str) -> int:
        """Count how many consecutive bookings this would create for a team on a date."""
        if team not in self.team_bookings:
            return 1
        
        same_day_bookings = [(d, t, a) for d, t, a in self.team_bookings[team] if d == date]
        if not same_day_bookings:
            return 1
        
        same_day_bookings.sort(key=lambda x: self.parse_time_slot(x[1])[0])
        consecutive_count = 1
        current_slot = new_time_slot
        
        # Check backwards for consecutive slots
        for _, existing_slot, _ in reversed(same_day_bookings):
            if self.are_consecutive_times(existing_slot, current_slot):
                consecutive_count += 1
                current_slot = existing_slot
            else:
                break
        
        # Check forwards for consecutive slots
        current_slot = new_time_slot
        for _, existing_slot, _ in same_day_bookings:
            if self.are_consecutive_times(current_slot, existing_slot):
                consecutive_count += 1
                current_slot = existing_slot
            else:
                break
        
        return consecutive_count - 1  # Subtract 1 because we counted the new slot twice
    
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
        
        # Check 3: Consecutive time limit (max 2, allow 3 only in emergency)
        consecutive_count = self.count_consecutive_bookings(team, date, time_slot)
        if consecutive_count > 2:
            if not allow_force:
                conflicts.append(f"Team {team} would have {consecutive_count} consecutive slots on {date} (max 2 allowed)")
        
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
    
    def get_next_available_time(self) -> datetime.time:
        """Get the next available start time in this block"""
        used_minutes = sum(booking['duration'] for booking in self.bookings)
        start_dt = datetime.datetime.combine(datetime.date.min, self.start_time)
        next_available_dt = start_dt + datetime.timedelta(minutes=used_minutes)
        return next_available_dt.time()


# =============================================================================
# SECTION 2: UTILITY FUNCTIONS
# =============================================================================

def normalize_team_info(raw: dict) -> dict:
    """Convert legacy JSON structures into new scheduler format."""
    out = dict(raw or {})

    # Preferred days normalization
    pref = out.get("preferred_days_and_times", {})
    norm_pref = {}
    if isinstance(pref, dict):
        for day, val in pref.items():
            if day.endswith("_strict"):
                norm_pref[day] = val
                continue
                
            if isinstance(val, list):
                if len(val) >= 2:
                    norm_pref[day] = f"{val[0]}-{val[1]}"
                elif len(val) == 1:
                    t = str(val[0])
                    try:
                        hh, mm = [int(x) for x in t.split(":")]
                        end_hh, end_mm = hh, mm + 60
                        if end_mm >= 60:
                            end_hh += end_mm // 60
                            end_mm = end_mm % 60
                        norm_pref[day] = f"{hh:02d}:{mm:02d}-{end_hh:02d}:{end_mm:02d}"
                    except Exception:
                        norm_pref[day] = f"{t}-{t}"
                else:
                    norm_pref[day] = ""
            else:
                norm_pref[day] = val
    out["preferred_days_and_times"] = norm_pref

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
        pass  # already in new format
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


def _safe_late_cutoff(team_info: dict):
    if team_info.get("late_ice_cutoff_enabled") and team_info.get("late_ice_cutoff_time"):
        return team_info.get("late_ice_cutoff_time")
    return team_info.get("late_ice_cutoff")


def _safe_allow_multiple(team_info: dict) -> bool:
    return bool(team_info.get("allow_multiple_per_day", False))


def get_week_number(date: datetime.date, start_date: datetime.date) -> int:
    """Calculate week number from start date."""
    days_diff = (date - start_date).days
    return (days_diff // 7) + 1


# =============================================================================
# SECTION 3: TEAM PROPERTY HELPERS
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


def has_mandatory_shared_ice(team_info: dict) -> bool:
    """Check if a team has mandatory shared ice enabled."""
    return bool(team_info.get("mandatory_shared_ice", False)) and bool(team_info.get("allow_shared_ice", True))


def calculate_team_priority(team_info: dict, team_name: str) -> int:
    """Calculate allocation priority for teams (lower = higher priority)."""
    priority = 0
    
    # Age priority (younger teams get higher priority)
    age = _get_age_numeric(team_info.get("age", ""))
    if age:
        priority += age
    else:
        priority += 50
    
    # Type priority
    team_type = team_info.get("type", "house")
    if team_type == "competitive":
        priority += 0
    else:
        priority += 10
    
    # Tier priority for competitive teams
    if team_type == "competitive":
        tier = _get_team_tier(team_name, team_info)
        tier_values = {"AA": 0, "A": 1, "BB": 2, "B": 3, "C": 4}
        priority += tier_values.get(tier, 5)
    
    # Mandatory shared ice gets highest priority
    if has_mandatory_shared_ice(team_info):
        priority -= 100
    
    # Strict preferences get additional priority boost
    if has_strict_preferences(team_info):
        priority -= 50
    
    return priority


def has_current_week_blackout(team_info: dict, current_week_dates: List[datetime.date]) -> bool:
    """Check if team has ANY blackout in the current week being scheduled"""
    blackout_dates = _safe_blackout_dates(team_info)
    for blackout_str in blackout_dates:
        try:
            blackout_date = _parse_date(blackout_str)
            if blackout_date in current_week_dates:
                return True
        except:
            continue
    return False


def count_current_week_blackouts(team_info: dict, current_week_dates: List[datetime.date]) -> int:
    """Count how many blackout dates are in the current week"""
    blackout_dates = _safe_blackout_dates(team_info)
    count = 0
    for blackout_str in blackout_dates:
        try:
            blackout_date = _parse_date(blackout_str)
            if blackout_date in current_week_dates:
                count += 1
        except:
            continue
    return count


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


def violates_late_cutoff(team_info: dict, block: AvailableBlock) -> bool:
    """Check if a block violates team's late cutoff time."""
    late_cutoff_str = _safe_late_cutoff(team_info)
    if late_cutoff_str:
        try:
            late_cutoff_time = datetime.datetime.strptime(late_cutoff_str, "%H:%M").time()
            if block.get_next_available_time() > late_cutoff_time:
                return True
        except Exception:
            pass
    return False


def can_team_have_multiple_per_day(team_info: dict, team_name: str) -> bool:
    """Check if team is eligible for multiple ice times per day (U13+ AA/A only)."""
    age = _get_age_numeric(team_info.get("age", ""))
    tier = _get_team_tier(team_name, team_info)
    
    return (age and age >= 13 and 
            team_info.get("type") == "competitive" and 
            tier in ["AA", "A"])


def team_has_session_on_date(team_data: dict, check_date: datetime.date) -> bool:
    """Check if team already has a session scheduled on a specific date."""
    return check_date in team_data.get("scheduled_dates", set())


# =============================================================================
# SECTION 4: ENHANCED AVAILABILITY CHECKING
# =============================================================================

def is_block_available_strict(block: AvailableBlock, team_info: Dict, team_data: Dict, 
                             rules_data: Dict, start_date: datetime.date) -> bool:
    """Strict availability check that enforces all constraints."""
    required_duration = team_info.get("practice_duration", 60)
    if not block.can_fit_duration(required_duration):
        return False
    
    # Blackout check
    if has_blackout_on_date(team_info, block.date):
        return False
    
    # Weekly quota check
    week_num = get_week_number(block.date, start_date)
    current_weekly_count = team_data["weekly_count"][week_num]
    
    team_type = team_info.get("type")
    team_age = team_info.get("age")
    max_per_week = (rules_data.get("ice_times_per_week", {})
                   .get(team_type, {}).get(team_age, 0))
    
    if current_weekly_count >= max_per_week:
        return False
    
    # STRICT multiple-per-day check
    allow_multiple = _safe_allow_multiple(team_info)
    if not allow_multiple and team_has_session_on_date(team_data, block.date):
        # Only allow if team is eligible for multiple sessions (U13+ AA/A)
        if not can_team_have_multiple_per_day(team_info, ""):
            return False
    
    # Late cutoff check
    if violates_late_cutoff(team_info, block):
        return False
    
    return True


def is_block_available_lenient(block: AvailableBlock, team_info: Dict, team_data: Dict, 
                              rules_data: Dict, start_date: datetime.date, 
                              current_week_dates: List[datetime.date]) -> bool:
    """Lenient availability check for guaranteed allocation mode."""
    required_duration = team_info.get("practice_duration", 60)
    if not block.can_fit_duration(required_duration):
        return False
    
    # ENHANCED BLACKOUT LOGIC: Only check current week, allow holding back max 1 session
    if has_blackout_on_date(team_info, block.date):
        # In current week, check how many blackouts vs how many sessions needed
        week_blackout_count = count_current_week_blackouts(team_info, current_week_dates)
        team_type = team_info.get("type")
        team_age = team_info.get("age")
        expected_weekly = (rules_data.get("ice_times_per_week", {})
                          .get(team_type, {}).get(team_age, 0))
        
        # Allow holding back max 1 session due to blackouts
        if week_blackout_count >= expected_weekly - 1:
            return False  # Too many blackouts this week
        # Otherwise, allow some blackout dates to be used if necessary
    
    # More lenient weekly quota check
    week_num = get_week_number(block.date, start_date)
    current_weekly_count = team_data["weekly_count"][week_num]
    
    team_type = team_info.get("type")
    team_age = team_info.get("age")
    max_per_week = (rules_data.get("ice_times_per_week", {})
                   .get(team_type, {}).get(team_age, 0))
    
    # Allow up to 150% of quota if needed for guaranteed allocation
    if current_weekly_count >= max_per_week * 1.5:
        return False
    
    # More lenient multiple-per-day check (still enforce for most teams)
    allow_multiple = _safe_allow_multiple(team_info)
    if not allow_multiple and team_has_session_on_date(team_data, block.date):
        if not can_team_have_multiple_per_day(team_info, ""):
            return False
    
    # Late cutoff check (keep this)
    if violates_late_cutoff(team_info, block):
        return False
    
    return True


# =============================================================================
# SECTION 5: ENHANCED SHARING LOGIC
# =============================================================================

def can_teams_share_ice_enhanced(team1_info: dict, team2_info: dict, team1_name: str = "", 
                                team2_name: str = "", emergency_mode: bool = False) -> tuple:
    """Enhanced shared ice compatibility for guaranteed allocation."""
    age1 = _get_age_numeric(team1_info.get("age", ""))
    age2 = _get_age_numeric(team2_info.get("age", ""))
    type1 = team1_info.get("type", "house")
    type2 = team2_info.get("type", "house")
    
    if age1 is None or age2 is None:
        return False, 999
    
    age_diff = abs(age1 - age2)
    
    # Check if both teams allow sharing
    allow1 = team1_info.get("allow_shared_ice", True)
    allow2 = team2_info.get("allow_shared_ice", True)
    
    # In emergency mode, override individual preferences if necessary
    if emergency_mode:
        allow1 = True
        allow2 = True
    elif not allow1 or not allow2:
        return False, 999
    
    # More lenient age restrictions for guaranteed allocation
    max_age_diff = 4 if emergency_mode else 3  # Increased from 2/3
    if age_diff > max_age_diff:
        return False, 999
    
    # Prioritize mandatory shared ice combinations
    mandatory1 = has_mandatory_shared_ice(team1_info)
    mandatory2 = has_mandatory_shared_ice(team2_info)
    
    if mandatory1 and mandatory2:
        return True, 5 + age_diff
    elif mandatory1 or mandatory2:
        return True, 10 + age_diff
    
    # Emergency mode allows more combinations
    if emergency_mode:
        return True, 30 + age_diff
    
    # Same type gets priority
    if type1 == type2:
        return True, 20 + age_diff
    
    # Mixed house/competitive
    return True, 40 + age_diff


# =============================================================================
# SECTION 6: PREFERENCE MATCHING FUNCTIONS
# =============================================================================

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
            if "-" in value:
                start_str, end_str = value.split("-", 1)
                start_time = datetime.datetime.strptime(start_str.strip(), "%H:%M").time()
                end_time = datetime.datetime.strptime(end_str.strip(), "%H:%M").time()
                windows[day_name].append((start_time, end_time, is_strict))
        except (ValueError, AttributeError):
            continue
    
    return windows


def get_block_preference_score(block: AvailableBlock, team_info: dict) -> int:
    """Score block based on preferences with detailed scoring"""
    windows = _parse_preferred_windows(team_info)
    block_day = block.date.strftime("%A")
    
    if block_day not in windows:
        return 0
    
    best_score = 0
    for start_pref, end_pref, is_strict_window in windows[block_day]:
        # Check for overlap
        if block.start_time < end_pref and block.end_time > start_pref:
            if is_strict_window:
                # Calculate how much of the block overlaps with strict preference
                overlap_start = max(block.start_time, start_pref)
                overlap_end = min(block.end_time, end_pref)
                
                block_duration = (datetime.datetime.combine(datetime.date.min, block.end_time) - 
                                datetime.datetime.combine(datetime.date.min, block.start_time)).total_seconds()
                overlap_duration = (datetime.datetime.combine(datetime.date.min, overlap_end) - 
                                  datetime.datetime.combine(datetime.date.min, overlap_start)).total_seconds()
                
                if overlap_duration >= block_duration * 0.8:  # 80% overlap for strict match
                    return 100  # Perfect strict match
                elif overlap_duration >= block_duration * 0.5:  # 50% overlap
                    return 80   # Good strict match
                else:
                    return 60   # Partial strict match
            else:
                # Non-strict preference
                overlap_start = max(block.start_time, start_pref)
                overlap_end = min(block.end_time, end_pref)
                
                block_duration = (datetime.datetime.combine(datetime.date.min, block.end_time) - 
                                datetime.datetime.combine(datetime.date.min, block.start_time)).total_seconds()
                overlap_duration = (datetime.datetime.combine(datetime.date.min, overlap_end) - 
                                  datetime.datetime.combine(datetime.date.min, overlap_start)).total_seconds()
                
                if overlap_duration >= block_duration * 0.8:
                    best_score = max(best_score, 50)  # Good preferred match
                else:
                    best_score = max(best_score, 30)  # Partial preferred match
    
    return best_score


def find_exact_preference_blocks(team_info: dict, available_blocks: List[AvailableBlock]) -> List[AvailableBlock]:
    """Find blocks that exactly match team's strict preferences."""
    exact_matches = []
    windows = _parse_preferred_windows(team_info)
    
    for block in available_blocks:
        block_day = block.date.strftime("%A")
        
        if block_day in windows:
            for start_pref, end_pref, is_strict_window in windows[block_day]:
                if is_strict_window:
                    # Check if block exactly matches or contains the preferred time
                    if (block.start_time <= start_pref and block.end_time >= end_pref):
                        exact_matches.append(block)
                        break
    
    return exact_matches


# =============================================================================
# SECTION 7: ENHANCED BOOKING FUNCTIONS
# =============================================================================

def _book_team_practice_enhanced(team_name: str, team_data: dict, block: AvailableBlock, 
                               start_date: datetime.date, schedule: List[dict], 
                               validator: ScheduleConflictValidator, force_mode: bool = False) -> bool:
    """Enhanced booking with proper constraint checking."""
    required_duration = team_data["info"].get("practice_duration", 60)
    
    if not block.can_fit_duration(required_duration):
        return False
    
    # STRICT multiple-per-day check before booking
    if not force_mode:
        allow_multiple = _safe_allow_multiple(team_data["info"])
        if not allow_multiple and team_has_session_on_date(team_data, block.date):
            if not can_team_have_multiple_per_day(team_data["info"], team_name):
                print(f"DEBUG: Blocked {team_name} multiple session on {block.date} (allow_multiple_per_day=False)")
                return False
    
    # Calculate booking details
    remaining_after_booking = block.remaining_minutes() - required_duration
    actual_duration = required_duration
    
    if remaining_after_booking > 0 and remaining_after_booking < 60:
        if remaining_after_booking >= 15:
            actual_duration = required_duration + remaining_after_booking
    
    try:
        booking_start, booking_end = block.add_booking(team_name, actual_duration, "practice")
    except ValueError:
        return False
    
    # Validate the booking with force mode if needed
    date_str = block.date.isoformat()
    time_slot_str = f"{booking_start.strftime('%H:%M')}-{booking_end.strftime('%H:%M')}"
    
    is_valid, conflicts = validator.validate_booking(team_name, block.arena, date_str, time_slot_str, force_mode)
    
    if not is_valid and not force_mode:
        block.bookings.pop()  # Remove the booking we just added
        print(f"DEBUG: Booking validation failed for {team_name}: {conflicts}")
        return False
    
    # Booking is valid or forced, proceed
    booking = {
        "team": team_name,
        "opponent": "Practice",
        "arena": block.arena,
        "date": date_str,
        "time_slot": time_slot_str,
        "type": "practice"
    }
    
    # Update tracking
    week_num = get_week_number(block.date, start_date)
    schedule.append(booking)
    validator.add_booking(team_name, block.arena, date_str, time_slot_str)
    team_data["needed"] -= 1
    team_data["weekly_count"][week_num] += 1
    team_data["scheduled_dates"].add(block.date)
    
    if force_mode and conflicts:
        print(f"FORCED BOOKING: {team_name} at {block.arena} on {block.date} (conflicts overridden)")
    
    return True


def _book_shared_practice_enhanced(team1_name: str, team2_name: str, team1_data: dict, 
                                 team2_data: dict, block: AvailableBlock, start_date: datetime.date, 
                                 schedule: List[dict], validator: ScheduleConflictValidator, 
                                 force_mode: bool = False) -> bool:
    """Enhanced shared booking with proper constraint checking."""
    team1_duration = team1_data["info"].get("practice_duration", 60)
    team2_duration = team2_data["info"].get("practice_duration", 60)
    required_duration = max(team1_duration, team2_duration)
    
    if not block.can_fit_duration(required_duration):
        return False
    
    # STRICT multiple-per-day check for BOTH teams before booking
    if not force_mode:
        # Check team1
        allow_multiple1 = _safe_allow_multiple(team1_data["info"])
        if not allow_multiple1 and team_has_session_on_date(team1_data, block.date):
            if not can_team_have_multiple_per_day(team1_data["info"], team1_name):
                print(f"DEBUG: Blocked shared practice - {team1_name} multiple session on {block.date}")
                return False
        
        # Check team2
        allow_multiple2 = _safe_allow_multiple(team2_data["info"])
        if not allow_multiple2 and team_has_session_on_date(team2_data, block.date):
            if not can_team_have_multiple_per_day(team2_data["info"], team2_name):
                print(f"DEBUG: Blocked shared practice - {team2_name} multiple session on {block.date}")
                return False
    
    remaining_after_booking = block.remaining_minutes() - required_duration
    actual_duration = required_duration
    
    if remaining_after_booking > 0 and remaining_after_booking < 60:
        if remaining_after_booking >= 15:
            actual_duration = required_duration + remaining_after_booking
    
    try:
        booking_start, booking_end = block.add_booking(f"{team1_name} & {team2_name}", actual_duration, "shared practice")
    except ValueError:
        return False
    
    # Validate both teams with force mode if needed
    date_str = block.date.isoformat()
    time_slot_str = f"{booking_start.strftime('%H:%M')}-{booking_end.strftime('%H:%M')}"
    
    # Check team1
    is_valid1, conflicts1 = validator.validate_booking(team1_name, block.arena, date_str, time_slot_str, force_mode)
    if not is_valid1 and not force_mode:
        block.bookings.pop()
        print(f"DEBUG: Shared booking validation failed for {team1_name}: {conflicts1}")
        return False
    
    # Check team2
    is_valid2, conflicts2 = validator.validate_booking(team2_name, block.arena, date_str, time_slot_str, force_mode)
    if not is_valid2 and not force_mode:
        block.bookings.pop()
        print(f"DEBUG: Shared booking validation failed for {team2_name}: {conflicts2}")
        return False
    
    # Both teams valid or forced, proceed
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
    
    if force_mode and (conflicts1 or conflicts2):
        print(f"FORCED SHARED BOOKING: {team1_name} + {team2_name} at {block.arena} on {block.date}")
    
    return True


# =============================================================================
# SECTION 8: STRICT PREFERENCE ALLOCATION PHASES
# =============================================================================

def allocate_strict_preferences_first(teams_needing_slots: Dict, available_blocks: List[AvailableBlock],
                                     start_date: datetime.date, schedule: List[Dict],
                                     rules_data: Dict, validator: ScheduleConflictValidator) -> int:
    """
    PHASE 0: Strict preference allocation - runs FIRST to claim exact preference matches.
    This ensures teams with strict preferences get their exact requested times.
    """
    allocated_count = 0
    
    # Get teams with strict preferences
    strict_preference_teams = []
    for team_name, team_data in teams_needing_slots.items():
        team_info = team_data["info"]
        if team_data["needed"] > 0 and has_strict_preferences(team_info):
            strict_preference_teams.append((team_data["allocation_priority"], team_name, team_data))
    
    if not strict_preference_teams:
        print("PHASE 0: No teams with strict preferences")
        return 0
    
    strict_preference_teams.sort()  # Sort by priority
    
    print(f"PHASE 0 - STRICT PREFERENCES: {len(strict_preference_teams)} teams with strict preferences")
    
    for priority, team_name, team_data in strict_preference_teams:
        team_info = team_data["info"]
        
        # Find exact preference matches for this team
        exact_matches = find_exact_preference_blocks(team_info, available_blocks)
        
        if not exact_matches:
            print(f"  {team_name}: No exact preference matches found")
            continue
        
        # Sort exact matches by preference score (highest first)
        scored_matches = []
        for block in exact_matches:
            if is_block_available_strict(block, team_info, team_data, rules_data, start_date):
                score = get_block_preference_score(block, team_info)
                scored_matches.append((score, block))
        
        scored_matches.sort(reverse=True)
        
        # Allocate up to team's full quota using exact preference matches
        sessions_allocated = 0
        max_sessions = min(team_data["needed"], 2)  # Limit to prevent hogging
        
        for score, block in scored_matches:
            if sessions_allocated >= max_sessions or team_data["needed"] <= 0:
                break
            
            if score >= 80:  # Only use high-quality strict matches
                if _book_team_practice_enhanced(team_name, team_data, block, start_date, schedule, validator):
                    allocated_count += 1
                    sessions_allocated += 1
                    print(f"  {team_name}: STRICT preference match (score {score}) on {block.date.strftime('%A')} {block.start_time}")
                    
                    # Remove block if fully used
                    if block.remaining_minutes() < 30:
                        available_blocks.remove(block)
    
    print(f"Phase 0 allocated: {allocated_count} strict preference sessions")
    return allocated_count


def allocate_mandatory_shared_ice_fixed(teams_needing_slots: Dict, available_blocks: List[AvailableBlock],
                                       start_date: datetime.date, schedule: List[Dict],
                                       rules_data: Dict, validator: ScheduleConflictValidator) -> int:
    """
    PHASE 1: Mandatory shared ice allocation (AFTER strict preferences handled).
    """
    allocated_count = 0
    
    # Get all teams with mandatory shared ice that still need slots
    mandatory_teams = []
    for team_name, team_data in teams_needing_slots.items():
        team_info = team_data["info"]
        if team_data["needed"] > 0 and has_mandatory_shared_ice(team_info):
            mandatory_teams.append((team_data["allocation_priority"], team_name, team_data))
    
    if not mandatory_teams:
        print("PHASE 1: No teams with mandatory shared ice")
        return 0
    
    mandatory_teams.sort()
    print(f"PHASE 1 - MANDATORY SHARED ICE: {len(mandatory_teams)} teams need shared ice")
    
    # Create partnerships and allocate
    max_rounds = 10
    round_num = 0
    
    while round_num < max_rounds:
        round_num += 1
        progress_made = False
        
        # Try all possible partnerships
        for i, (_, team1, team1_data) in enumerate(mandatory_teams):
            for j, (_, team2, team2_data) in enumerate(mandatory_teams[i+1:], i+1):
                if team1_data["needed"] <= 0 or team2_data["needed"] <= 0:
                    continue
                
                can_share, compatibility = can_teams_share_ice_enhanced(
                    team1_data["info"], team2_data["info"], team1, team2, False
                )
                
                if can_share:
                    # Find suitable shared blocks
                    best_block = None
                    best_score = -1
                    
                    for block in available_blocks:
                        if (is_block_available_strict(block, team1_data["info"], team1_data, rules_data, start_date) and
                            is_block_available_strict(block, team2_data["info"], team2_data, rules_data, start_date)):
                            
                            score1 = get_block_preference_score(block, team1_data["info"])
                            score2 = get_block_preference_score(block, team2_data["info"])
                            combined_score = max(score1, score2) + min(score1, score2) * 0.5
                            
                            if combined_score > best_score:
                                best_score = combined_score
                                best_block = block
                    
                    if best_block:
                        if _book_shared_practice_enhanced(team1, team2, team1_data, team2_data,
                                                        best_block, start_date, schedule, validator):
                            allocated_count += 1
                            progress_made = True
                            print(f"  MANDATORY SHARED: {team1} + {team2} on {best_block.date}")
                            
                            if best_block.remaining_minutes() < 30:
                                available_blocks.remove(best_block)
                            break
            
            if progress_made:
                break
        
        if not progress_made:
            break
    
    print(f"Phase 1 allocated: {allocated_count} mandatory shared sessions")
    return allocated_count


def allocate_individual_priority_fixed(teams_needing_slots: Dict, available_blocks: List[AvailableBlock],
                                      start_date: datetime.date, schedule: List[Dict],
                                      rules_data: Dict, validator: ScheduleConflictValidator) -> int:
    """
    PHASE 2: Individual allocation for remaining teams by priority.
    """
    allocated_count = 0
    
    max_iterations = 5
    iteration = 0
    
    while iteration < max_iterations:
        iteration += 1
        progress_made = False
        
        # Get teams needing slots, sorted by priority
        priority_teams = []
        for team_name, team_data in teams_needing_slots.items():
            if team_data["needed"] > 0:
                priority_teams.append((team_data["allocation_priority"], team_name, team_data))
        
        priority_teams.sort()
        
        if not priority_teams:
            break
        
        for priority, team_name, team_data in priority_teams:
            if team_data["needed"] <= 0:
                continue
            
            # Try to find best available block
            best_block = None
            best_score = -1
            
            for block in available_blocks:
                if is_block_available_strict(block, team_data["info"], team_data, rules_data, start_date):
                    score = get_block_preference_score(block, team_data["info"])
                    if score > best_score:
                        best_score = score
                        best_block = block
            
            if best_block:
                if _book_team_practice_enhanced(team_name, team_data, best_block, start_date, schedule, validator):
                    allocated_count += 1
                    progress_made = True
                    print(f"  INDIVIDUAL: {team_name} (score {best_score}) on {best_block.date}")
                    
                    if best_block.remaining_minutes() < 30:
                        available_blocks.remove(best_block)
                    break
        
        if not progress_made:
            break
    
    print(f"Phase 2 allocated: {allocated_count} individual sessions")
    return allocated_count


def allocate_shared_ice_remaining(teams_needing_slots: Dict, available_blocks: List[AvailableBlock],
                                 start_date: datetime.date, schedule: List[Dict],
                                 rules_data: Dict, validator: ScheduleConflictValidator) -> int:
    """
    PHASE 3: Shared ice allocation for remaining teams.
    """
    allocated_count = 0
    
    # Get teams that still need allocation and can share
    teams_can_share = []
    for team_name, team_data in teams_needing_slots.items():
        if team_data["needed"] > 0 and team_data["info"].get("allow_shared_ice", True):
            teams_can_share.append((team_data["allocation_priority"], team_name, team_data))
    
    teams_can_share.sort()
    
    if len(teams_can_share) < 2:
        print("PHASE 3: Insufficient teams for shared allocation")
        return 0
    
    print(f"PHASE 3 - SHARED ICE: {len(teams_can_share)} teams available for sharing")
    
    # Try partnerships
    max_rounds = 5
    round_num = 0
    
    while round_num < max_rounds:
        round_num += 1
        progress_made = False
        
        for i, (_, team1, team1_data) in enumerate(teams_can_share):
            for j, (_, team2, team2_data) in enumerate(teams_can_share[i+1:], i+1):
                if team1_data["needed"] <= 0 or team2_data["needed"] <= 0:
                    continue
                
                can_share, compatibility = can_teams_share_ice_enhanced(
                    team1_data["info"], team2_data["info"], team1, team2, False
                )
                
                if can_share:
                    # Find suitable block
                    best_block = None
                    for block in available_blocks:
                        if (is_block_available_strict(block, team1_data["info"], team1_data, rules_data, start_date) and
                            is_block_available_strict(block, team2_data["info"], team2_data, rules_data, start_date)):
                            best_block = block
                            break
                    
                    if best_block:
                        if _book_shared_practice_enhanced(team1, team2, team1_data, team2_data,
                                                        best_block, start_date, schedule, validator):
                            allocated_count += 1
                            progress_made = True
                            print(f"  SHARED: {team1} + {team2} on {best_block.date}")
                            
                            if best_block.remaining_minutes() < 30:
                                available_blocks.remove(best_block)
                            break
            
            if progress_made:
                break
        
        if not progress_made:
            break
    
    print(f"Phase 3 allocated: {allocated_count} shared sessions")
    return allocated_count


def allocate_guaranteed_final(teams_needing_slots: Dict, available_blocks: List[AvailableBlock],
                            start_date: datetime.date, schedule: List[Dict],
                            rules_data: Dict, validator: ScheduleConflictValidator) -> int:
    """
    PHASE 4: Guaranteed allocation with lenient constraints for critical shortfalls.
    """
    allocated_count = 0
    
    # Get teams that are critically short (less than 50% of target)
    critical_teams = []
    for team_name, team_data in teams_needing_slots.items():
        if team_data["needed"] > 0:
            allocated = team_data["total_target"] - team_data["needed"]
            percentage = (allocated / team_data["total_target"]) * 100 if team_data["total_target"] > 0 else 0
            
            if percentage < 50:  # Less than 50% allocated
                critical_teams.append((team_data["allocation_priority"], team_name, team_data, percentage))
    
    critical_teams.sort()
    
    if not critical_teams:
        print("PHASE 4: No critically underallocated teams")
        return 0
    
    print(f"PHASE 4 - GUARANTEED ALLOCATION: {len(critical_teams)} critically short teams")
    
    for priority, team_name, team_data, percentage in critical_teams:
        team_info = team_data["info"]
        sessions_to_allocate = min(team_data["needed"], 2)
        
        print(f"  Attempting guaranteed allocation for {team_name} ({percentage:.1f}% allocated)")
        
        for session in range(sessions_to_allocate):
            if team_data["needed"] <= 0:
                break
            
            # Try lenient individual allocation first
            best_block = None
            for block in available_blocks:
                current_week_dates = []
                week_start = block.date - datetime.timedelta(days=block.date.weekday())
                for i in range(7):
                    current_week_dates.append(week_start + datetime.timedelta(days=i))
                
                if is_block_available_lenient(block, team_info, team_data, rules_data, start_date, current_week_dates):
                    best_block = block
                    break
            
            if best_block:
                if _book_team_practice_enhanced(team_name, team_data, best_block, start_date, schedule, validator):
                    allocated_count += 1
                    print(f"    GUARANTEED: {team_name} individual session on {best_block.date}")
                    if best_block.remaining_minutes() < 30:
                        available_blocks.remove(best_block)
                    continue
            
            # Try forced shared if individual failed
            if team_info.get("allow_shared_ice", True):
                for other_name, other_data in teams_needing_slots.items():
                    if (other_name != team_name and other_data["needed"] > 0 and
                        other_data["info"].get("allow_shared_ice", True)):
                        
                        can_share, _ = can_teams_share_ice_enhanced(
                            team_info, other_data["info"], team_name, other_name, True  # Emergency mode
                        )
                        
                        if can_share and available_blocks:
                            for block in available_blocks:
                                current_week_dates = []
                                week_start = block.date - datetime.timedelta(days=block.date.weekday())
                                for i in range(7):
                                    current_week_dates.append(week_start + datetime.timedelta(days=i))
                                
                                if (is_block_available_lenient(block, team_info, team_data, rules_data, start_date, current_week_dates) and
                                    is_block_available_lenient(block, other_data["info"], other_data, rules_data, start_date, current_week_dates)):
                                    
                                    if _book_shared_practice_enhanced(team_name, other_name, team_data, other_data,
                                                                    block, start_date, schedule, validator, force_mode=True):
                                        allocated_count += 1
                                        print(f"    GUARANTEED SHARED: {team_name} + {other_name} on {block.date}")
                                        if block.remaining_minutes() < 30:
                                            available_blocks.remove(block)
                                        break
                            break
    
    print(f"Phase 4 allocated: {allocated_count} guaranteed sessions")
    return allocated_count


# =============================================================================
# SECTION 9: MAIN FIXED SCHEDULER FUNCTION
# =============================================================================

def generate_schedule_fixed_constraints(
    season_dates: Tuple[datetime.date, datetime.date],
    teams_data: Dict,
    arenas_data: Dict,
    rules_data: Dict,
):
    """
    FIXED SCHEDULER with proper constraint enforcement:
    
    Phase 0: Strict preferences get first pick of exact matches
    Phase 1: Mandatory shared ice teams
    Phase 2: Individual allocation by priority
    Phase 3: Shared ice for remaining teams
    Phase 4: Guaranteed allocation with lenient constraints for critical cases
    
    Key fixes:
    1. Strict preferences are honored FIRST before any other allocation
    2. Multiple-per-day constraints are strictly enforced unless explicitly allowed
    3. Proper constraint checking in both individual and shared bookings
    """
    
    print("=== FIXED CONSTRAINT SCHEDULER ===")
    print("Key fixes: Strict preferences first, proper multiple-per-day enforcement")
    
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
                            if team_name:  # Pre-assigned
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
    print(f"Total teams needing allocation: {len([t for t in teams_needing_slots.values() if t['needed'] > 0])}")

    # FIXED 4-PHASE ALLOCATION STRATEGY
    print("\n=== FIXED 4-PHASE ALLOCATION STRATEGY ===")
    
    print("=== PHASE 0: STRICT PREFERENCES FIRST ===")
    phase0_allocated = allocate_strict_preferences_first(teams_needing_slots, available_blocks, start_date, schedule, rules_data, validator)
    
    print("=== PHASE 1: MANDATORY SHARED ICE ===")
    phase1_allocated = allocate_mandatory_shared_ice_fixed(teams_needing_slots, available_blocks, start_date, schedule, rules_data, validator)
    
    print("=== PHASE 2: INDIVIDUAL PRIORITY ALLOCATION ===")
    phase2_allocated = allocate_individual_priority_fixed(teams_needing_slots, available_blocks, start_date, schedule, rules_data, validator)
    
    print("=== PHASE 3: SHARED ICE FOR REMAINING ===")
    phase3_allocated = allocate_shared_ice_remaining(teams_needing_slots, available_blocks, start_date, schedule, rules_data, validator)
    
    print("=== PHASE 4: GUARANTEED ALLOCATION ===")
    phase4_allocated = allocate_guaranteed_final(teams_needing_slots, available_blocks, start_date, schedule, rules_data, validator)

    # Generate final analysis and reports
    allocation_summary = analyze_team_allocation(teams_needing_slots, start_date, end_date, rules_data, schedule)
    summary_text = format_allocation_message(allocation_summary)
    write_schedule_log(summary_text)
    
    schedule = clean_schedule_duplicates(schedule)
    validator.clear()
    validator.add_existing_schedule(schedule)
    
    # Final conflict check
    final_conflicts = []
    for entry in schedule:
        team = entry.get("team", "")
        arena = entry.get("arena", "")
        date = entry.get("date", "")
        time_slot = entry.get("time_slot", "")
        
        if all([team, arena, date, time_slot]):
            is_valid, conflicts = validator.validate_booking(team, arena, date, time_slot)
            if not is_valid:
                final_conflicts.extend(conflicts)
    
    if final_conflicts:
        print("WARNING: Final schedule validation found conflicts:")
        for conflict in final_conflicts:
            print(f"  - {conflict}")

    # Enhanced final report
    print("\n=== FIXED SCHEDULER FINAL REPORT ===")
    total_allocated = 0
    total_target = 0
    underallocated = []
    teams_with_strict_unmet = []
    teams_with_multiple_violations = []
        
    for team_name, team_data in teams_needing_slots.items():
        target = team_data["total_target"]
        allocated = target - team_data["needed"]
        total_allocated += allocated
        total_target += target
        
        percentage = (allocated / target * 100) if target > 0 else 100
        
        if team_data["needed"] > 0:
            underallocated.append((team_name, allocated, target, team_data["needed"]))
            
            if has_strict_preferences(team_data["info"]):
                teams_with_strict_unmet.append(team_name)
        
        # Check for multiple sessions per day violations in final schedule
        team_sessions_by_date = defaultdict(int)
        for event in schedule:
            if event.get("team") == team_name or (event.get("type") == "shared practice" and event.get("opponent") == team_name):
                team_sessions_by_date[event.get("date")] += 1
        
        multiple_violations = [date for date, count in team_sessions_by_date.items() if count > 1]
        if multiple_violations and not _safe_allow_multiple(team_data["info"]) and not can_team_have_multiple_per_day(team_data["info"], team_name):
            teams_with_multiple_violations.append((team_name, multiple_violations))
        
        status_flags = []
        if has_mandatory_shared_ice(team_data["info"]):
            status_flags.append("MANDATORY_SHARED")
        if has_strict_preferences(team_data["info"]):
            status_flags.append("STRICT_PREFS")
        if _safe_allow_multiple(team_data["info"]):
            status_flags.append("ALLOW_MULTIPLE")
        
        status = f" [{', '.join(status_flags)}]" if status_flags else ""
        print(f"{team_name}: {allocated}/{target} ({percentage:.1f}%){status}")
    
    overall_percentage = (total_allocated / total_target * 100) if total_target > 0 else 100
    print(f"\nOVERALL ALLOCATION: {total_allocated}/{total_target} ({overall_percentage:.1f}%)")
    
    print(f"\nPhase Results:")
    print(f"  Phase 0 (Strict Preferences): {phase0_allocated} sessions")
    print(f"  Phase 1 (Mandatory Shared): {phase1_allocated} sessions")
    print(f"  Phase 2 (Individual Priority): {phase2_allocated} sessions")
    print(f"  Phase 3 (Shared Ice): {phase3_allocated} sessions")
    print(f"  Phase 4 (Guaranteed): {phase4_allocated} sessions")
    print(f"  Total new allocations: {phase0_allocated + phase1_allocated + phase2_allocated + phase3_allocated + phase4_allocated}")
    
    if underallocated:
        print(f"\nUNDERALLOCATED TEAMS ({len(underallocated)}):")
        for team, allocated, target, remaining in sorted(underallocated, key=lambda x: x[3], reverse=True):
            print(f"  {team}: {allocated}/{target} (missing {remaining})")
    
    if teams_with_strict_unmet:
        print(f"\nSTRICT PREFERENCE TEAMS WITH UNMET REQUIREMENTS:")
        for team in teams_with_strict_unmet:
            print(f"  - {team} (has strict preferences but didn't receive full allocation)")
    
    if teams_with_multiple_violations:
        print(f"\nMULTIPLE-PER-DAY CONSTRAINT VIOLATIONS:")
        for team, violation_dates in teams_with_multiple_violations:
            print(f"  - {team}: Multiple sessions on {len(violation_dates)} dates (should have allow_multiple_per_day=False respected)")

    print("\nFixed scheduler complete with proper constraint enforcement")
    return {"schedule": schedule, "allocation_summary": allocation_summary, "conflicts": final_conflicts}


# =============================================================================
# SECTION 10: ANALYSIS AND REPORTING
# =============================================================================

def analyze_team_allocation(
    teams_needing_slots: Dict,
    start_date: datetime.date,
    end_date: datetime.date,
    rules_data: Dict,
    schedule: List[Dict],
) -> Dict:
    """Analyze team allocation results."""
    total_weeks = max(1, (end_date - start_date).days // 7)
    team_weekly_schedule = defaultdict(lambda: defaultdict(int))

    for event in schedule:
        date_str = event.get("date")
        if not date_str:
            continue
        try:
            event_date = _parse_date(date_str)
        except Exception:
            continue
        week_num = get_week_number(event_date, start_date)

        etype = event.get("type")
        team = event.get("team")
        opponent = event.get("opponent")

        if etype == "shared practice":
            if team:
                team_weekly_schedule[team][week_num] += 1
            if opponent and opponent not in (None, "Practice", "TBD"):
                team_weekly_schedule[opponent][week_num] += 1
        else:
            if team:
                team_weekly_schedule[team][week_num] += 1

    allocation_details = {}
    underallocated_teams = []
    for team_name, team_data in teams_needing_slots.items():
        team_info = team_data["info"]
        team_type = team_info.get("type")
        team_age = team_info.get("age")
        expected_per_week = (
            rules_data.get("ice_times_per_week", {})
            .get(team_type, {}).get(team_age, 0)
        )
        expected_total = expected_per_week * total_weeks
        actual_total = sum(team_weekly_schedule[team_name].values())
        missing_weeks = []
        for week in range(1, total_weeks + 1):
            actual_weekly = team_weekly_schedule[team_name][week]
            if actual_weekly < expected_per_week:
                missing_weeks.append(
                    {
                        "week": week,
                        "expected": expected_per_week,
                        "actual": actual_weekly,
                        "short": expected_per_week - actual_weekly,
                    }
                )
        allocation_details[team_name] = {
            "expected_total": expected_total,
            "actual_total": actual_total,
            "expected_weekly": expected_per_week,
            "missing_weeks": missing_weeks,
            "fully_allocated": len(missing_weeks) == 0,
        }
        if not allocation_details[team_name]["fully_allocated"]:
            underallocated_teams.append(team_name)

    return {
        "allocation_details": allocation_details,
        "underallocated_teams": underallocated_teams,
        "total_weeks": total_weeks,
    }


def write_schedule_log(summary_text: str, filename: str = "schedule_log.txt"):
    """Write schedule log to file."""
    log_path = os.path.join(os.getcwd(), filename)
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(summary_text)
    print(f"Schedule log written to {log_path}")


def format_allocation_message(allocation_summary, required=None, available=None, shared=None) -> str:
    """Format allocation summary into human-readable message."""
    details = allocation_summary
    lines = []
    lines.append("=== Allocation Summary ===\n")
    for team, info in sorted(details.get("allocation_details", {}).items()):
        expected = info.get("expected_total", 0)
        actual = info.get("actual_total", 0)
        lines.append(f"{team}: {actual}/{expected} total ice times")
        if info.get("missing_weeks"):
            missing = ", ".join([f"W{w['week']} (-{w['short']})" for w in info["missing_weeks"]])
            lines.append(f"   Missing weeks: {missing}")
    if details.get("underallocated_teams"):
        lines.append("\nTeams still underallocated:")
        for team in sorted(details["underallocated_teams"]):
            lines.append(f"  - {team}")
    if required is not None and available is not None and shared is not None:
        lines.append(f"\nRequired slots: {required}, Available slots: {available}, Shared allocations: {shared}")
    return "\n".join(lines)


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
        else:
            print(f"DEBUG: Removed duplicate entry: {entry}")
    
    return cleaned


# =============================================================================
# SECTION 11: BACKWARD COMPATIBILITY AND WRAPPER FUNCTIONS
# =============================================================================

def generate_schedule(*args, **kwargs):
    """Backward compatibility wrapper for the fixed scheduler."""
    return generate_schedule_fixed_constraints(*args, **kwargs)


def generate_schedule_enhanced_fixed(*args, **kwargs):
    """Legacy function name compatibility."""
    return generate_schedule_fixed_constraints(*args, **kwargs)


def generate_schedule_guaranteed_allocation(*args, **kwargs):
    """Legacy function name compatibility."""
    return generate_schedule_fixed_constraints(*args, **kwargs)


# =============================================================================
# SECTION 12: VALIDATION FUNCTIONS
# =============================================================================

def validate_schedule_constraints(schedule: List[Dict], teams_data: Dict) -> List[str]:
    """Validate that the final schedule respects all constraints."""
    violations = []
    
    # Check multiple-per-day violations
    team_sessions_by_date = defaultdict(lambda: defaultdict(int))
    
    for entry in schedule:
        team = entry.get("team")
        date = entry.get("date")
        if team and date:
            team_sessions_by_date[team][date] += 1
        
        # Also count shared practice for opponent
        if entry.get("type") == "shared practice":
            opponent = entry.get("opponent")
            if opponent and opponent != "Practice" and date:
                team_sessions_by_date[opponent][date] += 1
    
    # Check for violations
    for team_name, team_info in teams_data.items():
        if not _safe_allow_multiple(team_info) and not can_team_have_multiple_per_day(team_info, team_name):
            for date, count in team_sessions_by_date[team_name].items():
                if count > 1:
                    violations.append(f"Team {team_name} has {count} sessions on {date} but allow_multiple_per_day=False")
    
    # Check strict preference violations
    for team_name, team_info in teams_data.items():
        if has_strict_preferences(team_info):
            team_sessions = [entry for entry in schedule 
                           if entry.get("team") == team_name or 
                           (entry.get("type") == "shared practice" and entry.get("opponent") == team_name)]
            
            if team_sessions:
                strict_matches = 0
                for session in team_sessions:
                    try:
                        session_date = _parse_date(session.get("date"))
                        session_day = session_date.strftime("%A")
                        
                        # Create a mock block to test preference score
                        start_time_str = session.get("time_slot", "").split("-")[0]
                        end_time_str = session.get("time_slot", "").split("-")[1]
                        start_time = datetime.datetime.strptime(start_time_str, "%H:%M").time()
                        end_time = datetime.datetime.strptime(end_time_str, "%H:%M").time()
                        
                        mock_block = AvailableBlock(
                            arena=session.get("arena", ""),
                            date=session_date,
                            start_time=start_time,
                            end_time=end_time,
                            weekday=session_date.weekday()
                        )
                        
                        score = get_block_preference_score(mock_block, team_info)
                        if score >= 80:  # Strict preference match
                            strict_matches += 1
                    except:
                        continue
                
                if strict_matches == 0:
                    violations.append(f"Team {team_name} has strict preferences but no sessions match them")
    
    return violations


# =============================================================================
# SECTION 13: MAIN ENTRY POINT FUNCTIONS
# =============================================================================

def run_fixed_constraint_scheduler(config_file_path: str = None, 
                                  start_date: str = None, 
                                  end_date: str = None) -> Dict:
    """
    Main entry point for running the fixed constraint scheduler.
    
    Args:
        config_file_path: Path to JSON configuration file
        start_date: Season start date (YYYY-MM-DD format)
        end_date: Season end date (YYYY-MM-DD format)
    
    Returns:
        Dictionary containing schedule, allocation summary, and conflicts
    """
    
    if config_file_path:
        try:
            with open(config_file_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            teams_data = config.get("teams", {})
            arenas_data = config.get("arenas", {})
            rules_data = config.get("rules", {})
            
            # Override dates if provided
            if start_date and end_date:
                season_dates = (_parse_date(start_date), _parse_date(end_date))
            else:
                # Try to infer from config or use defaults
                season_dates = (
                    datetime.date(2025, 9, 1),  # Default start
                    datetime.date(2026, 3, 31)  # Default end
                )
            
        except Exception as e:
            print(f"Error loading configuration: {e}")
            return {"error": f"Configuration loading failed: {e}"}
    
    else:
        print("Error: No configuration file provided")
        return {"error": "No configuration file provided"}
    
    # Run the scheduler
    try:
        result = generate_schedule_fixed_constraints(
            season_dates=season_dates,
            teams_data=teams_data,
            arenas_data=arenas_data,
            rules_data=rules_data
        )
        
        # Validate constraints
        violations = validate_schedule_constraints(result["schedule"], teams_data)
        if violations:
            print("\nCONSTRAINT VIOLATIONS DETECTED:")
            for violation in violations:
                print(f"  - {violation}")
            result["constraint_violations"] = violations
        else:
            print("\nCONSTRAINT VALIDATION PASSED: All constraints properly enforced")
            result["constraint_violations"] = []
        
        print(f"\nScheduler completed successfully!")
        print(f"Generated {len(result['schedule'])} schedule entries")
        
        return result
        
    except Exception as e:
        print(f"Scheduler execution failed: {e}")
        return {"error": f"Scheduler execution failed: {e}"}


if __name__ == "__main__":
    # Example usage
    import sys
    
    if len(sys.argv) > 1:
        config_path = sys.argv[1]
        start = sys.argv[2] if len(sys.argv) > 2 else None
        end = sys.argv[3] if len(sys.argv) > 3 else None
        
        result = run_fixed_constraint_scheduler(config_path, start, end)
        
        if "error" not in result:
            print(f"\nSchedule generation complete!")
            print(f"Check schedule_log.txt for detailed results")
        else:
            print(f"Error: {result['error']}")
    else:
        print("Usage: python scheduler_logic.py <config_file.json> [start_date] [end_date]")
        print("Example: python scheduler_logic.py hockey_config.json 2025-09-01 2026-03-31")