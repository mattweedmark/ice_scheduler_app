"""
Complete pipeline step implementations and configuration.
"""

import random
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple, Set
from collections import defaultdict

# Import the existing scheduler logic functions
try:
    # The file is named enhanced_scheduler_logic(1).py in the documents
    import sys
    import os
    
    # Try to import from the actual file name
    if 'enhanced_scheduler_logic' not in sys.modules:
        # Import the enhanced scheduler functions
        current_dir = os.path.dirname(__file__)
        enhanced_path = os.path.join(current_dir, 'enhanced_scheduler_logic(1).py')
        if os.path.exists(enhanced_path):
            import importlib.util
            spec = importlib.util.spec_from_file_location("enhanced_scheduler_logic", enhanced_path)
            enhanced_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(enhanced_module)
            sys.modules['enhanced_scheduler_logic'] = enhanced_module
    
    from scheduler_logic import (
        allocate_strict_preference_mandatory_shared_ice,
        allocate_strict_preference_individual,
        allocate_preferred_time_mandatory_shared_ice,
        allocate_high_priority_individual,
        allocate_regular_shared_ice_aggressive,
        allocate_remaining_individual_slots,
        allocate_emergency_shared_ice_enhanced,
        allocate_final_aggressive_fill
    )
    ENHANCED_SCHEDULER_AVAILABLE = True
except ImportError:
    ENHANCED_SCHEDULER_AVAILABLE = False

class PipelineStepResult:
    """Result object returned by each pipeline step"""
    def __init__(self, allocated_count: int = 0, step_name: str = "", 
                 success: bool = True, message: str = "", details: Dict = None):
        self.allocated_count = allocated_count
        self.step_name = step_name
        self.success = success
        self.message = message
        self.details = details or {}

# Pipeline step implementations that bridge to existing enhanced scheduler logic

def allocate_mandatory_shared_ice_comprehensive(teams_needing_slots, available_blocks, start_date, 
                                              schedule, rules_data, validator, **params):
    """
    Allocate ice for teams that require shared sessions (mandatory sharing).
    Uses the enhanced scheduler's strict preference mandatory shared ice logic.
    """
    if not ENHANCED_SCHEDULER_AVAILABLE:
        return PipelineStepResult(0, "Mandatory Shared Ice", False, "Enhanced scheduler not available")
    
    try:
        allocated_count = allocate_strict_preference_mandatory_shared_ice(
            teams_needing_slots, available_blocks, start_date, 
            schedule, rules_data, validator
        )
        
        return PipelineStepResult(
            allocated_count, 
            "Mandatory Shared Ice", 
            True, 
            f"Allocated {allocated_count} mandatory shared ice sessions",
            {"teams_processed": len([t for t in teams_needing_slots.values() 
                                   if t["info"].get("mandatory_shared_ice", False)])}
        )
    except Exception as e:
        return PipelineStepResult(0, "Mandatory Shared Ice", False, f"Error: {e}")

def allocate_high_priority_individual(teams_needing_slots, available_blocks, start_date, 
                                    schedule, rules_data, validator, **params):
    """
    Allocate individual ice slots for highest priority teams first.
    Uses the enhanced scheduler's strict preference individual logic.
    """
    if not ENHANCED_SCHEDULER_AVAILABLE:
        return PipelineStepResult(0, "High Priority Individual", False, "Enhanced scheduler not available")
    
    try:
        allocated_count = allocate_strict_preference_individual(
            teams_needing_slots, available_blocks, start_date, 
            schedule, rules_data, validator
        )
        
        return PipelineStepResult(
            allocated_count,
            "High-Priority Individual",
            True,
            f"Allocated {allocated_count} individual slots to high-priority teams",
            {"teams_processed": len([t for t in teams_needing_slots.values() if t["needed"] > 0])}
        )
    except Exception as e:
        return PipelineStepResult(0, "High Priority Individual", False, f"Error: {e}")

def allocate_shared_ice_optimization(teams_needing_slots, available_blocks, start_date,
                                   schedule, rules_data, validator, **params):
    """
    Optimize shared ice allocation for compatible teams.
    Uses the enhanced scheduler's preferred time mandatory shared ice logic.
    """
    if not ENHANCED_SCHEDULER_AVAILABLE:
        return PipelineStepResult(0, "Shared Ice Optimization", False, "Enhanced scheduler not available")
    
    try:
        allocated_count = allocate_preferred_time_mandatory_shared_ice(
            teams_needing_slots, available_blocks, start_date, 
            schedule, rules_data, validator
        )
        
        return PipelineStepResult(
            allocated_count,
            "Shared Ice Optimization",
            True,
            f"Allocated {allocated_count} optimized shared ice slots",
            {"sharing_groups": allocated_count}
        )
    except Exception as e:
        return PipelineStepResult(0, "Shared Ice Optimization", False, f"Error: {e}")

def allocate_remaining_individual_slots(teams_needing_slots, available_blocks, start_date,
                                      schedule, rules_data, validator, **params):
    """
    Fill remaining individual ice needs for teams that haven't been allocated yet.
    Uses the enhanced scheduler's high priority individual logic.
    """
    if not ENHANCED_SCHEDULER_AVAILABLE:
        return PipelineStepResult(0, "Remaining Individual", False, "Enhanced scheduler not available")
    
    try:
        allocated_count = allocate_high_priority_individual(
            teams_needing_slots, available_blocks, start_date, 
            schedule, rules_data, validator
        )
        
        return PipelineStepResult(
            allocated_count,
            "Remaining Individual Slots",
            True,
            f"Allocated {allocated_count} remaining individual slots",
            {"teams_processed": len([t for t in teams_needing_slots.values() if t["needed"] > 0])}
        )
    except Exception as e:
        return PipelineStepResult(0, "Remaining Individual", False, f"Error: {e}")

def allocate_emergency_shared_ice(teams_needing_slots, available_blocks, start_date,
                                schedule, rules_data, validator, **params):
    """
    Emergency allocation with relaxed rules for underallocated teams.
    Uses the enhanced scheduler's emergency shared ice logic.
    """
    if not ENHANCED_SCHEDULER_AVAILABLE:
        return PipelineStepResult(0, "Emergency Shared Ice", False, "Enhanced scheduler not available")
    
    try:
        allocated_count = allocate_emergency_shared_ice_enhanced(
            teams_needing_slots, available_blocks, start_date, 
            schedule, rules_data, True, validator
        )
        
        return PipelineStepResult(
            allocated_count,
            "Emergency Shared Ice",
            True,
            f"Emergency allocated {allocated_count} shared ice slots",
            {"teams_remaining": len([t for t in teams_needing_slots.values() if t["needed"] > 0])}
        )
    except Exception as e:
        return PipelineStepResult(0, "Emergency Shared Ice", False, f"Error: {e}")

def allocate_final_aggressive_fill(teams_needing_slots, available_blocks, start_date,
                                 schedule, rules_data, validator, **params):
    """
    Final aggressive allocation that ignores most constraints to maximize allocation.
    Uses the enhanced scheduler's final aggressive fill logic.
    """
    if not ENHANCED_SCHEDULER_AVAILABLE:
        return PipelineStepResult(0, "Final Aggressive Fill", False, "Enhanced scheduler not available")
    
    try:
        allocated_count = allocate_final_aggressive_fill(
            teams_needing_slots, available_blocks, start_date, 
            schedule, rules_data, validator
        )
        
        unallocated_count = len([t for t in teams_needing_slots.values() if t["needed"] > 0])
        
        return PipelineStepResult(
            allocated_count,
            "Final Aggressive Fill",
            unallocated_count == 0,
            f"Final allocation: {allocated_count} slots, {unallocated_count} teams still unallocated",
            {"teams_unallocated": unallocated_count, "aggressive_slots": allocated_count}
        )
    except Exception as e:
        return PipelineStepResult(0, "Final Aggressive Fill", False, f"Error: {e}")

# Pipeline step registry
PIPELINE_STEPS = {
    "mandatory_shared_ice": allocate_mandatory_shared_ice_comprehensive,
    "high_priority_individual": allocate_high_priority_individual,
    "shared_ice_optimization": allocate_shared_ice_optimization,
    "remaining_individual": allocate_remaining_individual_slots,
    "emergency_shared": allocate_emergency_shared_ice,
    "final_aggressive": allocate_final_aggressive_fill,
}

def get_default_pipeline_config():
    """Get the default pipeline configuration."""
    return {
        "pipeline_name": "Default Hockey Scheduler",
        "version": "1.0",
        "steps": [
            {
                "id": "mandatory_shared_ice",
                "name": "Mandatory Shared Ice Allocation",
                "description": "Allocate ice for teams requiring shared sessions with strict preferences",
                "enabled": True,
                "priority": 1,
                "critical": False,
                "parameters": {
                    "max_age_difference": 2,
                    "strict_compatibility": True
                }
            },
            {
                "id": "high_priority_individual",
                "name": "High-Priority Individual Slots",
                "description": "Allocate individual ice for highest priority teams with strict preferences",
                "enabled": True,
                "priority": 2,
                "critical": False,
                "parameters": {
                    "strict_preferences_only": True,
                    "priority_threshold": 8
                }
            },
            {
                "id": "shared_ice_optimization", 
                "name": "Shared Ice Optimization",
                "description": "Optimize shared ice allocation for compatible teams with preferred times",
                "enabled": True,
                "priority": 3,
                "critical": False,
                "parameters": {
                    "max_age_difference": 3,
                    "min_compatibility_score": 0.6
                }
            },
            {
                "id": "remaining_individual",
                "name": "Remaining Individual Slots",
                "description": "Fill remaining individual ice needs with flexible constraints",
                "enabled": True,
                "priority": 4,
                "critical": False,
                "parameters": {
                    "allow_suboptimal_times": True,
                    "priority_weight": 0.3
                }
            },
            {
                "id": "emergency_shared",
                "name": "Emergency Shared Ice",
                "description": "Emergency allocation with relaxed rules for underallocated teams",
                "enabled": True,
                "priority": 5,
                "critical": False,
                "parameters": {
                    "relax_age_restrictions": True,
                    "max_teams_per_emergency_slot": 6
                }
            },
            {
                "id": "final_aggressive",
                "name": "Final Aggressive Fill",
                "description": "Final allocation ignoring most constraints to maximize allocation",
                "enabled": True,
                "priority": 6,
                "critical": False,
                "parameters": {
                    "ignore_preferences": True,
                    "max_teams_per_slot": 8
                }
            }
        ],
        "global_settings": {
            "allocation_timeout_seconds": 300,
            "emergency_mode_threshold": 0.8,
            "max_iterations_per_step": 1000
        }
    }

def get_step_parameter_definitions():
    """Get parameter definitions for all pipeline steps."""
    return {
        "mandatory_shared_ice": {
            "max_age_difference": {
                "type": "integer",
                "label": "Max Age Difference",
                "description": "Maximum age difference between teams for shared ice",
                "default": 2,
                "min": 1,
                "max": 5
            },
            "strict_compatibility": {
                "type": "boolean", 
                "label": "Strict Compatibility",
                "description": "Require strict compatibility rules for team pairing",
                "default": True
            }
        },
        "high_priority_individual": {
            "strict_preferences_only": {
                "type": "boolean",
                "label": "Strict Preferences Only",
                "description": "Only allocate times that match strict preferences",
                "default": True
            },
            "priority_threshold": {
                "type": "integer",
                "label": "Priority Threshold", 
                "description": "Minimum priority score for high-priority treatment",
                "default": 8,
                "min": 1,
                "max": 10
            }
        },
        "shared_ice_optimization": {
            "max_age_difference": {
                "type": "integer",
                "label": "Max Age Difference",
                "description": "Maximum age difference for shared ice optimization",
                "default": 3,
                "min": 1,
                "max": 5
            },
            "min_compatibility_score": {
                "type": "float",
                "label": "Min Compatibility Score",
                "description": "Minimum compatibility score (0.0-1.0)",
                "default": 0.6,
                "min": 0.0,
                "max": 1.0
            }
        },
        "remaining_individual": {
            "allow_suboptimal_times": {
                "type": "boolean",
                "label": "Allow Suboptimal Times",
                "description": "Allow allocation to non-preferred time slots",
                "default": True
            },
            "priority_weight": {
                "type": "float",
                "label": "Priority Weight",
                "description": "Weight factor for team priority (0.0-1.0)",
                "default": 0.3,
                "min": 0.0,
                "max": 1.0
            }
        },
        "emergency_shared": {
            "relax_age_restrictions": {
                "type": "boolean",
                "label": "Relax Age Restrictions",
                "description": "Allow larger age gaps in emergency situations",
                "default": True
            },
            "max_teams_per_emergency_slot": {
                "type": "integer",
                "label": "Max Teams per Emergency Slot",
                "description": "Maximum teams that can share emergency ice time",
                "default": 6,
                "min": 2,
                "max": 10
            }
        },
        "final_aggressive": {
            "ignore_preferences": {
                "type": "boolean",
                "label": "Ignore Preferences",
                "description": "Ignore team preferences in final allocation",
                "default": True
            },
            "max_teams_per_slot": {
                "type": "integer",
                "label": "Max Teams per Slot",
                "description": "Maximum teams per final allocation slot",
                "default": 8,
                "min": 1,
                "max": 12
            }
        }
    }
