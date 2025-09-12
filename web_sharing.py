import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
import json
import threading
import webbrowser
import http.server
import socketserver
from urllib.parse import parse_qs, urlparse
import tempfile
import socket
import datetime

try:
    import qrcode
    from PIL import Image, ImageTk
    QR_AVAILABLE = True
except ImportError:
    QR_AVAILABLE = False

try:
    import smtplib
    from email.mime.text import MimeText
    from email.mime.multipart import MimeMultipart
    EMAIL_AVAILABLE = True
except ImportError:
    EMAIL_AVAILABLE = False

class WebSharingManager:
    """Manages web-based schedule sharing and notifications."""
    
    def __init__(self, main_app):
        self.main_app = main_app
        self.web_server = None
        self.server_port = 8080
        self.server_thread = None
        self.shared_schedules = {}
        
    def generate_web_schedule(self, schedule_data, teams_data):
        """Generate HTML for web-based schedule viewing."""
        html_template = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Hockey Schedule</title>
        <style>
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                margin: 0;
                padding: 20px;
                background-color: #f5f5f5;
            }
            .container {
                max-width: 1200px;
                margin: 0 auto;
                background: white;
                border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                overflow: hidden;
            }
            .header {
                background: linear-gradient(135deg, #2c3e50, #3498db);
                color: white;
                padding: 30px;
                text-align: center;
            }
            .header h1 {
                margin: 0;
                font-size: 2.5em;
                font-weight: 300;
            }
            .stats-bar {
                background: #34495e;
                color: white;
                padding: 15px 20px;
                display: flex;
                justify-content: space-around;
                text-align: center;
            }
            .stat-item h3 {
                margin: 0;
                font-size: 1.5em;
            }
            .stat-item p {
                margin: 5px 0 0 0;
                opacity: 0.8;
            }
            .filters {
                padding: 20px;
                background: #ecf0f1;
                border-bottom: 1px solid #bdc3c7;
            }
            .filter-group {
                display: inline-block;
                margin-right: 20px;
                margin-bottom: 10px;
            }
            .filter-group label {
                display: block;
                margin-bottom: 5px;
                font-weight: bold;
                color: #2c3e50;
            }
            .filter-group select, .filter-group input {
                padding: 8px 12px;
                border: 1px solid #bdc3c7;
                border-radius: 5px;
                font-size: 14px;
                min-width: 150px;
            }
            .schedule-grid {
                padding: 20px;
            }
            .event-card {
                background: white;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                margin-bottom: 15px;
                padding: 20px;
                box-shadow: 0 2px 5px rgba(0,0,0,0.1);
                transition: transform 0.2s, box-shadow 0.2s;
            }
            .event-card:hover {
                transform: translateY(-2px);
                box-shadow: 0 4px 15px rgba(0,0,0,0.15);
            }
            .event-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 15px;
            }
            .event-title {
                font-size: 1.3em;
                font-weight: bold;
                color: #2c3e50;
            }
            .event-type {
                padding: 5px 12px;
                border-radius: 20px;
                font-size: 0.8em;
                font-weight: bold;
                text-transform: uppercase;
            }
            .type-practice {
                background: #3498db;
                color: white;
            }
            .type-game {
                background: #e74c3c;
                color: white;
            }
            .type-shared {
                background: #f39c12;
                color: white;
            }
            .event-details {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 15px;
            }
            .detail-item {
                display: flex;
                align-items: center;
            }
            .detail-icon {
                width: 20px;
                height: 20px;
                margin-right: 10px;
                opacity: 0.7;
            }
            .no-results {
                text-align: center;
                padding: 60px 20px;
                color: #7f8c8d;
                font-size: 1.2em;
            }
            @media (max-width: 768px) {
                .container {
                    margin: 10px;
                    border-radius: 0;
                }
                .header {
                    padding: 20px;
                }
                .header h1 {
                    font-size: 2em;
                }
                .event-details {
                    grid-template-columns: 1fr;
                }
                .stats-bar {
                    flex-direction: column;
                    gap: 15px;
                }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Hockey Schedule</h1>
                <p>Stay up to date with all games and practices</p>
            </div>
            
            <div class="stats-bar">
                <div class="stat-item">
                    <h3 id="total-events">--</h3>
                    <p>Total Events</p>
                </div>
                <div class="stat-item">
                    <h3 id="total-teams">--</h3>
                    <p>Teams</p>
                </div>
                <div class="stat-item">
                    <h3 id="upcoming-events">--</h3>
                    <p>This Week</p>
                </div>
            </div>
            
            <div class="filters">
                <div class="filter-group">
                    <label for="team-filter">Team:</label>
                    <select id="team-filter">
                        <option value="">All Teams</option>
                    </select>
                </div>
                <div class="filter-group">
                    <label for="type-filter">Type:</label>
                    <select id="type-filter">
                        <option value="">All Types</option>
                        <option value="practice">Practice</option>
                        <option value="game">Game</option>
                        <option value="shared">Shared Practice</option>
                    </select>
                </div>
                <div class="filter-group">
                    <label for="date-filter">Date Range:</label>
                    <select id="date-filter">
                        <option value="all">All Dates</option>
                        <option value="week">This Week</option>
                        <option value="month">This Month</option>
                        <option value="upcoming">Upcoming Only</option>
                    </select>
                </div>
                <div class="filter-group">
                    <label for="search-filter">Search:</label>
                    <input type="text" id="search-filter" placeholder="Search teams, arenas...">
                </div>
            </div>
            
            <div class="schedule-grid" id="schedule-container">
                <div class="no-results" id="no-results" style="display: none;">
                    No events match your current filters.
                </div>
            </div>
        </div>

        <script>
            // Schedule data will be injected here
            const scheduleData = {schedule_data_json};
            
            let filteredData = [...scheduleData];
            
            function initializeFilters() {
                const teamFilter = document.getElementById('team-filter');
                const teams = [...new Set(scheduleData.map(event => event.team))].sort();
                
                teams.forEach(team => {
                    const option = document.createElement('option');
                    option.value = team;
                    option.textContent = team;
                    teamFilter.appendChild(option);
                });
                
                // Add event listeners
                document.getElementById('team-filter').addEventListener('change', applyFilters);
                document.getElementById('type-filter').addEventListener('change', applyFilters);
                document.getElementById('date-filter').addEventListener('change', applyFilters);
                document.getElementById('search-filter').addEventListener('input', applyFilters);
            }
            
            function applyFilters() {
                const teamFilter = document.getElementById('team-filter').value;
                const typeFilter = document.getElementById('type-filter').value;
                const dateFilter = document.getElementById('date-filter').value;
                const searchFilter = document.getElementById('search-filter').value.toLowerCase();
                
                filteredData = scheduleData.filter(event => {
                    // Team filter
                    if (teamFilter && event.team !== teamFilter) return false;
                    
                    // Type filter
                    if (typeFilter) {
                        const eventType = event.type.toLowerCase();
                        if (typeFilter === 'shared' && !eventType.includes('shared')) return false;
                        if (typeFilter !== 'shared' && !eventType.includes(typeFilter)) return false;
                    }
                    
                    // Date filter
                    if (dateFilter !== 'all') {
                        const eventDate = new Date(event.date);
                        const now = new Date();
                        const weekFromNow = new Date(now.getTime() + 7 * 24 * 60 * 60 * 1000);
                        const monthFromNow = new Date(now.getFullYear(), now.getMonth() + 1, now.getDate());
                        
                        switch(dateFilter) {
                            case 'week':
                                if (eventDate < now || eventDate > weekFromNow) return false;
                                break;
                            case 'month':
                                if (eventDate < now || eventDate > monthFromNow) return false;
                                break;
                            case 'upcoming':
                                if (eventDate < now) return false;
                                break;
                        }
                    }
                    
                    // Search filter
                    if (searchFilter) {
                        const searchText = `${event.team} ${event.opponent} ${event.arena}`.toLowerCase();
                        if (!searchText.includes(searchFilter)) return false;
                    }
                    
                    return true;
                });
                
                renderSchedule();
                updateStats();
            }
            
            function renderSchedule() {
                const container = document.getElementById('schedule-container');
                const noResults = document.getElementById('no-results');
                
                if (filteredData.length === 0) {
                    container.innerHTML = '';
                    container.appendChild(noResults);
                    noResults.style.display = 'block';
                    return;
                }
                
                noResults.style.display = 'none';
                
                // Sort by date and time
                filteredData.sort((a, b) => {
                    if (a.date !== b.date) return new Date(a.date) - new Date(b.date);
                    return a.time_slot.localeCompare(b.time_slot);
                });
                
                container.innerHTML = filteredData.map(event => createEventCard(event)).join('');
            }
            
            function createEventCard(event) {
                const eventType = event.type.toLowerCase();
                let typeClass = 'type-practice';
                if (eventType.includes('game')) typeClass = 'type-game';
                else if (eventType.includes('shared')) typeClass = 'type-shared';
                
                const eventDate = new Date(event.date);
                const formattedDate = eventDate.toLocaleDateString('en-US', {
                    weekday: 'long',
                    year: 'numeric',
                    month: 'long',
                    day: 'numeric'
                });
                
                const opponent = event.opponent === 'Practice' ? '' : ` vs ${event.opponent}`;
                
                return `
                    <div class="event-card">
                        <div class="event-header">
                            <div class="event-title">${event.team}${opponent}</div>
                            <div class="event-type ${typeClass}">${event.type}</div>
                        </div>
                        <div class="event-details">
                            <div class="detail-item">
                                <span class="detail-icon">[DATE]</span>
                                <span>${formattedDate}</span>
                            </div>
                            <div class="detail-item">
                                <span class="detail-icon">[TIME]</span>
                                <span>${event.time_slot}</span>
                            </div>
                            <div class="detail-item">
                                <span class="detail-icon">[ARENA]</span>
                                <span>${event.arena}</span>
                            </div>
                        </div>
                    </div>
                `;
            }
            
            function updateStats() {
                document.getElementById('total-events').textContent = scheduleData.length;
                document.getElementById('total-teams').textContent = 
                    new Set(scheduleData.map(event => event.team)).size;
                
                const now = new Date();
                const weekFromNow = new Date(now.getTime() + 7 * 24 * 60 * 60 * 1000);
                const thisWeekEvents = scheduleData.filter(event => {
                    const eventDate = new Date(event.date);
                    return eventDate >= now && eventDate <= weekFromNow;
                });
                document.getElementById('upcoming-events').textContent = thisWeekEvents.length;
            }
            
            // Initialize on page load
            document.addEventListener('DOMContentLoaded', function() {
                initializeFilters();
                renderSchedule();
                updateStats();
            });
        </script>
    </body>
    </html>"""
        
        # Convert schedule data to JSON
        schedule_json = json.dumps(schedule_data)
        
        # Replace placeholder with actual data
        html_content = html_template.replace('{schedule_data_json}', schedule_json)
        
        return html_content


class WebSharingDialog(tk.Toplevel):
    """Dialog for web sharing configuration and management."""
    
    def __init__(self, parent, main_app):
        super().__init__(parent)
        self.parent = parent
        self.main_app = main_app
        self.web_manager = WebSharingManager(main_app)
        
        self.title("Web Sharing & Integration")
        self.geometry("600x700")
        self.transient(parent)
        self.grab_set()
        
        # Initialize variables
        self.team_share_vars = {}
        self.temp_html = None
        
        self.setup_ui()
        
        # FIXED: Refresh team list after UI is set up and dialog is shown
        self.after(100, self.refresh_team_list)
        
    def setup_ui(self):
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Web Sharing Tab
        web_frame = ttk.Frame(notebook)
        notebook.add(web_frame, text="Web Sharing")
        self.setup_web_sharing_tab(web_frame)
        
        # Email Notifications Tab
        email_frame = ttk.Frame(notebook)
        notebook.add(email_frame, text="Email Notifications")
        self.setup_email_tab(email_frame)
        
        # Export Tab
        export_frame = ttk.Frame(notebook)
        notebook.add(export_frame, text="Calendar Export")
        self.setup_export_tab(export_frame)
        
    def setup_web_sharing_tab(self, parent):
        """Setup web sharing configuration."""
        # Server status
        status_frame = ttk.LabelFrame(parent, text="Server Status", padding=10)
        status_frame.pack(fill="x", padx=10, pady=5)
        
        self.server_status_var = tk.StringVar(value="Stopped")
        ttk.Label(status_frame, text="Status:").grid(row=0, column=0, sticky="w", padx=5)
        self.status_label = ttk.Label(status_frame, textvariable=self.server_status_var, 
                                     foreground="red")
        self.status_label.grid(row=0, column=1, sticky="w", padx=5)
        
        self.server_url_var = tk.StringVar(value="Not running")
        ttk.Label(status_frame, text="URL:").grid(row=1, column=0, sticky="w", padx=5)
        self.url_label = ttk.Label(status_frame, textvariable=self.server_url_var, 
                                  foreground="blue", cursor="hand2")
        self.url_label.grid(row=1, column=1, sticky="w", padx=5)
        self.url_label.bind("<Button-1>", self.open_web_schedule)
        
        # Control buttons
        control_frame = ttk.Frame(status_frame)
        control_frame.grid(row=2, column=0, columnspan=2, pady=10)
        
        self.start_button = ttk.Button(control_frame, text="Start Web Server", 
                                      command=self.start_web_server)
        self.start_button.pack(side="left", padx=5)
        
        self.stop_button = ttk.Button(control_frame, text="Stop Web Server", 
                                     command=self.stop_web_server, state="disabled")
        self.stop_button.pack(side="left", padx=5)
        
        qr_button = ttk.Button(control_frame, text="Generate QR Code", 
                              command=self.generate_qr_code)
        qr_button.pack(side="left", padx=5)
        if not QR_AVAILABLE:
            qr_button.config(state="disabled")
        
        # Configuration
        config_frame = ttk.LabelFrame(parent, text="Configuration", padding=10)
        config_frame.pack(fill="x", padx=10, pady=5)
        
        ttk.Label(config_frame, text="Port:").grid(row=0, column=0, sticky="w", padx=5)
        self.port_var = tk.StringVar(value="8080")
        port_entry = ttk.Entry(config_frame, textvariable=self.port_var, width=10)
        port_entry.grid(row=0, column=1, sticky="w", padx=5)
        
        self.public_access_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(config_frame, text="Allow public access (not just local network)", 
                       variable=self.public_access_var).grid(row=1, column=0, columnspan=2, 
                                                            sticky="w", padx=5, pady=5)
        
        # Access management
        access_frame = ttk.LabelFrame(parent, text="Access Management", padding=10)
        access_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        ttk.Label(access_frame, text="Share specific team schedules:").pack(anchor="w", pady=5)
        
        # Team selection for sharing
        self.team_share_frame = ttk.Frame(access_frame)
        self.team_share_frame.pack(fill="both", expand=True)
        
        # QR code display area
        if QR_AVAILABLE:
            self.qr_frame = ttk.LabelFrame(parent, text="QR Code", padding=10)
            self.qr_frame.pack(fill="x", padx=10, pady=5)
            
            self.qr_label = ttk.Label(self.qr_frame, text="QR codes will appear here")
            self.qr_label.pack(expand=True)

    def setup_email_tab(self, parent):
        """Setup email notification configuration."""
        # Check email availability first
        email_available = EMAIL_AVAILABLE
        
        if not email_available:
            warning_label = ttk.Label(parent, text="Email features require smtplib (usually built-in)", 
                                     foreground="orange")
            warning_label.pack(pady=20)
            
        # SMTP Configuration
        smtp_frame = ttk.LabelFrame(parent, text="Email Server Configuration", padding=10)
        smtp_frame.pack(fill="x", padx=10, pady=5)
        smtp_frame.columnconfigure(1, weight=1)
        
        ttk.Label(smtp_frame, text="SMTP Server:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        self.smtp_server_var = tk.StringVar(value="smtp-mail.outlook.com")
        smtp_server_entry = ttk.Entry(smtp_frame, textvariable=self.smtp_server_var)
        smtp_server_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=2)
        
        ttk.Label(smtp_frame, text="Port:").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        self.smtp_port_var = tk.StringVar(value="587")
        smtp_port_entry = ttk.Entry(smtp_frame, textvariable=self.smtp_port_var, width=10)
        smtp_port_entry.grid(row=1, column=1, sticky="w", padx=5, pady=2)
        
        ttk.Label(smtp_frame, text="Email:").grid(row=2, column=0, sticky="w", padx=5, pady=2)
        self.email_var = tk.StringVar()
        email_entry = ttk.Entry(smtp_frame, textvariable=self.email_var)
        email_entry.grid(row=2, column=1, sticky="ew", padx=5, pady=2)
        
        ttk.Label(smtp_frame, text="Password:").grid(row=3, column=0, sticky="w", padx=5, pady=2)
        self.password_var = tk.StringVar()
        password_entry = ttk.Entry(smtp_frame, textvariable=self.password_var, show="*")
        password_entry.grid(row=3, column=1, sticky="ew", padx=5, pady=2)
        
        # Create the test button first
        test_button = ttk.Button(smtp_frame, text="Test Connection", 
                                command=self.test_email_connection, state="disabled")
        test_button.grid(row=4, column=0, columnspan=2, pady=10)
        
        # FIXED: Corrected validation function with proper button reference
        def validate_email_fields(*args):
            email = self.email_var.get().strip()
            password = self.password_var.get().strip()
            server = self.smtp_server_var.get().strip()
            port = self.smtp_port_var.get().strip()
            
            # Debug print to see what's happening
            print(f"Validation check - Email: '{email}', Password: {'*' * len(password)}, Server: '{server}', Port: '{port}', EMAIL_AVAILABLE: {email_available}")
            
            # Enable test button only if all fields are filled and email is available
            if email and password and server and port and email_available:
                test_button.config(state="normal")
                print("Test button enabled")
            else:
                test_button.config(state="disabled")
                print("Test button disabled")
        
        # Bind validation to entry widgets directly
        smtp_server_entry.bind('<KeyRelease>', validate_email_fields)
        smtp_port_entry.bind('<KeyRelease>', validate_email_fields)
        email_entry.bind('<KeyRelease>', validate_email_fields)
        password_entry.bind('<KeyRelease>', validate_email_fields)
        
        # Also bind to StringVar traces as backup
        self.email_var.trace_add("write", validate_email_fields)
        self.password_var.trace_add("write", validate_email_fields)
        self.smtp_server_var.trace_add("write", validate_email_fields)
        self.smtp_port_var.trace_add("write", validate_email_fields)
        
        # Gmail and Outlook help
        help_frame = ttk.LabelFrame(parent, text="Email Configuration Help", padding=10)
        help_frame.pack(fill="x", padx=10, pady=5)
        
        help_text = """Email Provider Settings:

Outlook/Hotmail/Live:
• Server: smtp-mail.outlook.com, Port: 587
• Use your regular email and password
• May need to enable "Less secure app access" in security settings

Gmail:
• Server: smtp.gmail.com, Port: 587  
• Enable 2-Factor Authentication on your Google account
• Generate an "App Password" (not your regular password):
  - Go to Google Account settings → Security → 2-Step Verification → App passwords
  - Select 'Mail' and generate a password
  - Use that generated password here

Other providers:
• Yahoo: smtp.mail.yahoo.com, Port: 587
• Contact your IT department for corporate email settings"""
        
        help_label = ttk.Label(help_frame, text=help_text, justify="left", wraplength=500)
        help_label.pack(anchor="w")
        
        # Notification settings
        notify_frame = ttk.LabelFrame(parent, text="Notification Settings", padding=10)
        notify_frame.pack(fill="x", padx=10, pady=5)
        
        self.notify_changes_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(notify_frame, text="Send notifications when schedule changes", 
                       variable=self.notify_changes_var).pack(anchor="w", pady=2)
        
        self.notify_reminders_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(notify_frame, text="Send event reminders", 
                       variable=self.notify_reminders_var).pack(anchor="w", pady=2)
        
        # Recipient management
        recipients_frame = ttk.LabelFrame(parent, text="Email Recipients", padding=10)
        recipients_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        recipient_entry_frame = ttk.Frame(recipients_frame)
        recipient_entry_frame.pack(fill="x", pady=5)
        
        ttk.Label(recipient_entry_frame, text="Email:").pack(side="left", padx=5)
        self.recipient_email_var = tk.StringVar()
        ttk.Entry(recipient_entry_frame, textvariable=self.recipient_email_var, width=30).pack(side="left", padx=5)
        
        ttk.Label(recipient_entry_frame, text="Team:").pack(side="left", padx=5)
        self.recipient_team_var = tk.StringVar()
        self.recipient_team_combo = ttk.Combobox(recipient_entry_frame, textvariable=self.recipient_team_var, 
                                               width=20, state="readonly")
        self.recipient_team_combo.pack(side="left", padx=5)
        
        ttk.Button(recipient_entry_frame, text="Add", 
                  command=self.add_email_recipient).pack(side="left", padx=5)
        
        # Recipients list
        self.recipients_tree = ttk.Treeview(recipients_frame, columns=("Email", "Team"), show="headings", height=6)
        self.recipients_tree.heading("Email", text="Email Address")
        self.recipients_tree.heading("Team", text="Team")
        self.recipients_tree.pack(fill="both", expand=True, pady=5)
        
        ttk.Button(recipients_frame, text="Remove Selected", 
                  command=self.remove_email_recipient).pack(pady=5)

    def setup_export_tab(self, parent):
        """Setup calendar export options."""
        # iCal export
        ical_frame = ttk.LabelFrame(parent, text="iCal/Google Calendar Export", padding=10)
        ical_frame.pack(fill="x", padx=10, pady=5)
        
        ttk.Label(ical_frame, text="Export team schedules for import into calendar applications:").pack(anchor="w", pady=5)
        
        team_export_frame = ttk.Frame(ical_frame)
        team_export_frame.pack(fill="x", pady=5)
        
        ttk.Label(team_export_frame, text="Team:").pack(side="left", padx=5)
        self.export_team_var = tk.StringVar()
        self.export_team_combo = ttk.Combobox(team_export_frame, textvariable=self.export_team_var, 
                                            width=25, state="readonly")
        self.export_team_combo.pack(side="left", padx=5)
        
        ttk.Button(team_export_frame, text="Export Team Calendar", 
                  command=self.export_team_calendar).pack(side="left", padx=5)
        
        ttk.Button(ical_frame, text="Export All Teams", 
                  command=self.export_all_calendars).pack(pady=5)
        
        # Mobile sharing
        mobile_frame = ttk.LabelFrame(parent, text="Mobile Sharing", padding=10)
        mobile_frame.pack(fill="x", padx=10, pady=5)
        
        ttk.Label(mobile_frame, text="Generate mobile-friendly schedule links:").pack(anchor="w", pady=5)
        
        mobile_controls = ttk.Frame(mobile_frame)
        mobile_controls.pack(fill="x", pady=5)
        
        ttk.Button(mobile_controls, text="Generate Mobile Schedule", 
                  command=self.generate_mobile_schedule).pack(side="left", padx=5)
        
        qr_teams_button = ttk.Button(mobile_controls, text="Create QR Codes for Teams", 
                                    command=self.create_team_qr_codes)
        qr_teams_button.pack(side="left", padx=5)
        if not QR_AVAILABLE:
            qr_teams_button.config(state="disabled")
        
    def refresh_team_list(self):
        """Refresh the team list for sharing options."""
        # FIXED: Get teams data from main app with better error handling
        teams_data = {}
        
        try:
            if hasattr(self.main_app, 'teams_data') and self.main_app.teams_data:
                teams_data = self.main_app.teams_data
            elif hasattr(self.main_app, 'main_ui') and hasattr(self.main_app.main_ui, 'get_teams_data'):
                teams_data = self.main_app.main_ui.get_teams_data()
        except Exception as e:
            print(f"Error getting teams data: {e}")
        
        if not teams_data:
            # Show a message if no teams are available
            if hasattr(self, 'team_share_frame'):
                for widget in self.team_share_frame.winfo_children():
                    widget.destroy()
                ttk.Label(self.team_share_frame, text="No teams configured. Please add teams first.", 
                        foreground="orange").grid(row=0, column=0, padx=5, pady=10)
            
            # Update combo boxes with empty values
            if hasattr(self, 'recipient_team_combo'):
                self.recipient_team_combo.configure(values=["All Teams"])
            if hasattr(self, 'export_team_combo'):
                self.export_team_combo.configure(values=[])
            return
                
        # Clear existing team checkboxes
        if hasattr(self, 'team_share_frame'):
            for widget in self.team_share_frame.winfo_children():
                widget.destroy()
                
        self.team_share_vars = {}
        
        # Create checkboxes for each team
        team_names = sorted(teams_data.keys())
        for i, team_name in enumerate(team_names):
            var = tk.BooleanVar(value=True)
            self.team_share_vars[team_name] = var
            
            cb = ttk.Checkbutton(self.team_share_frame, text=team_name, variable=var)
            cb.grid(row=i//2, column=i%2, sticky="w", padx=5, pady=2)
            
        # FIXED: Update combo boxes with actual team data
        if hasattr(self, 'recipient_team_combo'):
            self.recipient_team_combo.configure(values=["All Teams"] + team_names)
            if not self.recipient_team_var.get():
                self.recipient_team_var.set("All Teams")
                
        if hasattr(self, 'export_team_combo'):
            self.export_team_combo.configure(values=team_names)
            if team_names and not self.export_team_var.get():
                self.export_team_var.set(team_names[0])
    
    def start_web_server(self):
        """Start the web server for schedule sharing."""
        try:
            port = int(self.port_var.get())
            
            # Generate HTML content
            schedule_data = getattr(self.main_app, 'schedule_data', [])
            if hasattr(self.main_app, 'main_ui') and hasattr(self.main_app.main_ui, 'get_schedule_data'):
                schedule_data = self.main_app.main_ui.get_schedule_data()
                
            teams_data = getattr(self.main_app, 'teams_data', {})
            
            if not schedule_data:
                messagebox.showwarning("No Data", "No schedule data available to share.")
                return
                
            html_content = self.web_manager.generate_web_schedule(schedule_data, teams_data)
            
            # Create temporary HTML file with UTF-8 encoding
            self.temp_html = tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8')
            self.temp_html.write(html_content)
            self.temp_html.close()
            
            # Start HTTP server
            def start_server():
                class CustomHandler(http.server.SimpleHTTPRequestHandler):
                    def __init__(self, *args, **kwargs):
                        super().__init__(*args, **kwargs)
                        
                    def do_GET(self):
                        if self.path == '/' or self.path == '/index.html':
                            self.send_response(200)
                            self.send_header('Content-type', 'text/html; charset=utf-8')
                            self.end_headers()
                            # Read and send file with UTF-8 encoding
                            with open(self.temp_html.name, 'r', encoding='utf-8') as f:
                                content = f.read()
                                self.wfile.write(content.encode('utf-8'))
                        else:
                            super().do_GET()
                            
                    def log_message(self, format, *args):
                        # Suppress server logs
                        pass
                            
                with socketserver.TCPServer(("", port), CustomHandler) as httpd:
                    self.web_manager.web_server = httpd
                    httpd.serve_forever()
                    
            self.web_manager.server_thread = threading.Thread(target=start_server, daemon=True)
            self.web_manager.server_thread.start()
            
            # Update UI
            self.server_status_var.set("Running")
            self.status_label.config(foreground="green")
            
            # Get local IP
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
            url = f"http://{local_ip}:{port}"
            self.server_url_var.set(url)
            
            self.start_button.config(state="disabled")
            self.stop_button.config(state="normal")
            
            messagebox.showinfo("Server Started", f"Web server started successfully!\n\nLocal access: http://localhost:{port}\nNetwork access: {url}")
            
        except Exception as e:
            messagebox.showerror("Server Error", f"Failed to start web server: {e}")

    def stop_web_server(self):
        """Stop the web server."""
        if self.web_manager.web_server:
            self.web_manager.web_server.shutdown()
            self.web_manager.web_server = None
            
        self.server_status_var.set("Stopped")
        self.status_label.config(foreground="red")
        self.server_url_var.set("Not running")
        
        self.start_button.config(state="normal")
        self.stop_button.config(state="disabled")
        
        # Clean up temp file
        if hasattr(self, 'temp_html'):
            try:
                os.unlink(self.temp_html.name)
            except:
                pass
                
    def open_web_schedule(self, event=None):
        """Open the web schedule in default browser."""
        url = self.server_url_var.get()
        if url != "Not running":
            webbrowser.open(url)
            
    def generate_qr_code(self):
        """Generate QR code for the web schedule."""
        if not QR_AVAILABLE:
            messagebox.showwarning("Feature Unavailable", "QR code generation requires qrcode and Pillow libraries.")
            return
            
        url = self.server_url_var.get()
        if url == "Not running":
            messagebox.showwarning("Server Not Running", "Please start the web server first.")
            return
            
        try:
            # Generate QR code
            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(url)
            qr.make(fit=True)
            
            # Create QR code image
            qr_img = qr.make_image(fill_color="black", back_color="white")
            
            # Convert for tkinter
            qr_img = qr_img.resize((200, 200), Image.Resampling.LANCZOS)
            self.qr_photo = ImageTk.PhotoImage(qr_img)
            
            # Display in dialog
            if hasattr(self, 'qr_label'):
                self.qr_label.configure(image=self.qr_photo, text="")
            
            # Save QR code
            filename = filedialog.asksaveasfilename(
                defaultextension=".png",
                filetypes=[("PNG files", "*.png")],
                initialfile="schedule_qr_code.png"
            )
            
            if filename:
                qr_img.save(filename)
                messagebox.showinfo("QR Code Saved", f"QR code saved to {filename}")
                
        except Exception as e:
            messagebox.showerror("QR Code Error", f"Failed to generate QR code: {e}")
            
    def test_email_connection(self):
        """Test the email server connection."""
        if not EMAIL_AVAILABLE:
            messagebox.showwarning("Feature Unavailable", "Email features require smtplib.")
            return
            
        try:
            import smtplib
            
            server_name = self.smtp_server_var.get().strip()
            port = int(self.smtp_port_var.get().strip())
            email = self.email_var.get().strip()
            password = self.password_var.get().strip()
            
            if not all([server_name, port, email, password]):
                messagebox.showerror("Missing Information", "Please fill in all email configuration fields.")
                return
            
            # Test connection
            server = smtplib.SMTP(server_name, port)
            server.starttls()
            server.login(email, password)
            server.quit()
            
            messagebox.showinfo("Connection Test", "Email connection successful!")
            
        except ValueError:
            messagebox.showerror("Invalid Port", "Port must be a number (usually 587 for most providers).")
        except smtplib.SMTPAuthenticationError:
            messagebox.showerror("Authentication Failed", 
                "Login failed. For Gmail, make sure you're using an App Password, not your regular password.\n\n"
                "For Outlook/Hotmail, check that your account allows SMTP access.")
        except smtplib.SMTPConnectError:
            messagebox.showerror("Connection Failed", 
                f"Cannot connect to {server_name}:{port}. Check server name and port number.")
        except Exception as e:
            messagebox.showerror("Connection Error", f"Email connection failed: {e}")
            
    def add_email_recipient(self):
        """Add an email recipient."""
        email = self.recipient_email_var.get().strip()
        team = self.recipient_team_var.get()
        
        if not email or not team:
            messagebox.showwarning("Missing Information", "Please enter both email and team.")
            return
            
        # Check for valid email format
        if "@" not in email or "." not in email:
            messagebox.showwarning("Invalid Email", "Please enter a valid email address.")
            return
            
        # Add to tree
        self.recipients_tree.insert("", "end", values=(email, team))
        
        # Clear entries
        self.recipient_email_var.set("")
        self.recipient_team_var.set("")
        
    def remove_email_recipient(self):
        """Remove selected email recipient."""
        selected_item = self.recipients_tree.selection()
        if selected_item:
            self.recipients_tree.delete(selected_item)
            
    def export_team_calendar(self):
        """Export calendar for selected team."""
        team_name = self.export_team_var.get()
        if not team_name:
            messagebox.showwarning("No Team Selected", "Please select a team to export.")
            return
            
        # Generate iCal content for the team
        schedule_data = getattr(self.main_app, 'schedule_data', [])
        if hasattr(self.main_app, 'main_ui') and hasattr(self.main_app.main_ui, 'get_schedule_data'):
            schedule_data = self.main_app.main_ui.get_schedule_data()
            
        team_events = [event for event in schedule_data if event.get("team") == team_name]
        
        if not team_events:
            messagebox.showwarning("No Events", f"No events found for team {team_name}.")
            return
            
        filename = filedialog.asksaveasfilename(
            defaultextension=".ics",
            filetypes=[("iCal files", "*.ics")],
            initialfile=f"{team_name}_schedule.ics"
        )
        
        if filename:
            self.generate_ical_file(team_events, filename, team_name)
            messagebox.showinfo("Export Complete", f"Calendar exported to {filename}")
        
    def generate_ical_file(self, events, filename, calendar_name):
        """Generate iCal file from events."""
        ical_content = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Hockey Scheduler//Team Schedule//EN",
            f"X-WR-CALNAME:{calendar_name} Hockey Schedule",
            f"X-WR-CALDESC:Hockey schedule for {calendar_name}"
        ]
        
        for event in events:
            date_str = event.get("date", "")
            time_slot = event.get("time_slot", "")
            arena = event.get("arena", "")
            opponent = event.get("opponent", "Practice")
            event_type = event.get("type", "practice")
            team = event.get("team", "")
            
            if date_str and time_slot and "-" in time_slot:
                try:
                    # Parse date and time
                    if isinstance(date_str, str):
                        event_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
                    else:
                        event_date = date_str
                        
                    start_time_str, end_time_str = time_slot.split("-")
                    start_time = datetime.datetime.strptime(start_time_str.strip(), "%H:%M").time()
                    end_time = datetime.datetime.strptime(end_time_str.strip(), "%H:%M").time()
                    
                    # Create datetime objects
                    start_datetime = datetime.datetime.combine(event_date, start_time)
                    end_datetime = datetime.datetime.combine(event_date, end_time)
                    
                    # Format for iCal
                    start_ical = start_datetime.strftime("%Y%m%dT%H%M%S")
                    end_ical = end_datetime.strftime("%Y%m%dT%H%M%S")
                    
                    # Create unique ID
                    uid = f"{team}-{date_str}-{start_time_str}@hockeyscheduler.local"
                    
                    # Determine event title
                    if opponent == "Practice":
                        title = f"{team} Practice"
                    else:
                        title = f"{team} vs {opponent}"
                    
                    ical_content.extend([
                        "BEGIN:VEVENT",
                        f"UID:{uid}",
                        f"DTSTART:{start_ical}",
                        f"DTEND:{end_ical}",
                        f"SUMMARY:{title}",
                        f"LOCATION:{arena}",
                        f"DESCRIPTION:Type: {event_type}",
                        "END:VEVENT"
                    ])
                    
                except ValueError:
                    continue  # Skip invalid events
        
        ical_content.append("END:VCALENDAR")
        
        # Write to file
        with open(filename, 'w', encoding='utf-8') as f:
            f.write('\n'.join(ical_content))
            
    def export_all_calendars(self):
        """Export calendars for all teams."""
        schedule_data = getattr(self.main_app, 'schedule_data', [])
        if hasattr(self.main_app, 'main_ui') and hasattr(self.main_app.main_ui, 'get_schedule_data'):
            schedule_data = self.main_app.main_ui.get_schedule_data()
            
        if not schedule_data:
            messagebox.showwarning("No Data", "No schedule data available to export.")
            return
            
        # Get all unique teams
        teams = sorted(set(event.get("team", "") for event in schedule_data if event.get("team")))
        
        if not teams:
            messagebox.showwarning("No Teams", "No teams found in schedule data.")
            return
            
        # Select directory
        directory = filedialog.askdirectory(title="Select directory to save team calendars")
        if not directory:
            return
            
        exported_count = 0
        for team_name in teams:
            team_events = [event for event in schedule_data if event.get("team") == team_name]
            if team_events:
                filename = os.path.join(directory, f"{team_name}_schedule.ics")
                try:
                    self.generate_ical_file(team_events, filename, team_name)
                    exported_count += 1
                except Exception as e:
                    messagebox.showerror("Export Error", f"Failed to export calendar for {team_name}: {e}")
                    
        messagebox.showinfo("Export Complete", f"Exported {exported_count} team calendars to {directory}")
        
    def generate_mobile_schedule(self):
        """Generate mobile-optimized schedule."""
        messagebox.showinfo("Mobile Schedule", "Mobile schedule generation feature would create a simplified, mobile-optimized HTML version of the schedule.")
        
    def create_team_qr_codes(self):
        """Create QR codes for individual teams."""
        if not QR_AVAILABLE:
            messagebox.showwarning("Feature Unavailable", "QR code generation requires qrcode and Pillow libraries.")
            return
            
        messagebox.showinfo("Team QR Codes", "This feature would generate individual QR codes for each team's specific schedule page.")

    def send_schedule_notification(self, subject, message, recipients=None):
        """Send email notification about schedule changes."""
        if not EMAIL_AVAILABLE:
            return False
            
        if not recipients:
            # Get recipients from the tree
            recipients = []
            for item in self.recipients_tree.get_children():
                values = self.recipients_tree.item(item)['values']
                recipients.append(values[0])  # Email address
                
        if not recipients:
            return False
            
        try:
            import smtplib
            from email.mime.text import MimeText
            from email.mime.multipart import MimeMultipart
            
            server = smtplib.SMTP(self.smtp_server_var.get(), int(self.smtp_port_var.get()))
            server.starttls()
            server.login(self.email_var.get(), self.password_var.get())
            
            for recipient in recipients:
                msg = MimeMultipart()
                msg['From'] = self.email_var.get()
                msg['To'] = recipient
                msg['Subject'] = subject
                
                msg.attach(MimeText(message, 'plain'))
                
                server.send_message(msg)
            
            server.quit()
            return True
            
        except Exception as e:
            messagebox.showerror("Email Error", f"Failed to send notifications: {e}")
            return False