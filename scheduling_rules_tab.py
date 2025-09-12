import tkinter as tk
from tkinter import ttk, messagebox
import json
import re

class SchedulingRulesWindow(tk.Toplevel):
    def __init__(self, parent, rules_data):
        super().__init__(parent)
        self.transient(parent)
        self.grab_set()
        self.title("Scheduling Rules")
        self.geometry("700x500")
        self.parent = parent
        self.rules = rules_data
        
        self.setup_ui()
        self.load_rules(self.rules)
    
    def setup_ui(self):
        main_frame = ttk.LabelFrame(self, text="Default Scheduling Rules", padding=10)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Ice Times per Week
        times_frame = ttk.LabelFrame(main_frame, text="Ice Times per Week", padding=10)
        times_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        tree_frame = ttk.Frame(times_frame)
        tree_frame.pack(fill="both", expand=True)
        
        columns = ("Type", "Age", "Times")
        self.times_tree = ttk.Treeview(tree_frame, columns=columns, show="headings")
        self.times_tree.tag_configure('house', background='#e8f0fe')
        self.times_tree.tag_configure('competitive', background='#fce8e6')

        for col in columns:
            self.times_tree.heading(col, text=col)
            self.times_tree.column(col, width=150, anchor='center')
        self.times_tree.pack(side="left", fill="both", expand=True)
        
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.times_tree.yview)
        scrollbar.pack(side="right", fill="y")
        self.times_tree.configure(yscrollcommand=scrollbar.set)
        
        # Action buttons
        button_frame = ttk.Frame(times_frame)
        button_frame.pack(fill="x", pady=5)
        
        ttk.Button(button_frame, text="Add Rule", command=self.add_new_rule).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Edit Rule", command=self.edit_selected_rule).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Delete Rule", command=self.delete_selected_rule).pack(side="left", padx=5)

        # Simple Rules (only default type)
        simple_rules_frame = ttk.LabelFrame(main_frame, text="General Rules", padding=10)
        simple_rules_frame.pack(fill="x", padx=5, pady=5)
        
        ttk.Label(simple_rules_frame, text="Default Ice Time Type:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.default_type_var = tk.StringVar(value='practice')
        ttk.Radiobutton(simple_rules_frame, text="Practice", variable=self.default_type_var, value="practice").grid(row=0, column=1, sticky="w", padx=5, pady=5)
        ttk.Radiobutton(simple_rules_frame, text="Game", variable=self.default_type_var, value="game").grid(row=0, column=2, sticky="w", padx=5, pady=5)
        
        # Save and Cancel buttons
        bottom_button_frame = ttk.Frame(self)
        bottom_button_frame.pack(pady=10)
        
        ttk.Button(bottom_button_frame, text="Save Rules", command=self.save_and_close).pack(side="left", padx=5)
        ttk.Button(bottom_button_frame, text="Cancel", command=self.destroy).pack(side="left", padx=5)
    
    def add_new_rule(self):
        self.edit_rule_dialog()
        
    def edit_selected_rule(self):
        selected_item = self.times_tree.focus()
        if not selected_item:
            messagebox.showerror("Error", "Please select a rule to edit.")
            return
        
        values = self.times_tree.item(selected_item, 'values')
        self.edit_rule_dialog(values, selected_item)
        
    def delete_selected_rule(self):
        selected_item = self.times_tree.focus()
        if not selected_item:
            messagebox.showerror("Error", "Please select a rule to delete.")
            return

        if messagebox.askyesno("Delete Rule", "Are you sure you want to delete this rule?"):
            self.times_tree.delete(selected_item)
            messagebox.showinfo("Success", "Rule deleted.")

    def edit_rule_dialog(self, initial_values=None, item=None):
        dialog = tk.Toplevel(self)
        dialog.transient(self)
        dialog.grab_set()
        dialog.title("Edit Ice Time Rule")
        dialog.geometry("300x200")

        frame = ttk.Frame(dialog, padding=10)
        frame.pack(fill="both", expand=True)
        
        # Team Type
        ttk.Label(frame, text="Team Type:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        type_var = tk.StringVar()
        type_dropdown = ttk.Combobox(frame, textvariable=type_var, values=["house", "competitive"], state="readonly")
        type_dropdown.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        # Age Group
        ttk.Label(frame, text="Age Group:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        age_var = tk.StringVar()
        age_dropdown = ttk.Combobox(frame, textvariable=age_var, values=[f"U{i}" for i in range(7, 19)], state="readonly")
        age_dropdown.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        
        # Ice Times
        ttk.Label(frame, text="Ice Times per Week:").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        times_entry = ttk.Entry(frame)
        times_entry.grid(row=2, column=1, padx=5, pady=5, sticky="ew")

        if initial_values:
            type_var.set(initial_values[0])
            age_var.set(initial_values[1])
            times_entry.insert(0, initial_values[2])
        
        def save_and_close():
            team_type = type_var.get()
            age_level = age_var.get()
            times_str = times_entry.get()

            if not team_type or not age_level or not re.fullmatch(r'(\d+)(,\s*\d+)*', times_str):
                messagebox.showerror("Invalid Input", "Please fill out all fields with valid data.")
                return

            if item:
                self.times_tree.item(item, values=(team_type, age_level, times_str))
            else:
                self.times_tree.insert("", "end", values=(team_type, age_level, times_str), tags=(team_type,))
            dialog.destroy()

        button_frame = ttk.Frame(dialog)
        button_frame.pack(pady=10)
        ttk.Button(button_frame, text="Save", command=save_and_close).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side="left", padx=5)

        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(0, weight=1)

    def get_rules(self):
        return self.rules

    def save_and_close(self):
        # Save simple rules
        self.rules['default_ice_time_type'] = self.default_type_var.get()
        
        # Save ice times per week
        ice_times_per_week = {}
        for item in self.times_tree.get_children():
            team_type, age_level, times_str = self.times_tree.item(item, 'values')
            
            times = [t.strip() for t in times_str.split(',') if t.strip()]

            if team_type not in ice_times_per_week:
                ice_times_per_week[team_type] = {}
            
            # The JSON file structure requires the age group to be a key and the value to be a number.
            # We'll save the first number from the list, since only one ice time is expected per rule.
            # I've updated the logic to handle this correctly.
            ice_times_per_week[team_type][age_level] = int(times[0]) if times else 0
        
        self.rules['ice_times_per_week'] = ice_times_per_week
        
        messagebox.showinfo("Success", "Scheduling rules have been updated.")
        self.destroy()

    def load_rules(self, rules):
        self.rules = rules
        
        self.default_type_var.set(rules.get('default_ice_time_type', 'practice'))
        
        # Load ice times per week
        for item in self.times_tree.get_children():
            self.times_tree.delete(item)
        
        ice_times = rules.get('ice_times_per_week', {})
        for team_type, age_data in ice_times.items():
            for age_level, times_value in age_data.items():
                # The JSON data has an integer, so we'll convert it to a string for display.
                times_str = str(times_value)
                self.times_tree.insert("", "end", values=(team_type, age_level, times_str), tags=(team_type,))
