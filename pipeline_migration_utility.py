"""
Pipeline Configuration Migration Utility
Analyzes existing team data and creates appropriate pipeline configuration.
"""

import re
from collections import Counter
from pipeline_steps import get_default_pipeline_config
import datetime

def migrate_team_data_to_pipeline_config(teams_data, rules_data=None):
    """
    Analyze existing team data and create a pipeline configuration that matches
    the team-level settings and preferences.
    
    Args:
        teams_data (dict): Dictionary of team configurations
        rules_data (dict): Optional rules data for additional context
        
    Returns:
        dict: Pipeline configuration optimized for the team data
    """
    
    # Start with default configuration
    pipeline_config = get_default_pipeline_config()
    
    # Analyze team data patterns
    analysis = analyze_team_patterns(teams_data)
    
    # Configure pipeline based on analysis
    configure_pipeline_from_analysis(pipeline_config, analysis, teams_data)
    
    return pipeline_config

def analyze_team_patterns(teams_data):
    """Analyze patterns in team data to determine appropriate pipeline configuration."""
    
    analysis = {
        'total_teams': len(teams_data),
        'teams_with_mandatory_shared': [],
        'teams_with_strict_preferences': [],
        'teams_allowing_shared': [],
        'teams_disallowing_shared': [],
        'age_distribution': {},
        'type_distribution': {},
        'strict_preference_patterns': {},
        'shared_ice_demand': 0,
        'individual_ice_demand': 0,
        'late_cutoff_teams': [],
        'multiple_per_day_eligible': []
    }
    
    for team_name, team_info in teams_data.items():
        # Basic demographics
        team_type = team_info.get('type', 'house')
        team_age = team_info.get('age', 'unknown')
        
        analysis['type_distribution'][team_type] = analysis['type_distribution'].get(team_type, 0) + 1
        analysis['age_distribution'][team_age] = analysis['age_distribution'].get(team_age, 0) + 1
        
        # Shared ice analysis
        allow_shared = team_info.get('allow_shared_ice', True)
        mandatory_shared = team_info.get('mandatory_shared_ice', False)
        
        if mandatory_shared:
            analysis['teams_with_mandatory_shared'].append(team_name)
            analysis['shared_ice_demand'] += 1
        elif allow_shared:
            analysis['teams_allowing_shared'].append(team_name)
        else:
            analysis['teams_disallowing_shared'].append(team_name)
            analysis['individual_ice_demand'] += 1
        
        # Strict preferences analysis
        if has_strict_preferences_in_team(team_info):
            analysis['teams_with_strict_preferences'].append(team_name)
            
            # Analyze preference patterns
            prefs = team_info.get('preferred_days_and_times', {})
            for key, value in prefs.items():
                if key.endswith('_strict') and value:
                    day = key.replace('_strict', '')
                    if day not in analysis['strict_preference_patterns']:
                        analysis['strict_preference_patterns'][day] = 0
                    analysis['strict_preference_patterns'][day] += 1
        
        # Late cutoff analysis
        if team_info.get('late_ice_cutoff_enabled') or team_info.get('late_ice_cutoff'):
            analysis['late_cutoff_teams'].append(team_name)
        
        # Multiple per day eligibility
        if can_team_have_multiple_sessions(team_info, team_name):
            analysis['multiple_per_day_eligible'].append(team_name)
    
    # Calculate ratios
    analysis['shared_ice_ratio'] = len(analysis['teams_allowing_shared']) / max(1, analysis['total_teams'])
    analysis['strict_preference_ratio'] = len(analysis['teams_with_strict_preferences']) / max(1, analysis['total_teams'])
    analysis['mandatory_shared_ratio'] = len(analysis['teams_with_mandatory_shared']) / max(1, analysis['total_teams'])
    
    return analysis

def configure_pipeline_from_analysis(pipeline_config, analysis, teams_data):
    """Configure pipeline steps based on team data analysis."""
    
    # Determine scheduling approach based on constraints
    is_constrained = (
        analysis['strict_preference_ratio'] > 0.3 or  # Many teams have strict preferences
        analysis['mandatory_shared_ratio'] > 0.2 or   # Significant mandatory sharing
        len(analysis['late_cutoff_teams']) > analysis['total_teams'] * 0.4  # Many late cutoffs
    )
    
    is_flexible = (
        analysis['shared_ice_ratio'] > 0.8 and  # Most teams allow sharing
        analysis['strict_preference_ratio'] < 0.2  # Few strict preferences
    )
    
    # Configure steps based on analysis
    for step in pipeline_config['steps']:
        step_id = step['id']
        
        if step_id == 'mandatory_shared_ice':
            # Enable if there are teams requiring mandatory sharing
            step['enabled'] = len(analysis['teams_with_mandatory_shared']) > 0
            if step['enabled']:
                # Configure age difference based on age distribution
                age_ranges = extract_age_ranges(analysis['age_distribution'])
                max_age_diff = calculate_optimal_age_difference(age_ranges, analysis['teams_with_mandatory_shared'], teams_data)
                step['parameters']['max_age_difference'] = max_age_diff
        
        elif step_id == 'high_priority_individual':
            # Always enabled, but configure strictness
            step['parameters']['strict_preferences_only'] = analysis['strict_preference_ratio'] > 0.5
            step['parameters']['priority_threshold'] = 7 if is_constrained else 8
        
        elif step_id == 'shared_ice_optimization':
            # Configure based on sharing patterns
            step['enabled'] = analysis['shared_ice_ratio'] > 0.3
            if step['enabled']:
                # More permissive age difference if many teams allow sharing
                base_age_diff = 2 if is_constrained else 3
                step['parameters']['max_age_difference'] = base_age_diff
                step['parameters']['min_compatibility_score'] = 0.7 if is_constrained else 0.6
        
        elif step_id == 'remaining_individual':
            # Configure flexibility based on constraints
            step['parameters']['allow_suboptimal_times'] = not is_constrained
            step['parameters']['priority_weight'] = 0.4 if is_constrained else 0.3
        
        elif step_id == 'emergency_shared':
            # Enable based on expected demand vs supply imbalance
            expected_demand = calculate_expected_demand(teams_data, analysis)
            step['enabled'] = expected_demand > analysis['total_teams'] * 1.5  # Rough heuristic
            if step['enabled']:
                step['parameters']['relax_age_restrictions'] = not is_constrained
                step['parameters']['max_teams_per_emergency_slot'] = 4 if is_constrained else 6
        
        elif step_id == 'final_aggressive':
            # Enable for flexible setups or high-demand situations
            step['enabled'] = is_flexible or analysis['total_teams'] > 15
            if step['enabled']:
                step['parameters']['max_teams_per_slot'] = 6 if is_constrained else 8
    
    # Configure global settings
    if is_constrained:
        pipeline_config['global_settings']['allocation_timeout_seconds'] = 450  # More time for complex scheduling
        pipeline_config['global_settings']['emergency_mode_threshold'] = 0.9
    elif is_flexible:
        pipeline_config['global_settings']['allocation_timeout_seconds'] = 200  # Less time needed
        pipeline_config['global_settings']['emergency_mode_threshold'] = 0.7
    
    # Add metadata about the migration
    pipeline_config['migration_info'] = {
        'migrated_from_teams': True,
        'migration_date': datetime.datetime.now().isoformat(),
        'team_count': analysis['total_teams'],
        'constraints_detected': is_constrained,
        'flexibility_detected': is_flexible,
        'mandatory_shared_teams': len(analysis['teams_with_mandatory_shared']),
        'strict_preference_teams': len(analysis['teams_with_strict_preferences'])
    }

def has_strict_preferences_in_team(team_info):
    """Check if team has strict time preferences defined."""
    if team_info.get('strict_preferred', False):
        return True
    
    prefs = team_info.get('preferred_days_and_times', {})
    return any(key.endswith('_strict') and value for key, value in prefs.items())

def can_team_have_multiple_sessions(team_info, team_name):
    """Check if team is eligible for multiple sessions per day."""
    if team_info.get('allow_multiple_per_day', False):
        return True
    
    # Check if it's a high-level competitive team (U13+ AA/A)
    age_match = re.search(r'(\d+)', team_info.get('age', ''))
    if age_match and int(age_match.group(1)) >= 13:
        if team_info.get('type') == 'competitive':
            # Check tier from team name or info
            tier = extract_team_tier(team_name, team_info)
            return tier in ['AA', 'A']
    
    return False

def extract_team_tier(team_name, team_info):
    """Extract team tier from name or info."""
    if team_info.get('type') == 'house':
        return 'HOUSE'
    
    tier_patterns = [r'U\d+(AA|A|BB|B|C)\b', r'U\d+\s+(AA|A|BB|B|C)\b']
    for pattern in tier_patterns:
        match = re.search(pattern, team_name, re.IGNORECASE)
        if match:
            return match.group(1).upper()
    
    return 'C'  # Default to C tier

def extract_age_ranges(age_distribution):
    """Extract numeric age ranges from age distribution."""
    ages = []
    for age_str in age_distribution.keys():
        match = re.search(r'(\d+)', age_str)
        if match:
            ages.append(int(match.group(1)))
    return sorted(ages)

def calculate_optimal_age_difference(age_ranges, mandatory_teams, teams_data):
    """Calculate optimal age difference for mandatory shared ice."""
    if len(mandatory_teams) < 2:
        return 2
    
    # Get ages of teams requiring mandatory sharing
    mandatory_ages = []
    for team_name in mandatory_teams:
        team_info = teams_data[team_name]
        age_str = team_info.get('age', '')
        match = re.search(r'(\d+)', age_str)
        if match:
            mandatory_ages.append(int(match.group(1)))
    
    if len(mandatory_ages) < 2:
        return 2
    
    # Calculate the minimum age difference needed to pair all mandatory teams
    mandatory_ages.sort()
    max_gap = max(mandatory_ages) - min(mandatory_ages)
    
    # Return a reasonable age difference that accommodates most pairings
    if max_gap <= 2:
        return 2
    elif max_gap <= 4:
        return 3
    else:
        return min(4, max_gap)  # Cap at 4 years maximum

def calculate_expected_demand(teams_data, analysis):
    """Estimate total ice time demand based on team requirements."""
    # This is a simplified calculation - in reality you'd factor in 
    # rules_data for ice times per week by team type/age
    
    demand = 0
    for team_name, team_info in teams_data.items():
        team_type = team_info.get('type', 'house')
        
        # Rough estimate: competitive teams need more ice
        if team_type == 'competitive':
            demand += 2.5  # Average sessions per week
        else:
            demand += 1.0   # House teams typically need less
    
    return demand

def generate_migration_report(teams_data, old_pipeline_config, new_pipeline_config):
    """Generate a report showing what was migrated from team data."""
    
    analysis = analyze_team_patterns(teams_data)
    
    report_lines = [
        "=== Pipeline Configuration Migration Report ===",
        f"Analyzed {analysis['total_teams']} teams",
        "",
        "Team Analysis Summary:",
        f"  • Teams with mandatory shared ice: {len(analysis['teams_with_mandatory_shared'])}",
        f"  • Teams with strict preferences: {len(analysis['teams_with_strict_preferences'])}",
        f"  • Teams allowing shared ice: {len(analysis['teams_allowing_shared'])}",
        f"  • Teams disallowing shared ice: {len(analysis['teams_disallowing_shared'])}",
        "",
        "Pipeline Configuration Changes:"
    ]
    
    # Compare old vs new configuration
    for step in new_pipeline_config['steps']:
        step_id = step['id']
        old_step = next((s for s in old_pipeline_config['steps'] if s['id'] == step_id), None)
        
        if old_step:
            if step['enabled'] != old_step['enabled']:
                status = "enabled" if step['enabled'] else "disabled"
                report_lines.append(f"  • {step['name']}: {status} based on team analysis")
            
            # Check for parameter changes
            old_params = old_step.get('parameters', {})
            new_params = step.get('parameters', {})
            
            for param, new_value in new_params.items():
                old_value = old_params.get(param)
                if old_value != new_value:
                    report_lines.append(f"    - {param}: {old_value} → {new_value}")
    
    if analysis['teams_with_mandatory_shared']:
        report_lines.extend([
            "",
            "Teams requiring mandatory shared ice:",
            *[f"  • {team}" for team in analysis['teams_with_mandatory_shared']]
        ])
    
    if analysis['teams_with_strict_preferences']:
        report_lines.extend([
            "",
            "Teams with strict time preferences:",
            *[f"  • {team}" for team in analysis['teams_with_strict_preferences']]
        ])
    
    return "\n".join(report_lines)

# Integration function for use in main application
def migrate_and_update_pipeline_config(main_app):
    """
    Migrate team data to pipeline configuration and update the main application.
    This function should be called when loading data or when explicitly requested.
    """
    
    if not hasattr(main_app, 'teams_data') or not main_app.teams_data:
        return None
    
    # Get current pipeline config (or default)
    old_config = getattr(main_app, 'pipeline_config', get_default_pipeline_config())
    
    # Migrate team data to new pipeline config
    new_config = migrate_team_data_to_pipeline_config(
        main_app.teams_data, 
        getattr(main_app, 'rules_data', None)
    )
    
    # Generate migration report
    report = generate_migration_report(main_app.teams_data, old_config, new_config)
    
    # Update main app
    main_app.pipeline_config = new_config
    
    return report