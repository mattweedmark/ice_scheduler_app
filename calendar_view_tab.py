import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import datetime as _dt
import calendar as _cal
from collections import defaultdict
import hashlib
import webbrowser
import os

class CalendarViewTab(ttk.Frame):
    """
    Calendar tab with Month / Week / Day views, per-team filter, and printable export.
    Expects schedule entries like:
    {
        "date": "YYYY-MM-DD",
        "time_slot": "HH:MM-HH:MM",
        "team": "U9 - Hawks",
        "opponent": "Practice" or "Other Team",
        "arena": "Rink A",
        "type": "practice" | "practice (shared)" | "game" | "game (shared)"
    }
    """
    def __init__(self, parent, main_app):
        super().__init__(parent)
        self.main_app = main_app
        self.schedule_data = []
        self.current_date = _dt.date.today()
        self.team_colors = {}
        self.cells = []  # track widgets to clear between renders

        # Color palettes (stable mapping per team via hash)
        self.palette = [
            {"bg": "#FF6B6B", "fg": "white"}, {"bg": "#4ECDC4", "fg": "white"},
            {"bg": "#45B7D1", "fg": "white"}, {"bg": "#96CEB4", "fg": "black"},
            {"bg": "#FECA57", "fg": "black"}, {"bg": "#FF9FF3", "fg": "black"},
            {"bg": "#54A0FF", "fg": "white"}, {"bg": "#5F27CD", "fg": "white"},
            {"bg": "#00D2D3", "fg": "black"}, {"bg": "#FF6348", "fg": "white"},
            {"bg": "#2ED573", "fg": "white"}, {"bg": "#A55EEA", "fg": "white"},
            {"bg": "#26DE81", "fg": "black"}, {"bg": "#FD79A8", "fg": "white"},
            {"bg": "#FDCB6E", "fg": "black"},
        ]

        self._build_ui()
        self._refresh_teams_filter()
        self.render()

    # ------------------------- UI -------------------------
    def _build_ui(self):
        top = ttk.Frame(self)
        top.pack(fill="x", padx=10, pady=6)

        # Navigation
        ttk.Button(top, text="◀ Prev", command=self.prev).pack(side="left", padx=4)
        ttk.Button(top, text="Today", command=self.goto_today).pack(side="left", padx=4)
        ttk.Button(top, text="Next ▶", command=self.next).pack(side="left", padx=4)

        # View selector
        ttk.Label(top, text="View:").pack(side="left", padx=(12,4))
        self.view_var = tk.StringVar(value="Month")
        view_cb = ttk.Combobox(top, textvariable=self.view_var, values=["Month", "Week", "Day"], state="readonly", width=8)
        view_cb.pack(side="left")
        view_cb.bind("<<ComboboxSelected>>", lambda e: self.render())

        # Team filter
        ttk.Label(top, text="  Team:").pack(side="left", padx=(12,4))
        self.team_var = tk.StringVar(value="All Teams")
        self.team_cb = ttk.Combobox(top, textvariable=self.team_var, values=["All Teams"], state="readonly", width=28)
        self.team_cb.pack(side="left")
        self.team_cb.bind("<<ComboboxSelected>>", lambda e: self.render())

        # Type filters
        self.show_games_var = tk.BooleanVar(value=True)
        self.show_practices_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(top, text="Games", variable=self.show_games_var, command=self.render).pack(side="left", padx=6)
        ttk.Checkbutton(top, text="Practices", variable=self.show_practices_var, command=self.render).pack(side="left")

        # Export
        ttk.Button(top, text="Print / Export", command=self.export_printable).pack(side="right", padx=4)
        self.title_var = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.title_var, font=("Arial", 12, "bold")).pack(fill="x", padx=10, pady=(0,6))

        # Main area (scrollable for all views now)
        self.container = ttk.Frame(self)
        self.container.pack(fill="both", expand=True, padx=10, pady=6)

        self.canvas = tk.Canvas(self.container, highlightthickness=0)
        
        # Both vertical and horizontal scrollbars
        self.vsb = ttk.Scrollbar(self.container, orient="vertical", command=self.canvas.yview)
        self.hsb = ttk.Scrollbar(self.container, orient="horizontal", command=self.canvas.xview)
        
        self.canvas.configure(yscrollcommand=self.vsb.set, xscrollcommand=self.hsb.set)
        
        # Pack scrollbars
        self.vsb.pack(side="right", fill="y")
        self.hsb.pack(side="bottom", fill="x")
        self.canvas.pack(side="left", fill="both", expand=True)
        
        self.inner = ttk.Frame(self.canvas)
        self.canvas.create_window((0,0), window=self.inner, anchor="nw")

        # Update scroll region when inner frame changes
        self.inner.bind("<Configure>", self._on_inner_configure)
        
        # Bind mousewheel to canvas for scrolling
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<Button-4>", self._on_mousewheel)
        self.canvas.bind("<Button-5>", self._on_mousewheel)

    def _on_inner_configure(self, event):
        # Update the scroll region to encompass the inner frame
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        
        # For month view, set a minimum width to ensure proper layout
        if self.view_var.get() == "Month":
            min_width = 900  # Minimum width for month view
            canvas_width = self.canvas.winfo_width()
            if canvas_width < min_width:
                self.canvas.itemconfig(self.canvas.find_all()[0], width=min_width)
            else:
                self.canvas.itemconfig(self.canvas.find_all()[0], width=canvas_width)

    def _on_mousewheel(self, event):
        # Handle mouse wheel scrolling
        if event.delta:
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        elif event.num == 4:
            self.canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self.canvas.yview_scroll(1, "units")

    # ------------------------- Helpers -------------------------
    def _get_team_color(self, team):
        if not team:
            return {"bg": "#EFEFEF", "fg": "black"}
        if team not in self.team_colors:
            h = int(hashlib.md5(team.encode()).hexdigest()[:8], 16)
            self.team_colors[team] = self.palette[h % len(self.palette)]
        return self.team_colors[team]

    def _filtered_events(self):
        """Return events filtered by team and type, with parsed datetimes."""
        selected_team = self.team_var.get()
        show_games = self.show_games_var.get()
        show_practices = self.show_practices_var.get()

        evts = []
        for e in self.schedule_data or []:
            etype = (e.get("type","") or "").lower()
            if ("game" in etype and not show_games) or ("practice" in etype and not show_practices):
                continue
            team = e.get("team") or ""
            if selected_team != "All Teams" and team != selected_team:
                continue
            # parse date
            try:
                d = _dt.datetime.strptime(e.get("date",""), "%Y-%m-%d").date()
            except Exception:
                continue
            # parse start/end
            start_s, end_s = (e.get("time_slot","") or "00:00-00:00").split("-")[:2]
            try:
                start_t = _dt.datetime.strptime(start_s.strip(), "%H:%M").time()
                end_t = _dt.datetime.strptime(end_s.strip(), "%H:%M").time()
            except Exception:
                start_t = _dt.time(0,0); end_t = _dt.time(0,0)
            evts.append({
                **e,
                "_date": d,
                "_start": start_t,
                "_end": end_t
            })
        evts.sort(key=lambda x: (x["_date"], x["_start"], x.get("arena",""), x.get("team","")))
        return evts

    def _refresh_teams_filter(self):
        teams = sorted({e.get("team","") for e in (self.schedule_data or []) if e.get("team")})
        values = ["All Teams"] + teams
        self.team_cb.configure(values=values)
        if self.team_var.get() not in values:
            self.team_var.set("All Teams")

    def load_schedule_data(self, schedule_data):
        self.schedule_data = schedule_data or []
        self._refresh_teams_filter()
        self.render()

    def get_schedule_data(self):
        return self.schedule_data

    def goto_today(self):
        self.current_date = _dt.date.today()
        self.render()

    def prev(self):
        mode = self.view_var.get()
        if mode == "Month":
            year = self.current_date.year - (1 if self.current_date.month == 1 else 0)
            month = 12 if self.current_date.month == 1 else self.current_date.month - 1
            day = min(self.current_date.day, _cal.monthrange(year, month)[1])
            self.current_date = _dt.date(year, month, day)
        elif mode == "Week":
            self.current_date -= _dt.timedelta(days=7)
        else:
            self.current_date -= _dt.timedelta(days=1)
        self.render()

    def next(self):
        mode = self.view_var.get()
        if mode == "Month":
            year = self.current_date.year + (1 if self.current_date.month == 12 else 0)
            month = 1 if self.current_date.month == 12 else self.current_date.month + 1
            day = min(self.current_date.day, _cal.monthrange(year, month)[1])
            self.current_date = _dt.date(year, month, day)
        elif mode == "Week":
            self.current_date += _dt.timedelta(days=7)
        else:
            self.current_date += _dt.timedelta(days=1)
        self.render()

    # ------------------------- Rendering -------------------------
    def _clear_inner(self):
        for w in self.inner.winfo_children():
            w.destroy()
        self.cells.clear()

    def render(self):
        self._clear_inner()
        mode = self.view_var.get()
        if mode == "Month":
            self._render_month()
        elif mode == "Week":
            self._render_week()
        else:
            self._render_day()
        
        # Reset scroll position to top-left
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)

    def _render_month(self):
        y, m = self.current_date.year, self.current_date.month
        self.title_var.set(self.current_date.strftime("%B %Y"))

        # Header row: days
        days = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
        for c, d in enumerate(days):
            lbl = ttk.Label(self.inner, text=d, anchor="center", padding=4, style="Heading.TLabel")
            lbl.grid(row=0, column=c, sticky="nsew", padx=1, pady=1)
            # Set minimum column width for better layout
            self.inner.grid_columnconfigure(c, weight=1, minsize=120)

        # Weeks grid
        cal = _cal.Calendar(firstweekday=0).monthdayscalendar(y, m)  # Monday-first
        # Build events by day
        by_day = defaultdict(list)
        for e in self._filtered_events():
            if e["_date"].year == y and e["_date"].month == m:
                by_day[e["_date"].day].append(e)

        for r, week in enumerate(cal, start=1):
            self.inner.grid_rowconfigure(r, weight=1, minsize=100)  # Set minimum row height
            for c, day in enumerate(week):
                frame = ttk.Frame(self.inner, relief="solid", borderwidth=1)
                frame.grid(row=r, column=c, sticky="nsew", padx=1, pady=1)
                self.cells.append(frame)
                if day == 0:
                    continue
                # Day label
                dl = ttk.Label(frame, text=str(day), anchor="nw")
                dl.pack(anchor="nw", padx=4, pady=(2,0))

                # Events
                for e in by_day.get(day, []):
                    self._create_event_chip(frame, e)

    def _render_week(self):
        # Compute Monday of current week
        monday = self.current_date - _dt.timedelta(days=self.current_date.weekday())
        dates = [monday + _dt.timedelta(days=i) for i in range(7)]
        self.title_var.set(f"Week of {monday.strftime('%b %d, %Y')}")

        # Header row: time axis + 7 days
        header = ["Time"] + [d.strftime("%a %b %d") for d in dates]
        for c, txt in enumerate(header):
            lbl = ttk.Label(self.inner, text=txt, anchor="center", padding=4, style="Heading.TLabel")
            lbl.grid(row=0, column=c, sticky="nsew", padx=1, pady=1)
            if c == 0:
                self.inner.grid_columnconfigure(c, weight=0, minsize=80)  # Time column
            else:
                self.inner.grid_columnconfigure(c, weight=1, minsize=120)  # Day columns

        # Build events by date
        by_date = defaultdict(list)
        for e in self._filtered_events():
            if monday <= e["_date"] <= dates[-1]:
                by_date[e["_date"]].append(e)

        # Build a sorted list of unique start times to use as rows
        unique_times = sorted({e["_start"] for evts in by_date.values() for e in evts})
        if not unique_times:
            unique_times = [_dt.time(h,0) for h in range(6,22)]

        for r, t in enumerate(unique_times, start=1):
            self.inner.grid_rowconfigure(r, weight=1, minsize=60)
            # Time label
            ttk.Label(self.inner, text=t.strftime("%H:%M"), anchor="e", padding=(4,2)).grid(row=r, column=0, sticky="nsew", padx=1, pady=1)
            # Day columns
            for c, d in enumerate(dates, start=1):
                cell = ttk.Frame(self.inner, relief="solid", borderwidth=1)
                cell.grid(row=r, column=c, sticky="nsew", padx=1, pady=1)
                self.cells.append(cell)
                # Put events that start at this time
                for e in sorted(by_date.get(d, []), key=lambda x: (x["_start"], x.get("arena",""), x.get("team",""))):
                    if e["_start"] == t:
                        self._create_event_chip(cell, e)

    def _render_day(self):
        d = self.current_date
        self.title_var.set(d.strftime("%A, %B %d, %Y"))

        # Header
        ttk.Label(self.inner, text="Time", padding=4, style="Heading.TLabel").grid(row=0, column=0, sticky="nsew", padx=1, pady=1)
        ttk.Label(self.inner, text="Event", padding=4, style="Heading.TLabel").grid(row=0, column=1, sticky="nsew", padx=1, pady=1)
        self.inner.grid_columnconfigure(0, weight=0, minsize=120)
        self.inner.grid_columnconfigure(1, weight=1, minsize=400)

        # Events
        evts = [e for e in self._filtered_events() if e["_date"] == d]
        if not evts:
            ttk.Label(self.inner, text="No events.", padding=12).grid(row=1, column=0, columnspan=2, sticky="w")
            return

        for r, e in enumerate(evts, start=1):
            self.inner.grid_rowconfigure(r, weight=0, minsize=50)
            ttk.Label(self.inner, text=f"{e['_start'].strftime('%H:%M')}–{e['_end'].strftime('%H:%M')}", padding=(6,2)).grid(row=r, column=0, sticky="e")
            cell = ttk.Frame(self.inner, relief="solid", borderwidth=1)
            cell.grid(row=r, column=1, sticky="nsew", padx=1, pady=1)
            self._create_event_chip(cell, e)

    def _create_event_chip(self, parent, e):
        team = e.get("team","")
        opp = e.get("opponent","")
        arena = e.get("arena","")
        etype = (e.get("type","") or "").lower()
        time_slot = e.get("time_slot","")
        col = self._get_team_color(team)

        frame = tk.Frame(parent, bg=col["bg"])
        frame.pack(fill="x", padx=2, pady=1)  # Reduced padding to make chips smaller

        title = team if not opp or opp == "Practice" else f"{team} vs {opp}"
        # Reduced font sizes to fit more content
        tk.Label(frame, text=title, bg=col["bg"], fg=col["fg"], font=("Arial", 8, "bold")).pack(anchor="w")
        tk.Label(frame, text=f"{time_slot}" + (f" @ {arena}" if arena else ""), bg=col["bg"], fg=col["fg"], font=("Arial", 7)).pack(anchor="w")

        # tiny type tag
        tag = "P" if "practice" in etype else "G"
        tk.Label(frame, text=tag, bg=col["bg"], fg=col["fg"], font=("Arial", 6, "bold")).place(relx=1, rely=0, anchor="ne")

        # click to show details
        frame.bind("<Button-1>", lambda _e=None, data=e: self._show_details(data))

    def _show_details(self, e):
        details = [
            f"Team: {e.get('team','')}",
            f"Opponent: {e.get('opponent','')}",
            f"Type: {e.get('type','')}",
            f"Date: {e.get('date','')}  Time: {e.get('time_slot','')}",
            f"Arena: {e.get('arena','')}",
        ]
        messagebox.showinfo("Event Details", "\n".join(details))

    # ------------------------- Export -------------------------
    def export_printable(self):
        """Export current view to a simple self-contained HTML file."""
        # Pick path
        default_name = f"calendar_{self.view_var.get().lower()}_{self.current_date.isoformat()}.html"
        path = filedialog.asksaveasfilename(defaultextension=".html", initialfile=default_name,
                                            filetypes=[("HTML files","*.html")])
        if not path:
            return

        html = self._render_html()
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(html)
        except Exception as ex:
            messagebox.showerror("Export Failed", str(ex))
            return

        try:
            webbrowser.open("file://" + os.path.abspath(path))
        except Exception:
            pass
        messagebox.showinfo("Export Complete", f"Saved to:\n{path}")

    def _render_html(self):
        mode = self.view_var.get()
        title = self.title_var.get()
        team = self.team_var.get()
        team_text = "" if team == "All Teams" else f" – {team}"

        # Build sections by mode
        if mode == "Month":
            body = self._html_month()
        elif mode == "Week":
            body = self._html_week()
        else:
            body = self._html_day()

        css = """
        <style>
        body{font-family:Arial,sans-serif;margin:16px;}
        h1{font-size:20px;margin:0 0 12px;}
        .grid{display:grid;grid-template-columns:repeat(7,1fr);gap:6px;}
        .cell{border:1px solid #ddd;padding:6px;min-height:80px;}
        .hdr{font-weight:bold;background:#f7f7f7;text-align:center;padding:6px;border:1px solid #ddd;}
        .chip{border-radius:6px;padding:6px;margin:4px 0;color:#fff;}
        .time{font-size:12px;opacity:.9}
        table{border-collapse:collapse;width:100%;}
        th,td{border:1px solid #ddd;padding:6px;font-size:14px;}
        th{background:#f7f7f7;}
        </style>
        """
        return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{mode} Calendar</title>{css}</head>
<body>
<h1>{title}{team_text}</h1>
{body}
</body></html>"""

    def _chip_html(self, e):
        team = e.get("team","")
        opp = e.get("opponent","")
        etype = (e.get("type","") or "").lower()
        arena = e.get("arena","")
        time_slot = e.get("time_slot","")
        col = self._get_team_color(team)["bg"]
        title = team if not opp or opp == "Practice" else f"{team} vs {opp}"
        return f'<div class="chip" style="background:{col}"><div><b>{title}</b></div><div class="time">{time_slot}{" @ "+arena if arena else ""}</div></div>'

    def _html_month(self):
        y, m = self.current_date.year, self.current_date.month
        days = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
        cal = _cal.Calendar(firstweekday=0).monthdayscalendar(y, m)
        by_day = defaultdict(list)
        for e in self._filtered_events():
            if e["_date"].year == y and e["_date"].month == m:
                by_day[e["_date"].day].append(e)
        # Header
        html = '<div class="grid">'
        html += "".join(f'<div class="hdr">{d}</div>' for d in days)
        # Cells
        for week in cal:
            for day in week:
                if day == 0:
                    html += '<div class="cell"></div>'
                    continue
                chips = "".join(self._chip_html(e) for e in by_day.get(day, []))
                html += f'<div class="cell"><div><b>{day}</b></div>{chips}</div>'
        html += "</div>"
        return html

    def _html_week(self):
        monday = self.current_date - _dt.timedelta(days=self.current_date.weekday())
        dates = [monday + _dt.timedelta(days=i) for i in range(7)]
        by_date = defaultdict(list)
        for e in self._filtered_events():
            if monday <= e["_date"] <= dates[-1]:
                by_date[e["_date"]].append(e)
        # table
        header = "".join(f"<th>{d.strftime('%a %b %d')}</th>" for d in dates)
        rows = []
        # unique starts
        unique_times = sorted({e["_start"] for evts in by_date.values() for e in evts}) or [_dt.time(h,0) for h in range(6,22)]
        for t in unique_times:
            cells = []
            for d in dates:
                chips = "".join(self._chip_html(e) for e in by_date.get(d, []) if e["_start"] == t)
                cells.append(f"<td>{chips}</td>")
            rows.append(f"<tr><th>{t.strftime('%H:%M')}</th>{''.join(cells)}</tr>")
        return f"<table><tr><th>Time</th>{header}</tr>{''.join(rows)}</table>"

    def _html_day(self):
        d = self.current_date
        evts = [e for e in self._filtered_events() if e["_date"] == d]
        if not evts:
            return "<p>No events.</p>"
        rows = []
        for e in evts:
            chip = self._chip_html(e)
            rows.append(f"<tr><td>{e['_start'].strftime('%H:%M')}–{e['_end'].strftime('%H:%M')}</td><td>{chip}</td></tr>")
        return "<table>" + "<tr><th>Time</th><th>Event</th></tr>" + "".join(rows) + "</table>"