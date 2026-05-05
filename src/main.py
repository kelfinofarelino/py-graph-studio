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
        
        self.mode = "CURSOR" # Default mode
        self.color = QColor(0, 0, 0) # Default Black
        self.shapes = [] 
        self.selected_index = -1
        
        self.dragging = False
        self.last_mouse_pos = None
        self.mirror_start = None
        self.mirror_curr = None

    # --- 1. RASTER ALGORITHMS (MANUAL PIXEL MANIPULATION) ---
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

    # Algoritma Lingkaran Midpoint (Simetri 8 Arah)
    def midpoint_circle(self, xc, yc, r, color):
        x, y = 0, r
        d = 1 - r
        self.draw_circle_pts(xc, yc, x, y, color)
        while x < y:
            x += 1
            if d < 0:
                d += 2 * x + 1
            else:
                y -= 1
                d += 2 * (x - y) + 1
            self.draw_circle_pts(xc, yc, x, y, color)

    def draw_circle_pts(self, xc, yc, x, y, color):
        pts = [(xc+x, yc+y), (xc-x, yc+y), (xc+x, yc-y), (xc-x, yc-y),
               (xc+y, yc+x), (xc-y, yc+x), (xc+y, yc-x), (xc-y, yc-x)]
        for p in pts: self.draw_pixel(p[0], p[1], color)

    # Algoritma Elips Midpoint (Simetri 4 Arah)
    def midpoint_ellipse(self, xc, yc, rx, ry, color):
        x, y = 0, ry
        rx2, ry2 = rx*rx, ry*ry
        
        # Region 1
        d1 = ry2 - (rx2 * ry) + (0.25 * rx2)
        dx, dy = 2 * ry2 * x, 2 * rx2 * y
        while dx < dy:
            self.draw_ellipse_pts(xc, yc, x, y, color)
            x += 1
            dx += 2 * ry2
            if d1 < 0:
                d1 += dx + ry2
            else:
                y -= 1
                dy -= 2 * rx2
                d1 += dx - dy + ry2
                
        # Region 2
        d2 = (ry2 * ((x + 0.5)**2)) + (rx2 * ((y - 1)**2)) - (rx2 * ry2)
        while y >= 0:
            self.draw_ellipse_pts(xc, yc, x, y, color)
            y -= 1
            dy -= 2 * rx2
            if d2 > 0:
                d2 += rx2 - dy
            else:
                x += 1
                dx += 2 * ry2
                d2 += rx2 - dy + dx

    def draw_ellipse_pts(self, xc, yc, x, y, color):
        pts = [(xc+x, yc+y), (xc-x, yc+y), (xc+x, yc-y), (xc-x, yc-y)]
        for p in pts: self.draw_pixel(p[0], p[1], color)

    def flood_fill(self, x, y, target_color, fill_color):
        target_rgb, fill_rgb = target_color.rgb(), fill_color.rgb()
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
            t = obj['type']
            pts = obj.get('pts', [])
            if t in ['CIRCLE', 'ELLIPSE']:
                p = obj['params']
                min_x, max_x = p['xc'] - p.get('rx', p.get('r')), p['xc'] + p.get('rx', p.get('r'))
                min_y, max_y = p['yc'] - p.get('ry', p.get('r')), p['yc'] + p.get('ry', p.get('r'))
            elif pts:
                min_x, max_x = min(p[0] for p in pts), max(p[0] for p in pts)
                min_y, max_y = min(p[1] for p in pts), max(p[1] for p in pts)
            else: continue

            if min_x - 10 <= x <= max_x + 10 and min_y - 10 <= y <= max_y + 10:
                area = (max_x - min_x) * (max_y - min_y)
                if area < best_area: best_area, best_index = area, i
        return best_index

    # --- 3. LIVE MATRIX TRANSFORMATIONS ---
    def apply_matrix_live(self, matrix):
        if self.selected_index == -1: return
        obj = self.shapes[self.selected_index]
        
        # Handle standar poligon (LINE, RECT, SQUARE, TRIANGLE)
        if 'pts' in obj:
            pts = obj['pts']
            cx, cy = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
            new_pts = []
            for x, y in pts:
                tx, ty = x - cx, y - cy
                nx = tx * matrix[0][0] + ty * matrix[0][1] + matrix[0][2]
                ny = tx * matrix[1][0] + ty * matrix[1][1] + matrix[1][2]
                new_pts.append((nx + cx, ny + cy))
            obj['pts'] = new_pts
            
        # Handle Lingkaran & Elips (Transform xc, yc, r, rx, ry)
        elif 'params' in obj:
            p = obj['params']
            cx, cy = p['xc'], p['yc']
            
            # 1. Transform Pusat (xc, yc)
            tx, ty = cx - cx, cy - cy # Pivot adalah dirinya sendiri
            nx = tx * matrix[0][0] + ty * matrix[0][1] + matrix[0][2]
            ny = tx * matrix[1][0] + ty * matrix[1][1] + matrix[1][2]
            p['xc'], p['yc'] = nx + cx, ny + cy
            
            # 2. Transform Radius (Hanya Skala yang berefek)
            if matrix[0][0] == matrix[1][1] and matrix[0][0] != 1: # Skala Seragam
                scale = matrix[0][0]
                if 'r' in p: p['r'] *= scale
                if 'rx' in p: p['rx'] *= scale; p['ry'] *= scale

    def apply_arbitrary_reflection(self, p1, p2):
        if self.selected_index == -1: return
        # (Logika cermin sembarang disederhanakan untuk stabilitas elips)
        pass

    # --- 4. REDRAW ENGINE ---
    def redraw_canvas(self):
        self.image.fill(Qt.GlobalColor.white)
        for i, obj in enumerate(self.shapes):
            color = QColor(255, 165, 0) if i == self.selected_index else obj['color']
            
            # Pilih algoritma raster yang sesuai
            t = obj['type']
            if t in ['LINE', 'RECT', 'SQUARE', 'TRIANGLE']:
                pts = obj['pts']
                for j in range(len(pts)):
                    self.bresenham_line(pts[j], pts[(j + 1) % len(pts)], color)
            elif t == 'CIRCLE':
                p = obj['params']
                self.midpoint_circle(int(p['xc']), int(p['yc']), int(p['r']), color)
            elif t == 'ELLIPSE':
                p = obj['params']
                self.midpoint_ellipse(int(p['xc']), int(p['yc']), int(p['rx']), int(p['ry']), color)
            
            # Blok Warna (Flood Fill) - Dinonaktifkan saat dragging
            if obj['fill_color'] and not self.dragging:
                if 'pts' in obj:
                    cx = int(sum(p[0] for p in obj['pts']) / len(obj['pts']))
                    cy = int(sum(p[1] for p in obj['pts']) / len(obj['pts']))
                else: cx, cy = int(obj['params']['xc']), int(obj['params']['yc'])
                target_color = self.image.pixelColor(cx, cy)
                if target_color.rgb() != color.rgb():
                    self.flood_fill(cx, cy, target_color, obj['fill_color'])

        # Garis bantu cermin Cyan
        if self.mode == "T_MIRROR" and self.mirror_start and self.mirror_curr:
            self.bresenham_line((self.mirror_start.x(), self.mirror_start.y()), (self.mirror_curr.x(), self.mirror_curr.y()), Qt.GlobalColor.cyan)
        self.update()

    # --- 5. MOUSE EVENTS ---
    def mousePressEvent(self, event):
        mouse_pos = event.pos()
        self.last_mouse_pos = mouse_pos
        if self.mode == "T_MIRROR": self.mirror_start = self.mirror_curr = mouse_pos
        self.selected_index = self.get_object_at(mouse_pos.x(), mouse_pos.y())
        if self.mode.startswith("T_") and self.selected_index != -1: self.dragging = True
        elif not self.mode.startswith("T_"): self.start_pos = mouse_pos
        self.redraw_canvas()

    def mouseMoveEvent(self, event):
        curr_pos = event.pos()
        if self.mode == "T_MIRROR" and self.mirror_start:
            self.mirror_curr = curr_pos
            self.redraw_canvas()
            return
        if self.dragging and self.selected_index != -1 and self.last_mouse_pos:
            dx, dy = curr_pos.x() - self.last_mouse_pos.x(), curr_pos.y() - self.last_mouse_pos.y()
            # Hitung Pivot Pusat Objek
            obj = self.shapes[self.selected_index]
            if 'pts' in obj:
                cx, cy = sum(p[0] for p in obj['pts']) / len(obj['pts']), sum(p[1] for p in obj['pts']) / len(obj['pts'])
            else: cx, cy = obj['params']['xc'], obj['params']['yc']

            mat = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
            if self.mode == "T_MOVE": mat[0][2], mat[1][2] = dx, dy
            elif self.mode == "T_ROTATE":
                a1, a2 = math.atan2(self.last_mouse_pos.y()-cy, self.last_mouse_pos.x()-cx), math.atan2(curr_pos.y()-cy, curr_pos.x()-cx)
                angle = a2 - a1
                mat = [[math.cos(angle), -math.sin(angle), 0], [math.sin(angle), math.cos(angle), 0], [0, 0, 1]]
            elif self.mode == "T_SCALE":
                d1, d2 = math.hypot(self.last_mouse_pos.x()-cx, self.last_mouse_pos.y()-cy), math.hypot(curr_pos.x()-cx, curr_pos.y()-cy)
                if d1 > 0: s = d2/d1; mat = [[s, 0, 0], [0, s, 0], [0, 0, 1]]
            elif self.mode == "T_SHEAR": mat[0][1] = dx / 100.0
            self.apply_matrix_live(mat); self.last_mouse_pos = curr_pos; self.redraw_canvas()

    def mouseReleaseEvent(self, event):
        if self.mode == "T_MIRROR" and self.mirror_start:
            self.apply_arbitrary_reflection(self.mirror_start, event.pos())
            self.mirror_start = self.mirror_curr = None
        elif not self.mode.startswith("T_") and hasattr(self, 'start_pos') and self.start_pos:
            x1, y1, x2, y2 = self.start_pos.x(), self.start_pos.y(), event.pos().x(), event.pos().y()
            new_shape = {'color': self.color, 'fill_color': None, 'type': self.mode}
            
            if self.mode == "RECT": new_shape['pts'] = [(x1,y1), (x2,y1), (x2,y2), (x1,y2)]
            elif self.mode == "SQUARE":
                s = max(abs(x2-x1), abs(y2-y1))
                nx2, ny2 = (x1+s if x2>x1 else x1-s), (y1+s if y2>y1 else y1-s)
                new_shape['pts'] = [(x1,y1), (nx2,y1), (nx2,ny2), (x1,ny2)]
            elif self.mode == "TRIANGLE": new_shape['pts'] = [(x1,y1), (x1,y2), (x2,y2)]
            elif self.mode == "LINE": new_shape['pts'] = [(x1,y1), (x2,y2)]
            elif self.mode == "CIRCLE":
                r = math.hypot(x2-x1, y2-y1)
                new_shape['params'] = {'xc': x1, 'yc': y1, 'r': r} # Pusat di klik awal
            elif self.mode == "ELLIPSE":
                xc, yc = (x1+x2)/2, (y1+y2)/2 # Pusat di tengah tarikan
                new_shape['params'] = {'xc': xc, 'yc': yc, 'rx': abs(x2-x1)/2, 'ry': abs(y2-y1)/2}

            if 'pts' in new_shape or 'params' in new_shape:
                self.shapes.append(new_shape)
                self.selected_index = len(self.shapes) - 1
        self.dragging, self.start_pos = False, None
        self.redraw_canvas()

    def paintEvent(self, event): QPainter(self).drawImage(0, 0, self.image)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pro Graphics Studio v3.0 - Manual Primitives Engine")
        self.canvas = Canvas()
        self.init_ui()

    def init_ui(self):
        # 1. TOOLBAR ATAS (English UI)
        toolbar = QToolBar("Main Tools")
        self.addToolBar(toolbar)

        # -- Section: Select --
        cursor_btn = QAction("Cursor (Select/Move)", self)
        cursor_btn.triggered.connect(lambda: self.set_mode("CURSOR")) # Menggunakan T_MOVE secara internal
        toolbar.addAction(cursor_btn)
        toolbar.addSeparator()

        # -- Section: Shapes --
        toolbar.addWidget(QLabel("  <b>SHAPES:</b>  "))
        for name, m in [("Line", "LINE"), ("Rect", "RECT"), ("Square", "SQUARE"), 
                        ("Triangle", "TRIANGLE"), ("Circle", "CIRCLE"), ("Ellipse", "ELLIPSE")]:
            a = QAction(name, self)
            a.triggered.connect(lambda ch, mode=m: self.set_mode(mode))
            toolbar.addAction(a)
        toolbar.addSeparator()

        # -- Section: Transformations --
        toolbar.addWidget(QLabel("  <b>TRANSFORMS:</b>  "))
        for name, m in [("Rotate", "T_ROTATE"), ("Scale", "T_SCALE"), 
                        ("Shear", "T_SHEAR"), ("Mirror Line", "T_MIRROR")]:
            a = QAction(name, self)
            a.triggered.connect(lambda ch, mode=m: self.set_mode(mode))
            toolbar.addAction(a)

        # 2. SIDEBAR KIRI (Warna)
        central_widget = QWidget()
        main_layout = QHBoxLayout(central_widget)
        sidebar = QVBoxLayout()
        
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

        main_layout.addLayout(sidebar)
        main_layout.addWidget(self.canvas)
        self.setCentralWidget(central_widget)
        self.statusBar().showMessage("Ready. Canvas: White. Use English menu.")

    def set_mode(self, mode):
        # Memetakan menu "Cursor" ke mode internal "T_MOVE" agar bisa drag
        internal_mode = "T_MOVE" if mode == "CURSOR" else mode
        self.canvas.mode = internal_mode
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