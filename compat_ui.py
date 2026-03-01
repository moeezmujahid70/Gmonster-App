import threading

from PyQt5 import QtCore, QtWidgets


_fallback_counter = 0


def _app_and_parent():
    app = QtWidgets.QApplication.instance()
    parent = app.activeWindow() if app else None
    return app, parent


def _run_on_main_thread(fn):
    app = QtWidgets.QApplication.instance()
    if app and threading.current_thread() is threading.main_thread():
        return fn()
    if app:
        result = {}
        event = threading.Event()

        def invoke():
            try:
                result["value"] = fn()
            finally:
                event.set()

        QtCore.QTimer.singleShot(0, invoke)
        event.wait()
        return result.get("value")
    return None


def alert(text="", title="Alert", button="OK"):
    def _show():
        _, parent = _app_and_parent()
        box = QtWidgets.QMessageBox(parent)
        box.setIcon(QtWidgets.QMessageBox.Information)
        box.setWindowTitle(str(title))
        box.setText(str(text))
        btn = box.addButton(str(button), QtWidgets.QMessageBox.AcceptRole)
        box.exec_()
        return btn.text()

    value = _run_on_main_thread(_show)
    if value is not None:
        return value

    print(f"[{title}] {text}")
    return button


def confirm(text="", title="Confirm", buttons=None):
    if buttons is None:
        buttons = ["OK", "Cancel"]
    buttons = [str(button) for button in buttons if str(button)]
    if not buttons:
        buttons = ["OK", "Cancel"]

    def _show():
        _, parent = _app_and_parent()
        box = QtWidgets.QMessageBox(parent)
        box.setIcon(QtWidgets.QMessageBox.Question)
        box.setWindowTitle(str(title))
        box.setText(str(text))
        created_buttons = []
        for index, label in enumerate(buttons):
            role = QtWidgets.QMessageBox.AcceptRole if index == 0 else QtWidgets.QMessageBox.RejectRole
            created_buttons.append(box.addButton(label, role))
        box.exec_()
        clicked = box.clickedButton()
        return clicked.text() if clicked else None

    value = _run_on_main_thread(_show)
    if value is not None:
        return value

    global _fallback_counter
    choice = buttons[0] if buttons else None
    _fallback_counter += 1
    print(f"[{title}] {text} -> {choice} (fallback)")
    return choice


def password(text="", title="Password", default="", mask="*"):
    def _show():
        _, parent = _app_and_parent()
        value, ok = QtWidgets.QInputDialog.getText(
            parent,
            str(title),
            str(text),
            QtWidgets.QLineEdit.Password,
            str(default),
        )
        return value if ok else None

    value = _run_on_main_thread(_show)
    if value is not None:
        return value

    return None
