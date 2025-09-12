import tkinter as tk
from tkinter import ttk, messagebox
import datetime

try:
    from tkcalendar import DateEntry
    CALENDAR_AVAILABLE = True
except ImportError:
    CALENDAR_AVAILABLE = False


class DatePickerEntry(ttk.Frame):
    """A custom widget that combines an Entry with a date picker button."""
    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.entry = ttk.Entry(self)
        self.entry.pack(side="left", fill="x", expand=True)

        self.button = ttk.Button(self, text="...", width=2, command=self.show_calendar)
        self.button.pack(side="left")

    def show_calendar(self):
        if not CALENDAR_AVAILABLE:
            messagebox.showwarning("Calendar Unavailable", "tkcalendar package not installed.")
            return
            
        def _set_date():
            self.entry.delete(0, tk.END)
            self.entry.insert(0, cal.get_date().strftime('%Y-%m-%d'))
            top.destroy()

        top = tk.Toplevel(self)
        top.grab_set()
        top.geometry("250x200")
        top.title("Select Date")
        cal = DateEntry(top, selectmode='day', date_pattern='yyyy-mm-dd')
        cal.pack(padx=10, pady=10)
        
        ok_button = ttk.Button(top, text="OK", command=_set_date)
        ok_button.pack(pady=5)

    def get(self):
        return self.entry.get()

    def set(self, value):
        self.entry.delete(0, tk.END)
        self.entry.insert(0, value)


class ArenaTab(ttk.Frame):
    def __init__(self, parent, main_app):
        super().__init__(parent)
        self.main_app = main_app
        self.arena_tree = None
        self.arena_data = {}
        self.current_arena_name = None
        self.create_widgets()

    def create_widgets(self):
        # Main frame to hold the two sub-frames
        main_frame = ttk.Frame(self)
        main_frame.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        
        # Frame for Arena List
        arena_list_frame = ttk.LabelFrame(main_frame, text="Arenas")
        arena_list_frame.pack(side="left", fill="y", expand=False)

        # Arena Treeview
        self.arena_tree = ttk.Treeview(arena_list_frame, columns=("Arena Name",), show="tree", selectmode="browse")
        self.arena_tree.pack(side="left", fill="both", expand=True)

        # Scrollbar for Arena Treeview
        arena_tree_scrollbar = ttk.Scrollbar(arena_list_frame, orient="vertical", command=self.arena_tree.yview)
        arena_tree_scrollbar.pack(side="right", fill="y")
        self.arena_tree.configure(yscrollcommand=arena_tree_scrollbar.set)
        
        # Bind double-click event
        self.arena_tree.bind("<Double-1>", self.select_arena)
        
        # Frame for Arena Details
        self.arena_details_frame = ttk.LabelFrame(main_frame, text="Arena Details", padding=10)
        self.arena_details_frame.pack(side="left", fill="both", expand=True, padx=10)
        
        self.arena_details_frame.columnconfigure(1, weight=1)

        # Arena Name
        ttk.Label(self.arena_details_frame, text="Arena Name:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.arena_name_entry = ttk.Entry(self.arena_details_frame)
        self.arena_name_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        # Buttons
        button_frame = ttk.Frame(self.arena_details_frame)
        button_frame.grid(row=1, column=0, columnspan=2, pady=5)
        ttk.Button(button_frame, text="Add/Update Arena", command=self.save_arena).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Delete Arena", command=self.delete_arena).pack(side="left", padx=5)
        
        # Create notebook for separating Regular Ice and Games
        self.notebook = ttk.Notebook(self.arena_details_frame)
        self.notebook.grid(row=2, column=0, columnspan=2, padx=5, pady=5, sticky="nsew")
        
        # Regular Ice Time Blocks Tab
        self.regular_ice_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.regular_ice_frame, text="Regular Ice Blocks")
        
        # Games Tab
        self.games_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.games_frame, text="Pre-assigned Games")
        
        self.create_regular_ice_widgets()
        self.create_games_widgets()

    def create_regular_ice_widgets(self):
        """Create widgets for regular ice time blocks"""
        # Frame for Ice Time Blocks
        ice_blocks_frame = ttk.LabelFrame(self.regular_ice_frame, text="Regular Ice Time Blocks", padding=10)
        ice_blocks_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Canvas and Scrollbar for the blocks
        canvas = tk.Canvas(ice_blocks_frame)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(ice_blocks_frame, orient="vertical", command=canvas.yview)
        scrollbar.pack(side="right", fill="y")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        self.blocks_container = ttk.Frame(canvas)
        canvas.create_window((0, 0), window=self.blocks_container, anchor="nw")
        
        self.blocks_container.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        # Buttons for managing ice time blocks
        block_button_frame = ttk.Frame(ice_blocks_frame)
        block_button_frame.pack(pady=5)
        ttk.Button(block_button_frame, text="Add Regular Ice Block", command=self.add_ice_time_block).pack(side="left", padx=5)

    def create_games_widgets(self):
        """Create widgets for game management"""
        # Frame for Games
        games_list_frame = ttk.LabelFrame(self.games_frame, text="Pre-assigned Games", padding=10)
        games_list_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Canvas and Scrollbar for games
        games_canvas = tk.Canvas(games_list_frame)
        games_canvas.pack(side="left", fill="both", expand=True)
        games_scrollbar = ttk.Scrollbar(games_list_frame, orient="vertical", command=games_canvas.yview)
        games_scrollbar.pack(side="right", fill="y")
        games_canvas.configure(yscrollcommand=games_scrollbar.set)
        
        self.games_container = ttk.Frame(games_canvas)
        games_canvas.create_window((0, 0), window=self.games_container, anchor="nw")
        
        self.games_container.bind("<Configure>", lambda e: games_canvas.configure(scrollregion=games_canvas.bbox("all")))

        # Buttons for managing games
        games_button_frame = ttk.Frame(games_list_frame)
        games_button_frame.pack(pady=5)
        ttk.Button(games_button_frame, text="Add New Game", command=self.add_game).pack(side="left", padx=5)

    def load_arenas_data(self, arena_data):
        self.arena_data = arena_data
        self.populate_arena_tree()

    def get_arenas_data(self):
        return self.arena_data

    def populate_arena_tree(self):
        for item in self.arena_tree.get_children():
            self.arena_tree.delete(item)
        for arena_name in sorted(self.arena_data.keys()):
            self.arena_tree.insert("", "end", iid=arena_name, text=arena_name)
            
    def save_arena(self):
        name = self.arena_name_entry.get().strip()
        if not name:
            messagebox.showerror("Error", "Arena name cannot be empty.")
            return

        if name not in self.arena_data:
            self.arena_data[name] = []
        
        self.populate_arena_tree()
        
        # Notify main app of changes
        if hasattr(self.main_app, 'on_arenas_updated'):
            self.main_app.on_arenas_updated(self.arena_data)
            
        messagebox.showinfo("Success", f"Arena '{name}' saved successfully!")
    
    def delete_arena(self):
        selected_item = self.arena_tree.focus()
        if not selected_item:
            messagebox.showerror("Error", "Please select an arena to delete.")
            return
            
        arena_name = self.arena_tree.item(selected_item, "text")
        if messagebox.askyesno("Delete Arena", f"Are you sure you want to delete arena '{arena_name}'?"):
            del self.arena_data[arena_name]
            self.populate_arena_tree()
            self.clear_details()
            
            # Notify main app of changes
            if hasattr(self.main_app, 'on_arenas_updated'):
                self.main_app.on_arenas_updated(self.arena_data)
            
    def select_arena(self, event):
        selected_item = self.arena_tree.focus()
        if not selected_item:
            return

        arena_name = self.arena_tree.item(selected_item, "text")
        self.current_arena_name = arena_name
        self.arena_name_entry.delete(0, tk.END)
        self.arena_name_entry.insert(0, arena_name)
        self.populate_blocks_frame(arena_name)
        self.populate_games_frame(arena_name)
        
    def clear_details(self):
        self.arena_name_entry.delete(0, tk.END)
        self.current_arena_name = None
        for widget in self.blocks_container.winfo_children():
            widget.destroy()
        for widget in self.games_container.winfo_children():
            widget.destroy()

    def populate_blocks_frame(self, arena_name):
        """Populate regular ice blocks (non-game blocks)"""
        for widget in self.blocks_container.winfo_children():
            widget.destroy()
            
        day_map = {'0': 'Mon', '1': 'Tue', '2': 'Wed', '3': 'Thu', '4': 'Fri', '5': 'Sat', '6': 'Sun'}
        
        regular_blocks = []
        for i, block in enumerate(self.arena_data.get(arena_name, [])):
            # Check if this block contains only practice slots (no pre-assigned games)
            has_games = False
            for day_slots in block.get('slots', {}).values():
                for slot in day_slots:
                    if slot.get('pre_assigned_team') or slot.get('type') == 'game':
                        has_games = True
                        break
                if has_games:
                    break
            
            if not has_games:
                regular_blocks.append((i, block))
        
        for block_index, block in regular_blocks:
            block_frame = ttk.Frame(self.blocks_container, padding=5, relief="solid", borderwidth=1)
            block_frame.pack(fill="x", pady=2)
            
            start_date_str = block.get('start', 'N/A')
            end_date_str = block.get('end', 'N/A')
            
            if isinstance(start_date_str, datetime.date):
                start_date_str = start_date_str.isoformat()
            if isinstance(end_date_str, datetime.date):
                end_date_str = end_date_str.isoformat()
            
            ttk.Label(block_frame, text=f"Dates: {start_date_str} to {end_date_str}").pack(anchor="w")

            time_summary = []
            for day_num, slots in block.get('slots', {}).items():
                day_name = day_map.get(day_num, 'Unknown')
                times = ", ".join([slot['time'] for slot in slots])
                time_summary.append(f"{day_name}: {times}")
            
            time_summary_str = "; ".join(time_summary)
            ttk.Label(block_frame, text=f"Time Slots: {time_summary_str}").pack(anchor="w")
            
            button_frame = ttk.Frame(block_frame)
            button_frame.pack(pady=5, anchor="e")
            
            ttk.Button(button_frame, text="Edit", command=lambda idx=block_index: self.edit_ice_time_block(idx)).pack(side="left", padx=5)
            ttk.Button(button_frame, text="Delete", command=lambda idx=block_index: self.remove_ice_time_block(idx)).pack(side="left")

    def populate_games_frame(self, arena_name):
        """Populate pre-assigned games"""
        for widget in self.games_container.winfo_children():
            widget.destroy()
            
        day_map = {'0': 'Mon', '1': 'Tue', '2': 'Wed', '3': 'Thu', '4': 'Fri', '5': 'Sat', '6': 'Sun'}
        
        games = []
        for block_index, block in enumerate(self.arena_data.get(arena_name, [])):
            for day_num, slots in block.get('slots', {}).items():
                for slot_index, slot in enumerate(slots):
                    if slot.get('pre_assigned_team') or slot.get('type') == 'game':
                        games.append({
                            'block_index': block_index,
                            'day_num': day_num,
                            'slot_index': slot_index,
                            'slot': slot,
                            'block_date': block.get('start', 'N/A')
                        })
        
        if not games:
            ttk.Label(self.games_container, text="No pre-assigned games configured.").pack(pady=10)
            return
        
        for game_info in games:
            game_frame = ttk.Frame(self.games_container, padding=5, relief="solid", borderwidth=1)
            game_frame.pack(fill="x", pady=2)
            
            slot = game_info['slot']
            day_name = day_map.get(game_info['day_num'], 'Unknown')
            
            team = slot.get('pre_assigned_team', 'Unknown Team')
            game_date = slot.get('pre_assigned_date', game_info['block_date'])
            game_time = slot.get('time', 'Unknown Time')
            duration = slot.get('duration', 60)
            
            ttk.Label(game_frame, text=f"Team: {team}").pack(anchor="w")
            ttk.Label(game_frame, text=f"Date: {game_date} ({day_name})").pack(anchor="w")
            ttk.Label(game_frame, text=f"Time: {game_time} ({duration} minutes)").pack(anchor="w")
            
            button_frame = ttk.Frame(game_frame)
            button_frame.pack(pady=5, anchor="e")
            
            ttk.Button(button_frame, text="Edit", command=lambda g=game_info: self.edit_game(g)).pack(side="left", padx=5)
            ttk.Button(button_frame, text="Delete", command=lambda g=game_info: self.delete_game(g)).pack(side="left")

    def add_game(self):
        """Add a new pre-assigned game"""
        if not self.current_arena_name:
            messagebox.showerror("Error", "Please select an arena first.")
            return
        
        self.open_game_dialog()

    def edit_game(self, game_info):
        """Edit an existing game"""
        self.open_game_dialog(game_info)

    def delete_game(self, game_info):
        """Delete a game"""
        if messagebox.askyesno("Delete Game", "Are you sure you want to delete this game?"):
            arena_name = self.current_arena_name
            block = self.arena_data[arena_name][game_info['block_index']]
            
            # Remove the game slot
            block['slots'][game_info['day_num']].pop(game_info['slot_index'])
            
            # If day has no more slots, remove the day
            if not block['slots'][game_info['day_num']]:
                del block['slots'][game_info['day_num']]
            
            # If block has no more slots, remove the block
            if not block['slots']:
                self.arena_data[arena_name].pop(game_info['block_index'])
            
            self.populate_games_frame(arena_name)
            
            # Notify main app of changes
            if hasattr(self.main_app, 'on_arenas_updated'):
                self.main_app.on_arenas_updated(self.arena_data)
                
            messagebox.showinfo("Success", "Game deleted successfully.")

    def open_game_dialog(self, game_info=None):
        """Open dialog for adding/editing games"""
        dialog = tk.Toplevel(self)
        dialog.title("Add Game" if game_info is None else "Edit Game")
        dialog.grab_set()
        dialog.geometry("500x400")
        
        # Get teams list
        teams = sorted(self.main_app.teams_data.keys()) if hasattr(self.main_app, 'teams_data') and self.main_app.teams_data else []
        
        # Team selection
        ttk.Label(dialog, text="Team:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        team_var = tk.StringVar()
        team_combo = ttk.Combobox(dialog, textvariable=team_var, values=teams, state="readonly")
        team_combo.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        
        # Game date
        ttk.Label(dialog, text="Game Date:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        date_entry = DatePickerEntry(dialog)
        date_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        
        # Game start time
        ttk.Label(dialog, text="Game Start Time (HH:MM):").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        start_time_entry = ttk.Entry(dialog)
        start_time_entry.grid(row=2, column=1, padx=5, pady=5, sticky="ew")
        
        # Game duration
        ttk.Label(dialog, text="Duration (minutes):").grid(row=3, column=0, padx=5, pady=5, sticky="w")
        duration_var = tk.StringVar(value="60")
        duration_combo = ttk.Combobox(dialog, textvariable=duration_var, values=["60", "90", "120"], state="readonly")
        duration_combo.grid(row=3, column=1, padx=5, pady=5, sticky="ew")
        
        # Available time slot
        ttk.Label(dialog, text="Available Time Slot:").grid(row=4, column=0, padx=5, pady=5, sticky="w")
        slot_var = tk.StringVar()
        slot_combo = ttk.Combobox(dialog, textvariable=slot_var, state="readonly")
        slot_combo.grid(row=4, column=1, padx=5, pady=5, sticky="ew")

        def populate_available_slots():
            try:
                available_slots = []
                selected_date = date_entry.get()
                
                if not selected_date:
                    return
                    
                # Parse the date
                game_date = datetime.datetime.strptime(selected_date, "%Y-%m-%d").date()
                weekday = str(game_date.weekday())
                
                # Check if we have arena data
                if not self.current_arena_name:
                    return
                    
                arena_blocks = self.arena_data.get(self.current_arena_name, [])
                if not arena_blocks:
                    return
                
                # Check each block
                for block in arena_blocks:
                    start_date = block.get('start')
                    end_date = block.get('end')
                    
                    # Convert string dates to date objects if needed
                    if isinstance(start_date, str):
                        start_date = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
                    if isinstance(end_date, str):
                        end_date = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()
                    
                    # Check if game date falls in this block's range
                    if start_date <= game_date <= end_date:
                        slots_for_day = block.get('slots', {}).get(weekday, [])
                        for slot in slots_for_day:
                            if not slot.get('pre_assigned_team'):
                                available_slots.append(slot['time'])
                
                # Update the dropdown
                slot_combo['values'] = available_slots
                if available_slots:
                    slot_var.set(available_slots[0])
                else:
                    slot_var.set('')
                    
            except Exception as e:
                print(f"Error in populate_available_slots: {e}")

        def on_date_change(event=None):
            populate_available_slots()

        # Bind the events
        date_entry.entry.bind('<KeyRelease>', on_date_change)
        date_entry.entry.bind('<FocusOut>', on_date_change)
        refresh_button = ttk.Button(dialog, text="↻", width=3, command=populate_available_slots)
        refresh_button.grid(row=4, column=2, padx=2, pady=5)
        
        # Pre-fill if editing
        if game_info:
            slot = game_info['slot']
            team_var.set(slot.get('pre_assigned_team', ''))
            date_entry.set(slot.get('pre_assigned_date', ''))
            start_time_entry.insert(0, slot.get('pre_assigned_time', ''))
            duration_var.set(str(slot.get('duration', 60)))
            slot_var.set(slot.get('time', ''))
        
        def save_game():
            if not all([team_var.get(), date_entry.get(), start_time_entry.get(), slot_var.get()]):
                messagebox.showerror("Error", "All fields are required.")
                return
            
            try:
                game_date = datetime.datetime.strptime(date_entry.get(), "%Y-%m-%d").date()
                game_start = datetime.datetime.strptime(start_time_entry.get(), "%H:%M")
                duration = int(duration_var.get())
                game_end = game_start + datetime.timedelta(minutes=duration)
                
                # Parse the selected time slot
                slot_time = slot_var.get()
                slot_start_str, slot_end_str = slot_time.split('-')
                slot_start = datetime.datetime.strptime(slot_start_str, "%H:%M")
                slot_end = datetime.datetime.strptime(slot_end_str, "%H:%M")
                
                # Validate game fits in slot
                if game_start < slot_start or game_end > slot_end:
                    messagebox.showerror("Error", "Game time must fit within the selected time slot.")
                    return
                
            except ValueError as e:
                messagebox.showerror("Error", f"Invalid time format: {e}")
                return
            
            # Create/update game entry
            weekday = str(game_date.weekday())
            
            # Create new block structure for this specific game
            game_slots = []
            
            # Add practice time before game if needed
            if game_start > slot_start:
                game_slots.append({
                    'time': f"{slot_start.strftime('%H:%M')}-{game_start.strftime('%H:%M')}",
                    'type': 'practice'
                })
            
            # Add the game slot
            game_slots.append({
                'time': f"{game_start.strftime('%H:%M')}-{game_end.strftime('%H:%M')}",
                'type': 'game',
                'pre_assigned_team': team_var.get(),
                'duration': duration,
                'pre_assigned_date': date_entry.get(),
                'pre_assigned_time': start_time_entry.get()
            })
            
            # Add practice time after game if needed
            if game_end < slot_end:
                game_slots.append({
                    'time': f"{game_end.strftime('%H:%M')}-{slot_end.strftime('%H:%M')}",
                    'type': 'practice'
                })
            
            # Add to arena data
            game_block = {
                'start': game_date,
                'end': game_date,
                'slots': {weekday: game_slots}
            }
            
            if game_info is None:
                # Adding new game
                self.arena_data[self.current_arena_name].append(game_block)
            else:
                # Editing existing game - remove old and add new
                old_block = self.arena_data[self.current_arena_name][game_info['block_index']]
                old_block['slots'][game_info['day_num']].pop(game_info['slot_index'])
                
                if not old_block['slots'][game_info['day_num']]:
                    del old_block['slots'][game_info['day_num']]
                if not old_block['slots']:
                    self.arena_data[self.current_arena_name].pop(game_info['block_index'])
                
                self.arena_data[self.current_arena_name].append(game_block)
            
            self.populate_games_frame(self.current_arena_name)
            
            # Notify main app of changes
            if hasattr(self.main_app, 'on_arenas_updated'):
                self.main_app.on_arenas_updated(self.arena_data)
                
            messagebox.showinfo("Success", "Game saved successfully.")
            dialog.destroy()
        
        # Buttons
        button_frame = ttk.Frame(dialog)
        button_frame.grid(row=5, column=0, columnspan=2, pady=10)
        ttk.Button(button_frame, text="Save", command=save_game).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side="left", padx=5)
        
        dialog.columnconfigure(1, weight=1)

    def add_ice_time_block(self):
        """Method to open a new, empty block editing window."""
        if not self.current_arena_name:
            messagebox.showerror("Error", "Please select an arena first.")
            return

        self._open_block_dialog(is_new_block=True)

    def edit_ice_time_block(self, block_index):
        """Method to open the block editing window with data from a selected block."""
        if not self.current_arena_name:
            messagebox.showerror("Error", "Please select an arena first.")
            return
        
        self._open_block_dialog(is_new_block=False, block_index=block_index)

    def _open_block_dialog(self, is_new_block, block_index=None):
        """Simplified block dialog - only for regular practice ice"""
        arena_name = self.current_arena_name

        block_data = {}
        if not is_new_block and block_index is not None:
            block_data = self.arena_data[arena_name][block_index]

        dialog = tk.Toplevel(self)
        dialog.title("Edit Regular Ice Block")
        dialog.grab_set()
        dialog.geometry("600x500")

        # Date Frame
        date_frame = ttk.LabelFrame(dialog, text="Block Dates (YYYY-MM-DD)")
        date_frame.pack(padx=10, pady=10, fill="x")
        date_frame.columnconfigure(1, weight=1)

        ttk.Label(date_frame, text="Start Date:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        start_date_entry = DatePickerEntry(date_frame)
        start_date_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        
        ttk.Label(date_frame, text="End Date:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        end_date_entry = DatePickerEntry(date_frame)
        end_date_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")

        # Weekday/Time Slots Frame
        slots_frame = ttk.LabelFrame(dialog, text="Regular Practice Time Slots")
        slots_frame.pack(padx=10, pady=10, fill="both", expand=True)

        # Canvas and Scrollbar for dynamic slots
        canvas = tk.Canvas(slots_frame)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(slots_frame, orient="vertical", command=canvas.yview)
        scrollbar.pack(side="right", fill="y")
        canvas.configure(yscrollcommand=scrollbar.set)

        self.slots_container = ttk.Frame(canvas)
        canvas.create_window((0, 0), window=self.slots_container, anchor="nw")
        
        self.slots_list = []  # To hold a reference to the slot widgets

        def add_slot_row(slot_data=None):
            row_frame = ttk.Frame(self.slots_container, padding=5)
            row_frame.pack(fill="x")
            
            days_of_week = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
            day_map = {day: str(i) for i, day in enumerate(days_of_week)}

            day_var = tk.StringVar(value=days_of_week[0])
            day_combobox = ttk.Combobox(row_frame, textvariable=day_var, values=days_of_week, state="readonly", width=10)
            day_combobox.pack(side="left", padx=5)

            ttk.Label(row_frame, text="from").pack(side="left")
            start_time_entry = ttk.Entry(row_frame, width=8)
            start_time_entry.pack(side="left", padx=5)

            ttk.Label(row_frame, text="to").pack(side="left")
            end_time_entry = ttk.Entry(row_frame, width=8)
            end_time_entry.pack(side="left", padx=5)

            def remove_row():
                row_frame.destroy()
                self.slots_list.remove(slot_info)
                canvas.configure(scrollregion=canvas.bbox("all"))

            remove_button = ttk.Button(row_frame, text="Remove", command=remove_row)
            remove_button.pack(side="left", padx=5)

            slot_info = {
                'frame': row_frame,
                'day_var': day_var,
                'start_time_entry': start_time_entry,
                'end_time_entry': end_time_entry
            }
            self.slots_list.append(slot_info)
            
            if slot_data:
                day_name = next((day for day, num in day_map.items() if num == slot_data['day']), days_of_week[0])
                day_var.set(day_name)
                start_time_entry.insert(0, slot_data['start_time'])
                end_time_entry.insert(0, slot_data['end_time'])

            self.slots_container.update_idletasks()
            canvas.configure(scrollregion=canvas.bbox("all"))

        # Pre-fill data if editing
        if not is_new_block:
            start_date = block_data.get('start', '')
            if isinstance(start_date, datetime.date):
                start_date_entry.set(start_date.isoformat())
            else:
                start_date_entry.set(start_date)

            end_date = block_data.get('end', '')
            if isinstance(end_date, datetime.date):
                end_date_entry.set(end_date.isoformat())
            else:
                end_date_entry.set(end_date)
            
            # Only add practice slots (skip any game slots)
            for day_num, slots in block_data.get('slots', {}).items():
                for slot in slots:
                    if not slot.get('pre_assigned_team') and slot.get('type', 'practice') == 'practice':
                        start_time, end_time = slot['time'].split('-')
                        add_slot_row({
                            'day': day_num,
                            'start_time': start_time,
                            'end_time': end_time
                        })
        else:
            add_slot_row()

        add_row_button = ttk.Button(dialog, text="Add Another Time Slot", command=lambda: add_slot_row())
        add_row_button.pack(pady=5)
            
        def save_block():
            try:
                start_date_str = start_date_entry.get()
                end_date_str = end_date_entry.get()
                start_date = datetime.date.fromisoformat(start_date_str)
                end_date = datetime.date.fromisoformat(end_date_str)
                if start_date > end_date:
                    raise ValueError("Start date cannot be after end date.")
            except ValueError as e:
                messagebox.showerror("Error", f"Invalid date format. Please use YYYY-MM-DD. {e}")
                return

            day_map_rev = {'Monday': '0', 'Tuesday': '1', 'Wednesday': '2', 'Thursday': '3', 'Friday': '4', 'Saturday': '5', 'Sunday': '6'}
            new_slots_data = {}
            
            for slot_info in self.slots_list:
                day_name = slot_info['day_var'].get()
                day_num = day_map_rev.get(day_name)
                start_time_str = slot_info['start_time_entry'].get().strip()
                end_time_str = slot_info['end_time_entry'].get().strip()

                if not start_time_str or not end_time_str:
                    continue
                
                # Validate time format
                try:
                    datetime.datetime.strptime(start_time_str, '%H:%M')
                    datetime.datetime.strptime(end_time_str, '%H:%M')
                except ValueError:
                    messagebox.showerror("Error", f"Invalid time format. Please use HH:MM format.")
                    return
                
                new_slot = {
                    'time': f"{start_time_str}-{end_time_str}",
                    'type': 'practice'
                }
                if day_num not in new_slots_data:
                    new_slots_data[day_num] = []
                new_slots_data[day_num].append(new_slot)
            
            if not new_slots_data:
                messagebox.showerror("Error", "Please add at least one time slot.")
                return
            
            new_block = {
                'start': start_date,
                'end': end_date,
                'slots': new_slots_data
            }

            if is_new_block:
                self.arena_data[arena_name].append(new_block)
            else:
                self.arena_data[arena_name][block_index] = new_block
                
            self.populate_blocks_frame(arena_name)
            
            # Notify main app of changes
            if hasattr(self.main_app, 'on_arenas_updated'):
                self.main_app.on_arenas_updated(self.arena_data)
                
            messagebox.showinfo("Success", "Regular ice block saved.")
            dialog.destroy()

        button_frame = ttk.Frame(dialog)
        button_frame.pack(pady=10)
        ttk.Button(button_frame, text="Save Block", command=save_block).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side="left", padx=5)

    def remove_ice_time_block(self, block_index):
        if not self.current_arena_name:
            messagebox.showerror("Error", "Please select an arena first.")
            return
        
        arena_name = self.current_arena_name
        
        if messagebox.askyesno("Remove Block", "Are you sure you want to remove this ice time block?"):
            del self.arena_data[arena_name][block_index]
            self.populate_blocks_frame(arena_name)
            
            # Notify main app of changes
            if hasattr(self.main_app, 'on_arenas_updated'):
                self.main_app.on_arenas_updated(self.arena_data)