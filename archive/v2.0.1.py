import sys
import math
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QGroupBox, QToolBar)
from PyQt6.QtGui import QPainter, QImage, QColor, QAction
from PyQt6.QtCore import Qt, QPoint

class Canvas(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(900, 600)
        self.image = QImage(900, 600, QImage.Format.Format_RGB32)
        self.image.fill(Qt.GlobalColor.white) # WHITE CANVAS
        
        self.mode = "T_MOVE" # Default to Cursor/Move
        self.color = QColor(0, 0, 0) # Default Black
        self.shapes = [] 
        self.selected_index = -1
        
        self.dragging = False
        self.last_mouse_pos = None
        self.mirror_start = None
        self.mirror_curr = None

    # --- 1. RASTER ALGORITHMS ---
    def draw_pixel(self, x, y, color):
        if 0 <= x < 900 and 0 <= y < 600:
            self.image.setPixelColor(int(x), int(y), color)

    def bresenham_line(self, p1, p2, color):
        x1, y1, x2, y2 = int(p1[0]), int(p1[1]), int(p2[0]), int(p2[1])
        dx, dy = abs(x2 - x1), abs(y2 - y1)
        sx = 1 if x1 < x2 else -1
        sy = 1 if y1 < y2 else -1
        err = dx - dy
        while True:
            self.draw_pixel(x1, y1, color)
            if x1 == x2 and y1 == y2: break
            e2 = 2 * err
            if e2 > -dy: err -= dy; x1 += sx
            if e2 < dx: err += dx; y1 += sy

    def flood_fill(self, x, y, target_color, fill_color):
        target_rgb = target_color.rgb()
        fill_rgb = fill_color.rgb()
        if target_rgb == fill_rgb: return
        
        stack = [(x, y)]
        while stack:
            cx, cy = stack.pop()
            if cx < 0 or cx >= 900 or cy < 0 or cy >= 600: continue
            
            if self.image.pixelColor(cx, cy).rgb() == target_rgb:
                self.image.setPixelColor(cx, cy, fill_color)
                stack.extend([(cx+1, cy), (cx-1, cy), (cx, cy+1), (cx, cy-1)])

    # --- 2. OBJECT MANAGEMENT ---
    def get_object_at(self, x, y):
        best_index = -1
        best_area = float('inf')
        
        for i, obj in enumerate(self.shapes):
            pts = obj['pts']
            min_x, max_x = min(p[0] for p in pts), max(p[0] for p in pts)
            min_y, max_y = min(p[1] for p in pts), max(p[1] for p in pts)
            
            if min_x - 10 <= x <= max_x + 10 and min_y - 10 <= y <= max_y + 10:
                area = (max_x - min_x) * (max_y - min_y)
                if area < best_area: 
                    best_area = area
                    best_index = i
        return best_index

    # --- 3. LIVE MATRIX TRANSFORMATIONS ---
    def apply_matrix_live(self, matrix):
        if self.selected_index == -1: return
        obj = self.shapes[self.selected_index]
        pts = obj['pts']
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        
        new_pts = []
        for x, y in pts:
            tx, ty = x - cx, y - cy
            nx = tx * matrix[0][0] + ty * matrix[0][1] + matrix[0][2]
            ny = tx * matrix[1][0] + ty * matrix[1][1] + matrix[1][2]
            new_pts.append((nx + cx, ny + cy))
        obj['pts'] = new_pts

    def apply_arbitrary_reflection(self, p1, p2):
        if self.selected_index == -1: return
        obj = self.shapes[self.selected_index]
        x1, y1, x2, y2 = p1.x(), p1.y(), p2.x(), p2.y()
        if x1 == x2 and y1 == y2: return 
        
        angle = math.atan2(y2 - y1, x2 - x1)
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        
        new_pts = []
        for x, y in obj['pts']:
            tx, ty = x - x1, y - y1
            rx = tx * cos_a + ty * sin_a
            ry = -tx * sin_a + ty * cos_a
            ry = -ry 
            nx = rx * cos_a - ry * sin_a
            ny = rx * sin_a + ry * cos_a
            new_pts.append((nx + x1, ny + y1))
        obj['pts'] = new_pts

    # --- 4. REDRAW ENGINE ---
    def redraw_canvas(self):
        self.image.fill(Qt.GlobalColor.white)
        
        for i, obj in enumerate(self.shapes):
            color = QColor(255, 165, 0) if i == self.selected_index else obj['color']
            pts = obj['pts']
            
            for j in range(len(pts)):
                self.bresenham_line(pts[j], pts[(j + 1) % len(pts)], color)
            
            if obj['fill_color'] and not self.dragging:
                cx = int(sum(p[0] for p in pts) / len(pts))
                cy = int(sum(p[1] for p in pts) / len(pts))
                target_color = self.image.pixelColor(cx, cy)
                
                if target_color.rgb() != color.rgb():
                    self.flood_fill(cx, cy, target_color, obj['fill_color'])

        if self.mode == "T_MIRROR" and self.mirror_start and self.mirror_curr:
            self.bresenham_line((self.mirror_start.x(), self.mirror_start.y()), 
                                (self.mirror_curr.x(), self.mirror_curr.y()), Qt.GlobalColor.cyan)
        self.update()

    # --- 5. MOUSE EVENTS ---
    def mousePressEvent(self, event):
        mouse_pos = event.pos()
        self.last_mouse_pos = mouse_pos
        
        if self.mode == "T_MIRROR":
            self.mirror_start = self.mirror_curr = mouse_pos
            
        self.selected_index = self.get_object_at(mouse_pos.x(), mouse_pos.y())
        
        if self.mode.startswith("T_") and self.selected_index != -1:
            self.dragging = True
        elif not self.mode.startswith("T_"):
            self.start_pos = mouse_pos
            
        self.redraw_canvas()

    def mouseMoveEvent(self, event):
        curr_pos = event.pos()
        
        if self.mode == "T_MIRROR" and self.mirror_start:
            self.mirror_curr = curr_pos
            self.redraw_canvas()
            return
            
        if self.dragging and self.selected_index != -1 and self.last_mouse_pos:
            dx = curr_pos.x() - self.last_mouse_pos.x()
            dy = curr_pos.y() - self.last_mouse_pos.y()
            
            obj = self.shapes[self.selected_index]
            cx = sum(p[0] for p in obj['pts']) / len(obj['pts'])
            cy = sum(p[1] for p in obj['pts']) / len(obj['pts'])

            mat = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]

            if self.mode == "T_MOVE":
                mat[0][2], mat[1][2] = dx, dy
            elif self.mode == "T_ROTATE":
                a1 = math.atan2(self.last_mouse_pos.y() - cy, self.last_mouse_pos.x() - cx)
                a2 = math.atan2(curr_pos.y() - cy, curr_pos.x() - cx)
                angle = a2 - a1
                mat = [[math.cos(angle), -math.sin(angle), 0], [math.sin(angle), math.cos(angle), 0], [0, 0, 1]]
            elif self.mode == "T_SCALE":
                d1 = math.hypot(self.last_mouse_pos.x() - cx, self.last_mouse_pos.y() - cy)
                d2 = math.hypot(curr_pos.x() - cx, curr_pos.y() - cy)
                if d1 > 0:
                    scale = d2 / d1
                    mat = [[scale, 0, 0], [0, scale, 0], [0, 0, 1]]
            elif self.mode == "T_SHEAR":
                mat[0][1] = dx / 100.0

            self.apply_matrix_live(mat)
            self.last_mouse_pos = curr_pos
            self.redraw_canvas()

    def mouseReleaseEvent(self, event):
        if self.mode == "T_MIRROR" and self.mirror_start:
            self.apply_arbitrary_reflection(self.mirror_start, event.pos())
            self.mirror_start = self.mirror_curr = None
            
        elif not self.mode.startswith("T_") and hasattr(self, 'start_pos') and self.start_pos:
            x1, y1, x2, y2 = self.start_pos.x(), self.start_pos.y(), event.pos().x(), event.pos().y()
            pts = []
            if self.mode == "RECT": pts = [(x1,y1), (x2,y1), (x2,y2), (x1,y2)]
            elif self.mode == "SQUARE":
                s = max(abs(x2-x1), abs(y2-y1))
                nx2, ny2 = (x1+s if x2>x1 else x1-s), (y1+s if y2>y1 else y1-s)
                pts = [(x1,y1), (nx2,y1), (nx2,ny2), (x1,ny2)]
            elif self.mode == "TRIANGLE": pts = [(x1,y1), (x1,y2), (x2,y2)]
            elif self.mode == "LINE": pts = [(x1,y1), (x2,y2)]
            
            if pts:
                self.shapes.append({'pts': pts, 'color': self.color, 'fill_color': None, 'type': self.mode})
                self.selected_index = len(self.shapes) - 1
                
        self.dragging = False
        self.start_pos = None
        self.redraw_canvas()

    def paintEvent(self, event):
        QPainter(self).drawImage(0, 0, self.image)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pro Graphics Suite v2.0")
        self.canvas = Canvas()
        self.init_ui()

    def init_ui(self):
        # 1. TOP TOOLBAR (Categorized Sections)
        toolbar = QToolBar("Main Tools")
        self.addToolBar(toolbar)

        # -- Section: Cursor / Select --
        cursor_btn = QAction("Cursor", self)
        cursor_btn.triggered.connect(lambda: self.set_mode("T_MOVE"))
        toolbar.addAction(cursor_btn)

        toolbar.addSeparator()

        # -- Section: Drawing Shapes --
        lbl_shapes = QLabel("  <b>SHAPES:</b>  ")
        toolbar.addWidget(lbl_shapes)

        for name, m in [("Line", "LINE"), ("Rectangle", "RECT"), ("Square", "SQUARE"), ("Triangle", "TRIANGLE")]:
            a = QAction(name, self)
            a.triggered.connect(lambda ch, mode=m: self.set_mode(mode))
            toolbar.addAction(a)
            
        toolbar.addSeparator()

        # -- Section: Transformations --
        lbl_trans = QLabel("  <b>TRANSFORMATIONS:</b>  ")
        toolbar.addWidget(lbl_trans)

        for name, m in [("Rotate", "T_ROTATE"), ("Scale", "T_SCALE"), 
                        ("Shear", "T_SHEAR"), ("Mirror Line", "T_MIRROR")]:
            a = QAction(name, self)
            a.triggered.connect(lambda ch, mode=m: self.set_mode(mode))
            toolbar.addAction(a)

        # 2. LEFT SIDEBAR (Colors & Attributes)
        central_widget = QWidget()
        main_layout = QHBoxLayout(central_widget)
        sidebar = QVBoxLayout()
        
        # Color Palette Group
        color_group = QGroupBox("Select Color")
        c_layout = QVBoxLayout()
        colors = [("Black", Qt.GlobalColor.black), ("White", Qt.GlobalColor.white), 
                  ("Red", Qt.GlobalColor.red), ("Green", Qt.GlobalColor.green), 
                  ("Blue", Qt.GlobalColor.blue)]
        for name, code in colors:
            btn = QPushButton(name)
            hex_color = QColor(code).name()
            txt_color = 'white' if name in ['Black', 'Blue', 'Red'] else 'black'
            btn.setStyleSheet(f"background-color: {hex_color}; color: {txt_color}; font-weight: bold; border-radius: 4px; padding: 5px;")
            btn.clicked.connect(lambda ch, c=code: self.set_color(c))
            c_layout.addWidget(btn)
        color_group.setLayout(c_layout)

        # Apply Action Group
        action_group = QGroupBox("Apply to Object")
        a_layout = QVBoxLayout()
        
        btn_outline = QPushButton("Apply Outline")
        btn_outline.clicked.connect(self.apply_outline)
        
        btn_fill = QPushButton("Apply Fill")
        btn_fill.clicked.connect(self.apply_fill)
        
        a_layout.addWidget(btn_outline)
        a_layout.addWidget(btn_fill)
        action_group.setLayout(a_layout)

        sidebar.addWidget(color_group)
        sidebar.addWidget(action_group)
        sidebar.addStretch()

        # 3. COMBINING LAYOUTS
        main_layout.addLayout(sidebar)
        main_layout.addWidget(self.canvas)
        self.setCentralWidget(central_widget)
        self.statusBar().showMessage("Ready. Default color is Black. Use 'Cursor' to select and move objects.")

    def set_mode(self, mode):
        self.canvas.mode = mode
        self.statusBar().showMessage(f"Active Mode: {mode}")

    def set_color(self, code):
        self.canvas.color = QColor(code)
        self.statusBar().showMessage(f"Color Selected: {QColor(code).name()}")

    def apply_outline(self):
        if self.canvas.selected_index != -1:
            self.canvas.shapes[self.canvas.selected_index]['color'] = self.canvas.color
            self.canvas.redraw_canvas()

    def apply_fill(self):
        if self.canvas.selected_index != -1:
            self.canvas.shapes[self.canvas.selected_index]['fill_color'] = self.canvas.color
            self.canvas.redraw_canvas()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())