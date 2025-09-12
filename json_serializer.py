import json
import os
import datetime
from tkinter import filedialog, messagebox
import re
from json_validator import repair_scheduler_json_object, validate_json_structure


# Default file name for saving and loading
DEFAULT_SAVE_FILE = "hockey_scheduler_data.json"

# Track the last file operations for auto-save functionality
_last_save_path = None
_last_load_path = None

class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            return obj.isoformat()
        elif isinstance(obj, datetime.date):
            return obj.isoformat()
        elif isinstance(obj, datetime.time):
            return obj.isoformat()
        return super().default(obj)

def normalize_preferred_days_and_times(data):
    if not isinstance(data, dict):
        return {}
    normalized = {}
    for day, val in data.items():
        if isinstance(val, dict):
            normalized[day] = {
                "time": val.get("time", ""),
                "strict": bool(val.get("strict", False))
            }
        else:
            normalized[day] = {"time": str(val), "strict": False}
    return normalized

def _parse_date(date_str):
    """
    Attempts to parse a date string in various formats.
    Returns a datetime.date object on success, otherwise None.
    """
    if not isinstance(date_str, str):
        return None
    
    # Try the most common format first (YYYY-MM-DD)
    try:
        return datetime.date.fromisoformat(date_str)
    except (ValueError, TypeError):
        pass

    # Try flexible formats (e.g., YYYY-M-D)
    try:
        # Regex to find YYYY-MM-DD or YYYY-M-D and normalize it
        match = re.match(r'(\d{4})-(\d{1,2})-(\d{1,2})', date_str)
        if match:
            year, month, day = match.groups()
            return datetime.date(int(year), int(month), int(day))
    except (ValueError, TypeError):
        pass
        
    return None

def save_all_data(data):
    """Saves all application data (teams, arenas, rules) to a single JSON file."""
    global _last_save_path
    try:
        file_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json")],
            initialfile=DEFAULT_SAVE_FILE
        )
        if not file_path:
            return False, None
            
        with open(file_path, 'w') as f:
            json.dump(data, f, cls=DateTimeEncoder, indent=4)
        
        _last_save_path = file_path
        return True, file_path
    except Exception as e:
        messagebox.showerror("Save Data Error", f"Failed to save data: {e}")
        return False, None

def save_all_data_to_path(data, file_path):
    """Saves all application data to a specific file path (for auto-save)."""
    global _last_save_path
    try:
        with open(file_path, 'w') as f:
            json.dump(data, f, cls=DateTimeEncoder, indent=4)
        
        _last_save_path = file_path
        return True
    except Exception as e:
        raise Exception(f"Failed to save data to {file_path}: {e}")

def load_all_data():
    """Load data with enhanced error handling and automatic repair."""
    file_path = filedialog.askopenfilename(
        title="Load All Data",
        filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
    )
    
    if not file_path:
        return None, None
    
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()
            
        # Check if file is empty
        if not content.strip():
            messagebox.showerror("Load Error", "The selected file is empty.")
            return None, None
            
        # Try to parse JSON
        try:
            raw_data = json.loads(content)
        except json.JSONDecodeError as e:
            messagebox.showerror("JSON Parse Error", 
                f"Invalid JSON format at line {e.lineno}, column {e.colno}:\n{e.msg}\n\n"
                f"Please check your JSON file for syntax errors.")
            return None, None

        # Validate basic structure
        if not isinstance(raw_data, dict):
            messagebox.showerror("Data Format Error", 
                "JSON file must contain a dictionary at the root level.")
            return None, None
        
        # Get validation issues before repair
        issues_before = validate_json_structure(raw_data)
        
        # Perform comprehensive repair
        try:
            repaired_data = repair_scheduler_json_object(raw_data)
        except Exception as e:
            messagebox.showerror("Data Repair Error", 
                f"Failed to repair data structure: {e}\n\n"
                f"The file may be severely corrupted.")
            return None, None
        
        # Get validation issues after repair
        issues_after = validate_json_structure(repaired_data)
        
        # Convert date strings back to datetime.date objects recursively
        convert_dates(repaired_data)
        
        # Show repair summary if there were issues
        if issues_before:
            repair_message = f"The file contained {len(issues_before)} issue(s) that were automatically repaired:\n\n"
            repair_message += "\n".join(f"• {issue}" for issue in issues_before[:5])  # Show first 5 issues
            
            if len(issues_before) > 5:
                repair_message += f"\n... and {len(issues_before) - 5} more issues"
            
            if issues_after:
                repair_message += f"\n\nWarning: {len(issues_after)} issue(s) could not be automatically fixed."
            
            repair_message += "\n\nThe repaired data will be saved back to the file."
            
            messagebox.showinfo("File Automatically Repaired", repair_message)
        
        # Save the repaired data back to the file
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(repaired_data, f, cls=DateTimeEncoder, indent=4)
        except Exception as e:
            messagebox.showwarning("Save Warning", 
                f"Data was successfully loaded and repaired, but could not save the "
                f"repaired version back to the file: {e}")
        
        # Provide warnings for missing sections (if any remain)
        missing_sections = []
        if 'teams' not in repaired_data or not repaired_data['teams']:
            missing_sections.append('teams')
        if 'arenas' not in repaired_data or not repaired_data['arenas']:
            missing_sections.append('arenas')
        if 'rules' not in repaired_data or not repaired_data['rules']:
            missing_sections.append('rules')
            
        if missing_sections:
            messagebox.showwarning("Missing Data", 
                f"The following sections are missing or empty: {', '.join(missing_sections)}\n\n"
                f"The application may not function correctly without these sections.")
        
        # Check for specific shared ice issues
        _check_shared_ice_configuration(repaired_data)
        
        global _last_load_path
        _last_load_path = file_path
        return repaired_data, file_path
        
    except FileNotFoundError:
        messagebox.showerror("File Error", "The selected file could not be found.")
        return None, None
    except PermissionError:
        messagebox.showerror("Permission Error", "Permission denied when trying to read the file.")
        return None, None
    except Exception as e:
        messagebox.showerror("Unexpected Error", f"An unexpected error occurred: {str(e)}")
        return None, None

def convert_dates(item):
    """Convert date strings back to datetime.date objects recursively"""
    if isinstance(item, dict):
        for key, value in item.items():
            if key in ['start', 'end'] and isinstance(value, str):
                try:
                    item[key] = datetime.date.fromisoformat(value)
                except ValueError:
                    pass # Keep as string if format is wrong
            else:
                convert_dates(value)
    elif isinstance(item, list):
        for sub_item in item:
            convert_dates(sub_item)

def _check_shared_ice_configuration(data):
    """Check for common shared ice configuration issues."""
    teams = data.get("teams", {})
    issues = []
    
    teams_with_mandatory_shared = []
    teams_without_shared_ice = []
    
    for team_name, team_info in teams.items():
        allow_shared = team_info.get("allow_shared_ice", True)
        mandatory_shared = team_info.get("mandatory_shared_ice", False)
        
        if mandatory_shared:
            teams_with_mandatory_shared.append(team_name)
        
        if not allow_shared:
            teams_without_shared_ice.append(team_name)
    
    # Check for potential shared ice problems
    if teams_with_mandatory_shared and len(teams_with_mandatory_shared) == 1:
        issues.append(f"Team '{teams_with_mandatory_shared[0]}' has mandatory shared ice but is the only team with this setting. Consider enabling this for compatible teams.")
    
    if len(teams_without_shared_ice) == len(teams):
        issues.append("No teams allow shared ice. This may result in scheduling difficulties if ice availability is limited.")
    
    # Check for age compatibility issues
    mandatory_ages = []
    for team_name in teams_with_mandatory_shared:
        team_info = teams[team_name]
        age_str = team_info.get("age", "")
        # Extract numeric age
        age_match = re.search(r'(\d+)', age_str)
        if age_match:
            mandatory_ages.append((team_name, int(age_match.group(1))))
    
    # Check if mandatory shared ice teams are compatible by age
    if len(mandatory_ages) > 1:
        for i, (team1, age1) in enumerate(mandatory_ages):
            for team2, age2 in mandatory_ages[i+1:]:
                if abs(age1 - age2) > 2:
                    issues.append(f"Teams '{team1}' (age {age1}) and '{team2}' (age {age2}) both have mandatory shared ice but may not be compatible due to age difference (>{2} years).")
    
    if issues:
        issue_text = "Potential shared ice configuration issues detected:\n\n"
        issue_text += "\n".join(f"• {issue}" for issue in issues)
        issue_text += "\n\nYou may want to review your team shared ice settings."
        messagebox.showinfo("Shared Ice Configuration", issue_text)

def get_last_save_path():
    """Returns the path of the last file save operation."""
    return _last_save_path

def get_last_load_path():
    """Returns the path of the last file load operation."""
    return _last_load_path

def save_schedule(schedule_data):
    """Saves the generated schedule to a JSON file."""
    try:
        file_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json")],
            initialfile="hockey_schedule.json"
        )
        if not file_path:
            return False
            
        with open(file_path, 'w') as f:
            json.dump(schedule_data, f, cls=DateTimeEncoder, indent=4)
        return True
    except Exception as e:
        messagebox.showerror("Save Schedule Error", f"Failed to save schedule: {e}")
        return False

def load_schedule():
    """Loads a schedule from a JSON file with validation and repair."""
    try:
        file_path = filedialog.askopenfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json")],
            initialfile="hockey_schedule.json"
        )
        if not file_path or not os.path.exists(file_path):
            return None
            
        with open(file_path, 'r') as f:
            schedule_data = json.load(f)
        
        # Validate schedule format
        if not isinstance(schedule_data, list):
            messagebox.showerror("Load Schedule Error", "Schedule file must contain a list of events.")
            return None
        
        # Repair/validate each schedule entry
        repaired_schedule = []
        for i, event in enumerate(schedule_data):
            if not isinstance(event, dict):
                continue  # Skip invalid entries
            
            # Ensure required fields exist
            repaired_event = {
                "team": str(event.get("team", "")),
                "opponent": str(event.get("opponent", "Practice")),
                "arena": str(event.get("arena", "")),
                "date": str(event.get("date", "")),
                "time_slot": str(event.get("time_slot", "")),
                "type": str(event.get("type", "practice"))
            }
            
            # Validate date format
            try:
                if repaired_event["date"]:
                    datetime.date.fromisoformat(repaired_event["date"])
            except ValueError:
                continue  # Skip events with invalid dates
            
            # Validate time slot format
            if repaired_event["time_slot"] and "-" not in repaired_event["time_slot"]:
                continue  # Skip events with invalid time slots
            
            repaired_schedule.append(repaired_event)
        
        # Convert date strings back to datetime.date objects
        for event in repaired_schedule:
            if isinstance(event.get('date'), str):
                try:
                    event['date'] = datetime.date.fromisoformat(event['date'])
                except ValueError:
                    pass  # Keep as string if invalid
        
        if len(repaired_schedule) != len(schedule_data):
            messagebox.showinfo("Schedule Repaired", 
                f"Loaded {len(repaired_schedule)} valid events out of {len(schedule_data)} total entries. "
                f"Invalid entries were skipped.")
        
        return repaired_schedule
        
    except FileNotFoundError:
        messagebox.showerror("Load Schedule Error", f"File not found: {file_path}")
        return None
    except json.JSONDecodeError:
        messagebox.showerror("Load Schedule Error", "Invalid JSON file format.")
        return None
    except Exception as e:
        messagebox.showerror("Load Schedule Error", f"An unexpected error occurred: {e}")
        return None

def validate_and_repair_file(file_path):
    """
    Standalone function to validate and repair a JSON file.
    Returns (success: bool, issues_found: list, issues_fixed: list)
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()
        
        if not content.strip():
            return False, ["File is empty"], []
        
        try:
            raw_data = json.loads(content)
        except json.JSONDecodeError as e:
            return False, [f"Invalid JSON format: {e.msg}"], []
        
        if not isinstance(raw_data, dict):
            return False, ["Root data must be a dictionary"], []
        
        # Get issues before repair
        issues_before = validate_json_structure(raw_data)
        
        # Perform repair
        repaired_data = repair_scheduler_json_object(raw_data)
        
        # Get issues after repair
        issues_after = validate_json_structure(repaired_data)
        
        # Calculate what was fixed
        issues_fixed = [issue for issue in issues_before if issue not in issues_after]
        
        # Save repaired data back
        with open(file_path, 'w', encoding='utf-8') as file:
            json.dump(repaired_data, file, cls=DateTimeEncoder, indent=4)
        
        return True, issues_before, issues_fixed
        
    except Exception as e:
        return False, [f"Error processing file: {e}"], []