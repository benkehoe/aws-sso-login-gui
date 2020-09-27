import webbrowser

from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5.QtCore import *


app = QApplication([])


if False:
    window = QWidget()
    layout = QVBoxLayout()
    layout.addWidget(QPushButton('Top'))
    layout.addWidget(QPushButton('Bottom'))
    window.setLayout(layout)
    window.show()

def on_message_click(*args):
    print(args)
    webbrowser.open("https://google.com")

icon = QIcon("sun.ico")

sys_tray_icon = QSystemTrayIcon(icon)
sys_tray_icon.activated.connect(on_message_click)
sys_tray_icon.messageClicked.connect(on_message_click)

sys_tray_icon.show()

button = QPushButton('Click')
def on_button_clicked():
    if False:
        alert = QMessageBox()
        alert.setText('You clicked the button!')
        alert.exec_()

    if True:
        sys_tray_icon.showMessage("foo", "bar")

button.clicked.connect(on_button_clicked)
button.show()

sys_tray_icon.showMessage("foo", "bar")

def change_message():
    sys_tray_icon.showMessage("bar", "foo")

QTimer.singleShot(5000, change_message)

app.exec_()

# FBS https://build-system.fman.io/

"""
from PySide.QtCore import QObject, Signal, Slot

class PunchingBag(QObject):
    ''' Represents a punching bag; when you punch it, it
        emits a signal that indicates that it was punched. '''
    punched = Signal()

    def __init__(self):
        # Initialize the PunchingBag as a QObject
        QObject.__init__(self)

    def punch(self):
        ''' Punch the bag '''
        self.punched.emit()
"""
