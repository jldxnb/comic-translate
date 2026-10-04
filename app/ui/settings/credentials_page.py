from PySide6 import QtWidgets, QtCore
from ..dayu_widgets.label import MLabel
from ..dayu_widgets.line_edit import MLineEdit
from ..dayu_widgets.check_box import MCheckBox
from ..dayu_widgets.push_button import MPushButton
from ..dayu_widgets.combo_box import MComboBox
from .utils import set_label_width


NEW_PROFILE_LABEL = "(New profile)"


class CredentialsPage(QtWidgets.QWidget):
    """Credentials settings. The Custom service is a multi-profile editor:
    users define several OpenAI-compatible endpoints and pick one in
    Settings > Tools > Translator (shown as 'Custom: <name>')."""

    profiles_changed = QtCore.Signal()

    def __init__(self, services: list[str], value_mappings: dict[str, str], parent=None):
        super().__init__(parent)
        self.services = services
        self.value_mappings = value_mappings
        self.credential_widgets: dict[str, MLineEdit] = {}

        self._profiles: list[dict] = []
        self._editing_name: str = ""
        self._updating_profile_ui = False

        # main layout (no internal scroll here — outer settings scroll handles it)
        main_layout = QtWidgets.QVBoxLayout(self)
        content_layout = QtWidgets.QVBoxLayout()

        self.save_keys_checkbox = MCheckBox(self.tr("Save Keys"))

        info_label = MLabel(self.tr(
            "These settings are for advanced users who wish to use their own Custom API endpoints (e.g. Local Language Models) for translation. "
            "For most users, no configuration is needed here."
        )).secondary()
        info_label.setWordWrap(True)

        content_layout.addWidget(info_label)
        content_layout.addSpacing(10)
        content_layout.addWidget(self.save_keys_checkbox)
        content_layout.addSpacing(20)

        for service_label in self.services:
            service_layout = QtWidgets.QVBoxLayout()
            service_header = MLabel(service_label).strong()
            service_header.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
            service_layout.addWidget(service_header)

            normalized = self.value_mappings.get(service_label, service_label)

            if normalized == "Custom":
                self._build_custom_profiles_section(service_layout)
            elif normalized == "Microsoft Azure":
                # OCR
                ocr_label = MLabel(self.tr("OCR")).secondary()
                service_layout.addWidget(ocr_label)

                ocr_api_key_input = MLineEdit()
                ocr_api_key_input.setEchoMode(QtWidgets.QLineEdit.Password)
                ocr_api_key_input.setFixedWidth(400)
                ocr_api_key_prefix = MLabel(self.tr("API Key")).border()
                set_label_width(ocr_api_key_prefix)
                ocr_api_key_prefix.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                ocr_api_key_input.set_prefix_widget(ocr_api_key_prefix)
                service_layout.addWidget(ocr_api_key_input)
                self.credential_widgets["Microsoft Azure_api_key_ocr"] = ocr_api_key_input

                endpoint_input = MLineEdit()
                endpoint_input.setFixedWidth(400)
                endpoint_prefix = MLabel(self.tr("Endpoint URL")).border()
                set_label_width(endpoint_prefix)
                endpoint_prefix.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                endpoint_input.set_prefix_widget(endpoint_prefix)
                service_layout.addWidget(endpoint_input)
                self.credential_widgets["Microsoft Azure_endpoint"] = endpoint_input

            elif normalized == "Yandex":
                api_key_input = MLineEdit()
                api_key_input.setEchoMode(QtWidgets.QLineEdit.Password)
                api_key_input.setFixedWidth(400)
                api_key_prefix = MLabel(self.tr("Secret Key")).border()
                set_label_width(api_key_prefix)
                api_key_prefix.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                api_key_input.set_prefix_widget(api_key_prefix)
                service_layout.addWidget(api_key_input)
                self.credential_widgets[f"{normalized}_api_key"] = api_key_input

                folder_id_input = MLineEdit()
                folder_id_input.setFixedWidth(400)
                folder_id_prefix = MLabel(self.tr("Folder ID")).border()
                set_label_width(folder_id_prefix)
                folder_id_prefix.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                folder_id_input.set_prefix_widget(folder_id_prefix)
                service_layout.addWidget(folder_id_input)
                self.credential_widgets[f"{normalized}_folder_id"] = folder_id_input

            else:
                self._build_custom_profiles_section(service_layout)

            content_layout.addLayout(service_layout)
            content_layout.addSpacing(20)

        content_layout.addStretch(1)
        main_layout.addLayout(content_layout)

        self._refresh_profile_combo(select=None)
        self._load_profile_into_fields(None)

    # ------------------------------------------------------------------
    # Custom profile editor
    # ------------------------------------------------------------------
    def _build_custom_profiles_section(self, service_layout: QtWidgets.QVBoxLayout):
        hint = MLabel(self.tr(
            "Define one or more OpenAI-compatible endpoints. Each profile appears in "
            "Settings > Tools > Translator as 'Custom: <name>'."
        )).secondary()
        hint.setWordWrap(True)
        service_layout.addWidget(hint)

        combo_row = QtWidgets.QHBoxLayout()
        combo_label = MLabel(self.tr("Model Profile:"))
        self.custom_profile_combo = MComboBox().small()
        self.custom_profile_combo.setFixedWidth(260)
        combo_row.addWidget(combo_label)
        combo_row.addWidget(self.custom_profile_combo)
        self.delete_profile_button = MPushButton(self.tr("Delete")).small()
        combo_row.addWidget(self.delete_profile_button)
        combo_row.addStretch()
        service_layout.addLayout(combo_row)

        def _field(prefix_text: str, password: bool = False) -> MLineEdit:
            field = MLineEdit()
            if password:
                field.setEchoMode(QtWidgets.QLineEdit.Password)
            field.setFixedWidth(400)
            prefix = MLabel(prefix_text).border()
            set_label_width(prefix)
            prefix.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            field.set_prefix_widget(prefix)
            service_layout.addWidget(field)
            return field

        self.custom_name_input = _field(self.tr("Name"))
        self.custom_api_key_input = _field(self.tr("API Key"), password=True)
        self.custom_api_url_input = _field(self.tr("Endpoint URL"))
        self.custom_model_input = _field(self.tr("Model"))

        save_row = QtWidgets.QHBoxLayout()
        self.save_profile_button = MPushButton(self.tr("Add / Update Profile"))
        save_row.addWidget(self.save_profile_button)
        save_row.addStretch()
        service_layout.addLayout(save_row)

        # Keep legacy widget keys available for any external readers.
        self.credential_widgets["Custom_api_key"] = self.custom_api_key_input
        self.credential_widgets["Custom_api_url"] = self.custom_api_url_input
        self.credential_widgets["Custom_model"] = self.custom_model_input

        self.custom_profile_combo.currentIndexChanged.connect(self._on_profile_combo_changed)
        self.save_profile_button.clicked.connect(self._on_save_profile_clicked)
        self.delete_profile_button.clicked.connect(self._on_delete_profile_clicked)

    def get_custom_profiles(self, commit: bool = False) -> list[dict]:
        """Current profiles. Pass commit=True from the settings-save path to
        first fold any pending field edits into the list. The default avoids
        touching widgets (this is also called from translation workers)."""
        if commit:
            self._commit_fields()
        return [dict(profile) for profile in self._profiles]

    def set_custom_profiles(self, profiles: list[dict] | None) -> None:
        self._profiles = [dict(profile) for profile in (profiles or [])]
        first = self._profiles[0]["name"] if self._profiles else None
        self._refresh_profile_combo(select=first)
        self._load_profile_into_fields(first)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _upsert_profile(self, entry: dict) -> None:
        for index, profile in enumerate(self._profiles):
            if profile["name"] == entry["name"]:
                self._profiles[index] = entry
                return
        self._profiles.append(entry)

    def _commit_fields(self) -> None:
        """Fold the current field values into the profile list."""
        if self._updating_profile_ui:
            return
        name = self.custom_name_input.text().strip()
        if not name:
            self._editing_name = ""
            return
        entry = {
            "name": name,
            "api_key": self.custom_api_key_input.text().strip(),
            "api_url": self.custom_api_url_input.text().strip(),
            "model": self.custom_model_input.text().strip(),
        }
        if self._editing_name and self._editing_name != name:
            for index, profile in enumerate(self._profiles):
                if profile["name"] == self._editing_name:
                    self._profiles[index] = entry
                    break
            else:
                self._upsert_profile(entry)
        else:
            self._upsert_profile(entry)
        self._editing_name = name
        self._refresh_profile_combo(select=name)

    def _refresh_profile_combo(self, select: str | None) -> None:
        self._updating_profile_ui = True
        try:
            combo = self.custom_profile_combo
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(self.tr(NEW_PROFILE_LABEL), "")
            for profile in self._profiles:
                combo.addItem(profile["name"], profile["name"])
            index = combo.findData(select) if select else 0
            combo.setCurrentIndex(max(0, index))
            combo.blockSignals(False)
        finally:
            self._updating_profile_ui = False
        self.profiles_changed.emit()

    def _find_profile(self, name: str | None) -> dict | None:
        if not name:
            return None
        for profile in self._profiles:
            if profile["name"] == name:
                return profile
        return None

    def _load_profile_into_fields(self, name: str | None) -> None:
        profile = self._find_profile(name)
        self._editing_name = profile["name"] if profile else ""
        self.custom_name_input.setText(profile["name"] if profile else "")
        self.custom_api_key_input.setText(profile.get("api_key", "") if profile else "")
        self.custom_api_url_input.setText(profile.get("api_url", "") if profile else "")
        self.custom_model_input.setText(profile.get("model", "") if profile else "")

    def _on_profile_combo_changed(self, _index: int) -> None:
        if self._updating_profile_ui:
            return
        self._commit_fields()
        name = self.custom_profile_combo.currentData() or ""
        self._load_profile_into_fields(name)

    def _on_save_profile_clicked(self) -> None:
        self._commit_fields()

    def _on_delete_profile_clicked(self) -> None:
        name = self.custom_profile_combo.currentData() or self._editing_name
        if not name:
            return
        self._profiles = [profile for profile in self._profiles if profile["name"] != name]
        self._editing_name = ""
        first = self._profiles[0]["name"] if self._profiles else None
        self._refresh_profile_combo(select=first)
        self._load_profile_into_fields(first)
