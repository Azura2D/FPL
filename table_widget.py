# table_widget.py

"""
This module provides custom Tkinter widgets for displaying pandas DataFrames.
"""
import tkinter as tk
from tkinter import ttk
import pandas as pd

class BaseTable(tk.Frame):
    def __init__(self, parent, dataframe, auto_resize=False, **kwargs):
        super().__init__(parent, **kwargs)
        self.dataframe = dataframe.copy()
        self.auto_resize = auto_resize
        self.style = ttk.Style()
        self.style_name = f"Dynamic.T{id(self)}.Treeview"
        self.style.map(self.style_name, **self.style.map("Treeview"))
        self.tree = ttk.Treeview(self, height=15, style=self.style_name)
        self.tree.tag_configure('oddrow', background='#f0f0f0')
        self.tree.tag_configure('evenrow', background='white')
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.hsb = ttk.Scrollbar(self, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=self.vsb.set, xscrollcommand=self.hsb.set)
        self.vsb.pack(side="right", fill="y")
        self.hsb.pack(side="bottom", fill="x")
        self.tree.pack(fill="both", expand=True)
        self.sort_column_name, self.sort_direction = None, "desc"
        if auto_resize: self.bind("<Configure>", self._on_resize)
        self._draw_table()

    def _format_value(self, value, column_name):
        if pd.isna(value): return "-"
        int_cols = ['total_points', 'goals_scored', 'assists', 'clean_sheets', 'bonus', 'Rank', 'Points Prev GW']
        if column_name in int_cols:
            return f"{int(round(pd.to_numeric(value, errors='coerce')))}"
        float_cols = ['form', 'points_per_game', 'Expected Points Next', 'Expected Points Prev GW', 'EP Diff', 'Avg Difficulty']
        if column_name in float_cols:
            return f"{pd.to_numeric(value, errors='coerce'):.1f}"
        return str(value)

    def update_data(self, new_dataframe):
        self.dataframe = new_dataframe.copy(); self._draw_table()

    def _sort_column(self, column_name):
        if self.sort_column_name == column_name: self.sort_direction = "asc" if self.sort_direction == "desc" else "desc"
        else: self.sort_column_name, self.sort_direction = column_name, "desc"
        try:
            self.dataframe = self.dataframe.sort_values(by=column_name, ascending=(self.sort_direction == "asc"))
        except Exception as e: print(f"Could not sort by column {column_name}: {e}")
        self._draw_table()

    def _draw_table(self): raise NotImplementedError
    def _on_resize(self, event=None): self._auto_resize_columns()
    def _auto_resize_columns(self): pass

class SortableTable(BaseTable):
    def __init__(self, parent, dataframe, **kwargs):
        super().__init__(parent, dataframe, **kwargs)
        self.tree.config(show="headings")
    
    def _draw_table(self):
        self.tree.delete(*self.tree.get_children())
        self.tree["columns"] = list(self.dataframe.columns)
        numeric_cols = self.dataframe.select_dtypes(include='number').columns.tolist()
        for col in self.dataframe.columns:
            self.tree.heading(col, text=str(col).replace('_', ' ').title(), command=lambda c=col: self._sort_column(c))
            self.tree.column(col, width=110, anchor="e" if col in numeric_cols else "w")
        for i, (_, row) in enumerate(self.dataframe.iterrows()):
            formatted_row = [self._format_value(row[col], col) for col in self.dataframe.columns]
            self.tree.insert("", "end", values=formatted_row, tags=('oddrow' if i % 2 else 'evenrow',))

class TransposedTable(BaseTable):
    def __init__(self, parent, dataframe, **kwargs):
        super().__init__(parent, dataframe, **kwargs)
        self.tree.config(show="tree headings")

    def _draw_table(self):
        self.tree.delete(*self.tree.get_children())
        columns = list(self.dataframe.columns)
        self.tree["columns"] = columns
        self.tree.column("#0", width=170, anchor="w", stretch=tk.NO)
        self.tree.heading("#0", text="Statistic", anchor="w")
        for col in columns:
            self.tree.heading(col, text=str(col).replace('_', ' ').title())
            self.tree.column(col, width=100, minwidth=80, anchor="center", stretch=tk.YES)
        for i, (stat_name, row) in enumerate(self.dataframe.iterrows()):
            formatted_row = [self._format_value(row[player], stat_name) for player in columns]
            self.tree.insert("", "end", iid=stat_name, text=str(stat_name).replace('_', ' ').title(), values=formatted_row, tags=('oddrow' if i % 2 else 'evenrow',))