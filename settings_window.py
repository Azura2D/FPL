# settings_window.py

"""
This module defines the SettingsWindow class, a Toplevel window that allows
the user to configure application settings, such as which data columns to display
in the tables.
"""
import tkinter as tk
from tkinter import ttk
from tkinter import filedialog
import json

class SettingsWindow(tk.Toplevel):
    """
    A Toplevel window for managing application settings, specifically for
    selecting which columns to display in the player tables.
    It operates modally, grabbing focus until it is closed.
    This window allows for both visibility toggling and reordering of columns.
    """
    def __init__(self, parent, all_columns, current_settings, callback):
        print("[settings_window] Initializing settings window...")
        super().__init__(parent)
        self.title("Settings")
        self.geometry("750x550")
        self.transient(parent)  # Keep this window on top of its parent.
        self.grab_set()  # Make the window modal, blocking interaction with the parent.

        self.all_columns = sorted(list(all_columns))
        self.current_settings = current_settings
        # A callback function is used to send the new settings back to the main app,
        # decoupling the settings window from the main application's implementation.
        self.callback = callback

        self.setup_ui()

    def setup_ui(self):
        print("[settings_window] Setting up UI components...")
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)

        # --- Create a tab for each table type ---
        # A Notebook widget provides a clean, tabbed interface for different settings categories.
        undrafted_frame = self._create_column_selection_frame(notebook, "undrafted")
        team_frame = self._create_column_selection_frame(notebook, "team")

        notebook.add(undrafted_frame, text="Undrafted Players Columns")
        notebook.add(team_frame, text="Team View Columns")

        # --- Bottom Buttons ---
        button_frame = ttk.Frame(self)
        button_frame.pack(fill="x", padx=10, pady=(0, 10))

        save_btn = ttk.Button(button_frame, text="Save & Apply", command=self.save_and_apply)
        save_btn.pack(side="right", padx=5)

        load_preset_btn = ttk.Button(button_frame, text="Load Preset...", command=self._load_preset)
        load_preset_btn.pack(side="left", padx=5)

        save_preset_btn = ttk.Button(button_frame, text="Save Preset...", command=self._save_preset)
        save_preset_btn.pack(side="left", padx=5)

        cancel_btn = ttk.Button(button_frame, text="Cancel", command=self._on_cancel)
        cancel_btn.pack(side="right")
        print("[settings_window] UI setup complete.")

    def _on_cancel(self):
        print("[settings_window] 'Cancel' clicked. Closing window without saving.")
        self.destroy()

    def _create_column_selection_frame(self, parent, view_type):
        """Creates a dual-listbox frame for showing, hiding, and reordering columns."""
        container = ttk.Frame(parent, padding="10")

        # --- Data ---
        visible_cols = self.current_settings[f'{view_type}_cols']
        hidden_cols = sorted([c for c in self.all_columns if c not in visible_cols])

        # --- UI Components ---
        # Hidden columns on the left
        hidden_frame = ttk.LabelFrame(container, text="Hidden Columns")
        hidden_frame.pack(side="left", fill="both", expand=True, padx=5)
        hidden_lb = tk.Listbox(hidden_frame, selectmode="extended", exportselection=False)
        hidden_lb.pack(side="left", fill="both", expand=True)
        hidden_sb = ttk.Scrollbar(hidden_frame, orient="vertical", command=hidden_lb.yview)
        hidden_sb.pack(side="right", fill="y")
        hidden_lb.config(yscrollcommand=hidden_sb.set)
        for col in hidden_cols:
            hidden_lb.insert("end", col)

        # Action buttons in the middle
        action_frame = ttk.Frame(container)
        action_frame.pack(side="left", fill="y", padx=10)
        
        # Visible columns on the right
        visible_frame = ttk.LabelFrame(container, text="Visible Columns (Ordered)")
        visible_frame.pack(side="left", fill="both", expand=True, padx=5)
        visible_lb = tk.Listbox(visible_frame, selectmode="browse", exportselection=False)
        visible_lb.pack(side="left", fill="both", expand=True)
        visible_sb = ttk.Scrollbar(visible_frame, orient="vertical", command=visible_lb.yview)
        visible_sb.pack(side="right", fill="y")
        visible_lb.config(yscrollcommand=visible_sb.set)
        for col in visible_cols:
            visible_lb.insert("end", col)

        # Reordering buttons on the far right
        reorder_frame = ttk.Frame(container)
        reorder_frame.pack(side="left", fill="y", padx=10)

        # --- Button Functions ---
        def move_to_visible():
            print("[settings_window] Moving items to 'Visible'.")
            selections = hidden_lb.curselection()
            for i in reversed(selections):
                item = hidden_lb.get(i)
                visible_lb.insert("end", item)
                hidden_lb.delete(i)

        def move_to_hidden():
            print("[settings_window] Moving items to 'Hidden'.")
            selections = visible_lb.curselection()
            for i in reversed(selections):
                item = visible_lb.get(i)
                hidden_lb.insert("end", item)
                visible_lb.delete(i)
            # Keep hidden list sorted for usability
            sorted_items = sorted(hidden_lb.get(0, "end"))
            hidden_lb.delete(0, "end")
            for item in sorted_items:
                hidden_lb.insert("end", item)

        def move_up():
            print("[settings_window] Moving item up.")
            selections = visible_lb.curselection()
            if not selections: return
            pos = selections[0]
            if pos == 0: return
            item = visible_lb.get(pos)
            visible_lb.delete(pos)
            visible_lb.insert(pos - 1, item)
            visible_lb.selection_set(pos - 1)

        def move_down():
            print("[settings_window] Moving item down.")
            selections = visible_lb.curselection()
            if not selections: return
            pos = selections[0]
            if pos == visible_lb.size() - 1: return
            item = visible_lb.get(pos)
            visible_lb.delete(pos)
            visible_lb.insert(pos + 1, item)
            visible_lb.selection_set(pos + 1)

        # --- Populate Action/Reorder Frames ---
        ttk.Button(action_frame, text=">>", command=move_to_visible).pack(pady=5)
        ttk.Button(action_frame, text="<<", command=move_to_hidden).pack(pady=5)

        ttk.Button(reorder_frame, text="Move Up", command=move_up).pack(pady=5)
        ttk.Button(reorder_frame, text="Move Down", command=move_down).pack(pady=5)

        # Store listboxes for data retrieval on save
        setattr(self, f"{view_type}_visible_lb", visible_lb)
        setattr(self, f"{view_type}_hidden_lb", hidden_lb)

        return container

    def _get_current_listbox_config(self):
        """Helper function to get the current column configuration from the listboxes."""
        undrafted_visible_lb = getattr(self, "undrafted_visible_lb")
        team_visible_lb = getattr(self, "team_visible_lb")
        return {
            'undrafted_cols': list(undrafted_visible_lb.get(0, "end")),
            'team_cols': list(team_visible_lb.get(0, "end")),
        }

    def _save_preset(self):
        """Saves the current column configuration to a user-selected JSON file."""
        print("[settings_window] Opening 'Save Preset' dialog...")
        filepath = filedialog.asksaveasfilename(
            title="Save Settings Preset",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if not filepath:
            print("[settings_window] Save preset cancelled.")
            return

        config = self._get_current_listbox_config()
        try:
            with open(filepath, 'w') as f:
                json.dump(config, f, indent=4)
            print(f"[settings_window] Preset saved to {filepath}")
        except IOError as e:
            print(f"[settings_window] ERROR: Could not save preset. {e}")

    def _load_preset(self):
        """Loads a column configuration from a user-selected JSON file and updates the UI."""
        print("[settings_window] Opening 'Load Preset' dialog...")
        filepath = filedialog.askopenfilename(
            title="Load Settings Preset",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if not filepath:
            print("[settings_window] Load preset cancelled.")
            return
        
        try:
            with open(filepath, 'r') as f:
                new_settings = json.load(f)
            # Re-initialize the entire window with the new settings to refresh the UI
            self.destroy()
            SettingsWindow(self.master, self.all_columns, new_settings, self.callback)
        except (IOError, json.JSONDecodeError, KeyError) as e:
            print(f"[settings_window] ERROR: Could not load or parse preset file. {e}")

    def save_and_apply(self):
        """
        Gathers the state of all checkboxes, constructs a new settings dictionary,
        and passes it to the callback function provided during initialization.
        """
        print("[settings_window] 'Save & Apply' clicked. Processing new settings...")
        
        new_settings = self._get_current_listbox_config()

        if self.callback:
            self.callback(new_settings)
            print("[settings_window] Callback executed. Closing window.")

        self.destroy()
