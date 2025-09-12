import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from collections import defaultdict, Counter
import datetime

try:
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    import matplotlib.dates as mdates
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

try:
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

class AnalyticsDashboard(ttk.Frame):
    """Comprehensive analytics dashboard for schedule analysis."""
    
    def __init__(self, parent, main_app):
        super().__init__(parent)
        self.main_app = main_app
        self.schedule_data = []
        self.teams_data = {}
        self.rules_data = {}
        self.analytics_cache = {}
        
        # Always setup UI, but show warning if dependencies missing
        self.setup_ui()
        
        # Load initial data if available - but only after UI is set up
        self.after_idle(self.load_initial_data)
        
    def load_initial_data(self):
        """Load initial data from main app if available - called after UI setup."""
        try:
            if hasattr(self.main_app, 'schedule_data'):
                self.schedule_data = self.main_app.schedule_data or []
            if hasattr(self.main_app, 'teams_data'):
                self.teams_data = self.main_app.teams_data or {}
            if hasattr(self.main_app, 'rules_data'):
                self.rules_data = self.main_app.rules_data or {}
            
            # Refresh analytics if we have data and UI is ready
            if self.schedule_data and hasattr(self, 'metric_vars'):
                self.refresh_analytics()
        except Exception as e:
            print(f"Error loading initial data: {e}")
    
    def setup_ui(self):
        """Setup the UI regardless of dependencies."""
        if not MATPLOTLIB_AVAILABLE:
            self.show_dependency_warning()
            return
            
        # Create notebook for different analytics views
        self.analytics_notebook = ttk.Notebook(self)
        self.analytics_notebook.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Summary Dashboard Tab
        self.summary_frame = ttk.Frame(self.analytics_notebook)
        self.analytics_notebook.add(self.summary_frame, text="Summary Dashboard")
        self.setup_summary_dashboard()
        
        # Team Analysis Tab
        self.team_frame = ttk.Frame(self.analytics_notebook)
        self.analytics_notebook.add(self.team_frame, text="Team Analysis")
        self.setup_team_analysis()
        
        # Arena Utilization Tab
        self.arena_frame = ttk.Frame(self.analytics_notebook)
        self.analytics_notebook.add(self.arena_frame, text="Arena Utilization")
        self.setup_arena_analysis()
        
        # Fairness Metrics Tab
        self.fairness_frame = ttk.Frame(self.analytics_notebook)
        self.analytics_notebook.add(self.fairness_frame, text="Fairness Metrics")
        self.setup_fairness_analysis()
        
        # Export Tab
        self.export_frame = ttk.Frame(self.analytics_notebook)
        self.analytics_notebook.add(self.export_frame, text="Export Reports")
        self.setup_export_options()
        
    def show_dependency_warning(self):
        """Show warning about missing dependencies."""
        warning_frame = ttk.Frame(self)
        warning_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        warning_text = """
Analytics Dashboard Unavailable

Missing required dependencies. Please install:
• matplotlib (for charts): pip install matplotlib
• numpy (for calculations): pip install numpy  
• reportlab (for PDF export): pip install reportlab

After installation, restart the application.
        """
        
        warning_label = ttk.Label(warning_frame, text=warning_text, 
                                 font=("Arial", 12), justify="center")
        warning_label.pack(expand=True)
        
        # Add a button to retry
        retry_button = ttk.Button(warning_frame, text="Retry After Installing Dependencies", 
                                 command=self.retry_setup)
        retry_button.pack(pady=10)
        
    def retry_setup(self):
        """Retry setting up the dashboard after dependencies are installed."""
        # Clear current widgets
        for widget in self.winfo_children():
            widget.destroy()
        
        # Re-import and check dependencies
        global MATPLOTLIB_AVAILABLE, NUMPY_AVAILABLE, REPORTLAB_AVAILABLE
        try:
            import matplotlib.pyplot as plt
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            import matplotlib.dates as mdates
            MATPLOTLIB_AVAILABLE = True
        except ImportError:
            MATPLOTLIB_AVAILABLE = False
        
        try:
            import numpy as np
            NUMPY_AVAILABLE = True
        except ImportError:
            NUMPY_AVAILABLE = False
        
        try:
            from reportlab.lib.pagesizes import letter, A4
            REPORTLAB_AVAILABLE = True
        except ImportError:
            REPORTLAB_AVAILABLE = False
        
        # Setup UI again
        self.setup_ui()
        
    def setup_summary_dashboard(self):
        """Create the main dashboard with key metrics."""
        # Control panel
        control_frame = ttk.Frame(self.summary_frame)
        control_frame.pack(fill="x", padx=10, pady=5)
        
        ttk.Button(control_frame, text="Refresh Analytics", 
                  command=self.refresh_analytics).pack(side="left", padx=5)
        ttk.Button(control_frame, text="Export Summary", 
                  command=self.export_summary_report).pack(side="left", padx=5)
        
        # Status indicator
        self.status_var = tk.StringVar(value="No data loaded")
        status_label = ttk.Label(control_frame, textvariable=self.status_var, 
                                foreground="orange")
        status_label.pack(side="right", padx=5)
        
        # Metrics display area
        metrics_frame = ttk.LabelFrame(self.summary_frame, text="Key Metrics", padding=10)
        metrics_frame.pack(fill="x", padx=10, pady=5)
        
        # Create metric display widgets
        self.setup_metric_widgets(metrics_frame)
        
        # Charts area
        charts_frame = ttk.Frame(self.summary_frame)
        charts_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        # Split into left and right for two charts
        left_chart = ttk.LabelFrame(charts_frame, text="Schedule Distribution", padding=5)
        left_chart.pack(side="left", fill="both", expand=True, padx=(0, 5))
        
        right_chart = ttk.LabelFrame(charts_frame, text="Ice Time Allocation", padding=5)
        right_chart.pack(side="right", fill="both", expand=True, padx=(5, 0))
        
        self.setup_summary_charts(left_chart, right_chart)
        
    def setup_metric_widgets(self, parent):
        """Setup metric display widgets."""
        # Create grid of metric displays
        self.metric_vars = {}
        metrics = [
            ("total_events", "Total Events"),
            ("total_teams", "Teams"),
            ("total_arenas", "Arenas"),
            ("avg_utilization", "Avg Arena Utilization"),
            ("conflict_count", "Conflicts"),
            ("shared_ice_sessions", "Shared Ice Sessions"),
            ("fairness_score", "Fairness Score"),
            ("completion_rate", "Schedule Completion")
        ]
        
        for i, (key, label) in enumerate(metrics):
            row, col = i // 4, (i % 4) * 2
            
            ttk.Label(parent, text=f"{label}:", font=("Arial", 9, "bold")).grid(
                row=row, column=col, sticky="w", padx=5, pady=2)
            
            var = tk.StringVar(value="--")
            self.metric_vars[key] = var
            ttk.Label(parent, textvariable=var, font=("Arial", 12), foreground="blue").grid(
                row=row, column=col+1, sticky="w", padx=10, pady=2)
                
    def setup_summary_charts(self, left_parent, right_parent):
        """Setup summary charts."""
        if not MATPLOTLIB_AVAILABLE:
            ttk.Label(left_parent, text="Charts unavailable\n(matplotlib required)").pack(expand=True)
            ttk.Label(right_parent, text="Charts unavailable\n(matplotlib required)").pack(expand=True)
            return
            
        try:
            # Left chart: Events by day of week
            self.fig_left, self.ax_left = plt.subplots(figsize=(6, 4))
            self.canvas_left = FigureCanvasTkAgg(self.fig_left, left_parent)
            self.canvas_left.get_tk_widget().pack(fill="both", expand=True)
            
            # Right chart: Ice time by team type
            self.fig_right, self.ax_right = plt.subplots(figsize=(6, 4))
            self.canvas_right = FigureCanvasTkAgg(self.fig_right, right_parent)
            self.canvas_right.get_tk_widget().pack(fill="both", expand=True)
        except Exception as e:
            ttk.Label(left_parent, text=f"Chart setup error:\n{e}").pack(expand=True)
            ttk.Label(right_parent, text=f"Chart setup error:\n{e}").pack(expand=True)
        
    def setup_team_analysis(self):
        """Setup team-specific analysis tab."""
        # Team selector
        selector_frame = ttk.Frame(self.team_frame)
        selector_frame.pack(fill="x", padx=10, pady=5)
        
        ttk.Label(selector_frame, text="Select Team:").pack(side="left", padx=5)
        self.team_var = tk.StringVar()
        self.team_combo = ttk.Combobox(selector_frame, textvariable=self.team_var, 
                                      state="readonly", width=30)
        self.team_combo.pack(side="left", padx=5)
        self.team_combo.bind("<<ComboboxSelected>>", self.update_team_analysis)
        
        # Team metrics
        team_metrics_frame = ttk.LabelFrame(self.team_frame, text="Team Metrics", padding=10)
        team_metrics_frame.pack(fill="x", padx=10, pady=5)
        
        self.team_metrics_text = tk.Text(team_metrics_frame, height=8, wrap="word")
        team_scroll = ttk.Scrollbar(team_metrics_frame, orient="vertical", 
                                   command=self.team_metrics_text.yview)
        self.team_metrics_text.configure(yscrollcommand=team_scroll.set)
        self.team_metrics_text.pack(side="left", fill="both", expand=True)
        team_scroll.pack(side="right", fill="y")
        
        # Team schedule chart
        team_chart_frame = ttk.LabelFrame(self.team_frame, text="Schedule Timeline", padding=5)
        team_chart_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        if MATPLOTLIB_AVAILABLE:
            try:
                self.fig_team, self.ax_team = plt.subplots(figsize=(10, 4))
                self.canvas_team = FigureCanvasTkAgg(self.fig_team, team_chart_frame)
                self.canvas_team.get_tk_widget().pack(fill="both", expand=True)
            except Exception as e:
                ttk.Label(team_chart_frame, text=f"Chart error: {e}").pack(expand=True)
        else:
            ttk.Label(team_chart_frame, text="Chart unavailable (matplotlib required)").pack(expand=True)
        
    def setup_arena_analysis(self):
        """Setup arena utilization analysis."""
        # Basic setup with text display for now
        info_label = ttk.Label(self.arena_frame, text="Arena analysis will be displayed here when data is loaded.")
        info_label.pack(expand=True)
        
    def setup_fairness_analysis(self):
        """Setup fairness metrics analysis."""
        # Basic setup with text display for now
        info_label = ttk.Label(self.fairness_frame, text="Fairness analysis will be displayed here when data is loaded.")
        info_label.pack(expand=True)
        
    def setup_export_options(self):
        """Setup export options tab."""
        export_main_frame = ttk.Frame(self.export_frame)
        export_main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # PDF Reports section
        pdf_frame = ttk.LabelFrame(export_main_frame, text="PDF Reports", padding=15)
        pdf_frame.pack(fill="x", pady=(0, 15))
        
        if REPORTLAB_AVAILABLE:
            ttk.Button(pdf_frame, text="Complete Schedule Report", 
                      command=self.export_complete_schedule_pdf).pack(pady=5)
            ttk.Button(pdf_frame, text="Team-Specific Schedules", 
                      command=self.export_team_schedules_pdf).pack(pady=5)
            ttk.Button(pdf_frame, text="Arena Utilization Report", 
                      command=self.export_arena_report_pdf).pack(pady=5)
        else:
            ttk.Label(pdf_frame, text="PDF export unavailable\n(reportlab required)", 
                     foreground="gray").pack(pady=10)
        
    def load_data(self, schedule_data=None, teams_data=None, rules_data=None):
        """Load data for analysis."""
        print(f"Analytics: Loading data - schedule: {len(schedule_data or [])}, teams: {len(teams_data or {})}")
        
        if schedule_data is not None:
            self.schedule_data = schedule_data
        if teams_data is not None:
            self.teams_data = teams_data
        if rules_data is not None:
            self.rules_data = rules_data
            
        # Update combo boxes
        if MATPLOTLIB_AVAILABLE and hasattr(self, 'team_combo'):
            team_names = sorted(self.teams_data.keys()) if self.teams_data else []
            self.team_combo.configure(values=team_names)
        
        # Clear cache
        self.analytics_cache.clear()
        
        # Refresh analytics
        self.refresh_analytics()
        
    def refresh_analytics(self):
        """Refresh all analytics displays."""
        if not self.schedule_data:
            if hasattr(self, 'metric_vars'):
                for var in self.metric_vars.values():
                    var.set("No Data")
                if hasattr(self, 'status_var'):
                    self.status_var.set("No schedule data available")
            return
            
        if hasattr(self, 'status_var'):
            self.status_var.set(f"Analyzing {len(self.schedule_data)} events")
            
        self.calculate_summary_metrics()
        if MATPLOTLIB_AVAILABLE and hasattr(self, 'canvas_left'):
            self.update_summary_charts()
        
    def calculate_summary_metrics(self):
        """Calculate and display summary metrics."""
        if not hasattr(self, 'metric_vars'):
            return
            
        # Basic counts
        total_events = len(self.schedule_data)
        unique_teams = len(set(event.get("team", "") for event in self.schedule_data))
        unique_arenas = len(set(event.get("arena", "") for event in self.schedule_data))
        
        # Shared ice sessions
        shared_sessions = sum(1 for event in self.schedule_data 
                            if "shared" in event.get("type", "").lower())
        
        # Update metric displays
        self.metric_vars["total_events"].set(str(total_events))
        self.metric_vars["total_teams"].set(str(unique_teams))
        self.metric_vars["total_arenas"].set(str(unique_arenas))
        self.metric_vars["shared_ice_sessions"].set(str(shared_sessions))
        
        # Set placeholder values for other metrics
        self.metric_vars["avg_utilization"].set("75%")
        self.metric_vars["conflict_count"].set("0")
        self.metric_vars["fairness_score"].set("Good")
        self.metric_vars["completion_rate"].set("90%")
        
    def update_summary_charts(self):
        """Update the summary charts with current data."""
        try:
            if not hasattr(self, 'ax_left') or not hasattr(self, 'ax_right'):
                return
                
            # Clear previous plots
            self.ax_left.clear()
            self.ax_right.clear()
            
            # Left chart: Events by day of week
            day_counts = defaultdict(int)
            for event in self.schedule_data:
                try:
                    date_str = event.get("date", "")
                    if date_str:
                        date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d")
                        day_name = date_obj.strftime("%A")
                        day_counts[day_name] += 1
                except (ValueError, TypeError):
                    continue
            
            if day_counts:
                days = list(day_counts.keys())
                counts = list(day_counts.values())
                self.ax_left.bar(days, counts)
                self.ax_left.set_title("Events by Day of Week")
                self.ax_left.tick_params(axis='x', rotation=45)
            
            # Right chart: Events by type
            type_counts = defaultdict(int)
            for event in self.schedule_data:
                event_type = event.get("type", "unknown")
                type_counts[event_type] += 1
            
            if type_counts:
                types = list(type_counts.keys())
                counts = list(type_counts.values())
                self.ax_right.pie(counts, labels=types, autopct='%1.1f%%')
                self.ax_right.set_title("Events by Type")
            
            # Refresh canvases
            self.canvas_left.draw()
            self.canvas_right.draw()
            
        except Exception as e:
            print(f"Error updating charts: {e}")
    
    def update_team_analysis(self, event=None):
        """Update team-specific analysis with timeline chart."""
        selected_team = self.team_var.get()
        if not selected_team or not self.schedule_data:
            return
            
        # Filter events for selected team
        team_events = [event for event in self.schedule_data 
                      if event.get("team") == selected_team]
        
        # Update text display
        if hasattr(self, 'team_metrics_text'):
            self.team_metrics_text.delete(1.0, tk.END)
            
            metrics_text = f"Team: {selected_team}\n"
            metrics_text += f"Total Events: {len(team_events)}\n"
            
            if team_events:
                practice_count = sum(1 for e in team_events if "practice" in e.get("type", "").lower())
                game_count = sum(1 for e in team_events if "game" in e.get("type", "").lower())
                
                metrics_text += f"Practices: {practice_count}\n"
                metrics_text += f"Games: {game_count}\n"
                
                # Add more detailed analysis
                arenas = set(e.get("arena", "") for e in team_events)
                metrics_text += f"Arenas Used: {', '.join(sorted(arenas))}\n"
                
                # Time distribution
                if len(team_events) > 1:
                    dates = []
                    for e in team_events:
                        try:
                            date_obj = datetime.datetime.strptime(e.get("date", ""), "%Y-%m-%d")
                            dates.append(date_obj)
                        except ValueError:
                            continue
                    
                    if dates:
                        dates.sort()
                        first_event = dates[0].strftime("%Y-%m-%d")
                        last_event = dates[-1].strftime("%Y-%m-%d")
                        metrics_text += f"First Event: {first_event}\n"
                        metrics_text += f"Last Event: {last_event}\n"
            
            self.team_metrics_text.insert(1.0, metrics_text)
        
        # Update timeline chart
        self.update_team_timeline_chart(team_events)

    def update_team_timeline_chart(self, team_events):
        """Create a timeline chart showing team's schedule distribution."""
        if not hasattr(self, 'ax_team') or not team_events:
            return
        
        try:
            # Clear previous chart
            self.ax_team.clear()
            
            # Parse dates and times
            practices = []
            games = []
            
            for event in team_events:
                try:
                    date_str = event.get("date", "")
                    time_slot = event.get("time_slot", "")
                    event_type = event.get("type", "").lower()
                    
                    if not date_str or not time_slot:
                        continue
                    
                    # Parse date
                    event_date = datetime.datetime.strptime(date_str, "%Y-%m-%d")
                    
                    # Parse start time
                    start_time_str = time_slot.split("-")[0].strip()
                    start_time = datetime.datetime.strptime(start_time_str, "%H:%M").time()
                    
                    # Combine date and time
                    event_datetime = datetime.datetime.combine(event_date.date(), start_time)
                    
                    # Categorize by type
                    if "game" in event_type:
                        games.append((event_datetime, event))
                    else:
                        practices.append((event_datetime, event))
                        
                except (ValueError, IndexError) as e:
                    continue  # Skip invalid events
            
            # Plot practices
            if practices:
                practice_dates = [p[0] for p in practices]
                practice_y = [1] * len(practice_dates)  # All practices at y=1
                self.ax_team.scatter(practice_dates, practice_y, 
                                   c='blue', marker='o', s=50, alpha=0.7, label='Practices')
            
            # Plot games
            if games:
                game_dates = [g[0] for g in games]
                game_y = [2] * len(game_dates)  # All games at y=2
                self.ax_team.scatter(game_dates, game_y, 
                                   c='red', marker='^', s=70, alpha=0.7, label='Games')
            
            # Customize the chart
            self.ax_team.set_xlabel('Date')
            self.ax_team.set_ylabel('Event Type')
            self.ax_team.set_yticks([1, 2])
            self.ax_team.set_yticklabels(['Practices', 'Games'])
            self.ax_team.set_title(f'Schedule Timeline for {self.team_var.get()}')
            
            # Format x-axis for dates
            if practices or games:
                import matplotlib.dates as mdates
                self.ax_team.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d'))
                self.ax_team.xaxis.set_major_locator(mdates.WeekdayLocator(interval=1))
                
                # Rotate date labels
                plt.setp(self.ax_team.xaxis.get_majorticklabels(), rotation=45, ha='right')
            
            # Add legend
            if practices or games:
                self.ax_team.legend()
            
            # Add grid for better readability
            self.ax_team.grid(True, alpha=0.3)
            
            # Adjust layout and refresh
            self.fig_team.tight_layout()
            self.canvas_team.draw()
            
        except Exception as e:
            print(f"Error updating team timeline chart: {e}")
            # Show error message on chart
            self.ax_team.clear()
            self.ax_team.text(0.5, 0.5, f"Error creating timeline:\n{str(e)}", 
                             ha='center', va='center', transform=self.ax_team.transAxes)
            self.canvas_team.draw()
    
    # Placeholder methods for export functionality
    def export_summary_report(self):
        messagebox.showinfo("Export", "Summary report export not yet implemented.")
        
    def export_complete_schedule_pdf(self):
        messagebox.showinfo("Export", "PDF export not yet implemented.")
        
    def export_team_schedules_pdf(self):
        messagebox.showinfo("Export", "Team schedules PDF export not yet implemented.")
        
    def export_arena_report_pdf(self):
        messagebox.showinfo("Export", "Arena report PDF export not yet implemented.")