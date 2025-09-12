import tkinter as tk
from tkinter import ttk
from ui.arena_tab import ArenaTab
from ui.team_tab import TeamTab
from ui.scheduler_tab import SchedulerTab
from ui.calendar_view_tab import CalendarViewTab

class HockeySchedulerUI(ttk.Frame):
    def __init__(self, parent, main_app):
        super().__init__(parent)
        self.main_app = main_app
        
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(padx=10, pady=10, fill="both", expand=True)
        
        # Create tabs
        self.teams_tab = TeamTab(self.notebook, self.main_app)
        self.notebook.add(self.teams_tab, text="Team Management")
        
        self.arena_tab = ArenaTab(self.notebook, self.main_app)
        self.notebook.add(self.arena_tab, text="Arena & Availability")
        
        self.scheduler_tab = SchedulerTab(self.notebook, self.main_app)
        self.notebook.add(self.scheduler_tab, text="Scheduler")
        
        # Add the calendar view tab
        self.calendar_tab = CalendarViewTab(self.notebook, self.main_app)
        self.notebook.add(self.calendar_tab, text="Calendar View")
        
        # Bind tab change event to sync data between tabs
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)
        
    def on_tab_changed(self, event):
        """Handle tab change events to sync data between tabs."""
        try:
            selected_tab = event.widget.tab('current')['text']
            
            # When switching to calendar view, update it with current schedule data
            if selected_tab == "Calendar View":
                schedule_data = self.scheduler_tab.get_schedule_data()
                self.calendar_tab.load_schedule_data(schedule_data)
        except (tk.TclError, IndexError):
            # Handle case where tab selection is invalid
            pass
            
    def load_teams_data(self, teams_data):
        """Load teams data into the teams tab."""
        if teams_data and hasattr(self.teams_tab, 'load_teams_data'):
            self.teams_tab.load_teams_data(teams_data)
        
    def get_teams_data(self):
        """Get teams data from the teams tab."""
        if hasattr(self.teams_tab, 'get_teams_data'):
            return self.teams_tab.get_teams_data()
        return {}

    def load_arenas_data(self, arenas_data):
        """Load arenas data into the arena tab."""
        if arenas_data and hasattr(self.arena_tab, 'load_arenas_data'):
            self.arena_tab.load_arenas_data(arenas_data)

    def get_arenas_data(self):
        """Get arenas data from the arena tab."""
        if hasattr(self.arena_tab, 'get_arenas_data'):
            return self.arena_tab.get_arenas_data()
        return {}

    def load_rules_data(self, rules_data):
        """Load rules data into the main application instance."""
        if rules_data:
            self.main_app.rules_data = rules_data
        
    def load_scheduler_data(self, scheduler_data):
        """Load scheduler data into the scheduler tab."""
        if scheduler_data and hasattr(self.scheduler_tab, 'load_scheduler_data'):
            self.scheduler_tab.load_scheduler_data(scheduler_data)
            
    def load_calendar_data(self, calendar_data):
        """Load calendar data into the calendar tab."""
        if calendar_data and hasattr(self.calendar_tab, 'load_calendar_data'):
            self.calendar_tab.load_calendar_data(calendar_data)
        
    def get_season_dates(self):
        """Get season dates from the scheduler tab."""
        if hasattr(self.scheduler_tab, 'get_season_dates'):
            return self.scheduler_tab.get_season_dates()
        raise ValueError("Scheduler tab not available or missing get_season_dates method")
        
    def get_schedule_data(self):
        """Get schedule data from the scheduler tab."""
        if hasattr(self.scheduler_tab, 'get_schedule_data'):
            return self.scheduler_tab.get_schedule_data()
        return []

    def display_schedule(self, schedule_data):
        """Display schedule in both scheduler tab and calendar view."""
        if not schedule_data:
            return
            
        # Update scheduler tab
        if hasattr(self.scheduler_tab, 'display_schedule'):
            self.scheduler_tab.display_schedule(schedule_data)
        
        # Update calendar tab
        if hasattr(self.calendar_tab, 'load_schedule_data'):
            self.calendar_tab.load_schedule_data(schedule_data)
        
        # If calendar tab is currently selected, refresh it
        try:
            current_tab = self.notebook.tab(self.notebook.select(), "text")
            if current_tab == "Calendar View" and hasattr(self.calendar_tab, 'render'):
                self.calendar_tab.render()
        except (tk.TclError, IndexError):
            # Handle case where tab selection is invalid
            pass

    def get_current_tab(self):
        """Get the currently selected tab name."""
        try:
            return self.notebook.tab(self.notebook.select(), "text")
        except (tk.TclError, IndexError):
            return None

    def switch_to_tab(self, tab_name):
        """Switch to a specific tab by name."""
        for i in range(self.notebook.index("end")):
            if self.notebook.tab(i, "text") == tab_name:
                self.notebook.select(i)
                return True
        return False

    def refresh_all_tabs(self):
        """Refresh data in all tabs."""
        # Get current data from main app
        teams_data = getattr(self.main_app, 'teams_data', {})
        arenas_data = getattr(self.main_app, 'arenas_data', {})
        schedule_data = getattr(self.main_app, 'schedule_data', [])
        
        # Refresh teams tab
        if teams_data:
            self.load_teams_data(teams_data)
        
        # Refresh arenas tab
        if arenas_data:
            self.load_arenas_data(arenas_data)
        
        # Refresh schedule display
        if schedule_data:
            self.display_schedule(schedule_data)

    def clear_all_data(self):
        """Clear all data from all tabs."""
        # Clear teams tab
        if hasattr(self.teams_tab, 'load_teams_data'):
            self.teams_tab.load_teams_data({})
        
        # Clear arenas tab
        if hasattr(self.arena_tab, 'load_arenas_data'):
            self.arena_tab.load_arenas_data({})
        
        # Clear scheduler tab
        if hasattr(self.scheduler_tab, 'display_schedule'):
            self.scheduler_tab.display_schedule([])
        
        # Clear calendar tab
        if hasattr(self.calendar_tab, 'load_schedule_data'):
            self.calendar_tab.load_schedule_data([])

    def validate_all_data(self):
        """Validate data in all tabs and return any issues found."""
        issues = []
        
        # Validate teams data
        teams_data = self.get_teams_data()
        if not teams_data:
            issues.append("No teams configured")
        else:
            for team_name, team_info in teams_data.items():
                if not team_info.get('age'):
                    issues.append(f"Team '{team_name}' missing age group")
                if not team_info.get('type'):
                    issues.append(f"Team '{team_name}' missing type")
        
        # Validate arenas data
        arenas_data = self.get_arenas_data()
        if not arenas_data:
            issues.append("No arenas configured")
        else:
            for arena_name, arena_blocks in arenas_data.items():
                if not arena_blocks:
                    issues.append(f"Arena '{arena_name}' has no time blocks configured")
        
        # Validate rules data
        rules_data = getattr(self.main_app, 'rules_data', {})
        if not rules_data.get('ice_times_per_week'):
            issues.append("No ice time rules configured")
        
        return issues

    def export_all_data(self):
        """Export all current data."""
        return {
            'teams': self.get_teams_data(),
            'arenas': self.get_arenas_data(),
            'rules': getattr(self.main_app, 'rules_data', {}),
            'schedule': self.get_schedule_data()
        }

    def import_all_data(self, data):
        """Import data into all tabs."""
        if not isinstance(data, dict):
            return False
        
        try:
            # Import teams
            if 'teams' in data:
                self.load_teams_data(data['teams'])
            
            # Import arenas
            if 'arenas' in data:
                self.load_arenas_data(data['arenas'])
            
            # Import rules
            if 'rules' in data:
                self.load_rules_data(data['rules'])
            
            # Import schedule
            if 'schedule' in data:
                self.display_schedule(data['schedule'])
            
            return True
        except Exception as e:
            print(f"Error importing data: {e}")
            return False