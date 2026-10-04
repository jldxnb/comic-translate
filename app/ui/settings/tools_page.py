from PySide6 import QtWidgets
from ..dayu_widgets.label import MLabel
from ..dayu_widgets.check_box import MCheckBox
from ..dayu_widgets.spin_box import MSpinBox
from .utils import create_title_and_combo, set_combo_box_width
from modules.utils.device import is_gpu_available

class ToolsPage(QtWidgets.QWidget):
    def __init__(
        self, 
        translators: list[str], 
        ocr_engines: list[str], 
        detectors: list[str],
        inpainters: list[str], 
        inpaint_strategy: list[str], 
        parent=None
    ):
        super().__init__(parent)
        self.translators = translators
        self.ocr_engines = ocr_engines
        self.detectors = detectors
        self.inpainters = inpainters
        self.inpaint_strategy = inpaint_strategy

        layout = QtWidgets.QVBoxLayout(self)

        translator_widget, self.translator_combo = create_title_and_combo(self.tr("Translator"), self.translators, h4=True)
        set_combo_box_width(self.translator_combo, self.translators)

        # Batch translation (merged LLM requests)
        batch_label = MLabel(self.tr("Batch Translation")).h4()
        batch_hint = MLabel(self.tr(
            "1 page per request keeps the original behavior. Higher values merge several pages "
            "into a single LLM request and divide API request usage (RPD/RPM) by that factor. "
            "Merging is skipped automatically when image input is enabled."
        )).secondary()
        batch_hint.setWordWrap(True)

        batch_pages_layout = QtWidgets.QHBoxLayout()
        batch_pages_label = MLabel(self.tr("Pages per LLM Request:"))
        self.batch_pages_spinbox = MSpinBox().small()
        self.batch_pages_spinbox.setFixedWidth(70)
        self.batch_pages_spinbox.setMinimum(1)
        self.batch_pages_spinbox.setMaximum(20)
        self.batch_pages_spinbox.setValue(6)
        batch_pages_layout.addWidget(batch_pages_label)
        batch_pages_layout.addWidget(self.batch_pages_spinbox)
        batch_pages_layout.addStretch()

        batch_blocks_layout = QtWidgets.QHBoxLayout()
        batch_blocks_label = MLabel(self.tr("Max Text Blocks per Request:"))
        self.batch_blocks_spinbox = MSpinBox().small()
        self.batch_blocks_spinbox.setFixedWidth(70)
        self.batch_blocks_spinbox.setMinimum(20)
        self.batch_blocks_spinbox.setMaximum(400)
        self.batch_blocks_spinbox.setValue(100)
        batch_blocks_layout.addWidget(batch_blocks_label)
        batch_blocks_layout.addWidget(self.batch_blocks_spinbox)
        batch_blocks_layout.addStretch()

        batch_widget = QtWidgets.QWidget()
        batch_widget_layout = QtWidgets.QVBoxLayout(batch_widget)
        batch_widget_layout.setContentsMargins(0, 0, 0, 0)
        batch_widget_layout.addWidget(batch_hint)
        batch_widget_layout.addLayout(batch_pages_layout)
        batch_widget_layout.addLayout(batch_blocks_layout)


        ocr_widget, self.ocr_combo = create_title_and_combo(self.tr("Text Recognition"), self.ocr_engines, h4=True)
        set_combo_box_width(self.ocr_combo, self.ocr_engines)

        detector_widget, self.detector_combo = create_title_and_combo(self.tr("Text Detector"), self.detectors, h4=True)
        set_combo_box_width(self.detector_combo, self.detectors)

        # Detection sensitivity: lower thresholds catch stylized / floating text
        detector_threshold_layout = QtWidgets.QHBoxLayout()
        detector_threshold_label = MLabel(self.tr("Detection Threshold:"))
        self.detector_threshold_spinbox = QtWidgets.QDoubleSpinBox()
        self.detector_threshold_spinbox.setFixedWidth(80)
        self.detector_threshold_spinbox.setRange(0.05, 0.50)
        self.detector_threshold_spinbox.setSingleStep(0.05)
        self.detector_threshold_spinbox.setDecimals(2)
        self.detector_threshold_spinbox.setValue(0.30)
        detector_threshold_layout.addWidget(detector_threshold_label)
        detector_threshold_layout.addWidget(self.detector_threshold_spinbox)
        detector_threshold_layout.addStretch()

        detector_hint = MLabel(self.tr(
            "Lower values detect more text (floating SFX, stylized lettering) at the "
            "cost of possible false detections. Try 0.10\u20130.15 for SFX-heavy comics."
        )).secondary()
        detector_hint.setWordWrap(True)

        detector_threshold_widget = QtWidgets.QWidget()
        detector_threshold_widget_layout = QtWidgets.QVBoxLayout(detector_threshold_widget)
        detector_threshold_widget_layout.setContentsMargins(0, 0, 0, 0)
        detector_threshold_widget_layout.addLayout(detector_threshold_layout)
        detector_threshold_widget_layout.addWidget(detector_hint)

        inpainting_label = MLabel(self.tr("Image Cleaning")).h4()
        inpainter_widget, self.inpainter_combo = create_title_and_combo(self.tr("Inpainter"), self.inpainters, h4=False)
        set_combo_box_width(self.inpainter_combo, self.inpainters)
        self.inpainter_combo.setCurrentText(self.tr("AOT"))

        inpaint_strategy_widget, self.inpaint_strategy_combo = create_title_and_combo(self.tr("HD Strategy"), self.inpaint_strategy, h4=False)
        set_combo_box_width(self.inpaint_strategy_combo, self.inpaint_strategy)
        self.inpaint_strategy_combo.setCurrentText(self.tr("Resize"))

        # HD Strategy detail widgets
        self.hd_strategy_widgets = QtWidgets.QWidget()
        self.hd_strategy_layout = QtWidgets.QVBoxLayout(self.hd_strategy_widgets)

        # Resize panel
        self.resize_widget = QtWidgets.QWidget()
        about_resize_layout = QtWidgets.QVBoxLayout(self.resize_widget)
        resize_layout = QtWidgets.QHBoxLayout()
        resize_label = MLabel(self.tr("Resize Limit:"))
        about_resize_label = MLabel(self.tr("Resize the longer side of the image to a specific size,\nthen do inpainting on the resized image."))
        self.resize_spinbox = MSpinBox().small()
        self.resize_spinbox.setFixedWidth(70)
        self.resize_spinbox.setMaximum(3000)
        self.resize_spinbox.setValue(960)
        resize_layout.addWidget(resize_label)
        resize_layout.addWidget(self.resize_spinbox)
        resize_layout.addStretch()
        about_resize_layout.addWidget(about_resize_label)
        about_resize_layout.addLayout(resize_layout)
        about_resize_layout.setContentsMargins(5, 5, 5, 5)
        about_resize_layout.addStretch()

        # Crop panel
        self.crop_widget = QtWidgets.QWidget()
        crop_layout = QtWidgets.QVBoxLayout(self.crop_widget)
        about_crop_label = MLabel(self.tr("Crop masking area from the original image to do inpainting."))
        crop_margin_layout = QtWidgets.QHBoxLayout()
        crop_margin_label = MLabel(self.tr("Crop Margin:"))
        self.crop_margin_spinbox = MSpinBox().small()
        self.crop_margin_spinbox.setFixedWidth(70)
        self.crop_margin_spinbox.setMaximum(3000)
        self.crop_margin_spinbox.setValue(512)
        crop_margin_layout.addWidget(crop_margin_label)
        crop_margin_layout.addWidget(self.crop_margin_spinbox)
        crop_margin_layout.addStretch()

        crop_trigger_layout = QtWidgets.QHBoxLayout()
        crop_trigger_label = MLabel(self.tr("Crop Trigger Size:"))
        self.crop_trigger_spinbox = MSpinBox().small()
        self.crop_trigger_spinbox.setFixedWidth(70)
        self.crop_trigger_spinbox.setMaximum(3000)
        self.crop_trigger_spinbox.setValue(512)
        crop_trigger_layout.addWidget(crop_trigger_label)
        crop_trigger_layout.addWidget(self.crop_trigger_spinbox)
        crop_trigger_layout.addStretch()

        crop_layout.addWidget(about_crop_label)
        crop_layout.addLayout(crop_margin_layout)
        crop_layout.addLayout(crop_trigger_layout)
        crop_layout.setContentsMargins(5, 5, 5, 5)

        self.hd_strategy_layout.addWidget(self.resize_widget)
        self.hd_strategy_layout.addWidget(self.crop_widget)

        self.resize_widget.show()
        self.crop_widget.hide()
        self.inpaint_strategy_combo.currentIndexChanged.connect(self._update_hd_strategy_widgets)


        self.use_gpu_checkbox = MCheckBox(self.tr("Use GPU"))
        if not is_gpu_available():
            self.use_gpu_checkbox.setVisible(False)


        layout.addWidget(translator_widget)
        layout.addSpacing(10)
        layout.addWidget(batch_label)
        layout.addWidget(batch_widget)
        layout.addSpacing(10)
        layout.addWidget(detector_widget)
        layout.addWidget(detector_threshold_widget)
        layout.addSpacing(10)
        layout.addWidget(ocr_widget)
        layout.addSpacing(10)
        layout.addWidget(inpainting_label)
        layout.addWidget(inpainter_widget)
        layout.addWidget(inpaint_strategy_widget)
        layout.addWidget(self.hd_strategy_widgets)
        layout.addSpacing(10)
        layout.addWidget(self.use_gpu_checkbox)
        layout.addStretch(1)

        self._update_hd_strategy_widgets(self.inpaint_strategy_combo.currentIndex())

    def _update_hd_strategy_widgets(self, index: int):
        strategy = self.inpaint_strategy_combo.itemText(index)
        self.resize_widget.setVisible(strategy == self.tr("Resize"))
        self.crop_widget.setVisible(strategy == self.tr("Crop"))
        if strategy == self.tr("Original"):
            self.hd_strategy_widgets.setFixedHeight(0)
        else:
            self.hd_strategy_widgets.setFixedHeight(self.hd_strategy_widgets.sizeHint().height())
