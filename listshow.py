"""
file: listshow.py
description: 列表显示模块
author: IYATT-yx
repository: https://github.com/IYATT-yx/NX-batch-PDF-exporter
copyright:  Copyright (c) 2026 IYATT-yx.
            Licensed under the MIT License. See LICENSE file in the project root for full license information.
"""
import tkinter as tk
from tkinter import ttk

import os

class ListShow(tk.Frame):
    def __init__(self, master, heading1: str = _('序号'), heading2: str = _('导出'), heading3: str = _('NX 文件路径'), defaultStatus: str = _('是')):
        super().__init__(master)
        self.master = master
        self.number = 1
        self.heading1 = heading1
        self.heading2 = heading2
        self.heading3 = heading3
        self.defaultStatus = defaultStatus
        self.createWidgets()

    def createWidgets(self):
        """
        创建组件
        """
        self.tree = ttk.Treeview(self, columns=('number', 'status', 'filePath'), show='headings', selectmode='extended')
        self.tree.heading('number', text=self.heading1, anchor=tk.CENTER)
        self.tree.heading('status', text=self.heading2, anchor=tk.CENTER)
        self.tree.heading('filePath', text=self.heading3, anchor=tk.W)
        self.tree.column('number', anchor=tk.CENTER, width=55, stretch=False)
        self.tree.column('status', anchor=tk.CENTER, width=60, stretch=False)
        self.tree.column('filePath', anchor=tk.W, width=260, stretch=True)

        vsb = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)

        self.tree.grid(row=0, column=0, sticky=tk.NSEW)
        vsb.grid(row=0, column=1, sticky=tk.NS)

        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        # 单击状态列切换导出状态；双击其它列（如文件路径）也切换，避免单击选行时误切换
        self.tree.bind('<Button-1>', self.onTreeClick)
        self.tree.bind('<Double-Button-1>', self.onTreeDoubleClick)

    def onTreeClick(self, event: tk.Event):
        """
        单击事件：仅在点击状态列时切换导出状态

        Args:
            event (tk.Event): 事件对象
        """
        if self.tree.identify_region(event.x, event.y) != 'cell':
            return
        if self.tree.identify_column(event.x) != '#2':
            return
        rowId = self.tree.identify_row(event.y)
        if rowId != '':
            self.toggleStatus(rowId)

    def onTreeDoubleClick(self, event: tk.Event):
        """
        双击事件：切换非状态列的导出状态（状态列已由单击事件处理，避免重复切换）

        Args:
            event (tk.Event): 事件对象
        """
        if self.tree.identify_region(event.x, event.y) != 'cell':
            return
        if self.tree.identify_column(event.x) == '#2':
            return
        rowId = self.tree.identify_row(event.y)
        if rowId != '':
            self.toggleStatus(rowId)

    def toggleStatus(self, rowId: str):
        """
        切换指定行的导出状态

        Args:
            rowId (str): 行 ID（文件路径）
        """
        status = self.tree.set(rowId)['status']
        if status == _('是'):
            self.tree.set(rowId, 'status', _('否'))
        else:
            self.tree.set(rowId, 'status', _('是'))

    def insertPrtList(self, prtList: list[str]):
        """
        插入图纸列表（自动忽略不存在的文件、去重、排序，默认状态为「是」）

        Args:
            prtList (list[str]): 图纸列表
        """
        prtList = [os.path.normpath(prt) for prt in prtList if os.path.exists(prt)]
        prtList = list(set(prtList)) # 去重
        prtList = sorted(prtList)
        for prt in prtList:
            try:
                self.tree.insert('', tk.END, iid=prt, values=(f'{self.number}', self.defaultStatus, prt))
                self.number += 1
            except tk.TclError as e:
                if 'already exists' in str(e): # 跳过重复文件
                    continue
                raise

    def clear(self):
        """
        清空图纸列表显示
        """
        self.tree.delete(*self.tree.get_children())
        self.number = 1

    def removeSelected(self) -> int:
        """
        删除列表中选中的项目，并重新排序号

        Returns:
            int: 删除的项目数量
        """
        selectedItems = self.tree.selection()
        if not selectedItems:
            return 0

        self.tree.delete(*selectedItems)
        self._renumber()
        return len(selectedItems)

    def _renumber(self):
        """
        按当前显示顺序重新设置序号
        """
        self.number = 1
        for rowId in self.tree.get_children():
            self.tree.set(rowId, 'number', f'{self.number}')
            self.number += 1

    def count(self) -> int:
        """
        获取列表中显示的项目数量

        Returns:
            int: 项目数量
        """
        return len(self.tree.get_children())

    def setAllStatus(self, status: bool = True):
        """
        设置所有图纸的导出状态

        Args:
            status (bool, optional): 导出状态. Defaults to True.
        """
        for rowId in self.tree.get_children():
            self.tree.set(rowId, 'status', _('是') if status else _('否'))

    def setSelectedStatus(self, status: bool = True):
        """
        设置选中图纸的导出状态

        Args:
            status (bool, optional): 导出状态. Defaults to True.
        """
        for rowId in self.tree.selection():
            self.tree.set(rowId, 'status', _('是') if status else _('否'))

    def getPrtList(self) -> list[str]:
        """
        获取需要导出的图纸列表

        Returns:
            list[str]: 需要导出的图纸列表
        """
        return [self.tree.set(rowId)['filePath'] for rowId in self.tree.get_children() if self.tree.set(rowId)['status'] == _('是')]
