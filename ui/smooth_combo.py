from PySide6.QtWidgets import QComboBox, QAbstractItemView, QFrame
from PySide6.QtGui import QRegion
from PySide6.QtCore import QVariantAnimation, QEasingCurve, QAbstractAnimation


class SmoothComboBox(QComboBox):

    def showPopup(self):
        super().showPopup()
        popup = self.findChild(QAbstractItemView)
        if not popup or not popup.isVisible():
            return

        popup.scrollToTop()
        container = popup.parent()
        if container:
            container.setFrameShape(QFrame.Shape.NoFrame)
            container.setStyleSheet("background: #252526;")
            combo_bottom = self.mapToGlobal(self.rect().bottomLeft())
            geo = container.geometry()
            geo.moveTop(combo_bottom.y())
            container.setGeometry(geo)
        popup.setViewportMargins(0, 0, 0, 0)

        w = popup.width()
        h = popup.height()

        anim = QVariantAnimation()
        anim.setDuration(180)
        anim.setStartValue(2)
        anim.setEndValue(h)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.valueChanged.connect(lambda v: popup.setMask(QRegion(0, 0, w, v)))
        anim.finished.connect(popup.clearMask)
        anim.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
        self._anim = anim
