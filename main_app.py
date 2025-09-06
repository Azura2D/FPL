# main_app.py

import tkinter as tk
from tkinter import messagebox, ttk
import traceback
import pandas as pd
import json

from data_fetcher import fetch_fpl_data
from table_widget import SortableTable, TransposedTable
from settings_window import SettingsWindow

class FPLApp:
    def __init__(self, root):
        self.root = root
        self.root.title("FPL Draft Analyzer")
        self.root.geometry("1200x900")

        self.settings_file = "settings.json"
        self.players_df, self.teams_tables, self.undrafted_table = None, None, None
        self.all_available_columns = set()

        self.default_settings = {
            "undrafted_cols": [
                'web_name', 'position', 'team_name', 'total_points', 'form', 'points_per_game', 
                'Expected Points Next', 'Points Prev GW', 'Expected Points Prev GW', 'EP Diff', 'Rank', 
                'Avg Difficulty', 'news'
            ],
            "team_cols": [
                'web_name', 'position', 'team_name', 'total_points', 'form', 'points_per_game',
                'Expected Points Next', 'Points Prev GW', 'Expected Points Prev GW', 'EP Diff', 'Rank', 
                'Avg Difficulty', 'news'
            ]
        }
        self.settings = {}
        self._load_settings()
        self.setup_ui()

    def _load_settings(self):
        try:
            with open(self.settings_file, 'r') as f: self.settings = json.load(f)
            settings_updated = False
            for view_type in ['undrafted_cols', 'team_cols']:
                if view_type not in self.settings:
                    self.settings[view_type] = self.default_settings[view_type]; settings_updated = True
                for col in self.default_settings[view_type]:
                    if col not in self.settings[view_type]:
                        self.settings[view_type].append(col); settings_updated = True
            if settings_updated: self._save_settings()
        except (FileNotFoundError, json.JSONDecodeError):
            self.settings = self.default_settings.copy(); self._save_settings()

    def _save_settings(self):
        try:
            with open(self.settings_file, 'w') as f: json.dump(self.settings, f, indent=4)
        except IOError as e: messagebox.showerror("Save Error", f"Could not save settings: {e}")

    def _apply_settings(self, new_settings):
        self.settings = new_settings; self._save_settings()
        self.status_label.config(text="Settings applied.", foreground="blue")
        self._refresh_current_view()

    def setup_ui(self):
        top_frame = ttk.Frame(self.root, padding="10")
        top_frame.pack(side="top", fill="x")

        ttk.Label(top_frame, text="Enter League ID:").pack(side="left")
        self.league_id_entry = ttk.Entry(top_frame, width=10); self.league_id_entry.pack(side="left", padx=5)
        self.league_id_entry.insert(0, "140951")

        ttk.Button(top_frame, text="Load League", command=self.load_fpl_data).pack(side="left", padx=5)
        self.refresh_btn = ttk.Button(top_frame, text="Refresh Data", command=lambda: self.load_fpl_data(True))
        self.refresh_btn.pack(side="left", padx=5); self.refresh_btn.config(state="disabled")

        self.status_label = ttk.Label(top_frame, text=""); self.status_label.pack(side="left", padx=10, expand=True, fill="x")
        ttk.Button(top_frame, text="Settings", command=self._open_settings_window).pack(side="right", padx=5)

        ttk.Separator(self.root, orient='horizontal').pack(fill='x', padx=10, pady=5)

        self.paned_window = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.paned_window.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        team_list_frame = ttk.Frame(self.paned_window); self.paned_window.add(team_list_frame, weight=1)
        self.team_tree = ttk.Treeview(team_list_frame, show="tree", selectmode="browse")
        self.team_tree.pack(fill="both", expand=True); self.team_tree.bind("<<TreeviewSelect>>", self._on_team_select)

        self.right_pane = ttk.Frame(self.paned_window); self.paned_window.add(self.right_pane, weight=4)
        self.table_display_frame = ttk.Frame(self.right_pane); self.table_display_frame.pack(fill="both", expand=True)
        
        self.analyzer_frame = ttk.LabelFrame(self.right_pane, text="Team Analyzer", padding="10")
        self.analyzer_text = tk.Text(self.analyzer_frame, height=10, wrap="word", relief="flat", state="disabled", font=("Segoe UI", 9), background=self.root.cget('bg'))
        self.analyzer_text.pack(fill="both", expand=True)
        self.table_widget = None

    def load_fpl_data(self, force_refresh=False):
        self.status_label.config(text="Loading...", foreground="orange"); self.root.update_idletasks()
        try:
            league_id = int(self.league_id_entry.get())
            result = fetch_fpl_data(league_id, force_refresh)
            if result and result[0] is not None:
                self.players_df, self.teams_tables, self.undrafted_table = result
                self.status_label.config(text="Data loaded successfully!", foreground="green")
                self.refresh_btn.config(state="normal")
                self.all_available_columns = set(self.players_df.columns)
                if not force_refresh: self._populate_team_list()
                self._refresh_current_view()
            else: messagebox.showerror("Error", "Failed to load FPL data."); self.status_label.config(text="Failed to load data.", foreground="red")
        except (ValueError, Exception) as e:
            traceback.print_exc(); self.status_label.config(text="An error occurred.", foreground="red"); messagebox.showerror("Error", f"An error occurred: {e}")

    def _populate_team_list(self):
        self.team_tree.delete(*self.team_tree.get_children())
        if self.table_widget: self.table_widget.destroy(); self.table_widget = None
        self.team_tree.insert("", "end", text="Undrafted Players", iid="undrafted", open=True)
        drafted_node = self.team_tree.insert("", "end", text="Drafted Teams", iid="drafted_teams", open=True)
        if self.teams_tables:
            for team_name in sorted(self.teams_tables.keys()): self.team_tree.insert(drafted_node, "end", text=team_name, iid=team_name)

    def _on_team_select(self, event):
        if not self.team_tree.selection(): return
        selected_iid = self.team_tree.selection()[0]
        if selected_iid == "drafted_teams": return
        if self.table_widget: self.table_widget.destroy()
        
        # Display table first, then analyzer feedback
        try:
            if selected_iid == "undrafted":
                self.analyzer_frame.pack_forget()
                df, cols_key = self.undrafted_table, 'undrafted_cols'
                cols = [c for c in self.settings[cols_key] if c in df.columns]
                self.table_widget = SortableTable(self.table_display_frame, df[cols].head(100))
            else:
                self.analyzer_frame.pack(fill="x", pady=(10,0))
                df, cols_key = self.teams_tables[selected_iid], 'team_cols'
                cols = [c for c in self.settings[cols_key] if c in df.columns]
                self.table_widget = TransposedTable(self.table_display_frame, df[cols].set_index('web_name').transpose()) if 'web_name' in cols else SortableTable(self.table_display_frame, df[cols])
            
            self.table_widget.pack(fill="both", expand=True)
            # Now generate feedback, which is less critical than drawing the table
            if selected_iid != "undrafted":
                self._generate_team_feedback(selected_iid, self.teams_tables[selected_iid])

        except Exception as e:
            traceback.print_exc(); messagebox.showerror("Display Error", f"Error: {e}")

    def _generate_team_feedback(self, team_name, team_df):
        feedback = []
        if self.players_df is None: return

        # --- Fixture Analysis ---
        if 'Avg Difficulty' in self.players_df.columns:
            good_fixtures_pool = self.players_df[self.players_df['owner'] != team_name]
            if not good_fixtures_pool.empty:
                good_target = good_fixtures_pool.sort_values('Avg Difficulty', ascending=True).iloc[0]
                owner = good_target['owner'] or 'Undrafted'
                feedback.append(f"📈 **Fixture Target**: **{good_target['web_name']}** ({owner}) has the best upcoming fixtures (Avg Diff: {good_target['Avg Difficulty']:.1f}).")
            if not team_df.empty:
                bad_target = team_df.sort_values('Avg Difficulty', ascending=False).iloc[0]
                feedback.append(f"📉 **Fixture Risk**: {bad_target['web_name']} has the toughest upcoming schedule on your team (Avg Diff: {bad_target['Avg Difficulty']:.1f}).")

        # --- Injury Analysis ---
        injured = team_df[team_df['news'].str.contains('suspended|%|doubtful|out', na=False, case=False) & (team_df['news'] != '')]
        for _, player in injured.iterrows():
            waiver, trade = self._find_best_replacements(player['position'], team_name)
            msg = f"❗️ **INJURY**: {player['web_name']} ({player['news']}).\n"
            # --- FIXED: Check if object is not None ---
            if waiver is not None: msg += f"   ➡️ **Waiver**: Pick up **{waiver['web_name']}** (Points: {waiver['total_points']}).\n"
            if trade is not None: msg += f"   🎯 **Trade**: Target **{trade['web_name']}** (Owned by: {trade['owner']})."
            feedback.append(msg)
        
        self._display_feedback(feedback)

    def _find_best_replacements(self, position, current_team_name):
        undrafted = self.undrafted_table[self.undrafted_table['position'] == position]
        best_waiver = undrafted.loc[undrafted['total_points'].idxmax()] if not undrafted.empty else None
        others = self.players_df[(self.players_df['position'] == position) & (self.players_df['owner'].notna()) & (self.players_df['owner'] != current_team_name)]
        best_trade = others.loc[others['total_points'].idxmax()] if not others.empty else None
        return best_waiver, best_trade

    def _display_feedback(self, feedback):
        self.analyzer_text.config(state="normal")
        self.analyzer_text.delete("1.0", tk.END)
        if feedback:
            self.analyzer_text.tag_configure("bold", font=("Segoe UI", 9, "bold"))
            for i, line in enumerate(feedback):
                if i > 0: self.analyzer_text.insert(tk.END, "\n\n")
                parts = line.split('**')
                for j, part in enumerate(parts):
                    self.analyzer_text.insert(tk.END, part, "bold" if j % 2 == 1 else "normal")
        else:
            self.analyzer_text.insert("1.0", "✅ Team looks solid! No immediate concerns found.")
        self.analyzer_text.config(state="disabled")

    def _refresh_current_view(self):
        if self.team_tree.selection(): self._on_team_select(None)
    
    def _open_settings_window(self):
        if self.all_available_columns: SettingsWindow(self.root, self.all_available_columns, self.settings, self._apply_settings)
        else: messagebox.showinfo("Info", "Please load league data first.")

if __name__ == "__main__":
    root = tk.Tk()
    app = FPLApp(root)
    root.mainloop()