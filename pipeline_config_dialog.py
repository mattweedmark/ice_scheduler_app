import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json
import os

# Import pipeline configuration functions
try:
    from pipeline_steps import get_default_pipeline_config, get_step_parameter_definitions
    from scheduler_pipeline import validate_pipeline_config
    PIPELINE_AVAILABLE = True
except ImportError:
    PIPELINE_AVAILABLE = False
    
    def get_default_pipeline_config():
        return {"steps": [], "global_settings": {}}
    
    def get_step_parameter_definitions():
        return {}
    
    def validate_pipeline_config(config):
        return [], []

class PipelineConfigDialog(tk.Toplevel):
    """Dialog for configuring the scheduling pipeline."""
    
    def __init__(self, parent, main_app):
        super().__init__(parent)
        self.parent = parent
        self.main_app = main_app
        
        self.title("Scheduling Pipeline Configuration")
        self.geometry("1000x700")
        self.transient(parent)
        self.grab_set()
        
        # Load current pipeline config or default
        self.pipeline_config = self.load_current_config()
        self.modified = False
        
        # Check if pipeline system is available
        if not PIPELINE_AVAILABLE:
            self.show_unavailable_message()
            return
        
        self.setup_ui()
        self.populate_steps()
        
    def show_unavailable_message(self):
        """Show message when pipeline system is not available."""
        message_frame = ttk.Frame(self)
        message_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        ttk.Label(message_frame, text="Pipeline Configuration Unavailable", 
                 font=("Arial", 14, "bold")).pack(pady=10)
        
        ttk.Label(message_frame, 
                 text="The scheduling pipeline system requires additional components that are not available.\n"
                      "Please ensure all scheduler modules are properly installed.",
                 wraplength=400, justify="center").pack(pady=10)
        
        ttk.Button(message_frame, text="Close", command=self.destroy).pack(pady=20)
        
    def load_current_config(self):
        """Load current pipeline configuration or default."""
        if hasattr(self.main_app, 'pipeline_config'):
            return self.main_app.pipeline_config.copy()
        else:
            return get_default_pipeline_config()
    
    def setup_ui(self):
        """Setup the main UI layout."""
        # Main container
        main_frame = ttk.Frame(self)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Top controls
        self.setup_top_controls(main_frame)
        
        # Main content area
        content_frame = ttk.Frame(main_frame)
        content_frame.pack(fill="both", expand=True, pady=(10, 0))
        
        # Left panel - Pipeline steps list
        left_panel = ttk.LabelFrame(content_frame, text="Pipeline Steps", padding=10)
        left_panel.pack(side="left", fill="both", expand=True, padx=(0, 5))
        
        self.setup_steps_panel(left_panel)
        
        # Right panel - Step details
        right_panel = ttk.LabelFrame(content_frame, text="Step Configuration", padding=10)
        right_panel.pack(side="right", fill="both", expand=True, padx=(5, 0))
        
        self.setup_details_panel(right_panel)
        
        # Bottom buttons
        self.setup_bottom_buttons(main_frame)
        
    def setup_top_controls(self, parent):
        """Setup preset and file controls."""
        controls_frame = ttk.Frame(parent)
        controls_frame.pack(fill="x", pady=(0, 10))
        
        # Preset configurations
        ttk.Label(controls_frame, text="Preset:").pack(side="left", padx=(0, 5))
        
        self.preset_var = tk.StringVar(value="Custom")
        preset_combo = ttk.Combobox(controls_frame, textvariable=self.preset_var,
                                   values=["Conservative", "Balanced", "Aggressive", "Custom"],
                                   state="readonly", width=15)
        preset_combo.pack(side="left", padx=(0, 10))
        preset_combo.bind("<<ComboboxSelected>>", self.load_preset)
        
        # File operations
        ttk.Button(controls_frame, text="Load Config", 
                  command=self.load_config_file).pack(side="left", padx=5)
        ttk.Button(controls_frame, text="Save Config", 
                  command=self.save_config_file).pack(side="left", padx=5)
        
        # Pipeline validation status
        self.validation_var = tk.StringVar(value="Configuration valid")
        self.validation_label = ttk.Label(controls_frame, textvariable=self.validation_var,
                                         foreground="green")
        self.validation_label.pack(side="right", padx=5)
        
    def setup_steps_panel(self, parent):
        """Setup the pipeline steps list with drag-drop capability."""
        # Steps list frame
        list_frame = ttk.Frame(parent)
        list_frame.pack(fill="both", expand=True)
        
        # Treeview for steps
        columns = ("Priority", "Name", "Status")
        self.steps_tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=12)
        
        # Configure columns
        self.steps_tree.heading("Priority", text="Order")
        self.steps_tree.heading("Name", text="Step Name")
        self.steps_tree.heading("Status", text="Status")
        
        self.steps_tree.column("Priority", width=60, anchor="center")
        self.steps_tree.column("Name", width=250)
        self.steps_tree.column("Status", width=80, anchor="center")
        
        # Scrollbar
        tree_scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.steps_tree.yview)
        self.steps_tree.configure(yscrollcommand=tree_scroll.set)
        
        self.steps_tree.pack(side="left", fill="both", expand=True)
        tree_scroll.pack(side="right", fill="y")
        
        # Bind selection event
        self.steps_tree.bind("<<TreeviewSelect>>", self.on_step_selected)
        
        # Control buttons
        button_frame = ttk.Frame(parent)
        button_frame.pack(fill="x", pady=(10, 0))
        
        ttk.Button(button_frame, text="Move Up", 
                  command=self.move_step_up).pack(side="left", padx=(0, 5))
        ttk.Button(button_frame, text="Move Down", 
                  command=self.move_step_down).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Enable/Disable", 
                  command=self.toggle_step_enabled).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Reset Defaults", 
                  command=self.reset_step_defaults).pack(side="right")
        
    def setup_details_panel(self, parent):
        """Setup the step details configuration panel."""
        # Step info frame
        info_frame = ttk.Frame(parent)
        info_frame.pack(fill="x", pady=(0, 10))
        
        self.step_name_var = tk.StringVar(value="No step selected")
        ttk.Label(info_frame, textvariable=self.step_name_var, 
                 font=("Arial", 12, "bold")).pack(anchor="w")
        
        self.step_desc_var = tk.StringVar(value="")
        desc_label = ttk.Label(info_frame, textvariable=self.step_desc_var, 
                              wraplength=300, justify="left")
        desc_label.pack(anchor="w", pady=(5, 0))
        
        # Parameters frame
        params_frame = ttk.LabelFrame(parent, text="Parameters", padding=5)
        params_frame.pack(fill="both", expand=True)
        
        # Scrollable parameters area
        self.params_canvas = tk.Canvas(params_frame)
        params_scroll = ttk.Scrollbar(params_frame, orient="vertical", 
                                     command=self.params_canvas.yview)
        self.params_frame = ttk.Frame(self.params_canvas)
        
        self.params_canvas.configure(yscrollcommand=params_scroll.set)
        self.params_canvas.pack(side="left", fill="both", expand=True)
        params_scroll.pack(side="right", fill="y")
        
        self.params_canvas.create_window((0, 0), window=self.params_frame, anchor="nw")
        self.params_frame.bind("<Configure>", 
                              lambda e: self.params_canvas.configure(
                                  scrollregion=self.params_canvas.bbox("all")))
        
        # Parameter widgets storage
        self.param_widgets = {}
        
    def setup_bottom_buttons(self, parent):
        """Setup bottom action buttons."""
        button_frame = ttk.Frame(parent)
        button_frame.pack(fill="x", pady=(10, 0))
        
        ttk.Button(button_frame, text="Test Configuration", 
                  command=self.test_configuration).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Export to File", 
                  command=self.export_configuration).pack(side="left", padx=5)
        
        ttk.Button(button_frame, text="Cancel", 
                  command=self.cancel).pack(side="right", padx=5)
        ttk.Button(button_frame, text="Apply", 
                  command=self.apply_changes).pack(side="right", padx=5)
        ttk.Button(button_frame, text="OK", 
                  command=self.save_and_close).pack(side="right", padx=5)
        
    def populate_steps(self):
        """Populate the steps tree with current configuration."""
        # Clear existing items
        for item in self.steps_tree.get_children():
            self.steps_tree.delete(item)
        
        # Sort steps by priority
        steps = sorted(self.pipeline_config["steps"], key=lambda x: x["priority"])
        
        for step in steps:
            status = "Enabled" if step["enabled"] else "Disabled"
            self.steps_tree.insert("", "end", iid=step["id"], values=(
                step["priority"],
                step["name"],
                status
            ))
            
    def on_step_selected(self, event):
        """Handle step selection."""
        selection = self.steps_tree.selection()
        if not selection:
            self.clear_details_panel()
            return
            
        step_id = selection[0]
        step = self.get_step_by_id(step_id)
        if step:
            self.show_step_details(step)
            
    def get_step_by_id(self, step_id):
        """Get step configuration by ID."""
        for step in self.pipeline_config["steps"]:
            if step["id"] == step_id:
                return step
        return None
        
    def show_step_details(self, step):
        """Show details for the selected step."""
        self.step_name_var.set(step["name"])
        self.step_desc_var.set(step["description"])
        
        # Clear previous parameter widgets
        for widget in self.params_frame.winfo_children():
            widget.destroy()
        self.param_widgets.clear()
        
        # Get parameter definitions for this step
        param_defs = get_step_parameter_definitions().get(step["id"], {})
        
        if not param_defs:
            ttk.Label(self.params_frame, text="No configurable parameters for this step.").pack(pady=20)
            return
            
        # Create parameter widgets
        row = 0
        for param_name, param_def in param_defs.items():
            self.create_parameter_widget(row, param_name, param_def, step)
            row += 1
            
    def create_parameter_widget(self, row, param_name, param_def, step):
        """Create a widget for a specific parameter."""
        # Label
        label_text = param_def.get("label", param_name)
        ttk.Label(self.params_frame, text=f"{label_text}:").grid(
            row=row, column=0, sticky="w", padx=5, pady=5)
        
        # Get current value
        current_value = step.get("parameters", {}).get(param_name, param_def.get("default"))
        
        # Create appropriate widget based on parameter type
        param_type = param_def.get("type", "string")
        
        if param_type == "boolean":
            var = tk.BooleanVar(value=current_value)
            widget = ttk.Checkbutton(self.params_frame, variable=var)
            self.param_widgets[param_name] = var
            
        elif param_type == "integer":
            var = tk.StringVar(value=str(current_value))
            widget = ttk.Entry(self.params_frame, textvariable=var, width=10)
            self.param_widgets[param_name] = var
            
        elif param_type == "float":
            var = tk.StringVar(value=str(current_value))
            widget = ttk.Entry(self.params_frame, textvariable=var, width=10)
            self.param_widgets[param_name] = var
            
        elif param_type == "choice":
            var = tk.StringVar(value=current_value)
            choices = param_def.get("choices", [])
            widget = ttk.Combobox(self.params_frame, textvariable=var, 
                                 values=choices, state="readonly")
            self.param_widgets[param_name] = var
            
        else:  # string
            var = tk.StringVar(value=str(current_value))
            widget = ttk.Entry(self.params_frame, textvariable=var, width=20)
            self.param_widgets[param_name] = var
            
        widget.grid(row=row, column=1, sticky="w", padx=5, pady=5)
        
        # Description/tooltip
        description = param_def.get("description", "")
        if description:
            ttk.Label(self.params_frame, text=description, 
                     font=("Arial", 8), foreground="gray").grid(
                row=row, column=2, sticky="w", padx=10, pady=5)
        
        # Bind change event
        if hasattr(var, 'trace_add'):
            var.trace_add("write", lambda *args: self.on_parameter_changed(step, param_name))
        elif hasattr(var, 'trace'):
            var.trace("w", lambda *args: self.on_parameter_changed(step, param_name))
        
    def on_parameter_changed(self, step, param_name):
        """Handle parameter value changes."""
        if param_name in self.param_widgets:
            widget_var = self.param_widgets[param_name]
            new_value = widget_var.get()
            
            # Convert to appropriate type
            param_defs = get_step_parameter_definitions().get(step["id"], {})
            param_def = param_defs.get(param_name, {})
            param_type = param_def.get("type", "string")
            
            try:
                if param_type == "integer":
                    new_value = int(new_value)
                elif param_type == "float":
                    new_value = float(new_value)
                elif param_type == "boolean":
                    new_value = bool(new_value)
            except ValueError:
                return  # Invalid value, ignore
            
            # Update the step configuration
            if "parameters" not in step:
                step["parameters"] = {}
            step["parameters"][param_name] = new_value
            
            self.modified = True
            self.validate_configuration()
            
    def clear_details_panel(self):
        """Clear the details panel."""
        self.step_name_var.set("No step selected")
        self.step_desc_var.set("")
        for widget in self.params_frame.winfo_children():
            widget.destroy()
        self.param_widgets.clear()
        
    def move_step_up(self):
        """Move selected step up in priority."""
        selection = self.steps_tree.selection()
        if not selection:
            return
            
        step_id = selection[0]
        step = self.get_step_by_id(step_id)
        
        if step and step["priority"] > 1:
            # Find step with priority - 1 and swap
            for other_step in self.pipeline_config["steps"]:
                if other_step["priority"] == step["priority"] - 1:
                    other_step["priority"] += 1
                    step["priority"] -= 1
                    break
                    
            self.modified = True
            self.populate_steps()
            self.steps_tree.selection_set(step_id)
            
    def move_step_down(self):
        """Move selected step down in priority."""
        selection = self.steps_tree.selection()
        if not selection:
            return
            
        step_id = selection[0]
        step = self.get_step_by_id(step_id)
        max_priority = len(self.pipeline_config["steps"])
        
        if step and step["priority"] < max_priority:
            # Find step with priority + 1 and swap
            for other_step in self.pipeline_config["steps"]:
                if other_step["priority"] == step["priority"] + 1:
                    other_step["priority"] -= 1
                    step["priority"] += 1
                    break
                    
            self.modified = True
            self.populate_steps()
            self.steps_tree.selection_set(step_id)
            
    def toggle_step_enabled(self):
        """Toggle enabled/disabled status of selected step."""
        selection = self.steps_tree.selection()
        if not selection:
            return
            
        step_id = selection[0]
        step = self.get_step_by_id(step_id)
        
        if step:
            step["enabled"] = not step["enabled"]
            self.modified = True
            self.populate_steps()
            self.steps_tree.selection_set(step_id)
            self.validate_configuration()
            
    def reset_step_defaults(self):
        """Reset selected step to default parameters."""
        selection = self.steps_tree.selection()
        if not selection:
            return
            
        step_id = selection[0]
        step = self.get_step_by_id(step_id)
        
        if step:
            # Get default parameters
            param_defs = get_step_parameter_definitions().get(step_id, {})
            default_params = {name: def_info.get("default") 
                            for name, def_info in param_defs.items()}
            
            step["parameters"] = default_params
            self.modified = True
            self.show_step_details(step)
            
    def load_preset(self, event=None):
        """Load a preset configuration."""
        preset = self.preset_var.get()
        if preset == "Custom":
            return
            
        # Load preset configuration
        if preset == "Conservative":
            self.pipeline_config = self.get_conservative_config()
        elif preset == "Balanced":
            self.pipeline_config = get_default_pipeline_config()
        elif preset == "Aggressive":
            self.pipeline_config = self.get_aggressive_config()
            
        self.modified = True
        self.populate_steps()
        self.clear_details_panel()
        self.validate_configuration()
        
    def get_conservative_config(self):
        """Get conservative pipeline configuration."""
        config = get_default_pipeline_config()
        
        # Modify for conservative approach
        for step in config["steps"]:
            if step["id"] == "emergency_shared":
                step["enabled"] = False
            elif step["id"] == "final_aggressive":
                step["enabled"] = False
            elif step["id"] == "shared_ice_optimization":
                step["parameters"]["max_age_difference"] = 1
                
        return config
        
    def get_aggressive_config(self):
        """Get aggressive pipeline configuration."""
        config = get_default_pipeline_config()
        
        # Modify for aggressive approach
        for step in config["steps"]:
            if step["id"] == "shared_ice_optimization":
                step["parameters"]["max_age_difference"] = 4
            elif step["id"] == "emergency_shared":
                step["parameters"]["max_age_difference"] = 5
                
        config["global_settings"]["emergency_mode_threshold"] = 0.6
        
        return config
        
    def validate_configuration(self):
        """Validate the current pipeline configuration."""
        errors, warnings = validate_pipeline_config(self.pipeline_config)
        
        # Update validation display
        if errors:
            self.validation_var.set(f"Errors: {'; '.join(errors[:2])}")
            self.validation_label.configure(foreground="red")
        elif warnings:
            self.validation_var.set(f"Warnings: {'; '.join(warnings[:2])}")
            self.validation_label.configure(foreground="orange")
        else:
            self.validation_var.set("Configuration valid")
            self.validation_label.configure(foreground="green")
            
        return len(errors) == 0
        
    def test_configuration(self):
        """Test the current configuration."""
        if not self.validate_configuration():
            messagebox.showerror("Invalid Configuration", 
                "Please fix configuration issues before testing.")
            return
            
        # Show test results dialog
        enabled_steps = [s for s in self.pipeline_config["steps"] if s["enabled"]]
        messagebox.showinfo("Configuration Test", 
            f"Configuration test passed!\n\n"
            f"Enabled steps: {len(enabled_steps)}\n"
            f"Total steps: {len(self.pipeline_config['steps'])}\n"
            f"Pipeline ready for scheduling.")
            
    def export_configuration(self):
        """Export configuration to file."""
        filename = filedialog.asksaveasfilename(
            title="Export Pipeline Configuration",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        
        if filename:
            try:
                with open(filename, 'w') as f:
                    json.dump(self.pipeline_config, f, indent=2)
                messagebox.showinfo("Export Successful", f"Configuration exported to {filename}")
            except Exception as e:
                messagebox.showerror("Export Failed", f"Failed to export configuration:\n{e}")
                
    def load_config_file(self):
        """Load configuration from file."""
        filename = filedialog.askopenfilename(
            title="Load Pipeline Configuration",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        
        if filename:
            try:
                with open(filename, 'r') as f:
                    self.pipeline_config = json.load(f)
                self.preset_var.set("Custom")
                self.modified = True
                self.populate_steps()
                self.clear_details_panel()
                self.validate_configuration()
                messagebox.showinfo("Load Successful", f"Configuration loaded from {filename}")
            except Exception as e:
                messagebox.showerror("Load Failed", f"Failed to load configuration:\n{e}")
                
    def save_config_file(self):
        """Save current configuration to file."""
        filename = filedialog.asksaveasfilename(
            title="Save Pipeline Configuration",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        
        if filename:
            try:
                with open(filename, 'w') as f:
                    json.dump(self.pipeline_config, f, indent=2)
                messagebox.showinfo("Save Successful", f"Configuration saved to {filename}")
            except Exception as e:
                messagebox.showerror("Save Failed", f"Failed to save configuration:\n{e}")
                
    def apply_changes(self):
        """Apply changes without closing dialog."""
        if self.validate_configuration():
            self.main_app.pipeline_config = self.pipeline_config.copy()
            self.modified = False
            messagebox.showinfo("Applied", "Pipeline configuration has been applied.")
        else:
            messagebox.showerror("Invalid Configuration", 
                "Please fix configuration issues before applying.")
            
    def save_and_close(self):
        """Save changes and close dialog."""
        if self.validate_configuration():
            self.main_app.pipeline_config = self.pipeline_config.copy()
            self.destroy()
        else:
            messagebox.showerror("Invalid Configuration", 
                "Please fix configuration issues before saving.")
            
    def cancel(self):
        """Cancel changes and close dialog."""
        if self.modified:
            if messagebox.askyesno("Unsaved Changes", 
                "You have unsaved changes. Are you sure you want to cancel?"):
                self.destroy()
        else:
            self.destroy()