# table_widget.py

"""
This module provides custom Tkinter widgets for displaying pandas DataFrames.
It includes a standard sortable table and a more complex transposed table,
both built on a shared base class.
"""
import tkinter as tk
from tkinter import ttk
import pandas as pd

class BaseTable(tk.Frame):
    """
    A base class for displaying a pandas DataFrame in a Tkinter Treeview.
    It handles the common setup of the Treeview widget, scrollbars, and
    provides a basic structure for data formatting and updates.
    """
    def __init__(self, parent, dataframe, auto_resize=False, **kwargs):
        print(f"[table_widget] Initializing BaseTable with a DataFrame of shape {dataframe.shape}.")
        super().__init__(parent, **kwargs)
        self.dataframe = dataframe.copy()
        self.auto_resize = auto_resize

        # Create a unique style for this specific widget instance to avoid style conflicts.
        self.style = ttk.Style()
        self.style_name = f"Dynamic.T{id(self)}.Treeview"
        self.style.map(self.style_name, **self.style.map("Treeview")) # Copy default style

        self.tree = ttk.Treeview(self, height=15, style=self.style_name)

        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.hsb = ttk.Scrollbar(self, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=self.vsb.set, xscrollcommand=self.hsb.set)

        self.vsb.pack(side="right", fill="y")
        self.hsb.pack(side="bottom", fill="x")
        self.tree.pack(fill="both", expand=True)

        self.sort_column_name = None
        self.sort_direction = "desc"
        
        if auto_resize:
            print("[table_widget] Auto-resize enabled for this table.")
            self.bind("<Configure>", self._on_resize)

        self._draw_table()

    def _format_value(self, value, column_name):
        """
        Formats a single data value for display in the table. It handles NaNs
        and applies specific formatting for numeric types (integer vs. float)
        based on the column name.
        """
        if pd.isna(value):
            return "-"
        
        numeric_col_names = [  # A list of columns that should be treated as numbers.
            'now_cost', 'selected_by_percent', 'total_points', 'cumulative_total_points',
            'form', 'goals_scored', 'assists', 'clean_sheets', 'bonus', 'bps',
            'influence', 'creativity', 'threat', 'ict_index'
        ]
        
        if column_name in numeric_col_names:
            numeric_value = pd.to_numeric(value, errors='coerce')
            if pd.notna(numeric_value):
                # Columns that should always be integers.
                int_cols = ['total_points', 'cumulative_total_points', 'goals_scored', 'assists', 'clean_sheets', 'bonus', 'bps']
                if column_name in int_cols:
                    return f"{int(round(numeric_value))}"
                else:
                    # Other numeric columns (like form, cost) are formatted to one decimal place.
                    return f"{numeric_value:.1f}"
        
        return str(value)

    def update_data(self, new_dataframe):
        """Updates the table with a new DataFrame."""
        self.dataframe = new_dataframe.copy()
        self._draw_table()

    def _sort_column(self, column_name):
        """Default sorting for standard tables. Sorts rows based on a column's values."""
        print(f"[table_widget] Sorting by column '{column_name}'.")
        if self.sort_column_name == column_name:
            self.sort_direction = "asc" if self.sort_direction == "desc" else "desc"
        else:
            self.sort_column_name = column_name
            self.sort_direction = "desc"
        
        self.dataframe = self.dataframe.sort_values(
            by=column_name,
            ascending=(self.sort_direction == "asc")
        )
        self._draw_table()

    def _draw_table(self):
        """Placeholder for the drawing method, to be implemented by child classes."""
        raise NotImplementedError("This method should be implemented by a subclass.")

    def _on_resize(self, event=None):
        """Callback for when the parent frame is resized."""
        # This method is debounced implicitly by the Tkinter event loop.
        self._auto_resize_height()
        self._auto_resize_columns()

    def _auto_resize_columns(self):
        """Distributes available width among the Treeview columns. Implemented by subclasses."""
        pass # Subclasses will override this.

    def _auto_resize_height(self):
        """Adjusts the visible row count of the Treeview. Implemented by subclasses."""
        pass # Subclasses will override this.

class SortableTable(BaseTable):
    """
    A standard table where rows are players and columns are stats.
    Clicking a column header sorts the table by that stat.
    """
    def __init__(self, parent, dataframe, **kwargs):
        print(f"[table_widget] Initializing SortableTable.")
        super().__init__(parent, dataframe, **kwargs)
        self.tree.config(show="headings")
    
    def _draw_table(self):
        print(f"[table_widget] Drawing SortableTable with {len(self.dataframe)} rows.")
        self.tree.delete(*self.tree.get_children())
        self.tree["columns"] = list(self.dataframe.columns)
        
        for col in self.dataframe.columns:
            print(f"[table_widget]   - Drawing column: {col}")
            # The lambda is used to capture the current value of `col` for the command.
            self.tree.heading(col, text=str(col).replace('_', ' ').title(), command=lambda c=col: self._sort_column(c))
            self.tree.column(col, width=100, anchor="center")

        for index, row in self.dataframe.iterrows():
            formatted_row = [self._format_value(row[col], col) for col in self.dataframe.columns]
            self.tree.insert("", "end", values=formatted_row)

    def _auto_resize_columns(self):
        """Evenly distributes the total width among all visible columns."""
        total_width = self.winfo_width()
        columns = self.tree["columns"]
        if not columns or total_width < 50: # Don't resize if too small
            return
        
        print(f"[table_widget] Resizing SortableTable columns. Total width: {total_width}")
        width_per_column = total_width / len(columns)
        
        for col in columns:
            self.tree.column(col, width=int(width_per_column))

class TransposedTable(BaseTable):
    """
    An inverted (transposed) table for displaying a single team's squad.
    In this view, rows represent player statistics (e.g., 'form', 'total_points')
    and columns represent the players themselves. This layout is useful for
    comparing players within a squad side-by-side.
    """
    def __init__(self, parent, dataframe, **kwargs):
        print(f"[table_widget] Initializing TransposedTable.")
        super().__init__(parent, dataframe, **kwargs)
        self.tree.config(show="tree headings")
        # When auto-resizing, we want the table to fill the space so we can calculate row height.
        # The vertical scrollbar will be hidden by the height calculation logic if not needed.

        self.tree.bind("<Button-1>", self._on_click)
        # Bind to the window's click events to dismiss the popup when clicking outside the table.
        self.winfo_toplevel().bind_all("<Button-1>", self._on_global_click, add="+")
        self._cell_popup = None # To hold the cell content popup

    def _sort_column(self, stat_name):
        """Custom sort for transposed table: sorts columns (players) left-to-right based on a stat row."""
        print(f"[table_widget] Sorting TransposedTable by stat '{stat_name}'.")
        try:
            sort_series = self.dataframe.loc[stat_name]
            
            # Toggles the sort direction on subsequent clicks of the same stat.
            current_order_is_desc = getattr(self, '_last_sort_asc', False)
            ascending = current_order_is_desc
            
            sorted_columns = sort_series.sort_values(ascending=ascending).index
            self.dataframe = self.dataframe[sorted_columns]
            
            # Store the sort direction for the next click.
            self._last_sort_asc = not current_order_is_desc
            
            self._draw_table()
        except KeyError:
            print(f"Cannot sort by '{stat_name}', as it's not a valid stat.")

    def _draw_table(self):
        print(f"[table_widget] Drawing TransposedTable with {len(self.dataframe.columns)} players.")

        self.tree.delete(*self.tree.get_children())
        columns = list(self.dataframe.columns)
        self.tree["columns"] = columns
        
        # The first column (#0) displays the stat names (tree column) and is not a data column.
        self.tree.column("#0", width=170, anchor="w", stretch=tk.NO)
        self.tree.heading("#0", text="Statistic", anchor="w", command=lambda: print("Cannot sort by header column."))

        # Configure the player columns to be resizable.
        for col in columns:
            self.tree.heading(col, text=str(col).replace('_', ' ').title())
            # If auto-resizing, we remove the minimum width constraint to allow columns to shrink fully.
            min_col_width = 0 if self.auto_resize else 80
            self.tree.column(col, width=100, minwidth=min_col_width, anchor="center", stretch=tk.YES)

        # Insert data row by row
        for stat_name, row in self.dataframe.iterrows():
            print(f"[table_widget]   - Drawing row for stat: {stat_name}")
            formatted_row = [self._format_value(row[player], stat_name) for player in columns]
            
            # Use the stat_name as the item ID (iid) for easy identification on click.
            self.tree.insert("", "end", iid=stat_name, text=str(stat_name).replace('_', ' ').title(), values=formatted_row)

    def _auto_resize_columns(self):
        """
        Distributes available width among player columns while keeping the
        first "Statistic" column at a fixed width.
        """
        total_width = self.winfo_width()
        player_columns = self.tree["columns"]
        if not player_columns or total_width < 200: # Don't resize if too small
            return

        print(f"[table_widget] Resizing TransposedTable columns. Total width: {total_width}")
        stat_col_width = self.tree.column("#0", "width")
        
        remaining_width = total_width - stat_col_width
        if remaining_width < 0: remaining_width = 0
        
        width_per_player = remaining_width / len(player_columns)
        for col in player_columns:
            self.tree.column(col, width=int(width_per_player))

    def _auto_resize_height(self):
        """
        Dynamically calculates and sets the row height to make the table's content
        fill the available vertical space.
        """
        if not self.auto_resize:
            return

        available_height = self.winfo_height()
        num_rows = len(self.dataframe.index)
        if num_rows == 0 or available_height < 50:
            return

        # Approximate height of the Treeview header
        header_height = 30 
        content_height = available_height - header_height
        new_row_height = max(20, content_height // num_rows) # Ensure a minimum row height

        print(f"[table_widget] Vertical resize: available_h={available_height}, rows={num_rows}, new_row_h={new_row_height}")
        self.style.configure(self.style_name, rowheight=new_row_height)

    def _on_global_click(self, event):
        """Handles clicks outside the Treeview to dismiss the popup."""
        print(f"[table_widget_global_click] Event on widget: {event.widget}")
        if event.widget != self.tree:
            print("[table_widget_global_click] Click was outside the tree. Dismissing popup.")
            self._dismiss_cell_popup()

    def _dismiss_cell_popup(self):
        """Destroys the cell content popup if it exists."""
        if self._cell_popup:
            print("[table_widget] Dismissing existing cell popup.")
            self._cell_popup.destroy()
            self._cell_popup = None

    def _show_cell_popup(self, row_id, column_id):
        """Displays a small popup window with the full content of a cell."""
        print(f"[table_widget] Attempting to show popup for cell: row='{row_id}', col='{column_id}'")
        # Get the full, un-formatted value from the dataframe
        try:
            full_value = self.dataframe.loc[row_id, column_id]
            if pd.isna(full_value) or str(full_value).strip() == "":
                return # Don't show popup for empty cells
        except KeyError:
            return
        print(f"[table_widget]   - Full value: '{full_value}'")

        # Get the bounding box of the cell relative to the treeview
        try:
            x, y, width, height = self.tree.bbox(row_id, column_id)
            print(f"[table_widget]   - Cell bbox: x={x}, y={y}, w={width}, h={height}")
        except Exception:
            return # Cell might not be visible

        # Calculate absolute screen coordinates
        abs_x = self.tree.winfo_rootx() + x
        abs_y = self.tree.winfo_rooty() + y

        print(f"[table_widget]   - Creating popup at screen coordinates: x={abs_x}, y={abs_y}")
        # Create the popup
        self._cell_popup = tk.Toplevel(self)
        self._cell_popup.wm_overrideredirect(True) # No title bar
        self._cell_popup.wm_geometry(f"+{abs_x}+{abs_y}")
        self._cell_popup.attributes("-topmost", True)

        popup_label = tk.Label(
            self._cell_popup, text=full_value, background="lightyellow",
            relief="solid", borderwidth=1, wraplength=350, justify="left",
            padx=4, pady=4
        )
        popup_label.pack()

    def _on_click(self, event):
        """
        Handles all click events on the TransposedTable.
        - A click on the first column (statistic name) triggers a sort.
        - A click on any other column (player data) shows a popup with the full content.
        """
        print("\n--- [table_widget_click] ---")
        region = self.tree.identify_region(event.x, event.y)
        print(f"[table_widget_click] Click detected. Raw Region: '{region}'")
        # The first column is the 'tree' region, others are 'cell'. We process both.
        if region not in ("cell", "tree"): # Ignore clicks on headings or empty space
            self._dismiss_cell_popup()
            print(f"[table_widget_click] Click was on region '{region}', not 'cell' or 'tree'. Action aborted.")
            return

        self._dismiss_cell_popup()  # Dismiss any existing popup before processing the new click.
        column_id_str = self.tree.identify_column(event.x)
        row_id = self.tree.identify_row(event.y)
        print(f"[table_widget_click] Identified cell: row='{row_id}', col_id='{column_id_str}'")

        if not row_id:
            print("[table_widget_click] No row identified. Action aborted.")
            return

        if column_id_str == "#0":
            # Click was on a statistic name, so sort by that stat.
            print("[table_widget_click] Action: Sort column.")
            self._sort_column(row_id)
        else:
            # Click was on a player data cell. We need to convert the positional column ID (e.g., '#1')
            # to the actual player name.
            try:
                col_index = int(column_id_str.replace('#', '')) - 1
                player_name = self.tree['columns'][col_index]
                print(f"[table_widget_click] Action: Show cell popup for player '{player_name}'.")
                self._show_cell_popup(row_id, player_name)
            except (ValueError, IndexError) as e:
                print(f"[table_widget_click] ERROR: Could not map column ID '{column_id_str}' to a player name. {e}")
