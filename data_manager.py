# data_manager.py
import json
import os
import datetime
from tkinter import filedialog, messagebox
import re

# Default file name for saving and loading
DEFAULT_SAVE_FILE = "hockey_scheduler_data.json"

class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder to handle datetime objects."""
    def default(self, obj):
        if isinstance(obj, (datetime.date, datetime.datetime)):
            return obj.isoformat()
        return super().default(obj)
    
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

def save_data(data):
    """Saves the main application data (teams, arenas, rules) to a JSON file."""
    try:
        # This function now correctly prompts the user for a file path
        file_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json")],
            initialfile=DEFAULT_SAVE_FILE
        )
        if not file_path:
            return False # User canceled the dialog

        # Use the custom encoder to handle datetime objects
        with open(file_path, 'w') as f:
            json.dump(data, f, cls=DateTimeEncoder, indent=4)
        return True
    except Exception as e:
        messagebox.showerror("Error", f"Error saving file: {e}")
        return False

def load_data():
    """Loads the main application data (teams, arenas, rules) from a JSON file."""
    try:
        # This function now correctly prompts the user for a file path
        file_path = filedialog.askopenfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json")],
            initialfile=DEFAULT_SAVE_FILE
        )
        if not file_path or not os.path.exists(file_path):
            return None # User canceled or selected a non-existent file
            
        with open(file_path, 'r') as f:
            data = json.load(f)

        def convert_strings_to_dates(obj):
            """Recursively converts date strings back to datetime.date objects."""
            if isinstance(obj, dict):
                return {k: convert_strings_to_dates(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_strings_to_dates(i) for i in obj]
            elif isinstance(obj, str):
                date_obj = _parse_date(obj)
                return date_obj if date_obj else obj
            return obj

        loaded_data = convert_strings_to_dates(data)
        return loaded_data

    except Exception as e:
        messagebox.showerror("Error", f"Error loading file: {e}")
        return None

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
    """Loads a schedule from a JSON file."""
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
        
        # Convert date strings back to datetime.date objects
        for event in schedule_data:
            if isinstance(event.get('date'), str):
                event['date'] = datetime.date.fromisoformat(event['date'])
        
        return schedule_data
    except Exception as e:
        messagebox.showerror("Load Schedule Error", f"Failed to load schedule: {e}")
        return None
