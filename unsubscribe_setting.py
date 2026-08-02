"""Small UI state controller for the server-owned unsubscribe setting."""


class UnsubscribeSettingController:
    def __init__(self, checkbox, load, save):
        self.checkbox = checkbox
        self.load = load
        self.save = save
        self.current_value = False

    def apply_loaded_value(self, enabled):
        previous = self.checkbox.blockSignals(True)
        self.checkbox.setChecked(bool(enabled))
        self.checkbox.setEnabled(True)
        self.checkbox.blockSignals(previous)
        self.current_value = bool(enabled)

    def persist_value(self, requested):
        return bool(self.save(bool(requested)))

    def restore_current_value(self):
        previous = self.checkbox.blockSignals(True)
        self.checkbox.setChecked(self.current_value)
        self.checkbox.setEnabled(True)
        self.checkbox.blockSignals(previous)
