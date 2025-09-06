# main_app.py

import tkinter as tk
from tkinter import messagebox, ttk
import traceback
import pandas as pd
import json
import time

# Make sure these files are in the same directory
from data_fetcher import fetch_fpl_data
from table_widget import SortableTable, TransposedTable
from settings_window import SettingsWindow
from saved_tables_browser import SavedTablesBrowser, prompt_save_table_details, SAVED_TABLES_FILE

class FPLApp:
    """
    The main application class for the FPL Draft Analyzer. This class is responsible
    for orchestrating the UI, managing application state (like loaded data and settings),
    and handling user interactions.
    """
    def __init__(self, root):
        print("[main_app] Initializing FPLApp...")
        self.root = root
        self.root.title("FPL Draft Analyzer")
        self.root.geometry("1200x700")

        self.settings_file = "settings.json"
        self.players_df = None
        self.teams_tables = None  # A dictionary mapping team names to their player DataFrames.
        self.undrafted_table = None
        self.current_team_name = None  # Tracks the currently selected view (e.g., 'Undrafted Players').
        self.all_available_columns = set()  # Populated after data load to power the settings window.
        self.open_saved_windows = [] # Holds records of open saved table windows for live updates.

        # Default settings are defined here. They are used as a fallback if the settings file
        # is missing or corrupt, and to create the initial settings file.
        self.default_settings = {
            "undrafted_cols": [
                'web_name', 'position', 'team_name', 'news', 'form', 
                'cumulative_total_points', 'total_points', 'goals_scored', 'assists', 
                'clean_sheets', 'bonus', 'bps', 'ict_index', 'influence', 
                'creativity', 'threat', 'now_cost'
            ],
            "team_cols": [
                'web_name', 'position', 'team_name', 'news', 'form', 
                'cumulative_total_points', 'total_points', 'goals_scored', 'assists', 
                'clean_sheets', 'bonus', 'bps', 'ict_index', 'influence', 
                'creativity', 'threat', 'now_cost', 'first_name', 'second_name'
            ]
        }
        self.settings = {}  # This will be populated by _load_settings.

        self._load_settings()
        self.setup_ui()

    def _load_settings(self):
        """
        Loads settings from the JSON file. If the file doesn't exist or is invalid,
        it falls back to default settings and creates a new file.
        """
        try:
            print(f"[main_app] Loading settings from '{self.settings_file}'...")
            with open(self.settings_file, 'r') as f:
                self.settings = json.load(f)
            # Basic validation: ensure the loaded settings have the expected keys.
            if "undrafted_cols" not in self.settings or "team_cols" not in self.settings:
                raise ValueError("Settings file is missing required keys.")
            print("[main_app] Settings loaded successfully.")
        except (FileNotFoundError, json.JSONDecodeError, ValueError) as e:
            print(f"[main_app] Info: Could not load settings file ({e}). Using and saving default settings.")
            self.settings = self.default_settings.copy()
            self._save_settings()

    def _save_settings(self):
        """Saves the current self.settings dictionary to the JSON file."""
        try:
            print(f"[main_app] Saving settings to '{self.settings_file}'...")
            with open(self.settings_file, 'w') as f:
                json.dump(self.settings, f, indent=4)
        except IOError as e:
            print(f"Error: Could not save settings to {self.settings_file}. Error: {e}")
            messagebox.showerror(
                "Save Error",
                f"Could not save settings to {self.settings_file}.\n\n"
                "Please check file permissions."
            )
        print("[main_app] Settings saved successfully.")

    def _apply_settings(self, new_settings):
        """
        Callback function passed to the SettingsWindow. It receives the new settings,
        updates the main application's state, saves them to file, and triggers a view refresh.
        """
        self.settings = new_settings
        print("[main_app] Applying new settings...")
        self._save_settings()  # Persist the new settings to the file.
        self._update_open_saved_windows() # Update any open saved windows with live settings
        self.status_label.config(text="Settings applied and saved.", foreground="blue")
        self._refresh_current_view()

    def setup_ui(self):
        """
        Initializes and packs all the UI components for the main window.
        This includes the top control bar and the main paned view.
        """
        # --- Top Controls Frame ---
        print("[main_app] Setting up UI...")
        top_frame = ttk.Frame(self.root, padding="10")
        top_frame.pack(side="top", fill="x")

        ttk.Label(top_frame, text="Enter League ID:").pack(side="left", padx=(0, 5))
        self.league_id_entry = ttk.Entry(top_frame)
        self.league_id_entry.insert(0, "140951")
        self.league_id_entry.pack(side="left", padx=5)

        self.load_btn = ttk.Button(top_frame, text="Load League", command=self.load_fpl_data)
        self.load_btn.pack(side="left", padx=5)

        self.refresh_btn = ttk.Button(top_frame, text="Refresh Data", command=lambda: self.load_fpl_data(force_refresh=True))
        self.refresh_btn.pack(side="left", padx=5)
        self.refresh_btn.config(state="disabled")  # Disabled until data is loaded

        self.status_label = ttk.Label(top_frame, text="")
        self.status_label.pack(side="left", padx=10)

        ttk.Button(top_frame, text="Settings", command=self._open_settings_window).pack(side="right", padx=5)

        ttk.Button(top_frame, text="Saved Tables", command=self._open_saved_tables_browser).pack(side="right", padx=5)

        # --- Main Content Area (Paned Window) ---
        # A PanedWindow provides a user-resizable divider between the team list and the data table.
        self.paned_window = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.paned_window.pack(fill="both", expand=True, padx=10, pady=10)

        # Left Pane: Hierarchical list of teams.
        self.team_list_frame = ttk.Frame(self.paned_window, padding=5)
        self.paned_window.add(self.team_list_frame, weight=1)
        
        self.team_tree = ttk.Treeview(self.team_list_frame, show="tree", selectmode="browse")
        self.team_tree.pack(fill="both", expand=True)
        self.team_tree.bind("<<TreeviewSelect>>", self._on_team_select)  # Event binding for selection.

        # Right Pane: Displays the selected team or player table.
        self.table_display_frame = ttk.Frame(self.paned_window, padding=5)
        self.paned_window.add(self.table_display_frame, weight=5)
        self.table_widget = None  # Placeholder for the current table widget.
        self.window_button = None  # Placeholder for the "Open in New Window" button.
        print("[main_app] UI setup complete.")

    def load_fpl_data(self, force_refresh=False):
        """
        Handles the entire data loading process. It calls the data_fetcher,
        updates the application state with the returned DataFrames, and then
        triggers UI updates.
        
        Args:
            force_refresh (bool): If True, bypasses the cache in the data_fetcher.
        """
        print(f"[main_app] Starting data load for league '{self.league_id_entry.get()}' (force_refresh={force_refresh})...")
        league_id_str = self.league_id_entry.get()
        action = "Refreshing" if force_refresh else "Loading"
        self.status_label.config(text=f"{action}...", foreground="orange")
        self.root.update_idletasks()  # Force the UI to update the status label immediately.

        try:
            # The main data fetching call.
            league_id = int(league_id_str)
            self.players_df, self.teams_tables, self.undrafted_table = fetch_fpl_data(league_id, force_refresh=force_refresh)
            
            if self.players_df is None:
                messagebox.showerror("Error", "Failed to load FPL data.")
                self.status_label.config(text="Failed to load data.", foreground="red")
                print("[main_app] Data load failed.")
                self.refresh_btn.config(state="disabled")
            else:
                self.status_label.config(text="Data loaded successfully!", foreground="green")
                self.refresh_btn.config(state="normal")
                # Store all possible columns to populate the settings window.
                self.all_available_columns = set(self.players_df.columns)
                print("[main_app] Data load successful.")
                # Only repopulate the team list on the initial load, not on refresh.
                if not force_refresh:
                    self._populate_team_list()
                self._update_open_saved_windows() # Update any open saved windows with live data
                self._refresh_current_view()  # Refresh the current table with new data.

        except ValueError:
            messagebox.showerror("Invalid Input", "Please enter a valid number for the league ID.")
            self.status_label.config(text="Invalid League ID.", foreground="red")
        except Exception as e:
            # A global exception handler to catch any unexpected errors during data fetching
            # or processing. It prints a full traceback to the console for easier debugging.
            traceback_str = traceback.format_exc()
            print("--- AN UNEXPECTED ERROR OCCURRED ---")
            print(traceback_str)
            print("------------------------------------")
            messagebox.showerror("Error", f"An unexpected error occurred: {e}\n\nSee console for detailed traceback.")
            self.status_label.config(text="An error occurred.", foreground="red")

    def _open_settings_window(self):
        """
        Creates and displays the settings window. It passes the available columns,
        current settings, and a callback function for applying the changes.
        """
        print("[main_app] Opening settings window...")
        if not self.all_available_columns:
            messagebox.showinfo("Info", "Please load league data first to see available columns.")
            return
        SettingsWindow(self.root, self.all_available_columns, self.settings, self._apply_settings)

    def _open_saved_tables_browser(self):
        """Opens the browser for saved tables."""
        print("[main_app] Opening saved tables browser...")
        SavedTablesBrowser(self.root, self.open_saved_table)

    def _update_open_saved_windows(self):
        """Iterates through open saved windows and updates them based on their configuration."""
        print(f"[main_app] Updating {len(self.open_saved_windows)} open saved windows...")
        if not self.open_saved_windows:
            return

        print("[main_app] --- Begin updating open saved windows ---")
        for record in self.open_saved_windows:
            print(f"[main_app]   Updating window for table ID: {record['id']}")
            # Determine the correct data source for this window
            data_source = None
            if record['live_data']:
                print("[main_app]     - Using LIVE data.")
                if record['view_id'] == 'undrafted':
                    data_source = self.undrafted_table
                    print("[main_app]     - Data source: undrafted_table")
                elif record['view_id'] in self.teams_tables:
                    data_source = self.teams_tables[record['view_id']]
                    print(f"[main_app]     - Data source: teams_tables['{record['view_id']}']")
            else:
                data_source = record['frozen_data']
                print("[main_app]     - Using FROZEN data.")

            if data_source is None:
                print("[main_app]     - WARNING: Data source is None, skipping update for this window.")
                continue # Skip if data source is not available

            # Determine the correct settings source for this window
            settings_source = self.settings if record['live_settings'] else record['frozen_settings']
            print(f"[main_app]     - Using {'LIVE' if record['live_settings'] else 'FROZEN'} settings.")
            
            # Get the correct list of columns based on the view type
            cols_key = 'undrafted_cols' if record['view_id'] == 'undrafted' else 'team_cols'
            display_cols = settings_source[cols_key]

            # Construct the final DataFrame to display
            ordered_visible_cols = [col for col in display_cols if col in data_source.columns]
            
            # The table widget itself handles the display logic (transposed vs. normal)
            table_widget = record['table_widget']
            table_class = type(table_widget)

            if table_class == SortableTable:
                final_df = data_source[ordered_visible_cols].head(100)
                print(f"[main_app]     - Updating SortableTable with DataFrame of shape {final_df.shape}")
                table_widget.update_data(final_df)
            elif table_class == TransposedTable:
                if 'web_name' not in ordered_visible_cols:
                    # This case is tricky for a live-updating window. For now, we just show an empty table.
                    # A more advanced solution would be to change the table type.
                    table_widget.update_data(pd.DataFrame())
                else:
                    squad_df = data_source[ordered_visible_cols]
                    transposed_df = squad_df.set_index('web_name').transpose()
                    print(f"[main_app]     - Updating TransposedTable with DataFrame of shape {transposed_df.shape}")
                    table_widget.update_data(transposed_df)
        print("[main_app] --- Finished updating open saved windows ---")

    def open_saved_table(self, table_id):
        """Opens a new window for a table specified by its ID from the saved tables file."""
        print(f"[main_app] Opening saved table with ID: {table_id}")
        try:
            with open(SAVED_TABLES_FILE, 'r') as f:
                all_saved_data = json.load(f)
            
            table_config = next((t for t in all_saved_data['tables'] if t['id'] == table_id), None)
            if not table_config:
                messagebox.showerror("Error", "Could not find the selected table. It may have been deleted.")
                print(f"[main_app] ERROR: Could not find table config for ID {table_id}")
                return

            # Create the window and table widget
            win = tk.Toplevel(self.root)
            win.title(f"[SAVED] {table_config['name']}")
            win.geometry("800x400")

            # Determine initial dataframe
            if table_config['frozen_data']:
                print("[main_app]   - Loading DataFrame from frozen_data in config.")
                df = pd.read_json(table_config['frozen_data'], orient='split')
            elif table_config['view_id'] == 'undrafted':
                print("[main_app]   - Loading DataFrame from live undrafted_table.")
                df = self.undrafted_table
            else:
                print(f"[main_app]   - Loading DataFrame from live teams_tables for view_id: {table_config['view_id']}")
                df = self.teams_tables.get(table_config['view_id'], pd.DataFrame())

            if df is None:
                print("[main_app]   - WARNING: DataFrame for saved table is None. Using empty DataFrame.")
                df = pd.DataFrame()

            table_class = SortableTable if table_config['table_class'] == 'SortableTable' else TransposedTable
            print(f"[main_app]   - Instantiating table of type: {table_class.__name__}")
            # The table is created directly in the window and packed to fill all available space.
            table_widget = table_class(win, df, auto_resize=True)
            table_widget.pack(fill="both", expand=True, padx=10, pady=10)

            # Create a record for live updates
            live_record = {
                "id": table_id,
                "window": win,
                "table_widget": table_widget,
                "view_id": table_config['view_id'],
                "live_data": table_config['live_data'],
                "live_settings": table_config['live_settings'],
                "frozen_data": pd.read_json(table_config['frozen_data'], orient='split') if table_config['frozen_data'] else None,
                "frozen_settings": table_config['frozen_settings']
            }
            self.open_saved_windows.append(live_record)
            win.protocol("WM_DELETE_WINDOW", lambda w=win, tid=table_id: self._on_saved_window_close(tid, w))
            self._update_open_saved_windows() # Perform an initial update
            print(f"[main_app] Successfully opened and registered saved table '{table_config['name']}'.")
        except Exception as e:
            print(f"[main_app] ERROR: An exception occurred in open_saved_table: {e}\n{traceback.format_exc()}")
            messagebox.showerror("Error", f"Failed to open saved table: {e}")

    def _refresh_current_view(self):
        """Redraws the currently selected table with current data and settings."""
        # This is called after applying settings or refreshing data to ensure the view is up-to-date.
        print("[main_app] Refreshing current view...")
        if not self.current_team_name:
            return  # Nothing to refresh if no view has been selected yet.
        
        selected_iid = self.team_tree.selection()
        if not selected_iid:
            return
            
        # Re-trigger the selection event handler to redraw the table.
        # Passing `None` for the event object is sufficient as it's not used in the handler.
        self._on_team_select(None)

    def _populate_team_list(self):
        """
        Clears and fills the team list Treeview in the left pane.
        This method builds the hierarchical structure with "Undrafted Players"
        and a "Drafted Teams" category.
        """
        print("[main_app] Populating team list...")
        for item in self.team_tree.get_children():
            self.team_tree.delete(item)

        if self.table_widget:
            self.table_widget.destroy()
            self.table_widget = None

        # Add the Undrafted Players option first
        self.team_tree.insert("", "end", text="Undrafted Players", iid="undrafted", open=True)
        
        # Add the drafted teams
        drafted_teams_node = self.team_tree.insert("", "end", text="Drafted Teams", iid="drafted_teams", open=True)
        if self.teams_tables:
            for team_name in sorted(self.teams_tables.keys()):
                self.team_tree.insert(drafted_teams_node, "end", text=team_name, iid=team_name)

    def _on_team_select(self, event):
        """
        Event handler for when a user selects an item in the team list Treeview.
        It determines which table to display, fetches the corresponding DataFrame,
        and creates the appropriate table widget (`SortableTable` or `TransposedTable`).
        """
        if not self.team_tree.selection():  # This can happen during a refresh.
            return
            
        print(f"[main_app] Team selection event triggered.")
        selected_iid = self.team_tree.selection()[0]

        if selected_iid in ("drafted_teams",):  # Ignore clicks on the non-selectable category header.
            return  

        # Clear the previous table widget if it exists
        if self.table_widget:
            self.table_widget.destroy()
        if self.window_button:
            self.window_button.destroy()
        
        try:
            # Logic to decide which DataFrame and table type to use.
            print(f"[main_app] Displaying table for '{selected_iid}'.")
            if selected_iid == "undrafted":
                self.current_team_name = "Undrafted Players"
                df = self.undrafted_table
                display_cols = self.settings['undrafted_cols']
                
                # Use the ordered list of columns from settings.
                # Only include columns that actually exist in the DataFrame to prevent errors.
                ordered_visible_cols = [col for col in display_cols if col in df.columns]
                display_df = df[ordered_visible_cols].head(100)
                self.table_widget = SortableTable(self.table_display_frame, display_df)
            else:
                self.current_team_name = selected_iid
                df = self.teams_tables[selected_iid]
                display_cols = self.settings['team_cols']
                
                ordered_visible_cols = [col for col in display_cols if col in df.columns]
                squad_df = df[ordered_visible_cols]
                
                # The transposed view requires 'web_name' as an index.
                if 'web_name' not in squad_df.columns:
                    # If the user has disabled 'web_name' in settings, fall back to a standard table.
                    messagebox.showwarning("Warning", "'web_name' must be selected in Settings for the Team View. Showing standard table.")
                    self.table_widget = SortableTable(self.table_display_frame, squad_df)
                else:
                    transposed_df = squad_df.set_index('web_name').transpose()
                    self.table_widget = TransposedTable(self.table_display_frame, transposed_df)
            
            self.table_widget.pack(fill="both", expand=True)
            
            # Add the "Open in New Window" button below the newly created table.
            self.window_button = ttk.Button(
                self.table_display_frame,
                text="Open in New Window",
                command=self._window_current_table
            )
            self.window_button.pack(side="bottom", pady=5)

        except Exception as e:
            # If any error occurs, show it to the user in a popup.
            error_message = f"Failed to display table for '{self.current_team_name}'.\n\nError: {e}"
            print(error_message) # Also print to console for debugging
            messagebox.showerror("Display Error", error_message)

    def _window_current_table(self):
        """
        Creates a new Toplevel window containing a "frozen" snapshot of the currently
        displayed table. This allows for side-by-side comparisons.
        """
        print(f"[main_app] Creating new window for frozen table view: '{self.current_team_name}'.")
        if not self.table_widget:
            return

        new_win = tk.Toplevel(self.root)
        new_win.title(f"Frozen View: {self.current_team_name}")
        new_win.geometry("800x400")

        # Create a container for the button and the table
        container = ttk.Frame(new_win)
        container.pack(fill="both", expand=True, padx=10, pady=10)
        new_win.bind("<Destroy>", lambda e, w=new_win: self._on_temp_window_close(w))

        # Create a new table instance with a deep copy of the current dataframe.
        df_copy = self.table_widget.dataframe.copy()
        table_class = type(self.table_widget)
        
        # The table is created directly in the container frame and packed to fill all space.
        new_table = table_class(container, df_copy, auto_resize=True)
        new_table.pack(fill="both", expand=True)

        # Add a "Save Table" button to the new window
        save_button = ttk.Button(
            container,
            text="Save this Table...",
            command=lambda: self._save_table(
                self.current_team_name, self.table_widget.dataframe, table_class, save_button
            )
        )
        save_button.pack(side="bottom", pady=5)

    def _on_temp_window_close(self, window):
        """Ensures temporary windows are tracked and cleaned up if necessary."""
        print(f"[main_app] Temporary window {window} closed.")

    def _on_saved_window_close(self, table_id, window):
        """Removes a closed saved window from the live update list."""
        print(f"[main_app] Saved window close event for table ID: {table_id}")
        print(f"[main_app] Saved window for table ID {table_id} closed. Removing from live updates.")
        self.open_saved_windows = [w for w in self.open_saved_windows if w['id'] != table_id]
        print(f"[main_app] Destroying window: {window}")
        window.destroy()

    def _save_table(self, view_id, df_to_save, table_class, save_button):
        """Handles the process of saving a table configuration to file."""
        print(f"[main_app] Prompting to save table for view: {view_id}")
        
        print("[main_app]   - Reading existing saved tables file...")
        try:
            with open(SAVED_TABLES_FILE, 'r') as f:
                saved_data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            print("[main_app]   - Saved tables file not found or invalid. Starting with a new structure.")
            saved_data = {"folders": [], "tables": []}

        details = prompt_save_table_details(self.root, saved_data.get('folders', []))
        if not details:
            print("[main_app] Table save cancelled by user.")
            return

        print(f"[main_app]   - Creating new record for table: '{details['name']}'")
        # Create the record to be saved to the JSON file
        new_record = {
            "id": f"{time.time():.2f}", # Unique ID based on timestamp
            "name": details['name'],
            "folder": details['folder'],
            "view_id": view_id,
            "table_class": table_class.__name__,
            "live_data": details['live_data'],
            "live_settings": details['live_settings'],
            "frozen_data": df_to_save.to_json(orient='split') if not details['live_data'] else None,
            "frozen_settings": self.settings.copy() if not details['live_settings'] else None,
        }
        saved_data['tables'].append(new_record)
        if details['folder'] and details['folder'] not in saved_data['folders']:
            saved_data['folders'].append(details['folder'])

        print("[main_app]   - Writing new data to saved_tables.json...")
        with open(SAVED_TABLES_FILE, 'w') as f:
            json.dump(saved_data, f, indent=4)
        
        print(f"[main_app] Table '{details['name']}' saved successfully.")
        save_button.config(text="Saved", state="disabled")

if __name__ == "__main__":
    print("[main_app] Application starting...")
    root = tk.Tk()
    app = FPLApp(root)
    root.mainloop()
