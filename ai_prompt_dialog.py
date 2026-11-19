"""AI prompt dialog: sends a prompt in the background and shows its progress."""

from threading import Thread

from PyQt5.QtCore import QTimer, Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

import var
from ai_generation import AIRequestError, ai_error_from_exception, request_server_ai
from compat_ui import alert
from utils import update_config_json

_STATUS_STYLE = "QLabel { font-size: 14px; color: #000; padding: 4px 10px; }"
_ERROR_STYLE = "QLabel { font-size: 14px; color: #b00020; padding: 4px 10px; }"


def _generate_with_server(prompt):
    return request_server_ai(prompt).answer


def show_answer_in_editor(editor, answer):
    """Show generated text verbatim.

    ``setText`` guesses rich text, which would swallow tags such as ``<b>`` and
    collapse paragraph breaks. Plain text keeps spintax braces, pipes,
    placeholders and blank lines exactly, for display, copy and save.
    """
    editor.setPlainText(answer)


class AIPromptDialog(QDialog):
    SLOW_STATUS_DELAY_MS = 15000
    LOADING_TEXT = "Generating your email…"
    SLOW_STATUS_TEXT = "Still generating your email…"

    promptSubmitted = pyqtSignal(str)
    aiSucceeded = pyqtSignal(str)
    aiFailed = pyqtSignal(str, bool)

    def __init__(self, parent=None, generate=None):
        """``generate(prompt)`` returns the answer text or raises AIRequestError."""
        super().__init__(parent)
        self._generate = generate or _generate_with_server
        self._request_in_progress = False
        self._worker_thread = None
        self._last_prompt = ""
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setGeometry(300, 200, 400, 300)
        layout = QVBoxLayout(self)
        self.title_label = QLabel("AI Assistant")
        layout.addWidget(self.title_label)
        self.text_input = QTextEdit(var.compose_prompt)
        layout.addWidget(self.text_input)
        self.status_label = QLabel("")
        self.status_label.setTextFormat(Qt.PlainText)
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(_STATUS_STYLE)
        self.status_label.hide()
        # Retry sits beside the error text so the button row keeps its width.
        status_row = QHBoxLayout()
        status_row.setContentsMargins(0, 0, 10, 0)
        status_row.addWidget(self.status_label, 1)
        self.retry_button = QPushButton("Retry")
        self.retry_button.setStyleSheet("QPushButton { padding: 5px 14px; }")
        self.retry_button.clicked.connect(self.retry_ai_response)
        self.retry_button.hide()
        status_row.addWidget(self.retry_button, 0, Qt.AlignTop)
        layout.addLayout(status_row)
        self.loader = QProgressBar()
        self.loader.setRange(0, 0)
        self.loader.hide()
        layout.addWidget(self.loader)
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 0, 10, 10)
        self.send_button = QPushButton("Send Prompt")
        self.send_button.clicked.connect(self.get_ai_response)
        self.close_button = QPushButton("Close Prompt")
        self.close_button.clicked.connect(self.reject)
        button_layout.addStretch()
        button_layout.addWidget(self.send_button)
        button_layout.addWidget(self.close_button)
        layout.addLayout(button_layout)
        self.setStyleSheet(
            "\n            QLabel::indicator {\n                width: 0px; /* Hide the circle indicator */\n                height: 0px;\n            }\n            QLabel {\n                font-size: 20px;\n                color: #000;\n                background-color: transparent;\n                border: none;\n                padding: 10px;\n            }\n                                    \n            QDialog {\n                background-color: #f9f9f9;\n                border-radius: 20px;\n                padding: 10px;\n            }\n\n            QTextEdit {\n                border: 2px solid black;    /* Black border */\n                border-radius: 10px;\n                padding: 5px;\n                background-color: #ffffff;\n            }\n\n            QDialogButtonBox {\n                background-color: #d4d4d4;\n                border-radius: 10px;\n                padding: 5px;\n            }\n\n            QPushButton {\n                border: 1px solid #555;\n                border-radius: 3px;\n                border-style: Solid;\n                background: rgba(0, 138, 191);\n                padding: 5px 28px;\n                color: rgb(255, 255, 255);\n                }\n            \n            QPushButton:hover {\n                background: rgba(0, 138, 191, 0.6);\n                opacity: 0.2\n                }\n            \n            QPushButton:pressed {\n                border-style: inset;\n                background: rgb(0, 138, 191);\n                }\n        "
        )
        self._slow_timer = QTimer(self)
        self._slow_timer.setSingleShot(True)
        self._slow_timer.timeout.connect(self._show_slow_ai_status)
        self.aiSucceeded.connect(self._handle_ai_success)
        self.aiFailed.connect(self._handle_ai_failure)

    def get_ai_response(self):
        if self._request_in_progress:
            return
        prompt = self.text_input.toPlainText().strip()
        var.compose_prompt = prompt
        Thread(target=update_config_json, daemon=True).start()
        if not prompt:
            alert(text="Please enter a prompt.", title="Warning", button="OK")
            return
        self._start_request(prompt)

    def retry_ai_response(self):
        """Manual retry of the prompt that failed. Never triggered automatically."""
        if self._request_in_progress or not self._last_prompt:
            return
        self._start_request(self._last_prompt)

    def _start_request(self, prompt):
        self._last_prompt = prompt
        self._set_ai_loading(True, self.LOADING_TEXT)
        self._slow_timer.start(self.SLOW_STATUS_DELAY_MS)
        self._worker_thread = Thread(
            target=self._run_ai_request,
            daemon=True,
            args=(prompt,),
        )
        self._worker_thread.start()

    def _run_ai_request(self, prompt):
        try:
            answer = self._generate(prompt)
        except Exception as error:
            failure = ai_error_from_exception(error)
            if not isinstance(error, AIRequestError):
                var.logger.error(f"AI request failed unexpectedly: {error!r}")
            self.aiFailed.emit(failure.message, failure.retryable)
        else:
            self.aiSucceeded.emit(answer)

    def _set_ai_loading(self, is_loading, status_text=""):
        self._request_in_progress = is_loading
        self.send_button.setEnabled(not is_loading)
        self.loader.setVisible(is_loading)
        self.retry_button.hide()
        if not is_loading:
            self._slow_timer.stop()
        self.status_label.setStyleSheet(_STATUS_STYLE)
        self.status_label.setText(status_text)
        self.status_label.setVisible(bool(status_text))

    def _show_slow_ai_status(self):
        if self._request_in_progress:
            self.status_label.setText(self.SLOW_STATUS_TEXT)

    def _handle_ai_success(self, answer):
        self._set_ai_loading(False)
        self.promptSubmitted.emit(answer)

    def _handle_ai_failure(self, message, retryable):
        self._set_ai_loading(False)
        self.status_label.setStyleSheet(_ERROR_STYLE)
        self.status_label.setText(message)
        self.status_label.show()
        self.retry_button.setVisible(bool(retryable))

    def done(self, result):
        self._slow_timer.stop()
        super().done(result)
