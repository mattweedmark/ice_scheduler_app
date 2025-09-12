import tkinter as tk
from tkinter import ttk, messagebox
import re
from tkcalendar import DateEntry
from scheduler_logic import normalize_team_info


class TeamTab(ttk.Frame):
    def __init__(self, parent, main_app):
        super().__init__(parent)
        self.main_app = main_app
        self.teams = {}
        self._editing_team = None  # Track which team is being edited
        self._build_ui()

    # -------------------- UI --------------------
    def _build_ui(self):
        container = ttk.Frame(self)
        container.pack(fill="both", expand=True, padx=10, pady=10)

        # Left: form
        form = ttk.LabelFrame(container, text="Team Details", padding=10)
        form.pack(side="left", fill="both", expand=True, padx=(0, 10))
        form.columnconfigure(1, weight=1)

        # Team name
        ttk.Label(form, text="Team Name:").grid(row=0, column=0, sticky="w", padx=4, pady=4)
        self.name_entry = ttk.Entry(form)
        self.name_entry.grid(row=0, column=1, sticky="ew", padx=4, pady=4)
        self.name_entry.bind('<KeyRelease>', self._on_form_change)

        # Age group
        ttk.Label(form, text="Age Group:").grid(row=1, column=0, sticky="w", padx=4, pady=4)
        self.age_entry = ttk.Entry(form)
        self.age_entry.grid(row=1, column=1, sticky="ew", padx=4, pady=4)
        self.age_entry.bind('<KeyRelease>', self._on_form_change)

        # Type
        ttk.Label(form, text="Type:").grid(row=2, column=0, sticky="w", padx=4, pady=4)
        self.type_var = tk.StringVar(value="house")
        self.type_combo = ttk.Combobox(
            form, textvariable=self.type_var,
            values=["house", "competitive"], state="readonly"
        )
        self.type_combo.grid(row=2, column=1, sticky="ew", padx=4, pady=4)
        self.type_combo.bind('<<ComboboxSelected>>', self._on_form_change)

        # Practice duration
        ttk.Label(form, text="Practice Duration (min):").grid(row=3, column=0, sticky="w", padx=4, pady=4)
        self.practice_duration_entry = ttk.Entry(form)
        self.practice_duration_entry.grid(row=3, column=1, sticky="ew", padx=4, pady=4)
        self.practice_duration_entry.insert(0, "60")
        self.practice_duration_entry.bind('<KeyRelease>', self._on_form_change)

        # Game duration
        ttk.Label(form, text="Game Duration (min):").grid(row=4, column=0, sticky="w", padx=4, pady=4)
        self.game_duration_entry = ttk.Entry(form)
        self.game_duration_entry.grid(row=4, column=1, sticky="ew", padx=4, pady=4)
        self.game_duration_entry.insert(0, "60")
        self.game_duration_entry.bind('<KeyRelease>', self._on_form_change)

        # Allow multiple per day
        self.allow_multiple_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            form, text="Allow multiple ice times per day",
            variable=self.allow_multiple_var, command=self._on_form_change
        ).grid(row=5, column=0, columnspan=2, sticky="w", padx=4, pady=4)

        # Allow shared ice
        self.shared_ice_var = tk.BooleanVar(value=True)
        self.shared_ice_cb = ttk.Checkbutton(
            form, text="Allow shared ice for this team",
            variable=self.shared_ice_var, command=self._on_shared_ice_change
        )
        self.shared_ice_cb.grid(row=6, column=0, columnspan=2, sticky="w", padx=4, pady=4)

        # NEW: Mandatory shared ice option
        self.mandatory_shared_ice_var = tk.BooleanVar(value=False)
        self.mandatory_shared_ice_cb = ttk.Checkbutton(
            form, text="Always require shared ice (mandatory)",
            variable=self.mandatory_shared_ice_var, command=self._on_mandatory_shared_change
        )
        self.mandatory_shared_ice_cb.grid(row=7, column=0, columnspan=2, sticky="w", padx=20, pady=2)
        self.mandatory_shared_ice_cb.config(state="disabled")  # Initially disabled

        # Late cutoff
        cutoff_frame = ttk.Frame(form)
        cutoff_frame.grid(row=8, column=0, columnspan=2, sticky="w", padx=4, pady=4)
        self.late_cutoff_var = tk.BooleanVar(value=False)
        self.late_cutoff_check = ttk.Checkbutton(
            cutoff_frame, text="Enforce late-ice cutoff (HH:MM)",
            variable=self.late_cutoff_var, command=self._toggle_late_cutoff
        )
        self.late_cutoff_check.pack(side="left")
        self.late_cutoff_entry = ttk.Entry(cutoff_frame, width=8)
        self.late_cutoff_entry.insert(0, "21:00")
        self.late_cutoff_entry.config(state="disabled")
        self.late_cutoff_entry.pack(side="left", padx=(8, 0))
        self.late_cutoff_entry.bind('<KeyRelease>', self._on_form_change)

        # Preferred days & times
        pref = ttk.LabelFrame(form, text="Preferred Days & Times", padding=8)
        pref.grid(row=9, column=0, columnspan=2, sticky="ew", padx=4, pady=(8, 4))
        pref.columnconfigure(1, weight=1)

        # Column headers
        ttk.Label(pref, text="Day").grid(row=0, column=0, padx=4, sticky="w")
        ttk.Label(pref, text="Time").grid(row=0, column=1, padx=4, sticky="w")
        ttk.Label(pref, text="Strict").grid(row=0, column=2, padx=4, sticky="w")

        # Instructions
        ttk.Label(
            pref, text="Check day + enter time (e.g., 17:30-19:00)",
            font=("Arial", 8)
        ).grid(row=1, column=0, columnspan=3, sticky="w")
        ttk.Label(
            pref, text="Format: HH:MM-HH:MM",
            foreground="gray", font=("Arial", 8, "italic")
        ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(0, 4))

        # Day rows
        self.preferred_day_widgets = {}
        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        for i, day in enumerate(days):
            row = 3 + i
            cbvar = tk.BooleanVar(value=False)
            cb = ttk.Checkbutton(pref, text=day, variable=cbvar,
                                 command=lambda d=day: self._toggle_pref_entry(d))
            cb.grid(row=row, column=0, sticky="w", padx=4, pady=2)

            entry = ttk.Entry(pref, width=12, state="disabled")
            entry.grid(row=row, column=1, sticky="w", padx=4, pady=2)
            entry.bind('<KeyRelease>', self._on_form_change)

            strict_var = tk.BooleanVar(value=False)
            strict_cb = ttk.Checkbutton(pref, variable=strict_var)
            strict_cb.grid(row=row, column=2, sticky="w", padx=4)

            self.preferred_day_widgets[day] = {
                "var": cbvar, "entry": entry, "strict": strict_var
            }

        # Blackouts
        blackout = ttk.LabelFrame(form, text="Blackout Dates", padding=8)
        blackout.grid(row=10, column=0, columnspan=2, sticky="ew", padx=4, pady=8)
        bo_top = ttk.Frame(blackout)
        bo_top.pack(fill="x", pady=(0, 4))
        ttk.Label(bo_top, text="Add blackout date:").pack(side="left")
        self.blackout_date = DateEntry(bo_top, date_pattern="yyyy-mm-dd")
        self.blackout_date.pack(side="left", padx=4)
        ttk.Button(bo_top, text="Add", command=self._add_blackout).pack(side="left")
        list_frame = ttk.Frame(blackout)
        list_frame.pack(fill="both", expand=True)
        self.blackout_list = tk.Listbox(list_frame, height=3)
        self.blackout_list.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(list_frame, orient="vertical", command=self.blackout_list.yview)
        sb.pack(side="right", fill="y")
        self.blackout_list.config(yscrollcommand=sb.set)
        ttk.Button(blackout, text="Remove Selected", command=self._remove_blackout).pack(pady=2)

        # Buttons
        btns = ttk.Frame(form)
        btns.grid(row=11, column=0, columnspan=2, pady=(6, 0))
        self.add_btn = ttk.Button(btns, text="Add New Team", command=self._add_update_team)
        self.add_btn.pack(side="left", padx=4)
        self.save_btn = ttk.Button(btns, text="Save Changes", command=self._save_changes, state="disabled")
        self.save_btn.pack(side="left", padx=4)
        ttk.Button(btns, text="Delete Team", command=self._delete_team).pack(side="left", padx=4)
        ttk.Button(btns, text="Clear Form", command=self._clear_form).pack(side="left", padx=4)

        # Right: team list
        list_wrap = ttk.LabelFrame(container, text="Existing Teams", padding=10)
        list_wrap.pack(side="left", fill="both", expand=True)

        tree_frame = ttk.Frame(list_wrap)
        tree_frame.pack(fill="both", expand=True)

        cols = ("Name", "Age", "Type", "Practice Min", "Game Min", "Shared",
                "Mandatory Shared", "Strict Pref", "Late Cutoff", "Preferred", "Blackouts")
        self.team_tree = ttk.Treeview(tree_frame, columns=cols, show="headings", height=8)
        for c in cols:
            self.team_tree.heading(c, text=c)
            width = 110 if c in ("Preferred", "Blackouts") else (100 if c == "Mandatory Shared" else 90)
            self.team_tree.column(c, width=width, anchor="center")

        v_scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.team_tree.yview)
        h_scrollbar = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.team_tree.xview)
        self.team_tree.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)

        self.team_tree.grid(row=0, column=0, sticky="nsew")
        v_scrollbar.grid(row=0, column=1, sticky="ns")
        h_scrollbar.grid(row=1, column=0, sticky="ew")

        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        self.team_tree.bind("<<TreeviewSelect>>", self._on_select_team)

        # Bind Ctrl+S
        self.bind_all("<Control-s>", self._on_ctrl_s)
        self.bind_all("<Control-S>", self._on_ctrl_s)

        self._populate_tree()

    # -------------------- Helpers --------------------
    def _on_shared_ice_change(self):
        """Handle changes to the shared ice checkbox"""
        if not self.shared_ice_var.get():
            # If shared ice is disabled, also disable mandatory shared ice
            self.mandatory_shared_ice_var.set(False)
            self.mandatory_shared_ice_cb.config(state="disabled")
        else:
            # If shared ice is enabled, enable the mandatory option
            self.mandatory_shared_ice_cb.config(state="normal")
        self._on_form_change()

    def _on_mandatory_shared_change(self):
        """Handle changes to the mandatory shared ice checkbox"""
        if self.mandatory_shared_ice_var.get():
            # If mandatory shared is enabled, ensure shared ice is also enabled
            self.shared_ice_var.set(True)
        self._on_form_change()

    def _toggle_late_cutoff(self):
        state = "normal" if self.late_cutoff_var.get() else "disabled"
        self.late_cutoff_entry.config(state=state)
        self._on_form_change()

    def _toggle_pref_entry(self, day):
        widgets = self.preferred_day_widgets[day]
        widgets["entry"].config(state="normal" if widgets["var"].get() else "disabled")
        self._on_form_change()

    def _on_form_change(self, event=None):
        if self._editing_team:
            self.save_btn.config(state="normal")

    def _on_ctrl_s(self, event=None):
        if self._editing_team and str(self.save_btn['state']) == 'normal':
            self._save_changes()
            if hasattr(self.main_app, 'save_all_data_silently'):
                self.main_app.save_all_data_silently()
            elif hasattr(self.main_app, 'save_all_data'):
                try:
                    self.main_app.save_all_data()
                except Exception:
                    pass
        return "break"

    def _add_blackout(self):
        # Convert date object to ISO string format
        date_obj = self.blackout_date.get_date()
        date_str = date_obj.isoformat() if hasattr(date_obj, 'isoformat') else str(date_obj)
        existing = set(self.blackout_list.get(0, "end"))
        if date_str not in existing:
            self.blackout_list.insert("end", date_str)
            self._on_form_change()

    def _remove_blackout(self):
        sel = list(self.blackout_list.curselection())
        for idx in reversed(sel):
            self.blackout_list.delete(idx)
        if sel:
            self._on_form_change()

    def _clear_form(self):
        self._editing_team = None
        self.save_btn.config(state="disabled")
        self.add_btn.config(state="normal")
        self.name_entry.delete(0, "end")
        self.age_entry.delete(0, "end")
        self.type_var.set("house")
        for e in (self.practice_duration_entry, self.game_duration_entry):
            e.delete(0, "end"); e.insert(0, "60")
        self.allow_multiple_var.set(False)
        self.shared_ice_var.set(True)
        self.mandatory_shared_ice_var.set(False)
        self.mandatory_shared_ice_cb.config(state="normal")  # Re-enable since shared ice is True
        self.late_cutoff_var.set(False); self._toggle_late_cutoff()
        self.late_cutoff_entry.delete(0, "end"); self.late_cutoff_entry.insert(0, "21:00")
        for day, w in self.preferred_day_widgets.items():
            w["var"].set(False)
            w["entry"].config(state="disabled"); w["entry"].delete(0, "end")
            w["strict"].set(False)
        self.blackout_list.delete(0, "end")

    # -------------------- Data ops --------------------
    def _on_select_team(self, _evt=None):
        sel = self.team_tree.selection()
        if not sel:
            return
        name = self.team_tree.item(sel[0], "values")[0]
        data = self.teams.get(name, {})
        if not data:
            return

        self._editing_team = name
        self.save_btn.config(state="disabled")
        self.add_btn.config(state="disabled")

        self._clear_form_without_reset()
        self.name_entry.insert(0, name)
        self.age_entry.insert(0, data.get("age", ""))
        self.type_var.set(data.get("type", "house"))
        self.practice_duration_entry.delete(0, "end"); self.practice_duration_entry.insert(0, str(data.get("practice_duration", 60)))
        self.game_duration_entry.delete(0, "end"); self.game_duration_entry.insert(0, str(data.get("game_duration", 60)))
        self.allow_multiple_var.set(bool(data.get("allow_multiple_per_day", False)))
        
        # Handle shared ice settings
        shared_ice_enabled = bool(data.get("allow_shared_ice", True))
        mandatory_shared = bool(data.get("mandatory_shared_ice", False))
        
        self.shared_ice_var.set(shared_ice_enabled)
        self.mandatory_shared_ice_var.set(mandatory_shared)
        
        # Update mandatory checkbox state based on shared ice setting
        if shared_ice_enabled:
            self.mandatory_shared_ice_cb.config(state="normal")
        else:
            self.mandatory_shared_ice_cb.config(state="disabled")

        if data.get("late_ice_cutoff_enabled"):
            self.late_cutoff_var.set(True); self._toggle_late_cutoff()
            self.late_cutoff_entry.delete(0, "end"); self.late_cutoff_entry.insert(0, data.get("late_ice_cutoff_time", "21:00"))

        pref = data.get("preferred_days_and_times", {})
        for day, w in self.preferred_day_widgets.items():
            val = pref.get(day, "")
            if val:
                w["var"].set(True); w["entry"].config(state="normal")
                w["entry"].delete(0, "end"); w["entry"].insert(0, val)
            w["strict"].set(bool(pref.get(f"{day}_strict", False)))

        # Fix blackout dates handling - ensure they're strings
        blackout_dates = data.get("blackout_dates", [])
        for d in blackout_dates:
            # Convert date objects to strings if needed
            if hasattr(d, 'isoformat'):
                date_str = d.isoformat()
            else:
                date_str = str(d)
            self.blackout_list.insert("end", date_str)

        self._editing_team = name

    def _clear_form_without_reset(self):
        self.name_entry.delete(0, "end")
        self.age_entry.delete(0, "end")
        self.type_var.set("house")
        for e in (self.practice_duration_entry, self.game_duration_entry):
            e.delete(0, "end"); e.insert(0, "60")
        self.allow_multiple_var.set(False)
        self.shared_ice_var.set(True)
        self.mandatory_shared_ice_var.set(False)
        self.mandatory_shared_ice_cb.config(state="normal")
        self.late_cutoff_var.set(False); self._toggle_late_cutoff()
        self.late_cutoff_entry.delete(0, "end"); self.late_cutoff_entry.insert(0, "21:00")
        for day, w in self.preferred_day_widgets.items():
            w["var"].set(False)
            w["entry"].config(state="disabled"); w["entry"].delete(0, "end")
            w["strict"].set(False)
        self.blackout_list.delete(0, "end")

    def _add_update_team(self):
        team_data = self._collect_team_data()
        if team_data is None:
            return
        name, team = team_data
        if name in self.teams:
            if not messagebox.askyesno("Team Exists", f"Team '{name}' already exists. Overwrite?"):
                return
        self.teams[name] = team
        self._populate_tree()
        self._clear_form()
        if hasattr(self.main_app, "on_teams_updated"):
            self.main_app.on_teams_updated(self.teams)

    def _save_changes(self):
        if not self._editing_team:
            return
        team_data = self._collect_team_data()
        if team_data is None:
            return
        name, team = team_data
        if name != self._editing_team and name in self.teams:
            messagebox.showerror("Error", f"Cannot rename to '{name}' - team already exists.")
            return
        if name != self._editing_team:
            del self.teams[self._editing_team]
        self.teams[name] = team
        self._populate_tree()
        self._editing_team = name
        self.save_btn.config(state="disabled")
        self.add_btn.config(state="disabled")
        if hasattr(self.main_app, "on_teams_updated"):
            self.main_app.on_teams_updated(self.teams)
        messagebox.showinfo("Success", f"Team '{name}' updated successfully!")

    def _collect_team_data(self):
        name = self.name_entry.get().strip()
        age = self.age_entry.get().strip()
        ttype = self.type_var.get().strip()
        if not name or not age:
            messagebox.showerror("Error", "Team Name and Age Group are required.")
            return None
        try:
            practice_minutes = self._parse_minutes(self.practice_duration_entry.get().strip())
            game_minutes = self._parse_minutes(self.game_duration_entry.get().strip())
        except ValueError as e:
            messagebox.showerror("Error", str(e))
            return None

        late_enabled = self.late_cutoff_var.get()
        late_time = None
        if late_enabled:
            late_time = (self.late_cutoff_entry.get() or "").strip()
            if late_time:
                if re.match(r"^\d{1,2}:\d{2}$", late_time) is None:
                    messagebox.showerror("Error", "Late cutoff time must be in HH:MM format.")
                    return None

        preferred, strict_flag = {}, False
        for day, w in self.preferred_day_widgets.items():
            if w["var"].get():
                val = w["entry"].get().strip()
                if val:
                    preferred[day] = val
                    if w["strict"].get():
                        preferred[f"{day}_strict"] = True
                        strict_flag = True

        blackouts = list(self.blackout_list.get(0, "end"))

        team = {
            "age": age,
            "type": ttype,
            "practice_duration": practice_minutes,
            "game_duration": game_minutes,
            "allow_multiple_per_day": self.allow_multiple_var.get(),
            "allow_shared_ice": self.shared_ice_var.get(),
            "mandatory_shared_ice": self.mandatory_shared_ice_var.get(),  # NEW FIELD
            "late_ice_cutoff_enabled": late_enabled,
            "late_ice_cutoff_time": late_time,
            "preferred_days_and_times": preferred,
            "strict_preferred": strict_flag,
            "blackout_dates": blackouts,
        }

        team = normalize_team_info(team)
        return name, team

    def _parse_minutes(self, txt):
        try:
            return int(txt)
        except ValueError:
            raise ValueError("Duration must be an integer number of minutes.")

    def _populate_tree(self):
        for i in self.team_tree.get_children():
            self.team_tree.delete(i)
        for name, team in self.teams.items():
            vals = (
                name,
                team.get("age", ""),
                team.get("type", ""),
                team.get("practice_duration", ""),
                team.get("game_duration", ""),
                "Yes" if team.get("allow_shared_ice") else "No",
                "Yes" if team.get("mandatory_shared_ice") else "No",  # NEW COLUMN
                "Yes" if team.get("strict_preferred") else "No",
                team.get("late_ice_cutoff_time") if team.get("late_ice_cutoff_enabled") else "No",
                ", ".join(f"{d}: {t}" for d, t in team.get("preferred_days_and_times", {}).items() if not d.endswith("_strict")),
                ", ".join(team.get("blackout_dates", [])),
            )
            self.team_tree.insert("", "end", values=vals)

    def _delete_team(self):
        sel = self.team_tree.selection()
        if not sel:
            return
        name = self.team_tree.item(sel[0], "values")[0]
        if not messagebox.askyesno("Confirm Delete", f"Delete team '{name}'?"):
            return
        del self.teams[name]
        self._populate_tree()
        self._clear_form()
        if hasattr(self.main_app, "on_teams_updated"):
            self.main_app.on_teams_updated(self.teams)

    def load_teams_data(self, teams_data):
        """Load teams data from external source (like file load)."""
        if teams_data:
            self.teams = dict(teams_data)  # Create a copy to avoid reference issues
            self._populate_tree()
            # Optionally clear the form since we're loading new data
            self._clear_form()

    def get_teams_data(self):
        """Return current teams data for saving/export."""
        return dict(self.teams)  # Return a copy to avoid external modifications