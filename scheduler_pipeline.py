import datetime
import time
from collections import defaultdict

# FIXED: Import from the correct scheduler logic files
try:
    from scheduler_logic import (
        ScheduleConflictValidator, AvailableBlock, normalize_team_info,
        _parse_date, get_week_number, analyze_team_allocation, 
        format_allocation_message, clean_schedule_duplicates
    )
    ENHANCED_SCHEDULER_AVAILABLE = True
    print("Scheduler logic imported successfully from scheduler_logic.py")
except ImportError as e:
    print(f"Scheduler logic not available: {e}")
    ENHANCED_SCHEDULER_AVAILABLE = False
    
    # Create minimal implementations if nothing is available
    class ScheduleConflictValidator:
        def __init__(self):
            pass
        def add_existing_schedule(self, schedule):
            pass
        def validate_booking(self, team, arena, date, time_slot):
            return True, []
    
    class AvailableBlock:
        def __init__(self, arena, date, start_time, end_time, weekday, slot_type="practice"):
            self.arena = arena
            self.date = date
            self.start_time = start_time
            self.end_time = end_time
            self.weekday = weekday
            self.slot_type = slot_type
            self.bookings = []
        
        def duration_minutes(self):
            start_dt = datetime.datetime.combine(datetime.date.min, self.start_time)
            end_dt = datetime.datetime.combine(datetime.date.min, self.end_time)
            return int((end_dt - start_dt).total_seconds() / 60)
    
    def normalize_team_info(team_info):
        return team_info
    
    def _parse_date(date_str):
        if isinstance(date_str, datetime.date):
            return date_str
        return datetime.date.fromisoformat(str(date_str))
    
    def get_week_number(date, start_date):
        return ((date - start_date).days // 7) + 1
    
    def analyze_team_allocation(teams_needing_slots, start_date, end_date, rules_data, schedule):
        return {"allocation_details": {}, "underallocated_teams": [], "total_weeks": 1}
    
    def format_allocation_message(allocation_summary):
        return "Allocation complete"
    
    def clean_schedule_duplicates(schedule):
        return schedule

from pipeline_steps import get_default_pipeline_config, PIPELINE_STEPS

class SchedulingPipeline:
    """Main pipeline execution engine for configurable scheduling."""
    
    def __init__(self, config=None):
        self.config = config or get_default_pipeline_config()
        self.validator = None
        self.execution_log = []
        self.step_results = {}
        
    def execute(self, season_dates, teams_data, arenas_data, rules_data):
        """Execute the complete scheduling pipeline."""
        start_time = time.time()
        
        # Initialize
        self.validator = ScheduleConflictValidator()
        self.execution_log = []
        self.step_results = {}
        
        start_date, end_date = season_dates
        teams_data = {k: normalize_team_info(v) for k, v in (teams_data or {}).items()}
        schedule = []
        
        self._log(f"Starting pipeline execution with {len(teams_data)} teams and {len(arenas_data)} arenas")
        
        # Generate available blocks
        available_blocks = self._generate_available_blocks(
            season_dates, arenas_data, schedule
        )
        
        self._log(f"Generated {len(available_blocks)} available blocks")
        
        # Build team needs
        teams_needing_slots = self._build_team_needs(
            teams_data, rules_data, start_date, end_date, schedule
        )
        
        # Calculate shortage metrics
        total_demand = sum(t["needed"] for t in teams_needing_slots.values())
        total_supply_hours = sum(block.duration_minutes() for block in available_blocks) // 60
        shortage_level = total_demand / max(1, total_supply_hours)
        
        self._log(f"Pipeline starting - Demand: {total_demand}, Supply: ~{total_supply_hours}h, Shortage: {shortage_level:.2f}")
        
        # Execute enabled steps in priority order
        enabled_steps = [step for step in self.config["steps"] if step.get("enabled", True)]
        enabled_steps.sort(key=lambda x: x.get("priority", 999))
        
        total_allocated = 0
        
        for step in enabled_steps:
            step_start = time.time()
            
            try:
                result = self._execute_step(
                    step, teams_needing_slots, available_blocks, 
                    start_date, schedule, rules_data
                )
                
                step_time = time.time() - step_start
                allocated = result.allocated_count if hasattr(result, 'allocated_count') else result
                total_allocated += allocated
                
                self.step_results[step["id"]] = {
                    "allocated": allocated,
                    "execution_time": step_time,
                    "success": True,
                    "result": result
                }
                
                self._log(f"✓ {step['name']}: {allocated} allocations in {step_time:.2f}s")
                
                # Check for timeout
                timeout = self.config.get("global_settings", {}).get("allocation_timeout_seconds", 300)
                if time.time() - start_time > timeout:
                    self._log("⚠ Pipeline timeout reached, stopping execution")
                    break
                    
            except Exception as e:
                step_time = time.time() - step_start
                self.step_results[step["id"]] = {
                    "allocated": 0,
                    "execution_time": step_time,
                    "success": False,
                    "error": str(e)
                }
                
                self._log(f"✗ {step['name']}: FAILED - {e}")
                
                # Continue with next step unless it's a critical failure
                if step.get("critical", False):
                    break
        
        # Generate final analysis
        allocation_summary = analyze_team_allocation(
            teams_needing_slots, start_date, end_date, rules_data, schedule
        )
        
        # Clean up schedule
        schedule = clean_schedule_duplicates(schedule)
        
        # Final validation
        final_conflicts = self._validate_final_schedule(schedule)
        
        total_time = time.time() - start_time
        self._log(f"Pipeline completed in {total_time:.2f}s - {total_allocated} total allocations")
        
        return {
            "schedule": schedule,
            "allocation_summary": allocation_summary,
            "conflicts": final_conflicts,
            "execution_log": self.execution_log,
            "step_results": self.step_results,
            "pipeline_config": self.config,
            "execution_time": total_time
        }
    
    def _execute_step(self, step, teams_needing_slots, available_blocks, 
                     start_date, schedule, rules_data):
        """Execute a single pipeline step."""
        step_id = step["id"]
        step_params = step.get("parameters", {})
        
        # Get the step function
        step_func = PIPELINE_STEPS.get(step_id)
        if not step_func:
            raise ValueError(f"Unknown step function: {step_id}")
        
        # Execute the step with parameters
        result = step_func(
            teams_needing_slots=teams_needing_slots,
            available_blocks=available_blocks,
            start_date=start_date,
            schedule=schedule,
            rules_data=rules_data,
            validator=self.validator,
            **step_params
        )
        
        return result
    
    def _generate_available_blocks(self, season_dates, arenas_data, schedule):
        """Generate all available ice blocks for the season."""
        start_date, end_date = season_dates
        available_blocks = []
        
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
                                if team_name:  # Pre-assigned slot
                                    slot_type = slot.get("type")
                                    # Handle pre-assigned games and practices
                                    if slot_type == "game" or (not slot_type and slot.get("game_duration")):
                                        # Create game entry
                                        game_duration = slot.get("duration", slot.get("game_duration", 60))
                                        game_end_dt = datetime.datetime.combine(current_date, start_time) + datetime.timedelta(minutes=game_duration)
                                        game_end = game_end_dt.time()

                                        opponent = slot.get("opponent", "TBD")
                                        schedule.append({
                                            "team": team_name,
                                            "opponent": opponent,
                                            "arena": arena,
                                            "date": current_date.isoformat(),
                                            "time_slot": f"{start_time.strftime('%H:%M')}-{game_end.strftime('%H:%M')}",
                                            "type": "game",
                                        })

                                        # Add remaining time as available if any
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
                                        # Pre-assigned practice
                                        schedule.append({
                                            "team": team_name,
                                            "opponent": "Practice",
                                            "arena": arena,
                                            "date": current_date.isoformat(),
                                            "time_slot": f"{start_time.strftime('%H:%M')}-{end_time.strftime('%H:%M')}",
                                            "type": "practice",
                                        })
                                else:
                                    # Available ice - add as available block
                                    available_blocks.append(AvailableBlock(
                                        arena=arena,
                                        date=current_date,
                                        start_time=start_time,
                                        end_time=end_time,
                                        weekday=weekday,
                                        slot_type="practice"
                                    ))

                            except Exception as e:
                                self._log(f"Skipping invalid slot in {arena}: {slot} ({e})")
                    current_date += datetime.timedelta(days=1)
        
        return available_blocks
    
    def _build_team_needs(self, teams_data, rules_data, start_date, end_date, schedule):
        """Build the teams_needing_slots data structure."""
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
                "allocation_priority": self._calculate_team_priority(team_info, team_name),
            }
        
        # Update with existing schedule
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
        
        return teams_needing_slots
    
    def _calculate_team_priority(self, team_info, team_name):
        """Calculate allocation priority for teams (lower = higher priority)."""
        priority = 0
        
        # Age priority (younger teams get higher priority)
        age_match = None
        age_str = team_info.get("age", "")
        if age_str:
            import re
            age_match = re.search(r'(\d+)', age_str)
        
        if age_match:
            priority += int(age_match.group(1))
        else:
            priority += 50  # Unknown age gets low priority
        
        # Type priority
        team_type = team_info.get("type", "house")
        if team_type == "competitive":
            priority += 0  # Competitive gets higher priority
        else:
            priority += 10  # House teams get slightly lower priority
        
        # Mandatory shared ice gets highest priority
        if team_info.get("mandatory_shared_ice", False):
            priority -= 100
        
        return priority
    
    def _validate_final_schedule(self, schedule):
        """Validate the final schedule for conflicts."""
        validator = ScheduleConflictValidator()
        validator.add_existing_schedule(schedule)
        
        conflicts = []
        for entry in schedule:
            team = entry.get("team", "")
            arena = entry.get("arena", "")
            date = entry.get("date", "")
            time_slot = entry.get("time_slot", "")
            
            if all([team, arena, date, time_slot]):
                is_valid, entry_conflicts = validator.validate_booking(team, arena, date, time_slot)
                if not is_valid:
                    conflicts.extend(entry_conflicts)
        
        return conflicts
    
    def _log(self, message):
        """Add a message to the execution log."""
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        self.execution_log.append(log_entry)
        print(log_entry)  # Also print to console for debugging
    
    def get_execution_summary(self):
        """Get a summary of the pipeline execution."""
        if not self.step_results:
            return "Pipeline has not been executed yet."
        
        summary = []
        summary.append("Pipeline Execution Summary:")
        summary.append("=" * 40)
        
        total_allocated = 0
        total_time = 0
        successful_steps = 0
        
        for step_id, result in self.step_results.items():
            step_name = next((s["name"] for s in self.config["steps"] if s["id"] == step_id), step_id)
            
            allocated = result.get("allocated", 0)
            exec_time = result.get("execution_time", 0)
            success = result.get("success", False)
            
            total_allocated += allocated
            total_time += exec_time
            if success:
                successful_steps += 1
            
            status = "✓" if success else "✗"
            summary.append(f"{status} {step_name}: {allocated} allocations ({exec_time:.2f}s)")
            
            if not success and "error" in result:
                summary.append(f"    Error: {result['error']}")
        
        summary.append("-" * 40)
        summary.append(f"Total: {total_allocated} allocations in {total_time:.2f}s")
        summary.append(f"Success rate: {successful_steps}/{len(self.step_results)} steps")
        
        return "\n".join(summary)


def execute_pipeline_scheduling(season_dates, teams_data, arenas_data, rules_data, config=None):
    """
    Main entry point for pipeline-based scheduling.
    This replaces the original generate_schedule_enhanced function.
    """
    pipeline = SchedulingPipeline(config)
    result = pipeline.execute(season_dates, teams_data, arenas_data, rules_data)
    
    # Add execution summary to the result
    result["execution_summary"] = pipeline.get_execution_summary()
    
    return result


def validate_pipeline_config(config):
    """Validate a pipeline configuration."""
    errors = []
    warnings = []
    
    # Check required fields
    if "steps" not in config:
        errors.append("Configuration missing 'steps' field")
        return errors, warnings
    
    if not isinstance(config["steps"], list):
        errors.append("'steps' must be a list")
        return errors, warnings
    
    # Check steps
    step_ids = set()
    priorities = set()
    enabled_count = 0
    
    for i, step in enumerate(config["steps"]):
        if not isinstance(step, dict):
            errors.append(f"Step {i} is not a dictionary")
            continue
        
        # Check required fields
        required_fields = ["id", "name", "priority", "enabled"]
        for field in required_fields:
            if field not in step:
                errors.append(f"Step {i} missing required field '{field}'")
        
        # Check for duplicate IDs
        step_id = step.get("id")
        if step_id in step_ids:
            errors.append(f"Duplicate step ID: {step_id}")
        step_ids.add(step_id)
        
        # Check for duplicate priorities
        priority = step.get("priority")
        if priority in priorities:
            warnings.append(f"Duplicate priority {priority} for step {step_id}")
        priorities.add(priority)
        
        # Count enabled steps
        if step.get("enabled", True):
            enabled_count += 1
    
    # Check for at least one enabled step
    if enabled_count == 0:
        warnings.append("No steps are enabled - scheduling will not work")
    
    # Check global settings
    global_settings = config.get("global_settings", {})
    if "allocation_timeout_seconds" in global_settings:
        timeout = global_settings["allocation_timeout_seconds"]
        if not isinstance(timeout, (int, float)) or timeout <= 0:
            warnings.append("allocation_timeout_seconds should be a positive number")
    
    return errors, warnings