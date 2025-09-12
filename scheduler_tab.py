import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from tkinter.filedialog import asksaveasfilename
import csv
import datetime
from collections import defaultdict

class ConflictResolutionDialog(tk.Toplevel):
    """Dialog for resolving scheduling conflicts and editing schedule entries."""
    
    def __init__(self, parent, schedule_entry, all_teams, all_arenas, callback=None):
        super().__init__(parent)
        self.parent = parent
        self.schedule_entry = schedule_entry.copy()
        self.original_entry = schedule_entry.copy()
        self.all_teams = all_teams
        self.all_arenas = all_arenas
        self.callback = callback
        self.result = None
        
        self.title("Edit Schedule Entry")
        self.geometry("500x400")
        self.transient(parent)
        self.grab_set()
        
        self.setup_ui()
        self.load_entry_data()
        
    def setup_ui(self):
        main_frame = ttk.Frame(self, padding=10)
        main_frame.pack(fill="both", expand=True)
        
        # Team selection
        ttk.Label(main_frame, text="Team:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.team_var = tk.StringVar()
        self.team_combo = ttk.Combobox(main_frame, textvariable=self.team_var, 
                                       values=sorted(self.all_teams), state="readonly")
        self.team_combo.grid(row=0, column=1, sticky="ew", padx=5, pady=5)
        
        # Opponent selection
        ttk.Label(main_frame, text="Opponent:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.opponent_var = tk.StringVar()
        opponent_values = ["Practice", "TBD"] + sorted(self.all_teams)
        self.opponent_combo = ttk.Combobox(main_frame, textvariable=self.opponent_var,
                                          values=opponent_values)
        self.opponent_combo.grid(row=1, column=1, sticky="ew", padx=5, pady=5)
        
        # Arena selection
        ttk.Label(main_frame, text="Arena:").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        self.arena_var = tk.StringVar()
        self.arena_combo = ttk.Combobox(main_frame, textvariable=self.arena_var,
                                       values=sorted(self.all_arenas), state="readonly")
        self.arena_combo.grid(row=2, column=1, sticky="ew", padx=5, pady=5)
        
        # Date selection
        ttk.Label(main_frame, text="Date (YYYY-MM-DD):").grid(row=3, column=0, sticky="w", padx=5, pady=5)
        self.date_var = tk.StringVar()
        self.date_entry = ttk.Entry(main_frame, textvariable=self.date_var)
        self.date_entry.grid(row=3, column=1, sticky="ew", padx=5, pady=5)
        
        # Time slot
        ttk.Label(main_frame, text="Time Slot (HH:MM-HH:MM):").grid(row=4, column=0, sticky="w", padx=5, pady=5)
        self.time_var = tk.StringVar()
        self.time_entry = ttk.Entry(main_frame, textvariable=self.time_var)
        self.time_entry.grid(row=4, column=1, sticky="ew", padx=5, pady=5)
        
        # Type selection
        ttk.Label(main_frame, text="Type:").grid(row=5, column=0, sticky="w", padx=5, pady=5)
        self.type_var = tk.StringVar()
        self.type_combo = ttk.Combobox(main_frame, textvariable=self.type_var,
                                      values=["practice", "game", "shared practice"], state="readonly")
        self.type_combo.grid(row=5, column=1, sticky="ew", padx=5, pady=5)
        
        # Conflict detection area
        conflict_frame = ttk.LabelFrame(main_frame, text="Potential Conflicts", padding=5)
        conflict_frame.grid(row=6, column=0, columnspan=2, sticky="ew", padx=5, pady=10)
        
        self.conflict_text = tk.Text(conflict_frame, height=6, wrap="word")
        conflict_scrollbar = ttk.Scrollbar(conflict_frame, orient="vertical", command=self.conflict_text.yview)
        self.conflict_text.configure(yscrollcommand=conflict_scrollbar.set)
        self.conflict_text.pack(side="left", fill="both", expand=True)
        conflict_scrollbar.pack(side="right", fill="y")
        
        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=7, column=0, columnspan=2, pady=10)
        
        ttk.Button(button_frame, text="Check Conflicts", command=self.check_conflicts).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Save Changes", command=self.save_changes).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Cancel", command=self.cancel).pack(side="left", padx=5)
        
        main_frame.columnconfigure(1, weight=1)
        
    def load_entry_data(self):
        """Load the current schedule entry data into the form."""
        self.team_var.set(self.schedule_entry.get("team", ""))
        self.opponent_var.set(self.schedule_entry.get("opponent", ""))
        self.arena_var.set(self.schedule_entry.get("arena", ""))
        self.date_var.set(self.schedule_entry.get("date", ""))
        self.time_var.set(self.schedule_entry.get("time_slot", ""))
        self.type_var.set(self.schedule_entry.get("type", ""))
        
    def check_conflicts(self):
        """Check for potential conflicts with the current settings."""
        conflicts = []
        
        # Get current values
        team = self.team_var.get()
        opponent = self.opponent_var.get()
        arena = self.arena_var.get()
        date = self.date_var.get()
        time_slot = self.time_var.get()
        
        # Basic validation
        if not all([team, arena, date, time_slot]):
            conflicts.append("Please fill in all required fields.")
            self.display_conflicts(conflicts)
            return
            
        try:
            datetime.datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            conflicts.append("Invalid date format. Use YYYY-MM-DD.")
            
        if "-" not in time_slot:
            conflicts.append("Invalid time slot format. Use HH:MM-HH:MM.")
        else:
            try:
                start_time, end_time = time_slot.split("-")
                datetime.datetime.strptime(start_time.strip(), "%H:%M")
                datetime.datetime.strptime(end_time.strip(), "%H:%M")
            except ValueError:
                conflicts.append("Invalid time format in time slot.")
        
        # Get parent's schedule data for conflict checking
        if hasattr(self.parent, 'schedule_data'):
            schedule_data = self.parent.schedule_data
            
            for entry in schedule_data:
                # Skip the original entry we're editing
                if entry == self.original_entry:
                    continue
                    
                # Check for team conflicts (same team, same date/time)
                if (entry.get("team") == team and 
                    entry.get("date") == date and 
                    entry.get("time_slot") == time_slot):
                    conflicts.append(f"Team {team} already has a booking at {time_slot} on {date}")
                
                # Check for arena conflicts (same arena, same date/time)
                if (entry.get("arena") == arena and 
                    entry.get("date") == date and 
                    entry.get("time_slot") == time_slot):
                    conflicts.append(f"Arena {arena} is already booked at {time_slot} on {date}")
                
                # Check if opponent team has conflicts
                if (opponent != "Practice" and opponent != "TBD" and
                    entry.get("team") == opponent and 
                    entry.get("date") == date and 
                    entry.get("time_slot") == time_slot):
                    conflicts.append(f"Opponent team {opponent} already has a booking at {time_slot} on {date}")
        
        if not conflicts:
            conflicts.append("No conflicts detected.")
            
        self.display_conflicts(conflicts)
        
    def display_conflicts(self, conflicts):
        """Display conflicts in the text area."""
        self.conflict_text.delete(1.0, tk.END)
        for conflict in conflicts:
            self.conflict_text.insert(tk.END, f"• {conflict}\n")
            
    def save_changes(self):
        """Save the changes and close the dialog."""
        # Update the schedule entry
        self.schedule_entry["team"] = self.team_var.get()
        self.schedule_entry["opponent"] = self.opponent_var.get()
        self.schedule_entry["arena"] = self.arena_var.get()
        self.schedule_entry["date"] = self.date_var.get()
        self.schedule_entry["time_slot"] = self.time_var.get()
        self.schedule_entry["type"] = self.type_var.get()
        
        # Validate required fields
        if not all([self.schedule_entry["team"], self.schedule_entry["arena"], 
                   self.schedule_entry["date"], self.schedule_entry["time_slot"]]):
            messagebox.showerror("Error", "Please fill in all required fields.")
            return
            
        self.result = self.schedule_entry
        if self.callback:
            self.callback(self.original_entry, self.schedule_entry)
        self.destroy()
        
    def cancel(self):
        """Cancel the dialog without saving."""
        self.result = None
        self.destroy()

class SchedulerTab(ttk.Frame):
    def __init__(self, parent, main_app):
        super().__init__(parent)
        self.main_app = main_app
        self.schedule_data = []
        self.filtered_schedule_data = []
        self.sort_state = {}
        self.create_widgets()
        
    def create_widgets(self):
        # Frame for schedule generation
        generation_frame = ttk.LabelFrame(self, text="Generate Schedule")
        generation_frame.pack(fill="x", padx=10, pady=10)
        generation_frame.columnconfigure(1, weight=1)

        # Season dates
        ttk.Label(
            generation_frame,
            text="Season Start Date (YYYY-MM-DD):"
        ).grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.start_date_entry = ttk.Entry(generation_frame)
        self.start_date_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        ttk.Label(
            generation_frame,
            text="Season End Date (YYYY-MM-DD):"
        ).grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.end_date_entry = ttk.Entry(generation_frame)
        self.end_date_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")

        # Buttons
        button_frame = ttk.Frame(generation_frame)
        button_frame.grid(row=2, column=0, columnspan=2, pady=10)
        ttk.Button(button_frame, text="Generate Schedule", command=self.generate_schedule).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Load Schedule", command=self.load_schedule).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Save Schedule", command=self.save_schedule).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Export to CSV", command=self.export_schedule_to_csv).pack(side="left", padx=5)

        # Manual entry button
        ttk.Button(button_frame, text="Add Manual Entry", command=self.add_manual_entry).pack(side="left", padx=5)

        # Filter frame
        filter_frame = ttk.LabelFrame(self, text="Filters")
        filter_frame.pack(fill="x", padx=10, pady=(0, 10))

        # Team filter
        ttk.Label(filter_frame, text="Team:").pack(side="left", padx=(10, 5))
        self.team_filter_var = tk.StringVar(value="All Teams")
        self.team_filter_cb = ttk.Combobox(filter_frame, textvariable=self.team_filter_var, 
                                          values=["All Teams"], state="readonly", width=25)
        self.team_filter_cb.pack(side="left", padx=5)
        self.team_filter_cb.bind("<<ComboboxSelected>>", lambda e: self.apply_filters())

        # Type filters (checkboxes)
        self.show_games_var = tk.BooleanVar(value=True)
        self.show_practices_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(filter_frame, text="Games", variable=self.show_games_var, 
                       command=self.apply_filters).pack(side="left", padx=(20, 5))
        ttk.Checkbutton(filter_frame, text="Practices", variable=self.show_practices_var, 
                       command=self.apply_filters).pack(side="left", padx=5)

        # Clear filters button
        ttk.Button(filter_frame, text="Clear Filters", command=self.clear_filters).pack(side="right", padx=10)

        # Schedule Display
        schedule_frame = ttk.LabelFrame(self, text="Generated Schedule")
        schedule_frame.pack(fill="both", expand=True, padx=10, pady=10)

        columns = ("team", "opponent", "arena", "date", "time_slot", "type")
        self.schedule_tree = ttk.Treeview(schedule_frame, columns=columns, show="headings")

        # Define headings and associate them with the sorting function
        self.schedule_tree.heading("team", text="Team", command=lambda: self.sort_column("team"))
        self.schedule_tree.heading("opponent", text="Opponent")
        self.schedule_tree.heading("arena", text="Arena", command=lambda: self.sort_column("arena"))
        self.schedule_tree.heading("date", text="Date", command=lambda: self.sort_column("date"))
        self.schedule_tree.heading("time_slot", text="Time")
        self.schedule_tree.heading("type", text="Type")

        # Set column widths
        self.schedule_tree.column("team", width=120)
        self.schedule_tree.column("opponent", width=120)
        self.schedule_tree.column("arena", width=100)
        self.schedule_tree.column("date", width=100)
        self.schedule_tree.column("time_slot", width=100)
        self.schedule_tree.column("type", width=80)

        self.schedule_tree.pack(fill="both", expand=True)
        
        # Bind right-click context menu
        self.schedule_tree.bind("<Button-3>", self.show_context_menu)
        self.schedule_tree.bind("<Double-1>", self.edit_selected_entry)
        
        # Create context menu
        self.context_menu = tk.Menu(self, tearoff=0)
        self.context_menu.add_command(label="Edit Entry", command=self.edit_selected_entry)
        self.context_menu.add_command(label="Delete Entry", command=self.delete_selected_entry)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Swap with...", command=self.swap_entry)
        self.context_menu.add_command(label="Move to Different Time", command=self.move_entry)

    def refresh_team_filter(self):
        """Update the team filter dropdown with available teams."""
        teams = sorted({e.get("team", "") for e in self.schedule_data if e.get("team")})
        values = ["All Teams"] + teams
        self.team_filter_cb.configure(values=values)
        
        # Reset to "All Teams" if current selection is no longer valid
        if self.team_filter_var.get() not in values:
            self.team_filter_var.set("All Teams")

    def apply_filters(self):
        """Apply the current filter settings to the schedule display."""
        selected_team = self.team_filter_var.get()
        show_games = self.show_games_var.get()
        show_practices = self.show_practices_var.get()

        # Filter the schedule data
        self.filtered_schedule_data = []
        for event in self.schedule_data:
            # Team filter
            team = event.get("team", "")
            if selected_team != "All Teams" and team != selected_team:
                continue
            
            # Type filter
            event_type = (event.get("type", "") or "").lower()
            if "game" in event_type and not show_games:
                continue
            if "practice" in event_type and not show_practices:
                continue
            
            self.filtered_schedule_data.append(event)

        # Update the display
        self.update_schedule_display()

    def clear_filters(self):
        """Reset all filters to their default state."""
        self.team_filter_var.set("All Teams")
        self.show_games_var.set(True)
        self.show_practices_var.set(True)
        self.apply_filters()

    def update_schedule_display(self):
        """Update the treeview with the current filtered data."""
        # Clear existing treeview data
        for item in self.schedule_tree.get_children():
            self.schedule_tree.delete(item)

        # Reset sort state for a new display
        self.sort_state = {}
        
        # Clear sort indicators from headers
        for column_id in self.schedule_tree["columns"]:
            heading_text = self.schedule_tree.heading(column_id, "text").strip('▲▼ ')
            self.schedule_tree.heading(column_id, text=heading_text)

        # Add filtered data to treeview
        for event in self.filtered_schedule_data:
            self.schedule_tree.insert("", "end", values=(
                event.get("team", ""),
                event.get("opponent", ""),
                event.get("arena", ""),
                event.get("date", ""),
                event.get("time_slot", ""),
                event.get("type", "")
            ))

    def show_context_menu(self, event):
        """Show context menu on right-click."""
        # Select the item under cursor
        item = self.schedule_tree.identify_row(event.y)
        if item:
            self.schedule_tree.selection_set(item)
            self.context_menu.post(event.x_root, event.y_root)

    def edit_selected_entry(self, event=None):
        """Edit the selected schedule entry."""
        selected_item = self.schedule_tree.selection()
        if not selected_item:
            messagebox.showwarning("No Selection", "Please select a schedule entry to edit.")
            return
            
        # Get the entry data
        item_values = self.schedule_tree.item(selected_item[0])['values']
        if not item_values:
            return
            
        entry = {
            "team": item_values[0],
            "opponent": item_values[1],
            "arena": item_values[2],
            "date": item_values[3],
            "time_slot": item_values[4],
            "type": item_values[5]
        }
        
        # Get available teams and arenas
        teams = list(self.main_app.teams_data.keys()) if self.main_app.teams_data else []
        arenas = list(self.main_app.arenas_data.keys()) if self.main_app.arenas_data else []
        
        # Open conflict resolution dialog
        dialog = ConflictResolutionDialog(self, entry, teams, arenas, self.update_schedule_entry)

    def add_manual_entry(self):
        """Add a new manual schedule entry."""
        teams = list(self.main_app.teams_data.keys()) if self.main_app.teams_data else []
        arenas = list(self.main_app.arenas_data.keys()) if self.main_app.arenas_data else []
        
        if not teams or not arenas:
            messagebox.showerror("Error", "Please ensure you have teams and arenas configured before adding manual entries.")
            return
        
        # Create empty entry
        entry = {
            "team": "",
            "opponent": "Practice",
            "arena": "",
            "date": "",
            "time_slot": "",
            "type": "practice"
        }
        
        dialog = ConflictResolutionDialog(self, entry, teams, arenas, self.add_new_schedule_entry)

    def update_schedule_entry(self, original_entry, updated_entry):
        """Update an existing schedule entry."""
        # Find and update the entry in schedule_data
        for i, entry in enumerate(self.schedule_data):
            if (entry.get("team") == original_entry.get("team") and
                entry.get("date") == original_entry.get("date") and
                entry.get("time_slot") == original_entry.get("time_slot") and
                entry.get("arena") == original_entry.get("arena")):
                self.schedule_data[i] = updated_entry
                break
        
        # Refresh the filters and display
        self.refresh_team_filter()
        self.apply_filters()
        
        # Notify main app of changes
        if hasattr(self.main_app, 'on_scheduler_updated'):
            self.main_app.on_scheduler_updated({'schedule': self.schedule_data})
            
        messagebox.showinfo("Success", "Schedule entry updated successfully.")

    def add_new_schedule_entry(self, original_entry, new_entry):
        """Add a new schedule entry."""
        self.schedule_data.append(new_entry)
        self.refresh_team_filter()
        self.apply_filters()
        
        # Notify main app of changes
        if hasattr(self.main_app, 'on_scheduler_updated'):
            self.main_app.on_scheduler_updated({'schedule': self.schedule_data})
            
        messagebox.showinfo("Success", "Schedule entry added successfully.")

    def delete_selected_entry(self):
        """Delete the selected schedule entry."""
        selected_item = self.schedule_tree.selection()
        if not selected_item:
            messagebox.showwarning("No Selection", "Please select a schedule entry to delete.")
            return
            
        if messagebox.askyesno("Confirm Delete", "Are you sure you want to delete this schedule entry?"):
            item_values = self.schedule_tree.item(selected_item[0])['values']
            
            # Remove from schedule_data
            self.schedule_data = [entry for entry in self.schedule_data 
                                if not (entry.get("team") == item_values[0] and
                                       entry.get("date") == item_values[3] and
                                       entry.get("time_slot") == item_values[4] and
                                       entry.get("arena") == item_values[2])]
            
            # Refresh the filters and display
            self.refresh_team_filter()
            self.apply_filters()
            
            # Notify main app of changes
            if hasattr(self.main_app, 'on_scheduler_updated'):
                self.main_app.on_scheduler_updated({'schedule': self.schedule_data})
                
            messagebox.showinfo("Success", "Schedule entry deleted successfully.")

    def swap_entry(self):
        """Swap the selected entry with another entry."""
        selected_item = self.schedule_tree.selection()
        if not selected_item:
            messagebox.showwarning("No Selection", "Please select a schedule entry to swap.")
            return
            
        # Create a simple dialog to select another entry to swap with
        messagebox.showinfo("Swap Feature", "This feature would allow you to select another schedule entry to swap times/arenas with. Implementation would require a selection dialog.")

    def move_entry(self):
        """Move the selected entry to a different time slot."""
        selected_item = self.schedule_tree.selection()
        if not selected_item:
            messagebox.showwarning("No Selection", "Please select a schedule entry to move.")
            return
            
        # For now, just open the edit dialog
        self.edit_selected_entry()

    def generate_schedule(self):
        start_date_str = self.start_date_entry.get()
        end_date_str = self.end_date_entry.get()

        if not start_date_str or not end_date_str:
            messagebox.showerror("Error", "Please enter both a start and end date.")
            return

        try:
            start_date = datetime.datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.datetime.strptime(end_date_str, '%Y-%m-%d').date()
            if start_date >= end_date:
                messagebox.showerror("Error", "End date must be after the start date.")
                return
        except ValueError:
            messagebox.showerror("Error", "Invalid date format. Please use YYYY-MM-DD.")
            return

        generated_schedule = self.main_app.generate_schedule((start_date, end_date))

        if generated_schedule:
            self.display_schedule(generated_schedule.get("schedule", []))

            # Import the helper function from scheduler_logic
            try:
                from scheduler_logic import format_allocation_message
                
                # Display enhanced summary with detailed allocation information
                allocation_analysis = generated_schedule.get("allocation_analysis", {})
                start_date_str = self.start_date_entry.get()
                end_date_str = self.end_date_entry.get()
                messagebox.showinfo("Schedule Generation Complete", 
                                f"Schedule from {start_date_str} to {end_date_str} generated successfully!")
            except ImportError:
                messagebox.showinfo("Schedule Generation Complete", 
                                   f"Schedule generated with {len(generated_schedule.get('schedule', []))} events.")

        else:
            messagebox.showinfo("No Schedule", "Could not generate a schedule. Please check your data and rules.")

    def display_schedule(self, schedule_data):
        """Display the schedule data and apply current filters."""
        self.schedule_data = schedule_data
        self.refresh_team_filter()
        self.apply_filters()
        
        # Notify main app that schedule was updated (this will trigger analytics update)
        if hasattr(self.main_app, 'on_scheduler_updated'):
            self.main_app.on_scheduler_updated({'schedule': self.schedule_data})

    def sort_column(self, col):
        current_sort_info = self.sort_state.get(col, ('', False))
        sort_order = current_sort_info[1]

        # Toggle sort order
        new_sort_order = not sort_order
        self.sort_state = {col: ('▲' if new_sort_order else '▼', new_sort_order)}

        # Update all headings to clear previous sort indicators and add the new one
        for column_id in self.schedule_tree["columns"]:
            heading_text = self.schedule_tree.heading(column_id, "text").strip('▲▼ ')
            if column_id == col:
                self.schedule_tree.heading(column_id, text=f"{heading_text} {'▲' if new_sort_order else '▼'}")
            else:
                self.schedule_tree.heading(column_id, text=heading_text)

        # Get all item IDs
        items = list(self.schedule_tree.get_children(''))

        # Define sorting key based on column
        if col == "date":
            # Sort by datetime.date objects for correct chronological order
            def sort_key(item_id):
                item_values = self.schedule_tree.item(item_id, 'values')
                date_str = item_values[3]
                try:
                    return datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
                except (ValueError, IndexError):
                    return datetime.date.min  # Fallback for invalid date strings
        else:
            # Sort alphabetically for other columns
            def sort_key(item_id):
                item_values = self.schedule_tree.item(item_id, 'values')
                col_index = self.schedule_tree["columns"].index(col)
                return item_values[col_index]

        # Sort the items
        sorted_items = sorted(items, key=sort_key, reverse=new_sort_order)

        # Rearrange items in the treeview
        for index, item_id in enumerate(sorted_items):
            self.schedule_tree.move(item_id, '', index)

    def save_schedule(self):
        self.main_app.save_schedule()

    def load_schedule(self):
        self.main_app.load_schedule()
        
    def get_season_dates(self):
        start_date_str = self.start_date_entry.get()
        end_date_str = self.end_date_entry.get()
        if not start_date_str or not end_date_str:
            raise ValueError("Please enter both start and end dates.")
        start_date = datetime.datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.datetime.strptime(end_date_str, '%Y-%m-%d').date()
        return start_date, end_date
        
    def get_schedule_data(self):
        return self.schedule_data

    def export_schedule_to_csv(self):
        if not self.schedule_data:
            messagebox.showerror("Error", "No schedule to export. Please generate a schedule first.")
            return

        try:
            file_path = asksaveasfilename(
                defaultextension=".csv",
                filetypes=[("CSV files", "*.csv")],
                initialfile="hockey_schedule.csv"
            )

            if not file_path:
                return

            with open(file_path, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(["Team", "Opponent", "Arena", "Date", "Start", "End", "Type"])
                for event in self.schedule_data:
                    time_slot = event.get("time_slot", "")
                    start, end = ("", "")
                    if "-" in time_slot:
                        parts = [p.strip() for p in time_slot.split("-", 1)]
                        try:
                            start = datetime.datetime.strptime(parts[0], "%H:%M").strftime("%I:%M %p")
                            end = datetime.datetime.strptime(parts[1], "%H:%M").strftime("%I:%M %p")
                        except ValueError:
                            # If parsing fails, just keep original values
                            start, end = parts

                    writer.writerow([
                        event.get("team", ""),
                        event.get("opponent", ""),
                        event.get("arena", ""),
                        event.get("date", ""),
                        start,
                        end,
                        event.get("type", "")
                    ])

            messagebox.showinfo("Success", "Schedule exported to CSV successfully!")
        except Exception as e:
            messagebox.showerror("Error", f"An error occurred while exporting: {e}")