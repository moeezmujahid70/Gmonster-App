from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt, pyqtSignal, QObject
import var
from var import logger
import database


class TableModel(QtCore.QAbstractTableModel):

    def __init__(self, data):
        super().__init__()
        self._data = data
        self.logger = logger

    def data(self, index, role):
        if role == Qt.DisplayRole:
            value = self._data.iloc[index.row(), index.column()]
            return str(value)

    def rowCount(self, index):
        return self._data.shape[0]

    def columnCount(self, index):
        return self._data.shape[1]

    def headerData(self, section, orientation, role):
        # section is the index of the column/row.
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                return str(self._data.columns[section])

            if orientation == Qt.Vertical:
                return str(self._data.index[section])

    def setData(self, index, value, role=QtCore.Qt.EditRole):
        """
        Edit data in table cells
        :param index:
        :param value:
        :param role:
        :return:
        """
        if index.isValid():
            row = self._data.iloc[index.row()].to_dict()
            row[str(self._data.columns[index.column()])] = value
            if self._data.iloc[index.row(), index.column()] != value:
                if database.db_update_row(row):
                    self._data.iloc[index.row(), index.column()] = value
                    self.dataChanged.emit(
                        index, index, (QtCore.Qt.DisplayRole, ))
                    return True

        return False

    def flags(self, index):
        """
        Make table editable.
        make first column non editable
        :param index:
        :return:
        """
        if index.column() > 0:
            return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEditable
        else:
            return QtCore.Qt.ItemIsSelectable

    def insertRows(self):
        try:
            row_count = self._data.shape[0]
            self.beginInsertRows(QtCore.QModelIndex(), row_count, row_count)
            result, id = database.db_insert_row()
            if result:
                self._data.loc[row_count] = [id] + \
                    [""] * (self._data.shape[1] - 1)
                row_count += 1
                self.endInsertRows()
                return True
            else:
                return False
        except Exception as e:
            print(f"Error at insert_rows: {e}")
            self.logger.error(f"Error at insert_rows - {e}")
            return False

    def removeRows(self, position):
        try:
            row_id = position
            result = database.db_remove_row(int(self._data.iloc[row_id, 0]))
            if result:
                row_count = self._data.shape[0]
                row_count -= 1
                self.beginRemoveRows(QtCore.QModelIndex(),
                                     row_count, row_count)
                self._data.drop(row_id, axis=0, inplace=True)
                self._data.reset_index(drop=True, inplace=True)
                self.endRemoveRows()
                return True
            return False
        except Exception as e:
            print(f"Error at remove_rows: {e}")
            self.logger.error(f"Error at remove_rows - {e}")
            return False


class InLineEditDelegate(QtWidgets.QItemDelegate):
    """
    Delegate is important for inline editing of cells
    """

    def createEditor(self, parent, option, index):
        return super(InLineEditDelegate, self).createEditor(parent, option, index)

    def setEditorData(self, editor, index):
        text = index.data(QtCore.Qt.EditRole) or index.data(
            QtCore.Qt.DisplayRole)
        editor.setText(str(text))
