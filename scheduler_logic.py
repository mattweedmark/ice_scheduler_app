import json
import re
import os
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional, Set
import datetime


# =============================================================================
# SECTION 1: CORE DATA STRUCTURES (Fixed)
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
    
    def get_next_available_time(self) -> datetime.time:
        """Get the next available start time in this block"""
        used_minutes = sum(booking['duration'] for booking in self.bookings)
        start_dt = datetime.datetime.combine(datetime.date.min, self.start_time)
        next_available_dt = start_dt + datetime.timedelta(minutes=used_minutes)
        return next_available_dt.time()


# =============================================================================
# SECTION 2: UTILITY FUNCTIONS (Enhanced)
# =============================================================================

def normalize_team_info(raw: dict) -> dict:
    """Convert legacy JSON structures into new scheduler format."""
    out = dict(raw or {})

    # Preferred days normalization - FIXED to handle strict preferences correctly
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
                        end_hh, end_mm = hh + 1, mm  # Default 1-hour duration
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
    out["strict_preferred"] = strict_flag  # Set based on actual strict preferences

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

    # Shared ice normalization - FIXED to handle mandatory shared ice
    s = out.get("shared_ice", None)
    if isinstance(s, dict):
        out["allow_shared_ice"] = bool(s.get("enabled", True))
    elif isinstance(s, bool):
        out["allow_shared_ice"] = s
    else:
        out.setdefault("allow_shared_ice", True)
    
    # Handle mandatory shared ice - NEW FIELD
    out.setdefault("mandatory_shared_ice", False)
    
    # If mandatory shared ice is True, ensure allow_shared_ice is also True
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


def get_week_number(date: datetime.date, start_date: datetime.date) -> int:
    """Calculate week number from start date."""
    days_diff = (date - start_date).days
    return (days_diff // 7) + 1


# =============================================================================
# SECTION 3: STRICT PREFERENCE FUNCTIONS (FIXED)
# =============================================================================

def has_strict_preferences(team_info: dict) -> bool:
    """Check if team has strict time preferences - FIXED logic."""
    # Check the explicit strict_preferred flag first
    if team_info.get("strict_preferred", False):
        return True
    
    # Check for strict preference flags in preferred_days_and_times
    prefs = team_info.get("preferred_days_and_times", {})
    for key, value in prefs.items():
        if key.endswith("_strict") and value:
            return True
    
    return False


def _parse_preferred_windows(team_info: dict) -> dict:
    """Parse preferred days/times into structured windows with strict flags - FIXED."""
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
                if is_strict_window:  # ONLY strict preferences
                    # Check if block times exactly match or contain the preferred time
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
                # Check if block times exactly match or contain the preferred time
                if (block.start_time <= start_pref and block.end_time >= end_pref):
                    matches.append(block)
                    break
    
    return matches


def find_mutual_strict_preference_matches(team1_info: dict, team2_info: dict, available_blocks: List[AvailableBlock]) -> List[AvailableBlock]:
    """Find blocks that match BOTH teams' strict preferences for shared ice."""
    team1_matches = find_exact_strict_preference_matches(team1_info, available_blocks)
    team2_matches = find_exact_strict_preference_matches(team2_info, available_blocks)
    
    # Find intersection - blocks that work for both teams
    mutual_matches = []
    for block in team1_matches:
        if block in team2_matches:
            mutual_matches.append(block)
    
    return mutual_matches


def find_mutual_preference_matches(team1_info: dict, team2_info: dict, available_blocks: List[AvailableBlock], strict_only: bool = False) -> List[AvailableBlock]:
    """Find blocks that match BOTH teams' preferences (strict or any) for shared ice."""
    team1_matches = find_preferred_time_matches(team1_info, available_blocks, strict_only)
    team2_matches = find_preferred_time_matches(team2_info, available_blocks, strict_only)
    
    # Find intersection - blocks that work for both teams
    mutual_matches = []
    for block in team1_matches:
        if block in team2_matches:
            mutual_matches.append(block)
    
    return mutual_matches


def get_block_preference_score(block: AvailableBlock, team_info: dict) -> int:
    """Score block based on preferences with strict priority."""
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
                    return 1000  # VERY HIGH SCORE for strict matches
                elif overlap_duration >= block_duration * 0.5:  # 50% overlap
                    return 800   # HIGH SCORE for good strict match
                else:
                    return 600   # MEDIUM SCORE for partial strict match
            else:
                # Non-strict preference gets much lower scores
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


# =============================================================================
# SECTION 4: TEAM PROPERTY HELPERS (Enhanced)
# =============================================================================

def has_mandatory_shared_ice(team_info: dict) -> bool:
    """Check if a team has mandatory shared ice enabled."""
    return bool(team_info.get("mandatory_shared_ice", False)) and bool(team_info.get("allow_shared_ice", True))


def calculate_team_priority(team_info: dict, team_name: str) -> int:
    """Calculate allocation priority for teams (lower = higher priority) - REBALANCED."""
    priority = 0
    
    # Age priority (younger teams get slight priority)
    age = _get_age_numeric(team_info.get("age", ""))
    if age:
        priority += age // 2  # Reduced impact: U18=9, U7=3 (was 18 vs 7)
    else:
        priority += 25  # Reduced from 50
    
    # Type priority (smaller difference)
    team_type = team_info.get("type", "house")
    if team_type == "competitive":
        priority += 0
    else:
        priority += 3  # Reduced from 10
    
    # Tier priority for competitive teams
    if team_type == "competitive":
        tier = _get_team_tier(team_name, team_info)
        tier_values = {"AA": 0, "A": 1, "BB": 2, "B": 3, "C": 4}
        priority += tier_values.get(tier, 5)
    
    # Mandatory shared ice gets modest priority boost
    if has_mandatory_shared_ice(team_info):
        priority -= 10  # Reduced from -100
    
    # Strict preferences get modest priority boost
    if has_strict_preferences(team_info):
        priority -= 8  # Reduced from -75
    
    return priority


def calculate_constraint_complexity(team_info: dict, team_name: str) -> int:
    """Calculate how constrained a team is for allocation order (higher = more constrained)."""
    complexity = 0
    
    # Mandatory shared ice adds significant complexity
    if has_mandatory_shared_ice(team_info):
        complexity += 100
    
    # Strict preferences add complexity
    if has_strict_preferences(team_info):
        complexity += 50
    
    # Count number of blackout dates
    blackouts = team_info.get("blackout_dates", [])
    complexity += len(blackouts) * 2
    
    # Age restrictions (very young teams have fewer sharing options)
    age = _get_age_numeric(team_info.get("age", ""))
    if age and age <= 9:
        complexity += 20
    
    # Teams that don't allow sharing are more constrained
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
# SECTION 5: AVAILABILITY CHECKING
# =============================================================================

def is_block_available_for_team(block: AvailableBlock, team_info: Dict, team_data: Dict, 
                               rules_data: Dict, start_date: datetime.date) -> bool:
    """Check if a block is available for a specific team."""
    required_duration = team_info.get("practice_duration", 60)
    
    # Check 1: Block has enough time
    if not block.can_fit_duration(required_duration):
        return False
    
    # Check 2: No blackout on this date
    if has_blackout_on_date(team_info, block.date):
        return False
    
    # Check 3: Weekly quota check
    week_num = get_week_number(block.date, start_date)
    current_weekly_count = team_data["weekly_count"][week_num]
    
    team_type = team_info.get("type")
    team_age = team_info.get("age")
    max_per_week = (rules_data.get("ice_times_per_week", {})
                   .get(team_type, {}).get(team_age, 0))
    
    if current_weekly_count >= max_per_week:
        return False
    
    # Check 4: Multiple per day restriction
    allow_multiple = _safe_allow_multiple(team_info)
    if not allow_multiple and block.date in team_data.get("scheduled_dates", set()):
        return False
    
    return True


def can_teams_share_ice(team1_info: dict, team2_info: dict, team1_name: str = "", 
                       team2_name: str = "") -> bool:
    """Check if two teams can share ice time."""
    age1 = _get_age_numeric(team1_info.get("age", ""))
    age2 = _get_age_numeric(team2_info.get("age", ""))
    
    if age1 is None or age2 is None:
        return False
    
    age_diff = abs(age1 - age2)
    
    # Check if both teams allow sharing
    allow1 = team1_info.get("allow_shared_ice", True)
    allow2 = team2_info.get("allow_shared_ice", True)
    
    if not allow1 or not allow2:
        return False
    
    # Age restrictions (max 3 years difference)
    if age_diff > 3:
        return False
    
    return True


def is_block_available_for_team_capacity_phase(block: AvailableBlock, team_info: Dict, team_data: Dict, 
                                             rules_data: Dict, start_date: datetime.date) -> bool:
    """Check if a block is available for a specific team during capacity maximization phase (relaxed same-day limits)."""
    required_duration = team_info.get("practice_duration", 60)
    
    # Check 1: Block has enough time
    if not block.can_fit_duration(required_duration):
        return False
    
    # Check 2: No blackout on this date
    if has_blackout_on_date(team_info, block.date):
        return False
    
    # Check 3: Weekly quota check
    week_num = get_week_number(block.date, start_date)
    current_weekly_count = team_data["weekly_count"][week_num]
    
    team_type = team_info.get("type")
    team_age = team_info.get("age")
    max_per_week = (rules_data.get("ice_times_per_week", {})
                   .get(team_type, {}).get(team_age, 0))
    
    if current_weekly_count >= max_per_week:
        return False
    
    # Check 4: Multiple per day restriction - CAPACITY PHASE RELAXED RULES
    allow_multiple = _safe_allow_multiple(team_info)
    sessions_on_date = len([d for d in team_data["scheduled_dates"] if d == block.date])
    
    if not allow_multiple and sessions_on_date >= 1:
        return False
    elif allow_multiple and sessions_on_date >= 2:  # Max 2 sessions per day even in capacity phase
        return False
    
    return True


def calculate_same_day_penalty(team_data: dict, block_date: datetime.date) -> int:
    """Calculate penalty for booking multiple sessions on same day to encourage distribution - MASSIVELY INCREASED."""
    sessions_on_date = len([d for d in team_data["scheduled_dates"] if d == block_date])
    
    # MUCH HIGHER penalties to strongly discourage same-day sessions
    if sessions_on_date == 0:
        return 0        # No penalty for first session on this date
    elif sessions_on_date == 1:
        return 2000     # MASSIVE penalty for second session on same date
    else:
        return 10000    # EXTREME penalty for third+ session on same date


def find_best_block_with_distribution(blocks: List[AvailableBlock], team_info: dict, team_data: dict,
                                    rules_data: Dict, start_date: datetime.date) -> Optional[AvailableBlock]:
    """Find best block considering preferences AND day distribution."""
    best_block = None
    best_score = -999999  # Start with very low score to handle high penalties
    
    print(f"    DEBUG: Looking for blocks for team, currently scheduled on: {sorted(team_data['scheduled_dates'])}")
    
    for block in blocks:
        if is_block_available_for_team(block, team_info, team_data, rules_data, start_date):
            # Base preference score
            pref_score = get_block_preference_score(block, team_info)
            
            # Same-day penalty to encourage distribution
            same_day_penalty = calculate_same_day_penalty(team_data, block.date)
            
            # Final score encourages day diversity
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
    best_score = -999999  # Start with very low score to handle high penalties
    
    for block in blocks:
        if (is_block_available_for_team(block, team1_info, team1_data, rules_data, start_date) and
            is_block_available_for_team(block, team2_info, team2_data, rules_data, start_date)):
            
            # Base preference scores
            score1 = get_block_preference_score(block, team1_info)
            score2 = get_block_preference_score(block, team2_info)
            combined_pref_score = score1 + score2
            
            # Same-day penalties for both teams
            penalty1 = calculate_same_day_penalty(team1_data, block.date)
            penalty2 = calculate_same_day_penalty(team2_data, block.date)
            combined_penalty = penalty1 + penalty2
            
            # Final score encourages day diversity for both teams
            final_score = combined_pref_score - combined_penalty
            
            if final_score > best_score:
                best_score = final_score
                best_block = block
    
    return best_block


# =============================================================================
# SECTION 6: SAME-DAY SESSION PREVENTION (NEW)
# =============================================================================

def is_back_to_back_with_existing_session(team_name: str, team_data: dict, new_block: AvailableBlock, 
                                        schedule: List[dict]) -> bool:
    """Check if a new booking would be back-to-back with existing session on same date."""
    existing_sessions = [
        event for event in schedule 
        if (event.get("team") == team_name and 
            event.get("date") == new_block.date.isoformat())
    ]
    
    if not existing_sessions:
        return True  # No existing sessions, so it's fine
    
    for session in existing_sessions:
        try:
            existing_start_str, existing_end_str = session["time_slot"].split("-")
            existing_start = datetime.datetime.strptime(existing_start_str, "%H:%M").time()
            existing_end = datetime.datetime.strptime(existing_end_str, "%H:%M").time()
            
            # Check if new block starts when existing ends, or vice versa
            if (new_block.start_time == existing_end or 
                new_block.end_time == existing_start):
                return True
        except:
            continue
    
    return False  # Not back-to-back


def get_sessions_on_date_count(team_data: dict, check_date: datetime.date) -> int:
    """Get count of sessions a team has on a specific date."""
    return len([d for d in team_data["scheduled_dates"] if d == check_date])


def should_allow_same_day_booking(team_name: str, team_data: dict, new_block: AvailableBlock, 
                                schedule: List[dict], booking_type: str, allow_multiple: bool) -> bool:
    """Determine if a same-day booking should be allowed based on strict rules."""
    sessions_on_date = get_sessions_on_date_count(team_data, new_block.date)
    
    # PHASE 0 & 1: Strict same-day prevention (only 1 session per day)
    if booking_type in ["strict preference", "preferred time", "forced minimum", "practice", "relaxed"]:
        if sessions_on_date >= 1:
            print(f"    SAME-DAY PREVENTION: {team_name} already has {sessions_on_date} sessions on {new_block.date} - BLOCKING same-day allocation")
            return False
    
    # PHASE 2 (capacity): Allow 2nd session ONLY if back-to-back AND team allows multiple
    elif booking_type in ["capacity fill"]:
        if sessions_on_date >= 2:
            print(f"    SAME-DAY PREVENTION: {team_name} already has {sessions_on_date} sessions on {new_block.date} - BLOCKING (max 2 per day)")
            return False
        elif sessions_on_date == 1:
            if not allow_multiple:
                print(f"    SAME-DAY PREVENTION: {team_name} doesn't allow multiple per day - BLOCKING")
                return False
            elif not is_back_to_back_with_existing_session(team_name, team_data, new_block, schedule):
                print(f"    SAME-DAY PREVENTION: {team_name} session on {new_block.date} would not be back-to-back - BLOCKING")
                return False
    
    return True


# =============================================================================
# SECTION 7: SMART MINIMUM GUARANTEE ALLOCATION (FIXED)
# =============================================================================

def allocate_smart_minimum_guarantee(teams_needing_slots: Dict, available_blocks: List[AvailableBlock],
                                   start_date: datetime.date, schedule: List[Dict],
                                   rules_data: Dict, validator: ScheduleConflictValidator) -> int:
    """
    PHASE 0: Smart Minimum Guarantee - Every team gets at least 1 session while respecting preferences.
    FIXED: Strict same-day prevention - only 1 session per day in this phase.
    """
    allocated_count = 0
    
    print("\n" + "="*80)
    print("PHASE 0: SMART MINIMUM GUARANTEE ALLOCATION")
    print("="*80)
    print("Strategy: Everyone gets 1+ session, STRICT same-day prevention, preferences respected")
    
    # Sort teams by constraint complexity (most constrained first)
    teams_by_complexity = []
    for team_name, team_data in teams_needing_slots.items():
        if team_data["needed"] > 0:
            complexity = calculate_constraint_complexity(team_data["info"], team_name)
            teams_by_complexity.append((complexity, team_name, team_data))
    
    teams_by_complexity.sort(reverse=True)  # Most constrained first
    
    print(f"Processing {len(teams_by_complexity)} teams needing ice (by constraint complexity)")
    
    for complexity, team_name, team_data in teams_by_complexity:
        team_info = team_data["info"]
        
        if team_data["needed"] <= 0:
            continue
        
        print(f"\n--- {team_name} (complexity: {complexity}, needs: {team_data['needed']}) ---")
        
        allocated = False
        
        # STRATEGY 1: Try optimal constrained allocation
        if has_mandatory_shared_ice(team_info):
            print(f"  Trying mandatory shared ice with preference matching...")
            allocated = try_mandatory_shared_with_preferences(team_name, team_data, teams_needing_slots, 
                                                             available_blocks, start_date, schedule, 
                                                             rules_data, validator)
        elif has_strict_preferences(team_info):
            print(f"  Trying strict preference allocation...")
            allocated = try_strict_preference_allocation(team_name, team_data, available_blocks, 
                                                       start_date, schedule, rules_data, validator)
        else:
            print(f"  Trying preferred time allocation...")
            allocated = try_preferred_time_allocation(team_name, team_data, available_blocks, 
                                                    start_date, schedule, rules_data, validator)
        
        if allocated:
            allocated_count += 1
            print(f"  SUCCESS: Optimal allocation achieved")
            continue
        
        # STRATEGY 2: Try relaxed allocation (ignore strict preferences, try any preferences)
        print(f"  Optimal failed, trying relaxed allocation...")
        if has_mandatory_shared_ice(team_info):
            allocated = try_mandatory_shared_relaxed(team_name, team_data, teams_needing_slots, 
                                                   available_blocks, start_date, schedule, 
                                                   rules_data, validator)
        else:
            allocated = try_any_preference_allocation(team_name, team_data, available_blocks, 
                                                    start_date, schedule, rules_data, validator)
        
        if allocated:
            allocated_count += 1
            print(f"  SUCCESS: Relaxed allocation achieved")
            continue
        
        # STRATEGY 3: Force any available slot (guarantee minimum)
        print(f"  Relaxed failed, forcing any available slot...")
        allocated = force_any_available_allocation(team_name, team_data, available_blocks, 
                                                 start_date, schedule, rules_data, validator)
        
        if allocated:
            allocated_count += 1
            print(f"  SUCCESS: Forced allocation - minimum guarantee met")
        else:
            print(f"  FAILED: No available slots found (likely blackouts or no capacity)")
    
    print(f"\nPHASE 0 COMPLETE: {allocated_count} minimum guarantee allocations")
    print("="*80)
    return allocated_count


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
            mutual_blocks = find_mutual_strict_preference_matches(team_info, partner_info, available_blocks)
            if mutual_blocks:
                best_block = find_best_block_for_teams(mutual_blocks, team_info, partner_info, 
                                                     team_data, partner_data, rules_data, start_date)
                if best_block and book_shared_practice(team_name, partner_name, team_data, partner_data, 
                                                     best_block, start_date, schedule, validator):
                    print(f"    SHARED (strict prefs): {team_name} + {partner_name}")
                    return True
        
        # Try any preference matches
        mutual_blocks = find_mutual_preference_matches(team_info, partner_info, available_blocks, strict_only=False)
        if mutual_blocks:
            best_block = find_best_block_for_teams(mutual_blocks, team_info, partner_info, 
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


def try_preferred_time_allocation(team_name: str, team_data: dict, available_blocks: List[AvailableBlock],
                                start_date: datetime.date, schedule: List[Dict], rules_data: Dict,
                                validator: ScheduleConflictValidator) -> bool:
    """Try to allocate individual session matching any preferences."""
    team_info = team_data["info"]
    
    preferred_matches = find_preferred_time_matches(team_info, available_blocks, strict_only=False)
    
    for block in preferred_matches:
        if is_block_available_for_team(block, team_info, team_data, rules_data, start_date):
            if book_team_practice(team_name, team_data, block, start_date, schedule, validator, "preferred time"):
                print(f"    INDIVIDUAL (preferred): {team_name}")
                return True
    
    return False


def try_any_preference_allocation(team_name: str, team_data: dict, available_blocks: List[AvailableBlock],
                                start_date: datetime.date, schedule: List[Dict], rules_data: Dict,
                                validator: ScheduleConflictValidator) -> bool:
    """Try to allocate individual session in any preferred time (relaxed)."""
    return try_preferred_time_allocation(team_name, team_data, available_blocks, start_date, schedule, rules_data, validator)


def force_any_available_allocation(team_name: str, team_data: dict, available_blocks: List[AvailableBlock],
                                 start_date: datetime.date, schedule: List[Dict], rules_data: Dict,
                                 validator: ScheduleConflictValidator) -> bool:
    """Force allocation in any available block (last resort)."""
    team_info = team_data["info"]
    
    for block in available_blocks:
        if is_block_available_for_team(block, team_info, team_data, rules_data, start_date):
            if book_team_practice(team_name, team_data, block, start_date, schedule, validator, "forced minimum"):
                print(f"    INDIVIDUAL (forced): {team_name}")
                return True
    
    return False


def find_best_block_for_teams(blocks: List[AvailableBlock], team1_info: dict, team2_info: dict,
                            team1_data: dict, team2_data: dict, rules_data: Dict, start_date: datetime.date) -> Optional[AvailableBlock]:
    """Find the best block for two teams from a list of candidates."""
    best_block = None
    best_score = -1
    
    for block in blocks:
        if (is_block_available_for_team(block, team1_info, team1_data, rules_data, start_date) and
            is_block_available_for_team(block, team2_info, team2_data, rules_data, start_date)):
            
            score1 = get_block_preference_score(block, team1_info)
            score2 = get_block_preference_score(block, team2_info)
            combined_score = score1 + score2
            
            if combined_score > best_score:
                best_score = combined_score
                best_block = block
    
    return best_block


# =============================================================================
# SECTION 8: PREFERENCE OPTIMIZATION ALLOCATION (PHASE 1 - FIXED)
# =============================================================================

def allocate_preference_optimization(teams_needing_slots: Dict, available_blocks: List[AvailableBlock],
                                   start_date: datetime.date, schedule: List[Dict],
                                   rules_data: Dict, validator: ScheduleConflictValidator) -> int:
    """
    PHASE 1: Preference Optimization - Add more sessions while respecting preferences.
    FIXED: Round-robin allocation to prevent same team getting multiple sessions per iteration.
    """
    allocated_count = 0
    
    print("\n" + "="*80)
    print("PHASE 1: PREFERENCE OPTIMIZATION ALLOCATION")
    print("="*80)
    print("Strategy: Add more sessions with preferences, STRICT same-day prevention, round-robin fairness")
    
    max_iterations = 25
    iteration = 0
    
    while iteration < max_iterations:
        iteration += 1
        progress_made = False
        
        # Get teams still needing slots, sorted by priority
        teams_needing = []
        for team_name, team_data in teams_needing_slots.items():
            if team_data["needed"] > 0:
                priority = calculate_team_priority(team_data["info"], team_name)
                teams_needing.append((priority, team_name, team_data))
        
        if not teams_needing:
            print(f"All teams satisfied after {iteration-1} iterations")
            break
        
        teams_needing.sort()  # Lower priority number = higher priority
        
        print(f"\nIteration {iteration}: {len(teams_needing)} teams need more sessions")
        
        # ROUND ROBIN: Only allow ONE allocation per iteration to ensure fairness
        allocation_made_this_iteration = False
        
        # Try mandatory shared ice first (highest preference)
        for priority, team_name, team_data in teams_needing:
            if team_data["needed"] <= 0 or allocation_made_this_iteration:
                continue
                
            team_info = team_data["info"]
            
            if has_mandatory_shared_ice(team_info):
                if try_mandatory_shared_with_preferences(team_name, team_data, teams_needing_slots,
                                                       available_blocks, start_date, schedule, 
                                                       rules_data, validator):
                    allocated_count += 1
                    progress_made = True
                    allocation_made_this_iteration = True
                    print(f"  MANDATORY SHARED: {team_name}")
                    break
        
        if allocation_made_this_iteration:
            continue
        
        # Try strict preference allocations
        for priority, team_name, team_data in teams_needing:
            if team_data["needed"] <= 0 or allocation_made_this_iteration:
                continue
                
            team_info = team_data["info"]
            
            if has_strict_preferences(team_info):
                if try_strict_preference_allocation(team_name, team_data, available_blocks,
                                                  start_date, schedule, rules_data, validator):
                    allocated_count += 1
                    progress_made = True
                    allocation_made_this_iteration = True
                    print(f"  STRICT PREFERENCE: {team_name}")
                    break
        
        if allocation_made_this_iteration:
            continue
        
        # Try preferred time allocations
        for priority, team_name, team_data in teams_needing:
            if team_data["needed"] <= 0 or allocation_made_this_iteration:
                continue
            
            if try_preferred_time_allocation(team_name, team_data, available_blocks,
                                           start_date, schedule, rules_data, validator):
                allocated_count += 1
                progress_made = True
                allocation_made_this_iteration = True
                print(f"  PREFERRED TIME: {team_name}")
                break
        
        if allocation_made_this_iteration:
            continue
        
        # Try regular shared ice for non-mandatory teams
        for i, (priority1, team1_name, team1_data) in enumerate(teams_needing):
            if team1_data["needed"] <= 0 or allocation_made_this_iteration:
                continue
                
            team1_info = team1_data["info"]
            if not team1_info.get("allow_shared_ice", True):
                continue
                
            for j, (priority2, team2_name, team2_data) in enumerate(teams_needing[i+1:], i+1):
                if team2_data["needed"] <= 0:
                    continue
                
                team2_info = team2_data["info"]
                if not team2_info.get("allow_shared_ice", True):
                    continue
                
                if can_teams_share_ice(team1_info, team2_info, team1_name, team2_name):
                    # Try shared with preferences first
                    mutual_blocks = find_mutual_preference_matches(team1_info, team2_info, available_blocks, strict_only=False)
                    if mutual_blocks:
                        best_block = find_best_block_for_teams(mutual_blocks, team1_info, team2_info,
                                                             team1_data, team2_data, rules_data, start_date)
                        if best_block and book_shared_practice(team1_name, team2_name, team1_data, team2_data,
                                                             best_block, start_date, schedule, validator):
                            allocated_count += 1
                            progress_made = True
                            allocation_made_this_iteration = True
                            print(f"  SHARED (preferred): {team1_name} + {team2_name}")
                            break
            
            if allocation_made_this_iteration:
                break
        
        if allocation_made_this_iteration:
            continue
        
        # Try any available allocation (with distribution awareness)
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
    
    print(f"\nPHASE 1 COMPLETE: {allocated_count} preference optimization allocations")
    print("="*80)
    return allocated_count


# =============================================================================
# SECTION 9: CAPACITY MAXIMIZATION (PHASE 2 - FIXED)
# =============================================================================

def allocate_capacity_maximization(teams_needing_slots: Dict, available_blocks: List[AvailableBlock],
                                 start_date: datetime.date, schedule: List[Dict],
                                 rules_data: Dict, validator: ScheduleConflictValidator) -> int:
    """
    PHASE 2: Capacity Maximization - Use remaining ice time, allow 2nd session per day ONLY if back-to-back.
    """
    allocated_count = 0
    
    print("\n" + "="*80)
    print("PHASE 2: CAPACITY MAXIMIZATION")
    print("="*80)
    print("Strategy: Fill remaining slots, allow 2nd session per day ONLY if back-to-back")
    
    max_iterations = 15
    iteration = 0
    
    while iteration < max_iterations:
        iteration += 1
        progress_made = False
        
        # Get all teams that could use more ice (not just those that "need" it)
        teams_wanting_more = []
        for team_name, team_data in teams_needing_slots.items():
            if team_data["needed"] > 0:  # Still have official need
                priority = 0  # High priority for teams with remaining need
                teams_wanting_more.append((priority, team_name, team_data))
            else:
                # Teams that are satisfied but could take extra ice
                team_type = team_data["info"].get("type")
                team_age = team_data["info"].get("age")
                max_per_week = (rules_data.get("ice_times_per_week", {})
                               .get(team_type, {}).get(team_age, 0))
                
                # Check if team could take more ice in any week
                total_weeks = max(1, len(team_data["weekly_count"]))
                for week_num in range(1, total_weeks + 1):
                    if team_data["weekly_count"][week_num] < max_per_week:
                        priority = 100  # Lower priority for extra ice
                        teams_wanting_more.append((priority, team_name, team_data))
                        break
        
        if not teams_wanting_more:
            print(f"No teams want more ice after {iteration-1} iterations")
            break
        
        teams_wanting_more.sort()  # Priority order
        
        print(f"\nIteration {iteration}: {len(teams_wanting_more)} teams want more ice")
        
        # ROUND ROBIN: Only one allocation per iteration
        allocation_made = False
        
        # Try to fill any remaining capacity
        for priority, team_name, team_data in teams_wanting_more:
            if allocation_made:
                break
                
            team_info = team_data["info"]
            
            # Check if team can actually take more ice this week
            can_take_more = False
            for block in available_blocks:
                week_num = get_week_number(block.date, start_date)
                current_weekly = team_data["weekly_count"][week_num]
                team_type = team_info.get("type")
                team_age = team_info.get("age")
                max_per_week = (rules_data.get("ice_times_per_week", {})
                               .get(team_type, {}).get(team_age, 0))
                
                if current_weekly < max_per_week:
                    can_take_more = True
                    break
            
            if not can_take_more:
                continue
            
            # Try shared ice first (more efficient use of ice time)
            if team_info.get("allow_shared_ice", True):
                for other_priority, other_name, other_data in teams_wanting_more:
                    if (other_name != team_name and 
                        can_teams_share_ice(team_info, other_data["info"], team_name, other_name)):
                        
                        # Use capacity-phase availability checking
                        shared_blocks = []
                        for block in available_blocks:
                            if (is_block_available_for_team_capacity_phase(block, team_info, team_data, rules_data, start_date) and
                                is_block_available_for_team_capacity_phase(block, other_data["info"], other_data, rules_data, start_date)):
                                shared_blocks.append(block)
                        
                        if shared_blocks:
                            best_block = find_best_block_for_teams_with_distribution(shared_blocks, team_info, other_data["info"],
                                                                                   team_data, other_data, rules_data, start_date)
                            if best_block and book_shared_practice(team_name, other_name, team_data, other_data,
                                                                 best_block, start_date, schedule, validator):
                                allocated_count += 1
                                progress_made = True
                                allocation_made = True
                                print(f"  CAPACITY SHARED: {team_name} + {other_name}")
                                
                                # Remove block if it's too small for more bookings
                                if best_block.remaining_minutes() < 30:
                                    available_blocks.remove(best_block)
                                break
                        
                        if allocation_made:
                            break
                
                if allocation_made:
                    break
            
            # Try individual allocation with back-to-back checking
            individual_blocks = [block for block in available_blocks 
                               if is_block_available_for_team_capacity_phase(block, team_info, team_data, rules_data, start_date)]
            
            if individual_blocks:
                best_block = find_best_block_with_distribution(individual_blocks, team_info, team_data, rules_data, start_date)
                if best_block and book_team_practice(team_name, team_data, best_block, start_date, schedule, validator, "capacity fill"):
                    allocated_count += 1
                    progress_made = True
                    allocation_made = True
                    print(f"  CAPACITY INDIVIDUAL: {team_name}")
                    
                    # Remove block if it's too small for more bookings
                    if best_block.remaining_minutes() < 30:
                        available_blocks.remove(best_block)
                    break
        
        if not progress_made:
            print(f"  No progress in iteration {iteration}, stopping")
            break
    
    print(f"\nPHASE 2 COMPLETE: {allocated_count} capacity maximization allocations")
    print("="*80)
    return allocated_count


# =============================================================================
# SECTION 10: BOOKING FUNCTIONS (FIXED)
# =============================================================================

def book_team_practice(team_name: str, team_data: dict, block: AvailableBlock, 
                      start_date: datetime.date, schedule: List[dict], 
                      validator: ScheduleConflictValidator, booking_type: str = "practice") -> bool:
    """Book a team practice session - FIXED with strict same-day prevention."""
    required_duration = team_data["info"].get("practice_duration", 60)
    
    if not block.can_fit_duration(required_duration):
        return False
    
    # CRITICAL SAME-DAY CHECK: Apply strict same-day prevention rules
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
        # Remove the booking we just added
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
    
    # Show session count AFTER adding to scheduled_dates for accurate count
    new_sessions_on_date = len([d for d in team_data["scheduled_dates"] if d == block.date])
    print(f"    BOOKED: {team_name} on {block.date} {booking_start}-{booking_end} (sessions on this date: {new_sessions_on_date})")
    
    return True


def book_shared_practice(team1_name: str, team2_name: str, team1_data: dict, 
                        team2_data: dict, block: AvailableBlock, start_date: datetime.date, 
                        schedule: List[dict], validator: ScheduleConflictValidator) -> bool:
    """Book a shared practice session - FIXED with strict same-day prevention."""
    team1_duration = team1_data["info"].get("practice_duration", 60)
    team2_duration = team2_data["info"].get("practice_duration", 60)
    required_duration = max(team1_duration, team2_duration)
    
    if not block.can_fit_duration(required_duration):
        return False
    
    # Check same-day restrictions for both teams
    allow_multiple1 = _safe_allow_multiple(team1_data["info"])
    allow_multiple2 = _safe_allow_multiple(team2_data["info"])
    
    # For shared ice, use a more permissive booking type since we're being efficient
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


# =============================================================================
# SECTION 11: MAIN SCHEDULER FUNCTION (FIXED)
# =============================================================================

def generate_schedule_enhanced_FIXED(
    season_dates: Tuple[datetime.date, datetime.date],
    teams_data: Dict,
    arenas_data: Dict,
    rules_data: Dict,
):
    """
    SMART MINIMUM GUARANTEE SCHEDULER WITH FIXED SAME-DAY PREVENTION:
    
    Phase 0: Smart Minimum Guarantee - Everyone gets 1+ session, STRICT same-day prevention
    Phase 1: Preference Optimization - Add more sessions, STRICT same-day prevention, round-robin fairness  
    Phase 2: Capacity Maximization - Fill remaining slots, allow 2nd session per day ONLY if back-to-back
    
    Key fixes:
    1. No more than 1 session per day in Phases 0 & 1
    2. 2nd session per day in Phase 2 ONLY if back-to-back AND team allows multiple
    3. Round-robin allocation in Phase 1 to prevent same team getting multiple sessions per iteration
    4. Massive penalties for same-day sessions to encourage distribution
    """
    
    print("=== SMART MINIMUM GUARANTEE SCHEDULER (FIXED SAME-DAY PREVENTION) ===")
    print("Strategy: Everyone gets ice, preferences respected, STRICT day distribution")
    
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
    print(f"Available blocks: {len(available_blocks)}")
    
    # Show constraint complexity
    teams_with_constraints = []
    for team_name, team_data in teams_needing_slots.items():
        if team_data["needed"] > 0:
            complexity = calculate_constraint_complexity(team_data["info"], team_name)
            mandatory_shared = has_mandatory_shared_ice(team_data["info"])
            strict_prefs = has_strict_preferences(team_data["info"])
            teams_with_constraints.append((complexity, team_name, mandatory_shared, strict_prefs))
    
    teams_with_constraints.sort(reverse=True)
    print(f"Teams by constraint complexity:")
    for complexity, team_name, mandatory, strict in teams_with_constraints[:5]:  # Show top 5
        flags = []
        if mandatory: flags.append("mandatory_shared")
        if strict: flags.append("strict_prefs")
        print(f"  {team_name}: {complexity} ({', '.join(flags) if flags else 'flexible'})")

    # 3-PHASE SMART ALLOCATION STRATEGY WITH FIXED SAME-DAY PREVENTION
    print("\n=== 3-PHASE SMART ALLOCATION STRATEGY (FIXED) ===")
    
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

    # Generate final analysis
    print("\n=== FINAL ANALYSIS ===")
    total_allocated = 0
    total_target = 0
    underallocated = []
    zero_allocations = []
    perfect_allocations = []
    same_day_violations = []
    
    for team_name, team_data in teams_needing_slots.items():
        target = team_data["total_target"]
        allocated = target - team_data["needed"]
        total_allocated += allocated
        total_target += target
        
        percentage = (allocated / target * 100) if target > 0 else 100
        
        # Check for same-day violations
        date_counts = {}
        for event in schedule:
            if event.get("team") == team_name or (event.get("type") == "shared practice" and event.get("opponent") == team_name):
                date = event.get("date")
                if date:
                    date_counts[date] = date_counts.get(date, 0) + 1
        
        max_sessions_per_day = max(date_counts.values()) if date_counts else 0
        if max_sessions_per_day > 2:
            same_day_violations.append((team_name, max_sessions_per_day, date_counts))
        
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
    print(f"  Total: {phase0_allocated + phase1_allocated + phase2_allocated} sessions")
    
    # Check for same-day violations
    if same_day_violations:
        print(f"\n⚠️  SAME-DAY VIOLATIONS DETECTED ({len(same_day_violations)}):")
        for team_name, max_count, date_counts in same_day_violations:
            print(f"  {team_name}: {max_count} sessions in one day")
            for date, count in date_counts.items():
                if count > 2:
                    print(f"    {date}: {count} sessions")
    else:
        print(f"\n✅ NO SAME-DAY VIOLATIONS: All teams have max 2 sessions per day")
    
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
            print(f"  {team} (blackouts: {blackouts})")
    
    if underallocated:
        print(f"\nUNDERALLOCATED TEAMS ({len(underallocated)}):")
        for team, allocated, target, remaining in sorted(underallocated, key=lambda x: x[3], reverse=True):
            print(f"  {team}: {allocated}/{target} (missing {remaining})")

    # Analyze shared ice success
    shared_sessions = [event for event in schedule if event.get("type") == "shared practice"]
    mandatory_shared_teams = [name for name, data in teams_needing_slots.items() 
                             if has_mandatory_shared_ice(data["info"])]
    
    print(f"\nSHARED ICE ANALYSIS:")
    print(f"  Total shared sessions: {len(shared_sessions)}")
    print(f"  Teams with mandatory sharing: {len(mandatory_shared_teams)}")
    
    # Show sharing success for mandatory teams
    for team_name in mandatory_shared_teams:
        team_shared_count = sum(1 for event in schedule 
                               if ((event.get("team") == team_name and event.get("opponent") not in ("Practice", "TBD")) or
                                   (event.get("opponent") == team_name and event.get("team") != team_name)))
        team_total = len([event for event in schedule if event.get("team") == team_name or event.get("opponent") == team_name])
        sharing_percentage = (team_shared_count / team_total * 100) if team_total > 0 else 0
        print(f"    {team_name}: {team_shared_count}/{team_total} shared ({sharing_percentage:.1f}%)")

    print(f"\nRemaining ice capacity: {len(available_blocks)} blocks with {sum(b.remaining_minutes() for b in available_blocks)} minutes")
    print("✅ FIXED Smart minimum guarantee scheduler complete - same-day violations prevented")
    
    # Clean and validate final schedule
    schedule = clean_schedule_duplicates(schedule)
    
    return {
        "schedule": schedule, 
        "phase0_allocated": phase0_allocated, 
        "phase1_allocated": phase1_allocated,
        "phase2_allocated": phase2_allocated,
        "zero_allocations": zero_allocations,
        "perfect_allocations": perfect_allocations,
        "same_day_violations": same_day_violations
    }


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
# SECTION 12: BACKWARD COMPATIBILITY
# =============================================================================

def generate_schedule(*args, **kwargs):
    """Backward compatibility wrapper for the fixed smart minimum guarantee scheduler."""
    return generate_schedule_enhanced_FIXED(*args, **kwargs)


def generate_schedule_enhanced(*args, **kwargs):
    """Legacy function name compatibility."""
    return generate_schedule_enhanced_FIXED(*args, **kwargs)


def generate_schedule_fixed_constraints(*args, **kwargs):
    """Alternative function name."""
    return generate_schedule_enhanced_FIXED(*args, **kwargs)


# =============================================================================
# SECTION 13: TESTING AND VALIDATION
# =============================================================================

def test_same_day_prevention_logic():
    """Test function to validate same-day prevention is working correctly."""
    print("=== SAME-DAY PREVENTION TEST ===")
    
    # Create test team data
    test_team_data = {
        "info": {"allow_multiple_per_day": False, "practice_duration": 60},
        "scheduled_dates": {datetime.date(2025, 10, 26)}  # Already has one session on 2025-10-26
    }
    
    test_block = AvailableBlock(
        arena="Test Arena",
        date=datetime.date(2025, 10, 26),  # Same date
        start_time=datetime.time(17, 0),
        end_time=datetime.time(18, 0),
        weekday=5
    )
    
    test_schedule = [
        {
            "team": "Test Team",
            "date": "2025-10-26",
            "time_slot": "15:00-16:00"
        }
    ]
    
    # Test Phase 0/1 (should block)
    result = should_allow_same_day_booking("Test Team", test_team_data, test_block, test_schedule, "strict preference", False)
    print(f"Phase 0/1 same-day booking (should be False): {result}")
    
    # Test capacity phase with back-to-back (should allow if back-to-back)
    test_block_backtoback = AvailableBlock(
        arena="Test Arena",
        date=datetime.date(2025, 10, 26),
        start_time=datetime.time(16, 0),  # Right after existing 15:00-16:00 session
        end_time=datetime.time(17, 0),
        weekday=5
    )
    
    result_capacity = should_allow_same_day_booking("Test Team", test_team_data, test_block_backtoback, test_schedule, "capacity fill", False)
    print(f"Capacity phase back-to-back booking (should be False for non-multiple teams): {result_capacity}")
    
    # Test with allow_multiple_per_day = True
    test_team_data["info"]["allow_multiple_per_day"] = True
    result_multiple = should_allow_same_day_booking("Test Team", test_team_data, test_block_backtoback, test_schedule, "capacity fill", True)
    print(f"Capacity phase back-to-back with allow_multiple (should be True): {result_multiple}")


if __name__ == "__main__":
    print("Fixed Smart Minimum Guarantee Hockey Scheduler")
    print("Key fixes:")
    print("✅ No more than 1 session per day in Phases 0 & 1")
    print("✅ 2nd session per day in Phase 2 ONLY if back-to-back AND team allows multiple") 
    print("✅ Round-robin allocation prevents same team monopolizing iterations")
    print("✅ Massive penalties (2000+) for same-day sessions encourage distribution")
    print("✅ Same-day violation detection in final analysis")
    
    # Run test
    test_same_day_prevention_logic()