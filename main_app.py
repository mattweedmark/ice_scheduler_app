import tkinter as tk
from tkinter import messagebox, filedialog
from data import json_serializer
from ui.main_ui import HockeySchedulerUI
from ui.scheduling_rules_tab import SchedulingRulesWindow
import os
import importlib
import sys

# Try to import optional components
try:
    from ui.web_sharing import WebSharingDialog
    WEB_SHARING_AVAILABLE = True
except ImportError:
    WEB_SHARING_AVAILABLE = False

try:
    from ui.analytics_dashboard import AnalyticsDashboard
    ANALYTICS_AVAILABLE = True
except ImportError:
    ANALYTICS_AVAILABLE = False

# Import scheduler logic with fallback
try:
    from scheduler_logic import generate_schedule_enhanced as generate_schedule
except ImportError:
    try:
        from scheduler_logic import generate_schedule
    except ImportError:
        def generate_schedule(*args, **kwargs):
            raise ImportError("Scheduler logic module not available")

class MainApplication(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Ice Scheduler")
        self.geometry("1200x800")
        
        # Central data storage for the application
        self.teams_data = {}
        self.arenas_data = {}
        self.rules_data = {
            'default_ice_time_type': 'practice',
            'ice_times_per_week': {
                'house': {'U9': 1, 'U11': 1, 'U13': 1, 'U15': 1, 'U18': 1},
                'competitive': {'U9': 2, 'U11': 2, 'U13': 3, 'U15': 3, 'U18': 3}
            }
        }
        self.schedule_data = []
        
        # Auto-save tracking
        self.current_save_file = None  # Path to currently loaded/saved file
        self.data_loaded_from_file = False  # Whether data was loaded from file
        self.auto_save_enabled = True  # Can be disabled if needed
        
        # Analytics dashboard reference
        self.analytics_dashboard = None
        
        self.main_ui = HockeySchedulerUI(self, self)
        self.main_ui.pack(fill="both", expand=True)

        self.setup_menu()
        self.setup_analytics()
        
    def setup_menu(self):
        menubar = tk.Menu(self)
        self.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Load All Data", command=self.load_data)
        file_menu.add_command(label="Save All Data", command=self.save_data)
        file_menu.add_command(label="Save As...", command=self.save_data_as)
        file_menu.add_separator()
        file_menu.add_command(label="Toggle Auto-Save", command=self.toggle_auto_save)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.quit)
        menubar.add_cascade(label="File", menu=file_menu)

        settings_menu = tk.Menu(menubar, tearoff=0)
        settings_menu.add_command(label="Scheduling Rules", command=self.open_rules_window)
        menubar.add_cascade(label="Settings", menu=settings_menu)
        
        tools_menu = tk.Menu(menubar, tearoff=0)
        if ANALYTICS_AVAILABLE:
            tools_menu.add_command(label="Analytics Dashboard", command=self.open_analytics_dashboard)
        tools_menu.add_command(label="Web Sharing & Integration", command=self.open_web_sharing)
        menubar.add_cascade(label="Tools", menu=tools_menu)
        
        # Update window title to show auto-save status
        self.update_window_title()
        
    def setup_analytics(self):
        """Initialize analytics dashboard if available."""
        if ANALYTICS_AVAILABLE:
            try:
                self.analytics_dashboard = None
            except Exception as e:
                print(f"Analytics dashboard initialization failed: {e}")
                
    def open_analytics_dashboard(self):
        """Open the analytics dashboard in a new window."""
        if not ANALYTICS_AVAILABLE:
            messagebox.showwarning("Feature Unavailable", 
                "Analytics dashboard requires matplotlib, numpy, and reportlab.\n"
                "Please install these packages and restart the application.")
            return
            
        analytics_window = tk.Toplevel(self)
        analytics_window.title("Analytics Dashboard")
        analytics_window.geometry("1000x700")
        
        self.analytics_dashboard = AnalyticsDashboard(analytics_window, self)
        self.analytics_dashboard.pack(fill="both", expand=True)
        
        # Force load current data after dashboard is fully created
        self.update_analytics_dashboard()
        
    def update_analytics_dashboard(self):
        """Update the analytics dashboard with current data."""
        if self.analytics_dashboard and hasattr(self.analytics_dashboard, 'load_data'):
            self.analytics_dashboard.load_data(
                schedule_data=self.schedule_data,
                teams_data=self.teams_data,
                rules_data=self.rules_data
            )
        
    def open_web_sharing(self):
        """Open the web sharing dialog."""
        web_dialog = WebSharingDialog(self, self)
        
    def update_window_title(self):
        """Update window title to show current file and auto-save status."""
        title = "Ice Scheduler"
        if self.current_save_file:
            filename = os.path.basename(self.current_save_file)
            title += f" - {filename}"
        if self.auto_save_enabled and (self.current_save_file or self.data_loaded_from_file):
            title += " (Auto-Save ON)"
        self.title(title)
    
    def toggle_auto_save(self):
        """Toggle auto-save functionality on/off."""
        self.auto_save_enabled = not self.auto_save_enabled
        status = "enabled" if self.auto_save_enabled else "disabled"
        messagebox.showinfo("Auto-Save", f"Auto-save has been {status}.")
        self.update_window_title()
        
    def on_data_changed(self, source_tab=None):
        """Called whenever data changes in any UI tab."""
        if not self.auto_save_enabled:
            return
            
        # If we have a current save file, auto-save silently
        if self.current_save_file and os.path.exists(os.path.dirname(self.current_save_file)):
            try:
                self._save_to_file(self.current_save_file, silent=True)
            except Exception as e:
                # If silent save fails, inform user but don't block workflow
                messagebox.showerror("Auto-Save Error", 
                    f"Failed to auto-save to {self.current_save_file}:\n{e}\n\nPlease save manually.")
        
        # If data was modified but we don't have a save location, prompt user
        elif self.data_loaded_from_file or self._has_data():
            response = messagebox.askyesno("Auto-Save", 
                "You have unsaved changes. Would you like to save them to a file?\n\n"
                "If you choose Yes, future changes will be automatically saved to this file.")
            
            if response:
                if self.save_data_as():  # This will set self.current_save_file
                    messagebox.showinfo("Auto-Save", 
                        "File saved successfully. Future changes will be auto-saved to this file.")

    def save_all_data_silently(self):
        """Silent save method for Ctrl+S functionality."""
        if self.current_save_file:
            try:
                self._save_to_file(self.current_save_file, silent=True)
                return True
            except Exception:
                return False
        return False
                        
    def _has_data(self):
        """Check if there's any data worth saving."""
        return bool(self.teams_data or self.arenas_data or self.rules_data or self.schedule_data)
        
    def _save_to_file(self, file_path, silent=False):
        """Internal method to save data to a specific file."""
        # Gather all data from the UI tabs
        self.teams_data = self.main_ui.get_teams_data()
        self.arenas_data = self.main_ui.get_arenas_data()
        self.schedule_data = self.main_ui.get_schedule_data()

        # Combine all data into a single dictionary
        data_to_save = {
            'teams': self.teams_data,
            'arenas': self.arenas_data,
            'rules': self.rules_data,
            'schedule': self.schedule_data
        }
        
        # Use a modified version of the save function that doesn't prompt for file path
        import json
        with open(file_path, 'w') as f:
            json.dump(data_to_save, f, cls=json_serializer.DateTimeEncoder, indent=4)
            
        if not silent:
            messagebox.showinfo("Save Data", "All data saved successfully!")
            
    def save_data(self):
        """Save data to current file, or prompt for location if none exists."""
        if self.current_save_file:
            try:
                self._save_to_file(self.current_save_file)
                return True
            except Exception as e:
                messagebox.showerror("Save Error", f"Failed to save to {self.current_save_file}:\n{e}")
                return False
        else:
            return self.save_data_as()
            
    def save_data_as(self):
        """Save data to a new file location."""
        # Gather all data from the UI tabs
        self.teams_data = self.main_ui.get_teams_data()
        self.arenas_data = self.main_ui.get_arenas_data()
        self.schedule_data = self.main_ui.get_schedule_data()

        # Combine all data into a single dictionary
        data_to_save = {
            'teams': self.teams_data,
            'arenas': self.arenas_data,
            'rules': self.rules_data,
            'schedule': self.schedule_data
        }
        
        success, file_path = json_serializer.save_all_data(data_to_save)
        if success:
            self.current_save_file = file_path
            self.update_window_title()
            messagebox.showinfo("Save Data", "All data saved successfully!")
            return True
        return False

    def load_data(self):
        """Load data from file and set up auto-save tracking."""
        loaded_data, file_path = json_serializer.load_all_data()
        if loaded_data:
            self.teams_data = loaded_data.get('teams', {})
            self.arenas_data = loaded_data.get('arenas', {})
            self.rules_data = loaded_data.get('rules', {
                'default_ice_time_type': 'practice',
                'ice_times_per_week': {
                    'house': {'U9': 1, 'U11': 1, 'U13': 1, 'U15': 1, 'U18': 1},
                    'competitive': {'U9': 2, 'U11': 2, 'U13': 3, 'U15': 3, 'U18': 3}
                }
            })
            self.schedule_data = loaded_data.get('schedule', [])
            
            # Set up auto-save tracking
            self.data_loaded_from_file = True
            self.current_save_file = file_path
            
            # Pass the loaded data to the UI tabs
            self.main_ui.load_teams_data(self.teams_data)
            self.main_ui.load_arenas_data(self.arenas_data)
            self.main_ui.load_rules_data(self.rules_data)
            if self.schedule_data:
                self.main_ui.display_schedule(self.schedule_data)
            
            # Update analytics dashboard if it's open
            self.update_analytics_dashboard()
            
            self.update_window_title()
            messagebox.showinfo("Load Data", "All data loaded successfully!")
            
    def on_teams_updated(self, teams_data):
        """Callback for when teams data is updated."""
        self.teams_data = teams_data
        self.on_data_changed("teams")
        # Update analytics dashboard if it's open
        self.update_analytics_dashboard()
        
    def on_arenas_updated(self, arenas_data):
        """Callback for when arenas data is updated."""  
        self.arenas_data = arenas_data
        self.on_data_changed("arenas")
        # Update analytics dashboard if it's open
        self.update_analytics_dashboard()
        
    def on_rules_updated(self, rules_data):
        """Callback for when rules data is updated."""
        self.rules_data = rules_data
        self.on_data_changed("rules")
        # Update analytics dashboard if it's open
        self.update_analytics_dashboard()

    def on_scheduler_updated(self, scheduler_data):
        """Callback for when scheduler data is updated."""
        self.schedule_data = scheduler_data.get('schedule', [])
        self.on_data_changed("scheduler")
        # Update analytics dashboard if it's open
        self.update_analytics_dashboard()

    def on_calendar_updated(self, calendar_data):
        """Callback for when calendar data is updated."""
        # Calendar view doesn't generate its own data, just displays schedule data
        pass
            
    def generate_schedule(self, season_dates):
        # Fetch the most recent data from the UI tabs before scheduling
        teams = self.main_ui.get_teams_data()
        arenas = self.main_ui.get_arenas_data()

        try:
            generated_schedule = generate_schedule(
                season_dates,
                teams,
                arenas,
                self.rules_data
            )
            
            # Store the schedule data
            if generated_schedule and 'schedule' in generated_schedule:
                self.schedule_data = generated_schedule['schedule']
                self.on_data_changed("scheduler")
                
                # Update analytics dashboard if it's open
                self.update_analytics_dashboard()
            
            return generated_schedule
        except ValueError as e:
            messagebox.showerror("Error", str(e))
            return {}
        except Exception as e:
            messagebox.showerror("Error", f"An unexpected error occurred during scheduling: {e}")
            return {}
            
    def save_schedule(self):
        schedule_data = self.main_ui.get_schedule_data()
        if not schedule_data:
            messagebox.showerror("Error", "No schedule to save. Please generate a schedule first.")
            return

        if json_serializer.save_schedule(schedule_data):
            messagebox.showinfo("Save Schedule", "Schedule saved successfully!")

    def load_schedule(self):
        schedule_data = json_serializer.load_schedule()
        if schedule_data:
            self.schedule_data = schedule_data
            self.main_ui.display_schedule(schedule_data)
            # Update analytics dashboard if it's open
            self.update_analytics_dashboard()
            messagebox.showinfo("Load Schedule", "Schedule loaded successfully!")
            
    def open_rules_window(self):
        rules_window = SchedulingRulesWindow(self, self.rules_data)
        self.wait_window(rules_window)
        # Refresh the rules data after the window is closed and trigger auto-save
        self.rules_data = rules_window.get_rules()
        self.on_rules_updated(self.rules_data)


if __name__ == "__main__":
    app = MainApplication()
    app.mainloop()