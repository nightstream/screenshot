# coding=utf-8

from math import sqrt

from PySide6.QtCore import Qt, QRect, QPoint, QRectF, QSize, QLineF, QPointF, QEventLoop, Signal
from PySide6.QtGui import QColor, QPainterPath, QKeySequence, QGuiApplication, QPen, QBrush, QImage, \
    QPolygonF, QClipboard, QCursor, QMouseEvent, QShortcut, QFont, QPixmap, QPainter
from PySide6.QtWidgets import QApplication, QGraphicsScene, QFileDialog, QWidget

from .constant import RECT, ELLIPSE, ARROW, LINE, FREEPEN, TEXT, DEFAULT, ACTION_LINE, ACTION_FREEPEN, \
    ACTION_SELECT, ACTION_MOVE_SELECTED, ACTION_RECT, ACTION_ELLIPSE, ACTION_ARROW, ACTION_TEXT, ACTION_UNDO, \
    ACTION_SAVE, ACTION_CANCEL, ACTION_SURE, DRAW_ACTION, ERRORRANGE, PENCOLOR, PENSIZE, MousePosition
from .basewidget import BaseGraphicsView
from .toolbar import ToolBar
from .colorbar import PenSetWidget
from .textinput import TextInput

qtApp = None


class Screenshot(BaseGraphicsView):
    """
    截图操作类

    QGraphicscene类为管理大量二维图形项提供了界面, QGraphicsView类提供部件, 用于显示QGraphicscene的内容
    """

    screen_shot_grabed = Signal(QImage)
    widget_closed = Signal()

    def __init__(self, flags: int = DEFAULT, parent: QWidget = None):
        """
        flags: binary flags. see the flags in the constant.py
        """
        super().__init__(parent)

        # Init
        self.penColorNow = QColor(PENCOLOR)
        self.penSizeNow = PENSIZE
        self.fontNow = QFont('Sans')
        self.clipboard = QApplication.clipboard()

        self.drawListResult = []  # 存放已经完成的绘制信息, 格式: [绘制类型, 坐标信息...]
        self.drawListProcess = None  # 正在进行的绘制, 鼠标左键仍在拖动, mouseMoveEvent导致时刻重绘中
        self.selected_area = QRect()  # 用户使用鼠标选定的截图/绘图区
        self.selectedAreaRaw = QRect()
        self.mousePosition = MousePosition.OUTSIDE_AREA  # 按类型记录鼠标当前的位置
        self.textRect = None

        self.mousePressed = False
        self.action = ACTION_SELECT  # 首先第一步默认是选择操作区
        self.mousePoint = self.cursor().pos()  # 鼠标位置，移动时赋值，绘制放大镜时使用

        self.startX, self.startY = 0, 0  # 鼠标按下时的起点信息
        self.endX, self.endY = 0, 0  # 鼠标松开时的终点信息
        self.pointPath = QPainterPath()  # 自由绘制时鼠标移动过的路径
        self.items_to_remove = []  # the items that should not draw on screenshot picture
        self.textPosition = None

        self.target_img = None  # 截图结果 QPixmap

        # Init window
        self.getscreenshot()
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)  # 窗口无边框且保持在最顶层

        self.setMouseTracking(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)  # 关闭水平滚动
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)  # 关闭垂直滚动
        self.setContentsMargins(0, 0, 0, 0)
        self.setStyleSheet("QGraphicsView { border-style: none; }")

        self.tooBar = ToolBar(flags, self)
        self.tooBar.trigger.connect(self.changeAction)

        self.penSetBar = None
        if flags & RECT or flags & ELLIPSE or flags & LINE or flags & FREEPEN or flags & ARROW or flags & TEXT:
            self.penSetBar = PenSetWidget(self)
            self.penSetBar.penSizeTrigger.connect(self.changePenSize)
            self.penSetBar.penColorTrigger.connect(self.changePenColor)
            self.penSetBar.fontChangeTrigger.connect(self.changeFont)

        self.textInput = TextInput(self)
        self.textInput.inputChanged.connect(self.textChange)
        self.textInput.cancelPressed.connect(self.cancelInput)
        self.textInput.okPressed.connect(self.okInput)

        self.show()
        # 创建scene, 参数左上角坐标和长宽
        self.graphics_scene = QGraphicsScene(0, 0, self.screenPixel.width(), self.screenPixel.height())
        self.setScene(self.graphics_scene)
        self.scale = self.get_scale()
        self.redraw()  # 首次手动调用，绘制背景图、放大镜、蒙板遮罩等控件

        QShortcut(QKeySequence('ctrl+s'), self).activated.connect(self.saveScreenshot)
        QShortcut(QKeySequence('ctrl+z'), self).activated.connect(self.undoOperation)
        QShortcut(QKeySequence('esc'), self).activated.connect(self.close)

    @staticmethod
    def take_screenshot(flags: int) -> QPixmap:
        """執行截圖操作"""
        loop = QEventLoop()
        screen_shot = Screenshot(flags)
        screen_shot.show()
        screen_shot.widget_closed.connect(loop.quit)

        loop.exec()  # 阻塞，等待截圖完成
        img = screen_shot.target_img
        return img

    def makeScreenPixel(self, tw: int, th: int, screenImgs: list):
        """拼接创建背景图"""
        self.screenPixel = QPixmap(QSize(tw, th))  # QPixmap，整体屏幕图
        painter = QPainter(self.screenPixel)
        for x, y, img in screenImgs:
            params = (x - self.topX, y - self.topY, img.width(), img.height(), img)
            painter.drawPixmap(*params)

    def getscreenshot(self):
        """截取静态屏幕作为图片"""
        # todo: 支持多屏截图
        mleft, mtop, mright, mbottom = 0, 0, 0, 0
        screenImgs = []
        for i, screen in enumerate(QGuiApplication.screens()):
            left, top, right, bottom = 0, 0, 0, 0
            geo = screen.geometry()
            if (left := geo.left()) < mleft:
                mleft = left
            if (top := geo.top()) < mtop:
                mtop = top
            if (right := geo.right()) > mright:
                mright = right
            if (bottom := geo.bottom()) > mbottom:
                mbottom = bottom
            screenImgs.append((left, top, screen.grabWindow(0)))
        self.topX, self.topY = mleft, mtop
        self.logger.debug(f"top, left: {mtop} {mleft}")
        self.move(mleft, mtop)  # 移动到最左上角
        self.resize(mright - mleft, mbottom - mtop)  # 重定义到最大大小
        self.makeScreenPixel(mright - mleft, mbottom - mtop, screenImgs)

    def mousePressEvent(self, event: QMouseEvent):
        """
        鼠标按下时触发事件

        确认事件类型(选定区域、准备区域、绘画)
        """
        if event.button() == Qt.RightButton:
            # todo: 选定区域外鼠标右键直接退出，区域内鼠标右键撤销上一步
            return
        if event.button() != Qt.LeftButton:
            return

        if self.action is None:
            self.action = ACTION_SELECT

        self.startX, self.startY = event.x(), event.y()

        if self.action == ACTION_SELECT:
            if self.mousePosition == MousePosition.OUTSIDE_AREA:
                self.mousePressed = True
                self.selected_area = QRect()
                self.selected_area.setTopLeft(QPoint(event.x(), event.y()))
                self.selected_area.setBottomRight(QPoint(event.x(), event.y()))
                self.redraw()
            elif self.mousePosition == MousePosition.INSIDE_AREA:
                self.mousePressed = True
            else:
                pass
        elif self.action == ACTION_MOVE_SELECTED:
            if self.mousePosition == MousePosition.OUTSIDE_AREA:
                self.action = ACTION_SELECT
                self.selected_area = QRect()
                self.selected_area.setTopLeft(QPoint(event.x(), event.y()))
                self.selected_area.setBottomRight(QPoint(event.x(), event.y()))
                self.redraw()
            self.mousePressed = True
        elif self.action in DRAW_ACTION:
            self.mousePressed = True
            if self.action == ACTION_FREEPEN:
                self.pointPath = QPainterPath()
                self.pointPath.moveTo(QPoint(event.x(), event.y()))
            elif self.action == ACTION_TEXT:
                if self.textPosition is None:
                    self.textPosition = QPoint(event.x(), event.y())
                    self.textRect = None
                    self.redraw()

    def mouseMoveEvent(self, event: QMouseEvent):
        """
        鼠标移动时触发事件

        执行事件类型指定的操作(直线、矩形、椭圆、文本等)
        """
        self.mousePoint = QPoint(event.x(), event.y())  # 鼠标移动时赋坐标值

        if self.action is None:
            self.action = ACTION_SELECT

        if not self.mousePressed:
            point = QPoint(event.x(), event.y())
            self.detect_mouse_position(point)
            self.setCursorStyle()
            self.redraw()
        else:
            self.endX, self.endY = event.x(), event.y()

            # if self.mousePosition != OUTSIDE_AREA:
            #    self.action = ACTION_MOVE_SELECTED

            if self.action == ACTION_SELECT:
                self.selected_area.setBottomRight(QPoint(event.x(), event.y()))
                self.redraw()
            elif self.action == ACTION_MOVE_SELECTED:
                self.selected_area = QRect(self.selectedAreaRaw)

                if self.mousePosition == MousePosition.INSIDE_AREA:
                    move_to_x = event.x() - self.startX + self.selected_area.left()
                    move_to_y = event.y() - self.startY + self.selected_area.top()
                    if 0 <= move_to_x <= self.screenPixel.width() - 1 - self.selected_area.width():
                        self.selected_area.moveLeft(move_to_x)
                    if 0 <= move_to_y <= self.screenPixel.height() - 1 - self.selected_area.height():
                        self.selected_area.moveTop(move_to_y)
                    self.selected_area = self.selected_area.normalized()
                    self.selectedAreaRaw = QRect(self.selected_area)
                    self.startX, self.startY = event.x(), event.y()
                    self.redraw()
                elif self.mousePosition == MousePosition.ON_THE_LEFT_SIDE:
                    move_to_x = event.x() - self.startX + self.selected_area.left()
                    if move_to_x <= self.selected_area.right():
                        self.selected_area.setLeft(move_to_x)
                        self.selected_area = self.selected_area.normalized()
                        self.redraw()
                elif self.mousePosition == MousePosition.ON_THE_RIGHT_SIDE:
                    move_to_x = event.x() - self.startX + self.selected_area.right()
                    self.selected_area.setRight(move_to_x)
                    self.selected_area = self.selected_area.normalized()
                    self.redraw()
                elif self.mousePosition == MousePosition.ON_THE_UP_SIDE:
                    move_to_y = event.y() - self.startY + self.selected_area.top()
                    self.selected_area.setTop(move_to_y)
                    self.selected_area = self.selected_area.normalized()
                    self.redraw()
                elif self.mousePosition == MousePosition.ON_THE_DOWN_SIDE:
                    move_to_y = event.y() - self.startY + self.selected_area.bottom()
                    self.selected_area.setBottom(move_to_y)
                    self.selected_area = self.selected_area.normalized()
                    self.redraw()
                elif self.mousePosition == MousePosition.ON_THE_TOP_LEFT_CORNER:
                    move_to_x = event.x() - self.startX + self.selected_area.left()
                    move_to_y = event.y() - self.startY + self.selected_area.top()
                    self.selected_area.setTopLeft(QPoint(move_to_x, move_to_y))
                    self.selected_area = self.selected_area.normalized()
                    self.redraw()
                elif self.mousePosition == MousePosition.ON_THE_BOTTOM_RIGHT_CORNER:
                    move_to_x = event.x() - self.startX + self.selected_area.right()
                    move_to_y = event.y() - self.startY + self.selected_area.bottom()
                    self.selected_area.setBottomRight(QPoint(move_to_x, move_to_y))
                    self.selected_area = self.selected_area.normalized()
                    self.redraw()
                elif self.mousePosition == MousePosition.ON_THE_TOP_RIGHT_CORNER:
                    move_to_x = event.x() - self.startX + self.selected_area.right()
                    move_to_y = event.y() - self.startY + self.selected_area.top()
                    self.selected_area.setTopRight(QPoint(move_to_x, move_to_y))
                    self.selected_area = self.selected_area.normalized()
                    self.redraw()
                elif self.mousePosition == MousePosition.ON_THE_BOTTOM_LEFT_CORNER:
                    move_to_x = event.x() - self.startX + self.selected_area.left()
                    move_to_y = event.y() - self.startY + self.selected_area.bottom()
                    self.selected_area.setBottomLeft(QPoint(move_to_x, move_to_y))
                    self.redraw()
                else:
                    pass
            elif self.action == ACTION_RECT:
                self.drawRect(self.startX, self.startY, event.x(), event.y(), False)
                self.redraw()
                pass
            elif self.action == ACTION_ELLIPSE:
                self.drawEllipse(self.startX, self.startY, event.x(), event.y(), False)
                self.redraw()
            elif self.action == ACTION_ARROW:
                self.drawArrow(self.startX, self.startY, event.x(), event.y(), False)
                self.redraw()
            elif self.action == ACTION_LINE:
                self.drawLine(self.startX, self.startY, event.x(), event.y(), False)
                self.redraw()
            elif self.action == ACTION_FREEPEN:
                y1, y2 = event.x(), event.y()
                rect = self.selected_area.normalized()
                if y1 <= rect.left():
                    y1 = rect.left()
                elif y1 >= rect.right():
                    y1 = rect.right()

                if y2 <= rect.top():
                    y2 = rect.top()
                elif y2 >= rect.bottom():
                    y2 = rect.bottom()

                self.pointPath.lineTo(y1, y2)
                self.drawFreeLine(self.pointPath, False)
                self.redraw()

    def mouseReleaseEvent(self, event: QMouseEvent):
        """松开鼠标, 表示当前动作结束并确认"""
        if event.button() != Qt.LeftButton:
            return

        if self.mousePressed:
            self.mousePressed = False
            self.endX, self.endY = event.x(), event.y()

            if self.action == ACTION_SELECT:
                self.selected_area.setBottomRight(QPoint(event.x(), event.y()))
                self.selectedAreaRaw = QRect(self.selected_area)
                self.action = ACTION_MOVE_SELECTED
                self.redraw()
            elif self.action == ACTION_MOVE_SELECTED:
                self.selectedAreaRaw = QRect(self.selected_area)
                self.redraw()
                # self.action = None
            elif self.action == ACTION_RECT:
                self.drawRect(self.startX, self.startY, event.x(), event.y(), True)
                self.redraw()
            elif self.action == ACTION_ELLIPSE:
                self.drawEllipse(self.startX, self.startY, event.x(), event.y(), True)
                self.redraw()
            elif self.action == ACTION_ARROW:
                self.drawArrow(self.startX, self.startY, event.x(), event.y(), True)
                self.redraw()
            elif self.action == ACTION_LINE:
                self.drawLine(self.startX, self.startY, event.x(), event.y(), True)
                self.redraw()
            elif self.action == ACTION_FREEPEN:
                self.drawFreeLine(self.pointPath, True)
                self.redraw()

    def detect_mouse_position(self, point: QPoint):
        """当鼠标未按下时, 检测鼠标所在的区域位置"""
        if self.selected_area == QRect():
            self.mousePosition = MousePosition.OUTSIDE_AREA
            return

        if self.selected_area.left() - ERRORRANGE <= point.x() <= self.selected_area.left() and (
                self.selected_area.top() - ERRORRANGE <= point.y() <= self.selected_area.top()):
            self.mousePosition = MousePosition.ON_THE_TOP_LEFT_CORNER
        elif self.selected_area.right() <= point.x() <= self.selected_area.right() + ERRORRANGE and (
                self.selected_area.top() - ERRORRANGE <= point.y() <= self.selected_area.top()):
            self.mousePosition = MousePosition.ON_THE_TOP_RIGHT_CORNER
        elif self.selected_area.left() - ERRORRANGE <= point.x() <= self.selected_area.left() and (
                self.selected_area.bottom() <= point.y() <= self.selected_area.bottom() + ERRORRANGE):
            self.mousePosition = MousePosition.ON_THE_BOTTOM_LEFT_CORNER
        elif self.selected_area.right() <= point.x() <= self.selected_area.right() + ERRORRANGE and (
                self.selected_area.bottom() <= point.y() <= self.selected_area.bottom() + ERRORRANGE):
            self.mousePosition = MousePosition.ON_THE_BOTTOM_RIGHT_CORNER
        elif -ERRORRANGE <= point.x() - self.selected_area.left() <= 0 and (
                self.selected_area.topLeft().y() < point.y() < self.selected_area.bottomLeft().y()):
            self.mousePosition = MousePosition.ON_THE_LEFT_SIDE
        elif 0 <= point.x() - self.selected_area.right() <= ERRORRANGE and (
                self.selected_area.topRight().y() < point.y() < self.selected_area.bottomRight().y()):
            self.mousePosition = MousePosition.ON_THE_RIGHT_SIDE
        elif -ERRORRANGE <= point.y() - self.selected_area.top() <= 0 and (
                self.selected_area.topLeft().x() < point.x() < self.selected_area.topRight().x()):
            self.mousePosition = MousePosition.ON_THE_UP_SIDE
        elif 0 <= point.y() - self.selected_area.bottom() <= ERRORRANGE and (
                self.selected_area.bottomLeft().x() < point.x() < self.selected_area.bottomRight().x()):
            self.mousePosition = MousePosition.ON_THE_DOWN_SIDE
        elif not self.selected_area.contains(point):
            self.mousePosition = MousePosition.OUTSIDE_AREA
        else:
            self.mousePosition = MousePosition.INSIDE_AREA

    def setCursorStyle(self):
        """设置鼠标样式"""
        if self.action in DRAW_ACTION:
            self.setCursor(Qt.CrossCursor)
            return

        if self.mousePosition == MousePosition.ON_THE_LEFT_SIDE or \
                self.mousePosition == MousePosition.ON_THE_RIGHT_SIDE:

            self.setCursor(Qt.SizeHorCursor)
        elif self.mousePosition == MousePosition.ON_THE_UP_SIDE or \
                self.mousePosition == MousePosition.ON_THE_DOWN_SIDE:

            self.setCursor(Qt.SizeVerCursor)
        elif self.mousePosition == MousePosition.ON_THE_TOP_LEFT_CORNER or \
                self.mousePosition == MousePosition.ON_THE_BOTTOM_RIGHT_CORNER:

            self.setCursor(Qt.SizeFDiagCursor)
        elif self.mousePosition == MousePosition.ON_THE_TOP_RIGHT_CORNER or \
                self.mousePosition == MousePosition.ON_THE_BOTTOM_LEFT_CORNER:

            self.setCursor(Qt.SizeBDiagCursor)
        elif self.mousePosition == MousePosition.OUTSIDE_AREA:
            self.setCursor(Qt.ArrowCursor)
        elif self.mousePosition == MousePosition.INSIDE_AREA:
            self.setCursor(Qt.OpenHandCursor)
        else:
            self.setCursor(Qt.ArrowCursor)
            pass

    def drawMagnifier(self):
        """绘制放大镜"""
        # todo: 重新resize选定区域时也需要放大镜
        watch_area_width = 16
        watch_area_height = 16

        cursor_pos = self.mousePoint

        watch_area = QRect(QPoint(cursor_pos.x() - watch_area_width / 2, cursor_pos.y() - watch_area_height / 2),
                           QPoint(cursor_pos.x() + watch_area_width / 2, cursor_pos.y() + watch_area_height / 2))
        if watch_area.left() < 0:
            watch_area.moveLeft(0)
            watch_area.moveRight(watch_area_width)
        if self.mousePoint.x() + watch_area_width / 2 >= self.screenPixel.width():
            watch_area.moveRight(self.screenPixel.width() - 1)
            watch_area.moveLeft(watch_area.right() - watch_area_width)
        if self.mousePoint.y() - watch_area_height / 2 < 0:
            watch_area.moveTop(0)
            watch_area.moveBottom(watch_area_height)
        if self.mousePoint.y() + watch_area_height / 2 >= self.screenPixel.height():
            watch_area.moveBottom(self.screenPixel.height() - 1)
            watch_area.moveTop(watch_area.bottom() - watch_area_height)

        # tricks to solve the hidpi impact on QCursor.pos()
        watch_area.setTopLeft(QPoint(watch_area.topLeft().x() * self.scale, watch_area.topLeft().y() * self.scale))
        watch_area.setBottomRight(
            QPoint(watch_area.bottomRight().x() * self.scale, watch_area.bottomRight().y() * self.scale))
        watch_area_pixmap = self.screenPixel.copy(watch_area)

        # second, calculate the magnifier area
        magnifier_area_width = watch_area_width * 10
        magnifier_area_height = watch_area_height * 10
        font_area_height = 40

        cursor_size = 24
        magnifier_area = QRectF(QPoint(cursor_pos.x() + cursor_size, cursor_pos.y() + cursor_size),
                                QPoint(cursor_pos.x() + cursor_size + magnifier_area_width,
                                       cursor_pos.y() + cursor_size + magnifier_area_height))
        if magnifier_area.right() >= self.screenPixel.width():
            magnifier_area.moveLeft(cursor_pos.x() - magnifier_area_width - cursor_size / 2)
        if magnifier_area.bottom() + font_area_height >= self.screenPixel.height():
            magnifier_area.moveTop(cursor_pos.y() - magnifier_area_height - cursor_size / 2 - font_area_height)

        # third, draw the watch area to magnifier area
        watch_area_scaled = watch_area_pixmap.scaled(
            QSize(magnifier_area_width * self.scale, magnifier_area_height * self.scale))
        magnifier_pixmap = self.graphics_scene.addPixmap(watch_area_scaled)
        magnifier_pixmap.setOffset(magnifier_area.topLeft())

        # then draw lines and text
        self.graphics_scene.addRect(QRectF(magnifier_area), QPen(QColor(255, 255, 255), 2))
        self.graphics_scene.addLine(QLineF(QPointF(magnifier_area.center().x(), magnifier_area.top()),
                                           QPointF(magnifier_area.center().x(), magnifier_area.bottom())),
                                    QPen(QColor(0, 255, 255), 2))
        self.graphics_scene.addLine(QLineF(QPointF(magnifier_area.left(), magnifier_area.center().y()),
                                           QPointF(magnifier_area.right(), magnifier_area.center().y())),
                                    QPen(QColor(0, 255, 255), 2))

        # get the rgb of mouse point
        point_rgb = QColor(self.screenPixel.toImage().pixel(self.mousePoint))

        # draw information
        self.graphics_scene.addRect(QRectF(magnifier_area.bottomLeft(),
                                           magnifier_area.bottomRight() + QPoint(0, font_area_height + 30)),
                                    QPen(Qt.black, 2),
                                    QBrush(Qt.black))
        rgb_info = self.graphics_scene.addSimpleText(
            ' Rgb: ({0}, {1}, {2})'.format(point_rgb.red(), point_rgb.green(), point_rgb.blue()))
        rgb_info.setPos(magnifier_area.bottomLeft() + QPoint(0, 5))
        rgb_info.setPen(QPen(QColor(255, 255, 255), 2))

        rect = self.selected_area.normalized()
        size_info = self.graphics_scene.addSimpleText(
            ' Size: {0} x {1}'.format(rect.width() * self.scale, rect.height() * self.scale))
        size_info.setPos(magnifier_area.bottomLeft() + QPoint(0, 15) + QPoint(0, font_area_height / 2))
        size_info.setPen(QPen(QColor(255, 255, 255), 2))

    def get_scale(self):
        return self.devicePixelRatio()

    def saveScreenshot(self, clipboard: bool = False, fileName: str = 'screenshot.png', picType: str = 'png'):
        """保存截图结果"""
        fullWindow = QRect(0, 0, self.width() - 1, self.height() - 1)
        selected = QRect(self.selected_area)
        if selected.left() < 0:
            selected.setLeft(0)
        if selected.right() >= self.width():
            selected.setRight(self.width() - 1)
        if selected.top() < 0:
            selected.setTop(0)
        if selected.bottom() >= self.height():
            selected.setBottom(self.height() - 1)

        source = (fullWindow & selected)
        source.setTopLeft(QPoint(source.topLeft().x() * self.scale, source.topLeft().y() * self.scale))
        source.setBottomRight(QPoint(source.bottomRight().x() * self.scale, source.bottomRight().y() * self.scale))
        image = self.grab(source)

        if clipboard:
            QGuiApplication.clipboard().setImage(image.toImage(), QClipboard.Clipboard)
        else:
            image.save(fileName, picType, 10)
        self.target_img = image
        self.screen_shot_grabed.emit(image.toImage())

    def redraw(self):
        """重新绘画全部內容"""
        # todo: 所有的绘画图形需要可重新编辑和拖动
        self.graphics_scene.clear()

        # 绘制背景图
        self.graphics_scene.addPixmap(self.screenPixel)

        # 准备所选的绘画区域
        rect = QRectF(self.selected_area).normalized()  # normalized：返回不含负高和负宽的矩形

        top_left_point = rect.topLeft()  # 操作区左上角
        top_right_point = rect.topRight()  # 操作区右上角
        bottom_left_point = rect.bottomLeft()  # 操作区左下角
        bottom_right_point = rect.bottomRight()  # 操作区右下角
        top_middle_point = (top_left_point + top_right_point) / 2
        left_middle_point = (top_left_point + bottom_left_point) / 2
        bottom_middle_point = (bottom_left_point + bottom_right_point) / 2
        right_middle_point = (top_right_point + bottom_right_point) / 2

        # 添加截图蒙版和遮罩
        mask = QColor(0, 0, 0, 155)
        if self.selected_area == QRect():
            # 未选择，全图添加遮罩
            self.graphics_scene.addRect(0, 0, self.screenPixel.width(), self.screenPixel.height(), QPen(Qt.NoPen), mask)
        else:
            # 已有作图区，以下4行绘制上半部遮罩、左半部遮罩、右半部遮罩、下半部遮罩
            self.graphics_scene.addRect(0, 0, self.screenPixel.width(), top_right_point.y(), QPen(Qt.NoPen), mask)
            self.graphics_scene.addRect(0, top_left_point.y(), top_left_point.x(), rect.height(), QPen(Qt.NoPen), mask)
            self.graphics_scene.addRect(top_right_point.x(), top_right_point.y(),
                                        self.screenPixel.width() - top_right_point.x(),
                                        rect.height(), QPen(Qt.NoPen), mask)
            self.graphics_scene.addRect(0, bottom_left_point.y(), self.screenPixel.width(),
                                        self.screenPixel.height() - bottom_left_point.y(),
                                        QPen(Qt.NoPen), mask)

        # 绘制工具栏
        if self.action != ACTION_SELECT:
            # 先展示工具栏，然后将工具栏移动到正确位置，因为首次展示时工具栏的宽度可能是错误的
            spacing = 5  # 设置间距
            self.tooBar.show()

            # dest 工具条左上角坐标：操作区右下角 - (工具条宽度，)
            self.logger.info(f"{bottom_right_point}")
            dest = QPointF(bottom_right_point - QPointF(self.tooBar.width() - spacing - self.topX, spacing))
            if dest.x() < spacing + self.topX:
                dest.setX(spacing + self.topX)
            pen_set_bar_height = self.penSetBar.height() if self.penSetBar is not None else 0
            if dest.y() + self.tooBar.height() + pen_set_bar_height >= self.height():
                # 边缘已到屏幕最下
                if rect.top() - self.tooBar.height() - pen_set_bar_height < spacing:
                    # 上方边缘空余不足
                    dest.setY(rect.top() + spacing)  # 设置到边缘下方，操作区内
                else:
                    dest.setY(rect.top() - self.tooBar.height() - pen_set_bar_height - spacing)

            self.tooBar.move(dest.toPoint())

            if self.penSetBar is not None:
                self.penSetBar.show()
                self.penSetBar.move(dest.toPoint() + QPoint(0, self.tooBar.height() + spacing))

                if self.action == ACTION_TEXT:
                    self.penSetBar.showFontWidget()
                else:
                    self.penSetBar.showPenWidget()
        else:
            self.tooBar.hide()

            if self.penSetBar is not None:
                self.penSetBar.hide()

        # 所有操作全部重新執行
        for step in self.drawListResult:
            self.drawOneStep(step)

        if self.drawListProcess is not None:
            self.drawOneStep(self.drawListProcess)
            if self.action != ACTION_TEXT:
                self.drawListProcess = None

        if self.selected_area != QRect():
            self.items_to_remove = []

            # 绘制截图区域的选定框
            pen = QPen(QColor(0, 255, 255), 2)
            self.items_to_remove.append(self.graphics_scene.addRect(rect, pen))

            # 绘制截图区选定框的拖动点
            radius = QPoint(3, 3)
            brush = QBrush(QColor(0, 255, 255))
            self.items_to_remove.append(
                self.graphics_scene.addEllipse(QRectF(top_left_point - radius, top_left_point + radius), pen, brush))
            self.items_to_remove.append(
                self.graphics_scene.addEllipse(QRectF(top_middle_point - radius, top_middle_point + radius), pen, brush))
            self.items_to_remove.append(
                self.graphics_scene.addEllipse(QRectF(top_right_point - radius, top_right_point + radius), pen, brush))
            self.items_to_remove.append(
                self.graphics_scene.addEllipse(QRectF(left_middle_point - radius, left_middle_point + radius), pen, brush))
            self.items_to_remove.append(
                self.graphics_scene.addEllipse(QRectF(right_middle_point - radius, right_middle_point + radius), pen, brush))
            self.items_to_remove.append(
                self.graphics_scene.addEllipse(QRectF(bottom_left_point - radius, bottom_left_point + radius), pen, brush))
            self.items_to_remove.append(
                self.graphics_scene.addEllipse(QRectF(bottom_middle_point - radius, bottom_middle_point + radius), pen,
                                               brush))
            self.items_to_remove.append(
                self.graphics_scene.addEllipse(QRectF(bottom_right_point - radius, bottom_right_point + radius), pen, brush))

        # 绘制文字编辑控件
        if self.textPosition is not None:
            # textSpacing = 50
            position = QPoint()
            if self.textPosition.x() + self.textInput.width() >= self.screenPixel.width():
                position.setX(self.textPosition.x() - self.textInput.width())
            else:
                position.setX(self.textPosition.x())

            if self.textRect is not None:
                if self.textPosition.y() + self.textInput.height() + self.textRect.height() >= self.screenPixel.height():
                    position.setY(self.textPosition.y() - self.textInput.height() - self.textRect.height())
                else:
                    position.setY(self.textPosition.y() + self.textRect.height())
            else:
                if self.textPosition.y() + self.textInput.height() >= self.screenPixel.height():
                    position.setY(self.textPosition.y() - self.textInput.height())
                else:
                    position.setY(self.textPosition.y())

            self.textInput.move(position)
            self.textInput.show()
            # self.textInput.getFocus()

        # 绘制放大镜
        if self.action == ACTION_SELECT:
            self.drawMagnifier()
            if self.mousePressed:
                self.drawSizeInfo()

        if self.action == ACTION_MOVE_SELECTED:
            self.drawSizeInfo()

    def drawOneStep(self, step: list[object]):
        """绘画drawListResult中的单个图形"""
        if step[0] == ACTION_RECT:
            self.graphics_scene.addRect(QRectF(QPointF(step[1], step[2]),
                                               QPointF(step[3], step[4])), step[5])
        elif step[0] == ACTION_ELLIPSE:
            self.graphics_scene.addEllipse(QRectF(QPointF(step[1], step[2]),
                                                  QPointF(step[3], step[4])), step[5])
        elif step[0] == ACTION_ARROW:
            arrow = QPolygonF()

            linex = float(step[1] - step[3])
            liney = float(step[2] - step[4])
            line = sqrt(pow(linex, 2) + pow(liney, 2))  # 計算長度

            # 长度为零直接返回
            if line == 0:
                return

            sinAngel = liney / line
            cosAngel = linex / line

            # sideLength is the length of bottom side of the body of an arrow
            # arrowSize is the size of the head of an arrow, left and right
            # sides' size is arrowSize, and the bottom side's size is arrowSize / 2
            sideLength = step[5].width()
            arrowSize = 8
            bottomSize = arrowSize / 2

            tmpPoint = QPointF(step[3] + arrowSize * sideLength * cosAngel, step[4] + arrowSize * sideLength * sinAngel)

            point1 = QPointF(step[1] + sideLength * sinAngel, step[2] - sideLength * cosAngel)
            point2 = QPointF(step[1] - sideLength * sinAngel, step[2] + sideLength * cosAngel)
            point3 = QPointF(tmpPoint.x() - sideLength * sinAngel, tmpPoint.y() + sideLength * cosAngel)
            point4 = QPointF(tmpPoint.x() - bottomSize * sideLength * sinAngel,
                             tmpPoint.y() + bottomSize * sideLength * cosAngel)
            point5 = QPointF(step[3], step[4])
            point6 = QPointF(tmpPoint.x() + bottomSize * sideLength * sinAngel,
                             tmpPoint.y() - bottomSize * sideLength * cosAngel)
            point7 = QPointF(tmpPoint.x() + sideLength * sinAngel, tmpPoint.y() - sideLength * cosAngel)

            arrow.append(point1)
            arrow.append(point2)
            arrow.append(point3)
            arrow.append(point4)
            arrow.append(point5)
            arrow.append(point6)
            arrow.append(point7)
            arrow.append(point1)

            self.graphics_scene.addPolygon(arrow, step[5], step[6])
        elif step[0] == ACTION_LINE:
            self.graphics_scene.addLine(QLineF(QPointF(step[1], step[2]), QPointF(step[3], step[4])), step[5])
        elif step[0] == ACTION_FREEPEN:
            self.graphics_scene.addPath(step[1], step[2])
        elif step[0] == ACTION_TEXT:
            textAdd = self.graphics_scene.addSimpleText(step[1], step[2])
            textAdd.setPos(step[3])
            textAdd.setBrush(QBrush(step[4]))
            self.textRect = textAdd.boundingRect()

    def drawSizeInfo(self):
        """左上角的区域大小的提示"""
        sizeInfoAreaWidth = 200
        sizeInfoAreaHeight = 30
        spacing = 5
        rect = self.selected_area.normalized()
        sizeInfoArea = QRect(rect.left(), rect.top() - spacing - sizeInfoAreaHeight,
                             sizeInfoAreaWidth, sizeInfoAreaHeight)

        if sizeInfoArea.top() < 0:
            sizeInfoArea.moveTopLeft(rect.topLeft() + QPoint(spacing, spacing))
        if sizeInfoArea.right() >= self.screenPixel.width():
            sizeInfoArea.moveTopLeft(rect.topLeft() - QPoint(spacing, spacing) - QPoint(sizeInfoAreaWidth, 0))
        if sizeInfoArea.left() < spacing:
            sizeInfoArea.moveLeft(spacing)
        if sizeInfoArea.top() < spacing:
            sizeInfoArea.moveTop(spacing)

        self.items_to_remove.append(self.graphics_scene.addRect(QRectF(sizeInfoArea), QPen(Qt.white, 2), QBrush(Qt.black)))

        sizeInfo = self.graphics_scene.addSimpleText(
            '  {0} x {1}'.format(rect.width() * self.scale, rect.height() * self.scale))
        sizeInfo.setPos(sizeInfoArea.topLeft() + QPoint(0, 2))
        sizeInfo.setPen(QPen(QColor(255, 255, 255), 2))
        self.items_to_remove.append(sizeInfo)

    def drawRect(self, x1: int, x2: int, y1: int, y2: int, result: bool):
        """鼠标放开时result=True, 否则为进行时, result为false"""
        rect = self.selected_area.normalized()
        tmpRect = QRect(QPoint(x1, x2), QPoint(y1, y2)).normalized()
        resultRect = rect & tmpRect
        tmp = [ACTION_RECT, resultRect.topLeft().x(), resultRect.topLeft().y(),
               resultRect.bottomRight().x(), resultRect.bottomRight().y(),
               QPen(QColor(self.penColorNow), int(self.penSizeNow))]
        if result:
            self.drawListResult.append(tmp)
        else:
            self.drawListProcess = tmp

    def drawEllipse(self, x1: int, x2: int, y1: int, y2: int, result: bool):
        rect = self.selected_area.normalized()
        tmpRect = QRect(QPoint(x1, x2), QPoint(y1, y2)).normalized()
        resultRect = rect & tmpRect
        tmp = [ACTION_ELLIPSE, resultRect.topLeft().x(), resultRect.topLeft().y(),
               resultRect.bottomRight().x(), resultRect.bottomRight().y(),
               QPen(QColor(self.penColorNow), int(self.penSizeNow))]
        if result:
            self.drawListResult.append(tmp)
        else:
            self.drawListProcess = tmp

    def drawArrow(self, x1: int, x2: int, y1: int, y2: int, result: bool):
        rect = self.selected_area.normalized()
        if y1 <= rect.left():
            y1 = rect.left()
        elif y1 >= rect.right():
            y1 = rect.right()

        if y2 <= rect.top():
            y2 = rect.top()
        elif y2 >= rect.bottom():
            y2 = rect.bottom()

        tmp = [ACTION_ARROW, x1, x2, y1, y2,
               QPen(QColor(self.penColorNow), int(self.penSizeNow)),
               QBrush(QColor(self.penColorNow))]
        if result:
            self.drawListResult.append(tmp)
        else:
            self.drawListProcess = tmp

    def drawLine(self, x1: int, x2: int, y1: int, y2: int, result: bool):
        rect = self.selected_area.normalized()
        if y1 <= rect.left():
            y1 = rect.left()
        elif y1 >= rect.right():
            y1 = rect.right()

        if y2 <= rect.top():
            y2 = rect.top()
        elif y2 >= rect.bottom():
            y2 = rect.bottom()

        tmp = [ACTION_LINE, x1, x2, y1, y2,
               QPen(QColor(self.penColorNow), int(self.penSizeNow))]
        if result:
            self.drawListResult.append(tmp)
        else:
            self.drawListProcess = tmp

    def drawFreeLine(self, pointPath: QPainterPath, result: bool):
        tmp = [ACTION_FREEPEN, QPainterPath(pointPath), QPen(QColor(self.penColorNow), int(self.penSizeNow))]
        if result:
            self.drawListResult.append(tmp)
        else:
            self.drawListProcess = tmp

    def textChange(self):
        if self.textPosition is None:
            return
        self.text = self.textInput.getText()
        self.drawListProcess = [ACTION_TEXT, str(self.text), QFont(self.fontNow), QPoint(self.textPosition),
                                QColor(self.penColorNow)]
        self.redraw()

    def undoOperation(self):
        if len(self.drawListResult) == 0:
            self.action = ACTION_SELECT
            self.selected_area = QRect()
            self.selectedAreaRaw = QRect()
            self.tooBar.hide()
            if self.penSetBar is not None:
                self.penSetBar.hide()
        else:
            self.drawListResult.pop()
        self.redraw()

    def saveOperation(self):
        filename = QFileDialog.getSaveFileName(self, 'Save file', './screenshot.png', '*.png;;*.jpg')
        if len(filename[0]) == 0:
            return
        else:
            self.saveScreenshot(False, filename[0], filename[1][2:])
            self.close()

    def close(self):
        self.widget_closed.emit()
        super().close()
        self.tooBar.close()
        if self.penSetBar is not None:
            self.penSetBar.close()

    def saveToClipboard(self):
        QApplication.clipboard().setText('Test in save function')

        self.saveScreenshot(True)
        self.close()

    def changeAction(self, nextAction: int):
        QApplication.clipboard().setText('Test in changeAction function')

        if nextAction == ACTION_UNDO:
            self.undoOperation()
        elif nextAction == ACTION_SAVE:
            self.saveOperation()
        elif nextAction == ACTION_CANCEL:
            self.close()
        elif nextAction == ACTION_SURE:
            self.saveToClipboard()

        else:
            self.action = nextAction

        self.setFocus()

    def changePenSize(self, nextPenSize: int):
        self.penSizeNow = nextPenSize

    def changePenColor(self, nextPenColor: str):
        self.penColorNow = nextPenColor

    def changeFont(self, font: QFont):
        self.fontNow = font

    def cancelInput(self):
        self.drawListProcess = None
        self.textPosition = None
        self.textRect = None
        self.textInput.hide()
        self.textInput.clearText()
        self.redraw()

    def okInput(self):
        self.text = self.textInput.getText()
        self.drawListResult.append(
            [ACTION_TEXT, str(self.text), QFont(self.fontNow), QPoint(self.textPosition), QColor(self.penColorNow)])
        self.textPosition = None
        self.textRect = None
        self.textInput.hide()
        self.textInput.clearText()
        self.redraw()
