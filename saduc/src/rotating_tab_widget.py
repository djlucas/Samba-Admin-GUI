#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# -----------------------------------------------------------------------------
# SADUC (Samba Active Directory Users and Computers)
#
# src/rotating_tab_widget.py
#
# Description:
# This file contains a custom rotating tab widget implementation for PyQt5,
# allowing multiple rows of tabs that can be cycled.
#
# -----------------------------------------------------------------------------

import logging
from PyQt5.QtWidgets import (
    QWidget, QStackedWidget, QVBoxLayout, QStyle, QStylePainter, QStyleOptionTab,
    QTabBar
)
from PyQt5.QtCore import Qt, pyqtSignal, QRect, QPoint
from PyQt5.QtGui import QIcon, QPainter, QColor, QFontMetrics, QPainterPath

from . import tab_styles

class RotatingTabBar(QWidget):
    currentChanged = pyqtSignal(int)

    def __init__(self, parent=None, logger=None):
        super().__init__(parent)
        if logger:
            self.logger = logger.getChild(self.__class__.__name__)
        else:
            self.logger = logging.getLogger(self.__class__.__name__)
            if not self.logger.handlers:
                self.logger.addHandler(logging.NullHandler())
        self._tabs = []
        self._rows = []
        self._current_index = -1
        self._tabs_per_row = 0
        self._tab_style = tab_styles.STYLE_DEFAULT
        self.setMinimumHeight(60)

    def setTabsPerRow(self, count):
        self._tabs_per_row = count
        self._calculate_geometry()
        self.update()

    def setTabStyle(self, style):
        self._tab_style = style
        self._calculate_geometry()
        self.update()

    def addTab(self, text, icon=None):
        tab_data = {"text": text, "icon": icon or QIcon(), "rect": QRect()}
        self._tabs.append(tab_data)
        self._calculate_geometry()
        self.update()
        return len(self._tabs) - 1

    def setCurrentIndex(self, index):
        if 0 <= index < len(self._tabs):
            if self._current_index != index:
                self._current_index = index
                self._rotate_to_make_tab_visible(index)
                self.currentChanged.emit(index)
                self.update()

    def _calculate_geometry(self):
        if not self._tabs:
            return

        fm = QFontMetrics(self.font())
        padding = self._tab_style.get("padding", 10)
        icon_size = 20
        row_height = fm.height() + padding
        y_offset_factor = self._tab_style.get("y_offset_factor", 5)
        
        self._rows = []
        if self._tabs_per_row > 0:
            tab_indices = list(range(len(self._tabs)))
            self._rows = [tab_indices[i:i+self._tabs_per_row] for i in range(0, len(tab_indices), self._tabs_per_row)]
        else:
            current_row = []
            x = 5
            for i, tab in enumerate(self._tabs):
                tab_width = fm.width(tab["text"]) + padding * 2 + icon_size
                if x + tab_width > self.width() and len(current_row) > 0:
                    self._rows.append(current_row)
                    current_row = []
                    x = 5
                current_row.append(i)
                x += tab_width
            if current_row:
                self._rows.append(current_row)

        for row in self._rows:
            if not row:
                continue
            tab_widths = [fm.width(self._tabs[i]["text"]) + padding * 2 + icon_size for i in row]
            total_width = sum(tab_widths)
            x = 5
            if total_width < self.width() - 5:
                remaining_space = self.width() - 5 - total_width
                extra_width_per_tab = remaining_space / len(row)
                for i, tab_index in enumerate(row):
                    new_width = int(tab_widths[i] + extra_width_per_tab)
                    self._tabs[tab_index]["rect"] = QRect(x, 0, new_width, row_height)
                    x += new_width
            else:
                for i, tab_index in enumerate(row):
                    self._tabs[tab_index]["rect"] = QRect(x, 0, tab_widths[i], row_height)
                    x += tab_widths[i]

        self._rotate_to_make_tab_visible(self._current_index)
        new_height = (len(self._rows) * (row_height - y_offset_factor)) + y_offset_factor
        if self.height() != new_height:
            self.setMinimumHeight(new_height)

    def _rotate_to_make_tab_visible(self, index):
        if index < 0 or not self._rows:
            return
        target_row_index = -1
        for i, row in enumerate(self._rows):
            if index in row:
                target_row_index = i
                break
        if target_row_index != -1 and target_row_index != len(self._rows) - 1:
            target_row = self._rows.pop(target_row_index)
            self._rows.append(target_row)

    def paintEvent(self, event):
        drawer_func_name = self._tab_style.get("drawer", "_paint_default_tabs")
        drawer_func = getattr(self, drawer_func_name, self._paint_default_tabs)
        drawer_func(event)

    def _paint_default_tabs(self, event):
        painter = QStylePainter(self)
        opt = QStyleOptionTab()
        padding = self._tab_style.get("padding", 10)
        y_offset_factor = self._tab_style.get("y_offset_factor", 5)
        row_height = QFontMetrics(self.font()).height() + padding
        
        for i, row in enumerate(self._rows[:-1]):
            y_pos = i * (row_height - y_offset_factor)
            for tab_index in row:
                tab = self._tabs[tab_index]
                opt.initFrom(self)
                opt.rect = tab["rect"].translated(0, y_pos)
                opt.text = tab["text"]
                opt.icon = tab["icon"]
                opt.state = QStyle.State_Enabled
                opt.palette.setColor(opt.palette.Button, self._tab_style["colors"].get("bg_back"))
                painter.drawControl(QStyle.CE_TabBarTabShape, opt)
                painter.drawControl(QStyle.CE_TabBarTabLabel, opt)
        
        if self._rows:
            front_row_y = (len(self._rows) - 1) * (row_height - y_offset_factor)
            for tab_index in self._rows[-1]:
                tab = self._tabs[tab_index]
                opt.initFrom(self)
                opt.rect = tab["rect"].translated(0, front_row_y)
                opt.text = tab["text"]
                opt.icon = tab["icon"]
                opt.state = QStyle.State_Enabled
                if tab_index == self._current_index:
                    opt.state |= QStyle.State_Selected
                else:
                    opt.palette.setColor(opt.palette.Button, self.palette().color(self.palette().Button))
                painter.drawControl(QStyle.CE_TabBarTabShape, opt)
                painter.drawControl(QStyle.CE_TabBarTabLabel, opt)

    def _paint_rounded_tabs(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        fm = QFontMetrics(self.font())
        padding = self._tab_style.get("padding", 20)
        border_radius = self._tab_style.get("border_radius", 15)
        y_offset_factor = self._tab_style.get("y_offset_factor", 10)
        row_height = fm.height() + padding
        colors = self._tab_style.get("colors", {})

        for i, row in enumerate(self._rows):
            y_pos = i * (row_height - y_offset_factor)
            for tab_index in row:
                tab = self._tabs[tab_index]
                rect = tab["rect"].translated(0, y_pos)
                is_selected = (tab_index == self._current_index)

                if is_selected:
                    bg_color = colors.get("bg_selected") or self.palette().color(self.palette().Highlight)
                    text_color = colors.get("text_selected") or self.palette().color(self.palette().HighlightedText)
                else: # Not selected
                    bg_color = colors.get("bg_back") or QColor(Qt.lightGray)
                    text_color = colors.get("text_back") or self.palette().color(self.palette().ButtonText)

                # For the gap, use a pen with the window's background color
                pen_color = self.palette().color(self.palette().Window)
                painter.setPen(pen_color)
                painter.setBrush(bg_color)
                
                path = QPainterPath()
                path.moveTo(rect.bottomLeft())
                path.lineTo(rect.topLeft() + QPoint(0, border_radius))
                path.arcTo(rect.left(), rect.top(), border_radius * 2, border_radius * 2, 180, -90)
                path.lineTo(rect.topRight() - QPoint(border_radius, 0))
                path.arcTo(rect.right() - border_radius * 2, rect.top(), border_radius * 2, border_radius * 2, 90, -90)
                path.lineTo(rect.bottomRight())
                path.closeSubpath()
                painter.drawPath(path)

                painter.setPen(text_color)
                painter.drawText(rect, Qt.AlignCenter, tab["text"])

    def mousePressEvent(self, event):
        fm = QFontMetrics(self.font())
        padding = self._tab_style.get("padding", 10)
        y_offset_factor = self._tab_style.get("y_offset_factor", 5)
        row_height = fm.height() + padding
        for i, row in enumerate(self._rows):
            y_pos = i * (row_height - y_offset_factor)
            for tab_index in row:
                tab = self._tabs[tab_index]
                if tab["rect"].translated(0, y_pos).contains(event.pos()):
                    self.setCurrentIndex(tab_index)
                    return
        super().mousePressEvent(event)

    def resizeEvent(self, event):
        self._calculate_geometry()
        self.update()
        super().resizeEvent(event)

class RotatingTabWidget(QWidget):
    def __init__(self, parent=None, logger=None):
        super().__init__(parent)
        self._tab_bar = RotatingTabBar(parent=parent, logger=logger)
        self._stack = QStackedWidget()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._tab_bar)
        layout.addWidget(self._stack)
        self._tab_bar.currentChanged.connect(self._stack.setCurrentIndex)

    def setTabsPerRow(self, count):
        self._tab_bar.setTabsPerRow(count)

    def setTabStyle(self, style):
        self._tab_bar.setTabStyle(style)

    def addTab(self, widget, text, icon=None):
        index = self._tab_bar.addTab(text, icon)
        self._stack.addWidget(widget)
        if self._tab_bar._current_index == -1:
            self._tab_bar.setCurrentIndex(0)
        return index

    def widget(self, index):
        return self._stack.widget(index)

    def currentIndex(self):
        return self._stack.currentIndex()

    def setCurrentIndex(self, index):
        if 0 <= index < self._stack.count():
            self._tab_bar.setCurrentIndex(index)
