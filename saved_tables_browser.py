# saved_tables_browser.py

"""
This module defines the SavedTablesBrowser, a Toplevel window for managing
persistently saved tables, organized into folders.
"""
import tkinter as tk
from tkinter import ttk, simpledialog, messagebox
import json
import os

SAVED_TABLES_FILE = "saved_tables.json"

class SavedTablesBrowser(tk.Toplevel):
    """
    A browser window to open, create, and delete saved tables and folders.
    It interacts with a `saved_tables.json` file to persist the data.
    """
    def __init__(self, parent, open_table_callback):
        print("[browser] Initializing Saved Tables Browser...")
        super().__init__(parent)
        self.title("Saved Tables")
        self.geometry("500x600")
        self.transient(parent)
        self.grab_set()

        self.open_table_callback = open_table_callback
        self.data = self._get_default_data_structure()

        self.setup_ui()
        self.load_and_display_data()

    def _get_default_data_structure(self):
        """Returns the default dictionary structure for the JSON file."""
        return {"folders": [], "tables": []}

    def load_and_display_data(self):
        """Loads data from the JSON file and populates the Treeview."""
        print(f"[browser] Loading data from {SAVED_TABLES_FILE}")
        try:
            if os.path.exists(SAVED_TABLES_FILE):
                with open(SAVED_TABLES_FILE, 'r') as f:
                    self.data = json.load(f)
            else:
                # If file doesn't exist, create it with default structure
                self.save_data()
        except (IOError, json.JSONDecodeError) as e:
            print(f"[browser] ERROR: Could not load or parse {SAVED_TABLES_FILE}. Using default. Error: {e}")
            self.data = self._get_default_data_structure()

        # Clear existing tree
        for item in self.tree.get_children():
            self.tree.delete(item)

        # Populate tree
        for folder_name in sorted(self.data['folders']):
            self.tree.insert("", "end", iid=folder_name, text=folder_name, open=True)

        for table in self.data['tables']:
            parent_folder = table.get('folder') or ""
            self.tree.insert(parent_folder, "end", iid=table['id'], text=table['name'])
        print("[browser] Treeview populated.")

    def save_data(self):
        """Saves the current data dictionary to the JSON file."""
        print(f"[browser] Saving data to {SAVED_TABLES_FILE}")
        try:
            with open(SAVED_TABLES_FILE, 'w') as f:
                json.dump(self.data, f, indent=4)
        except IOError as e:
            print(f"[browser] ERROR: Could not save data. {e}")

    def setup_ui(self):
        """Initializes and packs all UI components for the browser."""
        # --- Main Frame ---
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill="both", expand=True)

        # --- Treeview for Folders and Tables ---
        self.tree = ttk.Treeview(main_frame, show="tree headings", selectmode="browse")
        self.tree.pack(fill="both", expand=True)
        self.tree.heading("#0", text="Folders & Tables")
        self.tree.bind("<Double-1>", self._on_open_table)

        # --- Button Frame ---
        button_frame = ttk.Frame(self)
        button_frame.pack(fill="x", padx=10, pady=10)

        ttk.Button(button_frame, text="New Folder...", command=self._on_create_folder).pack(side="left")
        ttk.Button(button_frame, text="Delete", command=self._on_delete).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Open", command=self._on_open_table).pack(side="right")

    def _on_create_folder(self):
        """Prompts for a new folder name and adds it to the data."""
        print("[browser] 'New Folder' clicked.")
        folder_name = simpledialog.askstring("New Folder", "Enter folder name:", parent=self)
        if not folder_name or not folder_name.strip():
            return

        folder_name = folder_name.strip()
        if folder_name in self.data['folders']:
            messagebox.showwarning("Duplicate", f"A folder named '{folder_name}' already exists.", parent=self)
            return

        print(f"[browser] Creating new folder: {folder_name}")
        self.data['folders'].append(folder_name)
        self.save_data()
        self.load_and_display_data()

    def _on_open_table(self, event=None):
        """Handles opening the selected table."""
        selection = self.tree.selection()
        print(f"[browser] Open action triggered. Selection: {selection}")
        if not selection:
            return
        
        selected_id = selection[0]
        # Check if the selected item is a table (not a folder)
        if selected_id in self.data['folders']:
            print("[browser] Cannot open a folder.")
            return

        print(f"[browser] Opening table with ID: {selected_id}")
        self.open_table_callback(selected_id)
        self.destroy() # Close browser after opening a table

    def _on_delete(self):
        """Handles deleting the selected folder or table."""
        selection = self.tree.selection()
        print(f"[browser] 'Delete' clicked. Selection: {selection}")
        if not selection:
            return

        selected_id = selection[0]
        
        if selected_id in self.data['folders']:
            # Deleting a folder
            if not messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete the folder '{selected_id}' and all tables inside it?", parent=self):
                return
            print(f"[browser] Deleting folder: {selected_id}")
            self.data['folders'].remove(selected_id)
            # Remove all tables that were in that folder
            self.data['tables'] = [t for t in self.data['tables'] if t.get('folder') != selected_id]
        else:
            # Deleting a table
            table_name = self.tree.item(selected_id, "text")
            if not messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete the saved table '{table_name}'?", parent=self):
                return
            print(f"[browser] Deleting table with ID: {selected_id}")
            self.data['tables'] = [t for t in self.data['tables'] if t['id'] != selected_id]

        self.save_data()
        self.load_and_display_data()

def prompt_save_table_details(parent, existing_folders):
    """
    Opens a dialog to get the name, folder, and update behavior for a new saved table.
    Returns a dictionary with the details, or None if cancelled.
    """
    print("[browser_dialog] Opening 'Save Table' dialog.")
    dialog = tk.Toplevel(parent)
    dialog.title("Save Table Configuration")
    dialog.transient(parent)
    dialog.grab_set()
    dialog.geometry("350x220")

    details = {}

    # --- Widgets ---
    ttk.Label(dialog, text="Save as Name:").pack(pady=(10, 0))
    name_var = tk.StringVar()
    ttk.Entry(dialog, textvariable=name_var).pack(fill='x', padx=20)

    ttk.Label(dialog, text="Folder:").pack(pady=(10, 0))
    folder_var = tk.StringVar()
    ttk.Combobox(dialog, textvariable=folder_var, values=existing_folders).pack(fill='x', padx=20)

    live_data_var = tk.BooleanVar(value=True)
    live_settings_var = tk.BooleanVar(value=False)
    ttk.Checkbutton(dialog, text="Update with Live Data", variable=live_data_var).pack(pady=5, anchor='w', padx=20)
    ttk.Checkbutton(dialog, text="Update with Live Settings", variable=live_settings_var).pack(pady=5, anchor='w', padx=20)

    def on_ok():
        print("[browser_dialog] 'Save' clicked in dialog.")
        if not name_var.get().strip():
            messagebox.showerror("Input Error", "Table name cannot be empty.", parent=dialog)
            return
        details['name'] = name_var.get().strip()
        details['folder'] = folder_var.get().strip()
        details['live_data'] = live_data_var.get()
        details['live_settings'] = live_settings_var.get()
        print(f"[browser_dialog] Details gathered: {details}")
        dialog.destroy()

    ok_button = ttk.Button(dialog, text="Save", command=on_ok)
    ok_button.pack(pady=10)

    parent.wait_window(dialog)
    return details if 'name' in details else None