"""Small line icons for the sidebar, drawn in the current system text color."""
import math
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QIcon, QIconEngine, QPainter, QPainterPath, QPalette, QPen, QPixmap
from PySide6.QtWidgets import QApplication


class SidebarIcon(QIconEngine):
    def __init__(self, kind):
        super().__init__()
        self.kind = kind

    def clone(self):
        return SidebarIcon(self.kind)

    def pixmap(self, size, mode, state):
        pixmap = QPixmap(size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        self.paint(painter, pixmap.rect(), mode, state)
        painter.end()
        return pixmap

    def paint(self, painter, rect, mode, state):
        palette = QApplication.palette()
        group = QPalette.Disabled if mode == QIcon.Disabled else QPalette.Active
        pen = QPen(palette.color(group, QPalette.Text), 1.4)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        edge = min(rect.width(), rect.height())
        painter.translate(rect.center().x() - edge/2, rect.center().y() - edge/2)
        painter.scale(edge/20, edge/20)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        self.draw(painter)
        painter.restore()

    @staticmethod
    def line(painter, *points):
        path = QPainterPath(QPointF(*points[0]))
        for point in points[1:]:
            path.lineTo(QPointF(*point))
        painter.drawPath(path)

    def draw(self, painter):
        if self.kind == 'folder':
            self.line(painter, (2.5, 16), (2.5, 5), (7.5, 5), (9.5, 7),
                      (17.5, 7), (17.5, 16), (2.5, 16))
        elif self.kind == 'camera':
            painter.drawRoundedRect(QRectF(2.5, 6, 15, 11), 2, 2)
            painter.drawEllipse(QRectF(7, 8.5, 6, 6))
            self.line(painter, (6, 6), (7.5, 3.5), (12.5, 3.5), (14, 6))
        elif self.kind == 'settings':
            path = QPainterPath()
            for index in range(32):
                angle = math.tau * index/32
                radius = 7.5 if index % 4 in (1, 2) else 5.9
                point = QPointF(10 + radius*math.cos(angle), 10 + radius*math.sin(angle))
                if index == 0:
                    path.moveTo(point)
                else:
                    path.lineTo(point)
            path.closeSubpath()
            painter.drawPath(path)
            painter.drawEllipse(QRectF(7.5, 7.5, 5, 5))
        elif self.kind == 'new':
            self.line(painter, (10, 3.5), (10, 16.5))
            self.line(painter, (3.5, 10), (16.5, 10))
        elif self.kind == 'image':
            painter.drawRoundedRect(QRectF(3, 3, 14, 14), 2, 2)
            painter.drawEllipse(QRectF(6, 6, 2.5, 2.5))
            self.line(painter, (3.5, 14), (8, 10), (11, 13), (13.5, 10.5), (16.5, 13))
        elif self.kind == 'edit':
            self.line(painter, (4, 12.5), (13.5, 3), (17, 6.5), (7.5, 16), (3, 17), (4, 12.5))
            self.line(painter, (11.5, 5), (15, 8.5))
        else:  # saved session or metadata report
            self.line(painter, (4, 3), (12, 3), (16, 7), (16, 17), (4, 17), (4, 3))
            self.line(painter, (12, 3), (12, 7), (16, 7))
            self.line(painter, (7, 10), (13, 10))
            self.line(painter, (7, 13), (12, 13))


def sidebar_icon(kind):
    return QIcon(SidebarIcon(kind))
