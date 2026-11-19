from PyQt5 import QtCore, QtWidgets

from unsubscribe_management import filter_records


PAGE_STYLE = """
QWidget#unsubscribePage { background-color: #ffffff; }
QLabel#unsubscribeTitle {
    background: transparent; color: #111827;
    font-family: Arial; font-size: 26px; font-weight: bold;
}
QLabel#unsubscribeSubtitle, QLabel#unsubscribeStatus {
    background: transparent; color: #667085;
    font-family: Arial; font-size: 12px;
}
QFrame#unsubscribeControls {
    background-color: #eef2f7;
    border: 1px solid #d8e3ee;
    border-radius: 10px;
}
QLineEdit#unsubscribeSearch {
    background-color: #ffffff; color: #111827;
    border: 1px solid #d8e0ea; border-radius: 8px;
    padding: 7px 12px; font-family: Arial; font-size: 12px;
}
QLineEdit#unsubscribeSearch:focus { border-color: #028fc3; }
QPushButton#unsubscribePrimary {
    background-color: #028fc3; color: #ffffff;
    border: 1px solid #028fc3; border-radius: 8px;
    padding: 8px 18px; font-family: Arial; font-size: 12px;
}
QPushButton#unsubscribePrimary:hover { background-color: #027faf; }
QPushButton#unsubscribeSecondary {
    background-color: #ffffff; color: #344054;
    border: 1px solid #cbd5e1; border-radius: 8px;
    padding: 8px 18px; font-family: Arial; font-size: 12px;
}
QPushButton#unsubscribeSecondary:hover { background-color: #f8fafc; }
QTableWidget#unsubscribeTable {
    background-color: #ffffff; alternate-background-color: #f7fafd;
    color: #344054; border: 1px solid #d8e3ee;
    border-radius: 10px; gridline-color: #e9eef5;
    font-family: Arial; font-size: 12px;
    selection-background-color: #dceef6; selection-color: #111827;
}
QTableWidget#unsubscribeTable QHeaderView::section {
    background-color: #eef2f7; color: #344054;
    border: none; border-bottom: 1px solid #d8e3ee;
    padding: 10px 12px; font-family: Arial;
    font-size: 12px; font-weight: bold; text-align: left;
}
QTableWidget#unsubscribeTable QTableCornerButton::section {
    background-color: #eef2f7; border: none;
}
"""


class UnsubscribePage(QtWidgets.QWidget):
    refreshRequested = QtCore.pyqtSignal()
    manualAddRequested = QtCore.pyqtSignal(str)
    exportRequested = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("unsubscribePage")
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self.setStyleSheet(PAGE_STYLE)
        self.records = []
        self.filtered_records = []
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)
        header = QtWidgets.QHBoxLayout()
        header.setSpacing(16)
        heading = QtWidgets.QVBoxLayout()
        heading.setSpacing(4)
        title = QtWidgets.QLabel("Unsubscribes")
        title.setObjectName("unsubscribeTitle")
        subtitle = QtWidgets.QLabel("Manage recipients who opted out of future emails")
        subtitle.setObjectName("unsubscribeSubtitle")
        heading.addWidget(title)
        heading.addWidget(subtitle)
        self.refresh_button = QtWidgets.QPushButton("Refresh")
        self.refresh_button.setObjectName("unsubscribeSecondary")
        self.refresh_button.setMinimumHeight(40)
        header.addLayout(heading)
        header.addStretch()
        header.addWidget(self.refresh_button)
        controls = QtWidgets.QFrame()
        controls.setObjectName("unsubscribeControls")
        actions = QtWidgets.QHBoxLayout(controls)
        actions.setContentsMargins(16, 16, 16, 16)
        actions.setSpacing(10)
        self.search_input = QtWidgets.QLineEdit()
        self.search_input.setObjectName("unsubscribeSearch")
        self.search_input.setPlaceholderText("Search email, source, or campaign")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setMinimumHeight(40)
        self.add_button = QtWidgets.QPushButton("Add manually")
        self.add_button.setObjectName("unsubscribePrimary")
        self.add_button.setMinimumHeight(40)
        self.export_button = QtWidgets.QPushButton("Export CSV")
        self.export_button.setObjectName("unsubscribeSecondary")
        self.export_button.setMinimumHeight(40)
        actions.addWidget(self.search_input, 1)
        actions.addWidget(self.add_button)
        actions.addWidget(self.export_button)
        self.status_label = QtWidgets.QLabel("")
        self.status_label.setObjectName("unsubscribeStatus")
        self.table = QtWidgets.QTableWidget(0, 4)
        self.table.setObjectName("unsubscribeTable")
        self.table.setHorizontalHeaderLabels(["Email", "Unsubscribed at", "Source", "Campaign subject"])
        self.table.horizontalHeader().setDefaultAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        self.table.horizontalHeader().resizeSection(0, 260)
        self.table.horizontalHeader().resizeSection(1, 180)
        self.table.horizontalHeader().resizeSection(2, 140)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(42)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        layout.addLayout(header)
        layout.addWidget(controls)
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
