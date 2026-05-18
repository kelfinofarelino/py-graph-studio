import sys
import math
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QGroupBox, QToolBar,
                             QColorDialog) 
from PyQt6.QtGui import QPainter, QImage, QColor, QAction
from PyQt6.QtCore import Qt, QPoint

class Canvas(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(900, 600)
        self.image = QImage(900, 600, QImage.Format.Format_RGB32)
        self.image.fill(Qt.GlobalColor.white) 
        
        self.mode = "CURSOR" 
        self.color = QColor(0, 0, 0) 
        self.shapes = [] 
        self.selected_index = -1
        
        self.dragging = False
        self.last_mouse_pos = None
        self.start_pos = None
        self.curr_mouse_pos = None

        # --- SISTEM UNDO & REDO ---
        self.undo_stack = []
        self.redo_stack = []
        self.save_state() 

    # --- 1. STATE MANAGEMENT (UNDO / REDO) ---
    def _copy_shapes(self, source_shapes):
        cloned = []
        for s in source_shapes:
            new_s = {
                'color': QColor(s['color'].rgba()),
                'fill_color': QColor(s['fill_color'].rgba()) if s.get('fill_color') else None,
                'type': s['type']
            }
            if 'pts' in s: new_s['pts'] = list(s['pts'])
            if 'params' in s: new_s['params'] = dict(s['params'])
            cloned.append(new_s)
        return cloned

    def save_state(self):
        self.undo_stack.append(self._copy_shapes(self.shapes))
        if len(self.undo_stack) > 30: 
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def undo(self):
        if len(self.undo_stack) > 1:
            self.redo_stack.append(self.undo_stack.pop())
            self.shapes = self._copy_shapes(self.undo_stack[-1])
            self.selected_index = -1
            self.redraw_canvas()

    def redo(self):
        if self.redo_stack:
            state = self.redo_stack.pop()
            self.undo_stack.append(state)
            self.shapes = self._copy_shapes(state)
            self.selected_index = -1
            self.redraw_canvas()

    # --- 2. RASTER ALGORITHMS (MANUAL PIXEL MANIPULATION) ---
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

    def midpoint_circle(self, xc, yc, r, color):
        x, y = 0, r
        d = 1 - r
        self.draw_circle_pts(xc, yc, x, y, color)
        while x < y:
            x += 1
            if d < 0: d += 2 * x + 1
            else: y -= 1; d += 2 * (x - y) + 1
            self.draw_circle_pts(xc, yc, x, y, color)

    def draw_circle_pts(self, xc, yc, x, y, color):
        pts = [(xc+x, yc+y), (xc-x, yc+y), (xc+x, yc-y), (xc-x, yc-y),
               (xc+y, yc+x), (xc-y, yc+x), (xc+y, yc-x), (xc-y, yc-x)]
        for p in pts: self.draw_pixel(p[0], p[1], color)

    def midpoint_ellipse(self, xc, yc, rx, ry, color):
        x, y = 0, ry
        rx2, ry2 = rx*rx, ry*ry
        d1 = ry2 - (rx2 * ry) + (0.25 * rx2)
        dx, dy = 2 * ry2 * x, 2 * rx2 * y
        while dx < dy:
            self.draw_ellipse_pts(xc, yc, x, y, color)
            x += 1
            dx += 2 * ry2
            if d1 < 0: d1 += dx + ry2
            else: y -= 1; dy -= 2 * rx2; d1 += dx - dy + ry2
                
        d2 = (ry2 * ((x + 0.5)**2)) + (rx2 * ((y - 1)**2)) - (rx2 * ry2)
        while y >= 0:
            self.draw_ellipse_pts(xc, yc, x, y, color)
            y -= 1
            dy -= 2 * rx2
            if d2 > 0: d2 += rx2 - dy
            else: x += 1; dx += 2 * ry2; d2 += rx2 - dy + dx

    def draw_ellipse_pts(self, xc, yc, x, y, color):
        for p in [(xc+x, yc+y), (xc-x, yc+y), (xc+x, yc-y), (xc-x, yc-y)]: self.draw_pixel(p[0], p[1], color)

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

    # --- 3. OBJECT MANAGEMENT ---
    def get_object_at(self, x, y):
        best_index, best_area = -1, float('inf')
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

    # --- 4. INSTANT TRANSFORMS (FLIP & DELETE) ---
    def flip_object(self, axis):
        if self.selected_index == -1: return
        mat = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
        if axis == 'X': mat[0][0] = -1
        elif axis == 'Y': mat[1][1] = -1
        
        self.apply_matrix_live(mat)
        self.redraw_canvas()
        self.save_state()

    def delete_selected(self):
        if self.selected_index != -1:
            self.shapes.pop(self.selected_index)
            self.selected_index = -1
            self.redraw_canvas()
            self.save_state()

    # --- 5. LIVE MATRIX TRANSFORMATIONS ---
    def apply_matrix_live(self, matrix):
        if self.selected_index == -1: return
        obj = self.shapes[self.selected_index]
        
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
            
        elif 'params' in obj:
            p = obj['params']
            cx, cy = p['xc'], p['yc']
            tx, ty = cx - cx, cy - cy
            nx = tx * matrix[0][0] + ty * matrix[0][1] + matrix[0][2]
            ny = tx * matrix[1][0] + ty * matrix[1][1] + matrix[1][2]
            p['xc'], p['yc'] = nx + cx, ny + cy
            
            if matrix[0][0] == matrix[1][1] and matrix[0][0] != 1:
                scale = matrix[0][0]
                if 'r' in p: p['r'] *= scale
                if 'rx' in p: p['rx'] *= scale; p['ry'] *= scale

    # --- 6. REDRAW ENGINE ---
    def redraw_canvas(self):
        self.image.fill(Qt.GlobalColor.white)
        
        for i, obj in enumerate(self.shapes):
            color = QColor(255, 165, 0) if i == self.selected_index else obj['color']
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
            
            if obj['fill_color'] and not self.dragging:
                if 'pts' in obj:
                    cx = int(sum(p[0] for p in obj['pts']) / len(obj['pts']))
                    cy = int(sum(p[1] for p in obj['pts']) / len(obj['pts']))
                else: cx, cy = int(obj['params']['xc']), int(obj['params']['yc'])
                target_color = self.image.pixelColor(cx, cy)
                if target_color.rgb() != color.rgb():
                    self.flood_fill(cx, cy, target_color, obj['fill_color'])

        # --- LIVE PREVIEW (RUBBER-BANDING) ---
        if not self.mode.startswith("T_") and self.mode != "FILL" and self.start_pos and self.curr_mouse_pos:
            x1, y1 = self.start_pos.x(), self.start_pos.y()
            x2, y2 = self.curr_mouse_pos.x(), self.curr_mouse_pos.y()
            prev_col = self.color 
            
            if self.mode == "LINE":
                self.bresenham_line((x1,y1), (x2,y2), prev_col)
            elif self.mode == "RECT":
                self.bresenham_line((x1,y1), (x2,y1), prev_col); self.bresenham_line((x2,y1), (x2,y2), prev_col)
                self.bresenham_line((x2,y2), (x1,y2), prev_col); self.bresenham_line((x1,y2), (x1,y1), prev_col)
            elif self.mode == "SQUARE":
                s = max(abs(x2-x1), abs(y2-y1))
                nx2 = x1 + s if x2 > x1 else x1 - s; ny2 = y1 + s if y2 > y1 else y1 - s
                self.bresenham_line((x1,y1), (nx2,y1), prev_col); self.bresenham_line((nx2,y1), (nx2,ny2), prev_col)
                self.bresenham_line((nx2,ny2), (x1,ny2), prev_col); self.bresenham_line((x1,ny2), (x1,y1), prev_col)
            elif self.mode == "TRIANGLE":
                s = abs(x2 - x1)
                h = s * math.sqrt(3) / 2
                dy = 1 if y2 > y1 else -1
                
                p1 = (int((x1 + x2) / 2), int(y1))
                p2 = (int(x1), int(y1 + dy * h))
                p3 = (int(x2), int(y1 + dy * h))
                
                self.bresenham_line(p1, p2, prev_col)
                self.bresenham_line(p2, p3, prev_col)
                self.bresenham_line(p3, p1, prev_col)
            elif self.mode == "CIRCLE":
                r = math.hypot(x2-x1, y2-y1)
                self.midpoint_circle(int(x1), int(y1), int(r), prev_col)
            elif self.mode == "ELLIPSE":
                xc, yc = (x1+x2)/2, (y1+y2)/2
                rx, ry = abs(x2-x1)/2, abs(y2-y1)/2
                self.midpoint_ellipse(int(xc), int(yc), int(rx), int(ry), prev_col)
        
        self.update()

    # --- 7. MOUSE EVENTS ---
    def mousePressEvent(self, event):
        mouse_pos = event.pos()
        self.last_mouse_pos = mouse_pos
        self.selected_index = self.get_object_at(mouse_pos.x(), mouse_pos.y())
        
        # Mode Interaktif FILL (Cat)
        if self.mode == "FILL":
            if self.selected_index != -1 and self.shapes[self.selected_index]['type'] != 'LINE':
                self.shapes[self.selected_index]['fill_color'] = self.color
                self.save_state()
            self.redraw_canvas()
            return

        if self.mode.startswith("T_") and self.selected_index != -1: 
            self.dragging = True
        elif not self.mode.startswith("T_") and self.mode != "FILL": 
            self.start_pos = mouse_pos
            self.curr_mouse_pos = mouse_pos 
        self.redraw_canvas()

    def mouseMoveEvent(self, event):
        curr_pos = event.pos()
        
        if self.dragging and self.selected_index != -1 and self.last_mouse_pos:
            dx, dy = curr_pos.x() - self.last_mouse_pos.x(), curr_pos.y() - self.last_mouse_pos.y()
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
            
            self.apply_matrix_live(mat)
            self.last_mouse_pos = curr_pos
            self.redraw_canvas()
            
        elif not self.mode.startswith("T_") and self.mode != "FILL" and hasattr(self, 'start_pos') and self.start_pos:
            self.curr_mouse_pos = curr_pos
            self.redraw_canvas()

    def mouseReleaseEvent(self, event):
        action_taken = False
        
        if not self.mode.startswith("T_") and self.mode != "FILL" and hasattr(self, 'start_pos') and self.start_pos:
            x1, y1, x2, y2 = self.start_pos.x(), self.start_pos.y(), event.pos().x(), event.pos().y()
            
            # Default Fill Color selalu 'None', user harus menekan Menu Fill
            new_shape = {'color': self.color, 'fill_color': None, 'type': self.mode}
            
            if self.mode == "RECT": new_shape['pts'] = [(x1,y1), (x2,y1), (x2,y2), (x1,y2)]
            elif self.mode == "SQUARE":
                s = max(abs(x2-x1), abs(y2-y1))
                nx2, ny2 = (x1+s if x2>x1 else x1-s), (y1+s if y2>y1 else y1-s)
                new_shape['pts'] = [(x1,y1), (nx2,y1), (nx2,ny2), (x1,ny2)]
            elif self.mode == "TRIANGLE": 
                s = abs(x2 - x1)
                h = s * math.sqrt(3) / 2
                dy = 1 if y2 > y1 else -1
                
                p1 = (int((x1 + x2) / 2), int(y1))
                p2 = (int(x1), int(y1 + dy * h))
                p3 = (int(x2), int(y1 + dy * h))
                
                new_shape['pts'] = [p1, p2, p3]
            elif self.mode == "LINE": new_shape['pts'] = [(x1,y1), (x2,y2)]
            elif self.mode == "CIRCLE":
                r = math.hypot(x2-x1, y2-y1)
                new_shape['params'] = {'xc': x1, 'yc': y1, 'r': r}
            elif self.mode == "ELLIPSE":
                xc, yc = (x1+x2)/2, (y1+y2)/2
                new_shape['params'] = {'xc': xc, 'yc': yc, 'rx': abs(x2-x1)/2, 'ry': abs(y2-y1)/2}

            if 'pts' in new_shape or 'params' in new_shape:
                self.shapes.append(new_shape)
                self.selected_index = len(self.shapes) - 1
                action_taken = True
        elif self.dragging:
            action_taken = True 
                
        self.dragging = False
        self.start_pos = None
        self.curr_mouse_pos = None
        self.redraw_canvas()
        
        if action_taken:
            self.save_state()

    def paintEvent(self, event): QPainter(self).drawImage(0, 0, self.image)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("KelDraw - Raster Graphics Editor")
        self.canvas = Canvas()
        self.init_ui()

    def init_ui(self):
        # 1. TOOLBAR ATAS 
        toolbar = QToolBar("Main Tools")
        self.addToolBar(toolbar)

        # Cursor and Delete group
        cursor_btn = QAction("Cursor (Select/Move)", self)
        cursor_btn.triggered.connect(lambda: self.set_mode("CURSOR")) 
        toolbar.addAction(cursor_btn)
        
        delete_btn = QAction("Delete", self)
        delete_btn.triggered.connect(self.canvas.delete_selected)
        toolbar.addAction(delete_btn)
        
        toolbar.addSeparator()

        # Shapes & Tools group
        toolbar.addWidget(QLabel("  <b>SHAPES & TOOLS:</b>  "))
        for name, m in [("Line", "LINE"), ("Rect", "RECT"), ("Square", "SQUARE"), 
                        ("Triangle", "TRIANGLE"), ("Circle", "CIRCLE"), ("Ellipse", "ELLIPSE"),
                        ("Fill Bucket", "FILL")]:
            a = QAction(name, self)
            a.triggered.connect(lambda ch, mode=m: self.set_mode(mode))
            toolbar.addAction(a)
        toolbar.addSeparator()

        # Transforms group
        toolbar.addWidget(QLabel("  <b>TRANSFORMS:</b>  "))
        for name, m in [("Rotate", "T_ROTATE"), ("Scale", "T_SCALE"), ("Shear", "T_SHEAR")]:
            a = QAction(name, self)
            a.triggered.connect(lambda ch, mode=m: self.set_mode(mode))
            toolbar.addAction(a)
            
        toolbar.addSeparator()
        
        flip_x = QAction("Flip X", self)
        flip_x.triggered.connect(lambda: self.canvas.flip_object('X'))
        toolbar.addAction(flip_x)

        flip_y = QAction("Flip Y", self)
        flip_y.triggered.connect(lambda: self.canvas.flip_object('Y'))
        toolbar.addAction(flip_y)

        # 2. SIDEBAR KIRI
        central_widget = QWidget()
        main_layout = QHBoxLayout(central_widget)
        sidebar = QVBoxLayout()
        
        # --- Group Warna Global (Preset + Color Dialog) ---
        color_group = QGroupBox("Colors")
        c_layout = QVBoxLayout()
        
        # Preset Colors berbentuk kotak melingkar (HBoxLayout)
        preset_layout = QHBoxLayout()
        preset_colors = [
            ("Red", Qt.GlobalColor.red), 
            ("Blue", Qt.GlobalColor.blue), 
            ("Green", Qt.GlobalColor.green), 
            ("Black", Qt.GlobalColor.black), 
            ("White", Qt.GlobalColor.white)
        ]
        
        for name, code in preset_colors:
            btn = QPushButton()
            btn.setFixedSize(30, 30)
            hex_color = QColor(code).name()
            # Style bulat layaknya palette warna
            btn.setStyleSheet(f"background-color: {hex_color}; border: 1px solid gray; border-radius: 15px;")
            btn.setToolTip(name)
            btn.clicked.connect(lambda ch, c=code: self.set_preset_color(c))
            preset_layout.addWidget(btn)
            
        c_layout.addLayout(preset_layout)
        
        # Color Chooser (QColorDialog)
        self.btn_pick_color = QPushButton("Color Chooser")
        self.btn_pick_color.setStyleSheet("background-color: black; color: white; font-weight: bold; padding: 10px; margin-top: 5px;")
        self.btn_pick_color.clicked.connect(self.pick_color)
        c_layout.addWidget(self.btn_pick_color)
        
        # Apply Actions
        btn_apply_outline = QPushButton("Apply Outline to Selected") 
        btn_apply_outline.clicked.connect(self.apply_global_outline)
        c_layout.addWidget(btn_apply_outline)

        btn_apply_fill = QPushButton("Apply Fill to Selected") 
        btn_apply_fill.clicked.connect(self.apply_global_fill)
        c_layout.addWidget(btn_apply_fill)
        
        color_group.setLayout(c_layout)

        # --- Group History (Undo/Redo) ---
        history_group = QGroupBox("History")
        h_layout = QHBoxLayout()
        btn_undo = QPushButton("Undo")
        btn_undo.setStyleSheet("background-color: #555; color: white;")
        btn_undo.clicked.connect(self.canvas.undo)
        
        btn_redo = QPushButton("Redo")
        btn_redo.setStyleSheet("background-color: #555; color: white;")
        btn_redo.clicked.connect(self.canvas.redo)
        
        h_layout.addWidget(btn_undo)
        h_layout.addWidget(btn_redo)
        history_group.setLayout(h_layout)

        # Penempatan Sidebar
        sidebar.addWidget(color_group)
        sidebar.addStretch()
        sidebar.addWidget(history_group) 

        main_layout.addLayout(sidebar)
        main_layout.addWidget(self.canvas)
        self.setCentralWidget(central_widget)
        self.statusBar().showMessage("Ready. Default color is Black. Use English menu.")

    def set_mode(self, mode):
        internal_mode = "T_MOVE" if mode == "CURSOR" else mode
        self.canvas.mode = internal_mode
        self.statusBar().showMessage(f"Active Mode: {mode}")

    def set_preset_color(self, code):
        color = QColor(code)
        self.canvas.color = color
        brightness = (color.red() * 299 + color.green() * 587 + color.blue() * 114) / 1000
        txt_color = 'black' if brightness > 128 else 'white'
        self.btn_pick_color.setStyleSheet(f"background-color: {color.name()}; color: {txt_color}; font-weight: bold; padding: 10px; margin-top: 5px;")
        self.statusBar().showMessage(f"Global Color set to: {color.name()}")

    def pick_color(self):
        color = QColorDialog.getColor(self.canvas.color, self, "Pick Global Color")
        if color.isValid():
            self.canvas.color = color
            brightness = (color.red() * 299 + color.green() * 587 + color.blue() * 114) / 1000
            txt_color = 'black' if brightness > 128 else 'white'
            self.btn_pick_color.setStyleSheet(f"background-color: {color.name()}; color: {txt_color}; font-weight: bold; padding: 10px; margin-top: 5px;")
            self.statusBar().showMessage(f"Global Color set to: {color.name()}")

    def apply_global_outline(self):
        idx = self.canvas.selected_index
        if idx != -1:
            self.canvas.shapes[idx]['color'] = self.canvas.color
            self.canvas.redraw_canvas()
            self.canvas.save_state() 
            self.statusBar().showMessage("Outline color applied to selected object.")

    def apply_global_fill(self):
        idx = self.canvas.selected_index
        if idx != -1:
            if self.canvas.shapes[idx]['type'] != "LINE":
                self.canvas.shapes[idx]['fill_color'] = self.canvas.color
            self.canvas.redraw_canvas()
            self.canvas.save_state() 
            self.statusBar().showMessage("Fill color applied to selected object.")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())