from PyQt5 import QtCore, QtWidgets

from unsubscribe_management import filter_records


class UnsubscribePage(QtWidgets.QWidget):
    refreshRequested = QtCore.pyqtSignal()
    manualAddRequested = QtCore.pyqtSignal(str)
    exportRequested = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.records = []
        self.filtered_records = []
        layout = QtWidgets.QVBoxLayout(self)
        header = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("Unsubscribes")
        title.setStyleSheet("font-size: 22px; font-weight: 600; color: #1f2937;")
        self.refresh_button = QtWidgets.QPushButton("Refresh")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.refresh_button)
        actions = QtWidgets.QHBoxLayout()
        self.search_input = QtWidgets.QLineEdit()
        self.search_input.setPlaceholderText("Search email, source, or campaign")
        self.search_input.setClearButtonEnabled(True)
        self.add_button = QtWidgets.QPushButton("Add manually")
        self.export_button = QtWidgets.QPushButton("Export CSV")
        actions.addWidget(self.search_input, 1)
        actions.addWidget(self.add_button)
        actions.addWidget(self.export_button)
        self.status_label = QtWidgets.QLabel("")
        self.table = QtWidgets.QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Email", "Unsubscribed at", "Source", "Campaign subject"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        layout.addLayout(header)
        layout.addLayout(actions)
        layout.addWidget(self.status_label)
        layout.addWidget(self.table, 1)
        self.refresh_button.clicked.connect(self.refreshRequested.emit)
        self.search_input.textChanged.connect(self.apply_filter)
        self.add_button.clicked.connect(self.request_manual_add)
        self.export_button.clicked.connect(self.exportRequested.emit)

    def set_loading(self):
        self.status_label.setText("Loading unsubscribes…")
        self.refresh_button.setEnabled(False)

    def set_error(self, message):
        self.status_label.setText(message)
        self.refresh_button.setEnabled(True)

    def set_records(self, records):
        self.records = list(records)
        self.refresh_button.setEnabled(True)
        self.apply_filter(self.search_input.text())

    def apply_filter(self, query):
        self.filtered_records = filter_records(self.records, query)
        self.table.setRowCount(len(self.filtered_records))
        for row_index, record in enumerate(self.filtered_records):
            for column_index, key in enumerate(("email", "unsubscribed_at", "source", "campaign_subject")):
                self.table.setItem(row_index, column_index, QtWidgets.QTableWidgetItem(str(record.get(key) or "")))
        self.status_label.setText(
            "No unsubscribed recipients" if not self.filtered_records
            else "{} unsubscribed recipient(s)".format(len(self.filtered_records))
        )

    def request_manual_add(self):
        email, accepted = QtWidgets.QInputDialog.getText(self, "Add unsubscribe", "Recipient email:")
        if accepted and email.strip():
            self.manualAddRequested.emit(email.strip())
