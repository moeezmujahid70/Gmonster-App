"""Signup contract checks without launching the application's startup flow."""
import ast
import json
import logging
import os
import runpy
import sys
import warnings
from pathlib import Path
from threading import Event, Thread
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
import requests
from PyQt5 import QtCore, QtGui, QtWidgets, uic

from user_messages import display_text, login_response_message, operation_message


SUCCESS = "Account created. Contact the admin to activate your account before signing in."
PENDING = "This account already exists and is awaiting activation. Contact the admin to activate it."
EXISTS = "This account already exists. Try signing in."


@pytest.mark.parametrize("text, code, body", [
    ("  Successfully Registered\n", "REGISTRATION_SUCCESS", SUCCESS),
    ("  Account exists—activation required\n", "ACCOUNT_PENDING_ACTIVATION", PENDING),
    ("  Already exists\n", "ACCOUNT_EXISTS", EXISTS),
    (json.dumps({"code": "REGISTRATION_SUCCESS"}), "REGISTRATION_SUCCESS", SUCCESS),
    (json.dumps({"code": "ACCOUNT_PENDING_ACTIVATION"}), "ACCOUNT_PENDING_ACTIVATION", PENDING),
    (json.dumps({"code": "ACCOUNT_EXISTS"}), "ACCOUNT_EXISTS", EXISTS),
])
def test_signup_recognizes_only_explicit_results(text, code, body):
    message = login_response_message(text, "register")
    assert message.code == code
    assert message.body == body


@pytest.mark.parametrize("text", ["", "Success", "not registered", "already unavailable", '{"code": "UNKNOWN"}', "[]", '{"code": []}', '{"code":', '<html>Already exists</html>'])
def test_unknown_signup_results_are_never_duplicates(text):
    assert login_response_message(text, "register").code == "REGISTRATION_UNKNOWN_RESPONSE"


@pytest.fixture(params=["source_ui", "generated_wrapper"])
def signup_env(request):
    # Load the real handlers, excluding module-level GUI startup and runtime imports.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        tree = ast.parse(Path("dialog.py").read_text())
    definitions = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef))
                   and node.name in {"Sign_up", "myMainClass", "make_sign_up_requests", "get_request_timeout", "check"}]
    state = SimpleNamespace(sign_up_label="", sign_up_in_progress=False,
                            sign_up_can_sign_in=False,
                            api="https://example.invalid/", version="test", API_TIMEOUT=(1, 1))
    state.window_title = "Gmonster"
    if request.param == "source_ui":
        ui_class, _ = uic.loadUiType("ui/sign_up.ui")
    else:
        with patch.dict(sys.modules, {"var": state}):
            ui_class = runpy.run_path("sign_up.py")["Ui_Dialog"]
    namespace = dict(su=SimpleNamespace(Ui_Dialog=ui_class), QtCore=QtCore,
                     QtGui=QtGui, QtWidgets=QtWidgets, Thread=Thread, var=state,
                     set_icon=lambda dialog: None, get_system_identifiers=lambda: ("test", "test"),
                     requests=requests, loads=json.loads, dumps=json.dumps,
                     logger=logging.getLogger("signup-test"), display_text=display_text,
                     login_response_message=login_response_message, operation_message=operation_message,
                     regex=r"[^@]+@[^@]+\.[^@]+", re=__import__("re"))
    exec(compile(ast.Module(body=definitions, type_ignores=[]), "dialog.py", "exec"), namespace)
    return state, namespace


def response(text, status=200):
    result = requests.Response()
    result.status_code = status
    result.encoding = "utf-8"
    result._content = text.encode()
    return result


@pytest.mark.parametrize("result, expected", [
    (response("  Successfully Registered\n"), SUCCESS),
    (response("  Account exists—activation required\n"), PENDING),
    (response("  Already exists\n"), EXISTS),
    (response('{"code":"ACCOUNT_PENDING_ACTIVATION"}'), PENDING),
])
def test_request_shows_signup_guidance(signup_env, result, expected):
    state, namespace = signup_env
    state.sign_up_in_progress = True
    with patch.object(requests, "post", return_value=result):
        namespace["make_sign_up_requests"]("person@example.com", "password123", "register")
    assert state.sign_up_label == expected
    assert state.sign_up_in_progress is False


@pytest.mark.parametrize("result", [response("Already exists", 500), response("Successfully Registered", 403),
                                         response("Successfully Registered", 201), response("Already exists", 302),
                                         requests.exceptions.ConnectionError(), requests.exceptions.Timeout()])
def test_request_failures_are_not_duplicates_and_release_submission(signup_env, result):
    state, namespace = signup_env
    state.sign_up_in_progress = True
    kwargs = {"side_effect": result} if isinstance(result, Exception) else {"return_value": result}
    with patch.object(requests, "post", **kwargs):
        namespace["make_sign_up_requests"]("person@example.com", "password123", "register")
    assert "ACCOUNT_EXISTS" not in state.sign_up_label
    assert "Account created" not in state.sign_up_label
    if isinstance(result, requests.Response):
        assert "HTTP {}".format(result.status_code) in state.sign_up_label
    elif isinstance(result, requests.exceptions.Timeout):
        assert "CONNECTION_TIMEOUT" in state.sign_up_label
    else:
        assert "CONNECTION_FAILED" in state.sign_up_label
    assert state.sign_up_in_progress is False


@pytest.fixture(scope="module")
def qt_app():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


def test_signup_blocks_repeated_requests_and_displays_full_message(signup_env, qt_app):
    state, namespace = signup_env
    window = QtWidgets.QDialog()
    ui = namespace["Sign_up"](window)
    starting_size = window.size()
    window.show()
    qt_app.processEvents()
    assert not ui.pushButton_sign_in.isVisible()
    ui.lineEdit_email.setText("person@example.com")
    ui.lineEdit_password.setText("password123")
    ui.lineEdit_confirm_password.setText("password123")
    entered, release, finished = Event(), Event(), Event()
    submissions = []

    def post(*args, **kwargs):
        submissions.append(kwargs["json"]["email"])
        entered.set()
        release.wait(3)
        return response("Successfully Registered")

    worker = namespace["make_sign_up_requests"]
    def tracked_worker(*args):
        try:
            worker(*args)
        finally:
            finished.set()
    namespace["make_sign_up_requests"] = tracked_worker
    try:
        with patch.object(requests, "post", side_effect=post):
            ui.validate()
            assert entered.wait(2)
            ui.validate()
            assert not ui.pushButton_sign_up.isEnabled()
            assert not ui.pushButton_sign_in.isEnabled()
            assert submissions == ["person@example.com"]
            release.set()
            assert finished.wait(2)
            ui.setText()
        assert ui.pushButton_sign_up.isEnabled()
        assert ui.pushButton_sign_in.isEnabled()
        assert not ui.timer.isActive()
        assert ui.label_status.text() == SUCCESS
        window.show()
        qt_app.processEvents()
        initial_size = window.size()
        assert initial_size == starting_size
        assert window.width() >= 560
        assert window.height() >= 400
        for message in [SUCCESS, PENDING, EXISTS,
                        display_text(operation_message("register", requests.exceptions.ConnectionError()))]:
            state.sign_up_label = message
            ui.setText()
            qt_app.processEvents()
            assert ui.label_status.width() >= window.width() - 110
            assert ui.label_status.height() >= ui.label_status.heightForWidth(ui.label_status.width())
            assert window.size() == initial_size
    finally:
        release.set()
        finished.wait(2)
        ui.timer.stop()
        window.close()


@pytest.mark.parametrize("text", ["Successfully Registered", "Account exists—activation required", "Already exists"])
def test_signup_sign_in_button_returns_to_login_with_email(signup_env, qt_app, text):
    state, namespace = signup_env
    window = QtWidgets.QDialog()
    ui = namespace["Sign_up"](window)
    ui.lineEdit_email.setText(" person@example.com ")
    with patch.object(requests, "post", return_value=response(text)):
        namespace["make_sign_up_requests"]("person@example.com", "password123", "register")
    ui.setText()
    window.show()
    qt_app.processEvents()
    assert ui.pushButton_sign_in.isVisible()
    assert ui.pushButton_sign_in.y() > ui.pushButton_sign_up.y()
    ui.pushButton_sign_in.click()
    assert window.result() == QtWidgets.QDialog.Accepted
    assert state.login_email == "person@example.com"
    window.close()


def test_signup_controller_opens_login_when_sign_in_is_clicked(signup_env, qt_app):
    state, namespace = signup_env
    controller = namespace["myMainClass"].__new__(namespace["myMainClass"])
    controller.update_needed = True
    login_emails = []
    controller.sign_in = lambda: login_emails.append(state.login_email)

    def click_sign_in():
        window = qt_app.activeModalWidget()
        window.ui.lineEdit_email.setText("person@example.com")
        with patch.object(requests, "post", return_value=response("Successfully Registered")):
            namespace["make_sign_up_requests"]("person@example.com", "password123", "register")
        window.ui.setText()
        window.ui.pushButton_sign_in.click()

    QtCore.QTimer.singleShot(0, click_sign_in)
    controller.sign_up()
    assert login_emails == ["person@example.com"]


@pytest.mark.parametrize("result", [response("unknown"), response("Already exists", 500),
                                   requests.exceptions.ConnectionError()])
def test_signup_errors_keep_sign_in_hidden(signup_env, qt_app, result):
    state, namespace = signup_env
    window = QtWidgets.QDialog()
    ui = namespace["Sign_up"](window)
    window.show()
    qt_app.processEvents()
    size = window.size()
    kwargs = {"side_effect": result} if isinstance(result, Exception) else {"return_value": result}
    with patch.object(requests, "post", **kwargs):
        namespace["make_sign_up_requests"]("person@example.com", "password123", "register")
    ui.setText()
    qt_app.processEvents()
    assert not ui.pushButton_sign_in.isVisible()
    assert window.size() == size
    window.close()
