from datetime import datetime

from app_settings import AppSettings
from backend.models.lcmdiffusion_setting import DiffusionTask
from constants import (
    APP_NAME,
    APP_VERSION,
    LCM_DEFAULT_MODEL,
    LCM_DEFAULT_MODEL_OPENVINO,
)
from context import Context
from frontend.gui.image_variations_widget import ImageVariationsWidget
from frontend.gui.upscaler_widget import UpscalerWidget
from frontend.gui.img2img_widget import Img2ImgWidget
from frontend.utils import (
    enable_openvino_controls,
    get_valid_model_id,
    is_reshape_required,
)
from paths import FastStableDiffusionPaths
from PyQt5 import QtCore, QtWidgets
from PyQt5.QtCore import QSize, Qt, QThreadPool, QUrl
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSpacerItem,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from models.interface_types import InterfaceType
from frontend.gui.base_widget import BaseWidget

# DPI scale fix
QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)


class MainWindow(QMainWindow):
    settings_changed = QtCore.pyqtSignal()
    """ This signal is used for enabling/disabling the negative prompt field for 
    modes that support it; in particular, negative prompt is supported with OpenVINO models 
    and in LCM-LoRA mode but not in LCM mode
    """

    def __init__(self, config: AppSettings):
        super().__init__()
        self.config = config
        # Prevent saved LoRA and ControlNet settings from being used by
        # default; in GUI mode, the user must explicitly enable those
        if self.config.settings.lcm_diffusion_setting.lora:
            self.config.settings.lcm_diffusion_setting.lora.enabled = False
        if self.config.settings.lcm_diffusion_setting.controlnet:
            self.config.settings.lcm_diffusion_setting.controlnet.enabled = False
        self.setWindowTitle(APP_NAME)
        self.setFixedSize(QSize(600, 670))
        self.init_ui()
        self.pipeline = None
        self.threadpool = QThreadPool()
        self.device = "cpu"
        self.previous_width = 0
        self.previous_height = 0
        self.previous_model = ""
        self.previous_num_of_images = 0
        self.context = Context(InterfaceType.GUI)
        self.init_ui_values()
        self.gen_images = []
        self.image_index = 0
        print(f"Output path : {self.config.settings.generated_images.path}")

    def init_ui_values(self):
        self.lcm_model.setEnabled(
            not self.config.settings.lcm_diffusion_setting.use_openvino
        )
        self.guidance.setValue(
            int(self.config.settings.lcm_diffusion_setting.guidance_scale * 10)
        )
        self.seed_value.setEnabled(self.config.settings.lcm_diffusion_setting.use_seed)
        self.safety_checker.setChecked(
            self.config.settings.lcm_diffusion_setting.use_safety_checker
        )
        self.use_openvino_check.setChecked(
            self.config.settings.lcm_diffusion_setting.use_openvino
        )
        self.width.setCurrentText(
            str(self.config.settings.lcm_diffusion_setting.image_width)
        )
        self.height.setCurrentText(
            str(self.config.settings.lcm_diffusion_setting.image_height)
        )
        self.inference_steps.setValue(
            int(self.config.settings.lcm_diffusion_setting.inference_steps)
        )
        self.clip_skip.setValue(
            int(self.config.settings.lcm_diffusion_setting.clip_skip)
        )
        self.token_merging.setValue(
            int(self.config.settings.lcm_diffusion_setting.token_merging * 100)
        )
        self.seed_check.setChecked(self.config.settings.lcm_diffusion_setting.use_seed)
        self.seed_value.setText(str(self.config.settings.lcm_diffusion_setting.seed))
        self.use_local_model_folder.setChecked(
            self.config.settings.lcm_diffusion_setting.use_offline_model
        )
        self.results_path.setText(self.config.settings.generated_images.path)
        self.num_images.setValue(
            self.config.settings.lcm_diffusion_setting.number_of_images
        )
        self.use_tae_sd.setChecked(
            self.config.settings.lcm_diffusion_setting.use_tiny_auto_encoder
        )
        self.use_lcm_lora.setChecked(
            self.config.settings.lcm_diffusion_setting.use_lcm_lora
        )
        self.lcm_model.setCurrentText(
            get_valid_model_id(
                self.config.lcm_models,
                self.config.settings.lcm_diffusion_setting.lcm_model_id,
                LCM_DEFAULT_MODEL,
            )
        )
        self.base_model_id.setCurrentText(
            get_valid_model_id(
                self.config.stable_diffsuion_models,
                self.config.settings.lcm_diffusion_setting.lcm_lora.base_model_id,
            )
        )
        self.lcm_lora_id.setCurrentText(
            get_valid_model_id(
                self.config.lcm_lora_models,
                self.config.settings.lcm_diffusion_setting.lcm_lora.lcm_lora_id,
            )
        )
        self.openvino_lcm_model_id.setCurrentText(
            get_valid_model_id(
                self.config.openvino_lcm_models,
                self.config.settings.lcm_diffusion_setting.openvino_lcm_model_id,
                LCM_DEFAULT_MODEL_OPENVINO,
            )
        )
        self.openvino_lcm_model_id.setEnabled(
            self.config.settings.lcm_diffusion_setting.use_openvino
        )

    def init_ui(self):
        self.create_main_tab()
        self.create_settings_tab()
        self.create_about_tab()
        self.show()

    def create_main_tab(self):
        self.tab_widget = QTabWidget(self)
        self.tab_main = BaseWidget(self.config, self)
        self.tab_settings = QWidget()
        self.tab_about = QWidget()
        self.img2img_tab = Img2ImgWidget(self.config, self)
        self.variations_tab = ImageVariationsWidget(self.config, self)
        self.upscaler_tab = UpscalerWidget(self.config, self)

        # Add main window tabs here
        self.tab_widget.addTab(self.tab_main, "Text to Image")
        self.tab_widget.addTab(self.img2img_tab, "Image to Image")
        self.tab_widget.addTab(self.variations_tab, "Image Variations")
        self.tab_widget.addTab(self.upscaler_tab, "Upscaler")
        self.tab_widget.addTab(self.tab_settings, "Settings")
        self.tab_widget.addTab(self.tab_about, "About")

        self.setCentralWidget(self.tab_widget)
        self.use_seed = False

    def create_settings_tab(self):
        self.lcm_model_label = QLabel("Latent Consistency Model:")
        # self.lcm_model = QLineEdit(LCM_DEFAULT_MODEL)
        self.lcm_model = QComboBox(self)
        self.lcm_model.addItems(self.config.lcm_models)
        self.lcm_model.currentIndexChanged.connect(self.on_lcm_model_changed)

        self.use_lcm_lora = QCheckBox("Use LCM LoRA")
        self.use_lcm_lora.setChecked(False)
        self.use_lcm_lora.stateChanged.connect(self.use_lcm_lora_changed)

        self.lora_base_model_id_label = QLabel("Lora base model ID :")
        self.base_model_id = QComboBox(self)
        self.base_model_id.addItems(self.config.stable_diffsuion_models)
        self.base_model_id.currentIndexChanged.connect(self.on_base_model_id_changed)

        self.lcm_lora_model_id_label = QLabel("LCM LoRA model ID :")
        self.lcm_lora_id = QComboBox(self)
        self.lcm_lora_id.addItems(self.config.lcm_lora_models)
        self.lcm_lora_id.currentIndexChanged.connect(self.on_lcm_lora_id_changed)

        self.inference_steps_value = QLabel("Number of inference steps: 4")
        self.inference_steps = QSlider(orientation=Qt.Orientation.Horizontal)
        self.inference_steps.setMaximum(25)
        self.inference_steps.setMinimum(1)
        self.inference_steps.setValue(4)
        self.inference_steps.valueChanged.connect(self.update_steps_label)

        self.num_images_value = QLabel("Number of images: 1")
        self.num_images = QSlider(orientation=Qt.Orientation.Horizontal)
        self.num_images.setMaximum(100)
        self.num_images.setMinimum(1)
        self.num_images.setValue(1)
        self.num_images.valueChanged.connect(self.update_num_images_label)

        self.guidance_value = QLabel("Guidance scale: 1")
        self.guidance = QSlider(orientation=Qt.Orientation.Horizontal)
        self.guidance.setMaximum(20)
        self.guidance.setMinimum(10)
        self.guidance.setValue(10)
        self.guidance.valueChanged.connect(self.update_guidance_label)

        self.clip_skip_value = QLabel("CLIP Skip: 1")
        self.clip_skip = QSlider(orientation=Qt.Orientation.Horizontal)
        self.clip_skip.setMaximum(12)
        self.clip_skip.setMinimum(1)
        self.clip_skip.setValue(1)
        self.clip_skip.valueChanged.connect(self.update_clip_skip_label)

        self.token_merging_value = QLabel("Token Merging: 0")
        self.token_merging = QSlider(orientation=Qt.Orientation.Horizontal)
        self.token_merging.setMaximum(100)
        self.token_merging.setMinimum(0)
        self.token_merging.setValue(0)
        self.token_merging.valueChanged.connect(self.update_token_merging_label)

        self.width_value = QLabel("Width :")
        self.width = QComboBox(self)
        self.width.addItem("256")
        self.width.addItem("512")
        self.width.addItem("768")
        self.width.addItem("1024")
        self.width.setCurrentText("512")
        self.width.currentIndexChanged.connect(self.on_width_changed)

        self.height_value = QLabel("Height :")
        self.height = QComboBox(self)
        self.height.addItem("256")
        self.height.addItem("512")
        self.height.addItem("768")
        self.height.addItem("1024")
        self.height.setCurrentText("512")
        self.height.currentIndexChanged.connect(self.on_height_changed)

        self.seed_check = QCheckBox("Use seed")
        self.seed_value = QLineEdit()
        self.seed_value.setInputMask("9999999999")
        self.seed_value.setText("123123")
        self.seed_check.stateChanged.connect(self.seed_changed)

        self.safety_checker = QCheckBox("Use safety checker")
        self.safety_checker.setChecked(True)
        self.safety_checker.stateChanged.connect(self.use_safety_checker_changed)

        self.use_openvino_check = QCheckBox("Use OpenVINO")
        self.use_openvino_check.setChecked(False)
        self.openvino_model_label = QLabel("OpenVINO LCM model:")
        self.use_local_model_folder = QCheckBox(
            "Use locally cached model or downloaded model folder(offline)"
        )
        self.openvino_lcm_model_id = QComboBox(self)
        self.openvino_lcm_model_id.addItems(self.config.openvino_lcm_models)
        self.openvino_lcm_model_id.currentIndexChanged.connect(
            self.on_openvino_lcm_model_id_changed
        )

        self.use_openvino_check.setEnabled(enable_openvino_controls())
        self.use_local_model_folder.setChecked(False)
        self.use_local_model_folder.stateChanged.connect(self.use_offline_model_changed)
        self.use_openvino_check.stateChanged.connect(self.use_openvino_changed)

        self.use_tae_sd = QCheckBox("Use Tiny AutoEncoder (Fast, moderate quality)")
        self.use_tae_sd.setChecked(False)
        self.use_tae_sd.stateChanged.connect(self.use_tae_sd_changed)

        hlayout = QHBoxLayout()
        hlayout.addWidget(self.seed_check)
        hlayout.addWidget(self.seed_value)
        hspacer = QSpacerItem(20, 10, QSizePolicy.Expanding, QSizePolicy.Minimum)
        slider_hspacer = QSpacerItem(20, 10, QSizePolicy.Expanding, QSizePolicy.Minimum)

        self.results_path_label = QLabel("Output path:")
        self.results_path = QLineEdit()
        self.results_path.textChanged.connect(self.on_path_changed)
        self.browse_folder_btn = QToolButton()
        self.browse_folder_btn.setText("...")
        self.browse_folder_btn.clicked.connect(self.on_browse_folder)

        self.reset = QPushButton("Reset All")
        self.reset.clicked.connect(self.reset_all_settings)

        vlayout = QVBoxLayout()
        vspacer = QSpacerItem(20, 20, QSizePolicy.Minimum, QSizePolicy.Expanding)
        vlayout.addItem(hspacer)
        vlayout.setSpacing(3)
        vlayout.addWidget(self.lcm_model_label)
        vlayout.addWidget(self.lcm_model)
        vlayout.addWidget(self.use_local_model_folder)
        vlayout.addWidget(self.use_lcm_lora)
        vlayout.addWidget(self.lora_base_model_id_label)
        vlayout.addWidget(self.base_model_id)
        vlayout.addWidget(self.lcm_lora_model_id_label)
        vlayout.addWidget(self.lcm_lora_id)
        vlayout.addWidget(self.use_openvino_check)
        vlayout.addWidget(self.openvino_model_label)
        vlayout.addWidget(self.openvino_lcm_model_id)
        vlayout.addWidget(self.use_tae_sd)
        vlayout.addItem(slider_hspacer)
        vlayout.addWidget(self.inference_steps_value)
        vlayout.addWidget(self.inference_steps)
        vlayout.addWidget(self.num_images_value)
        vlayout.addWidget(self.num_images)
        vlayout.addWidget(self.width_value)
        vlayout.addWidget(self.width)
        vlayout.addWidget(self.height_value)
        vlayout.addWidget(self.height)
        vlayout.addWidget(self.guidance_value)
        vlayout.addWidget(self.guidance)
        vlayout.addWidget(self.clip_skip_value)
        vlayout.addWidget(self.clip_skip)
        vlayout.addWidget(self.token_merging_value)
        vlayout.addWidget(self.token_merging)
        vlayout.addLayout(hlayout)
        vlayout.addWidget(self.safety_checker)

        vlayout.addWidget(self.results_path_label)
        hlayout_path = QHBoxLayout()
        hlayout_path.addWidget(self.results_path)
        hlayout_path.addWidget(self.browse_folder_btn)
        vlayout.addLayout(hlayout_path)
        self.tab_settings.setLayout(vlayout)
        hlayout_reset = QHBoxLayout()
        hspacer = QSpacerItem(20, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        hlayout_reset.addItem(hspacer)
        hlayout_reset.addWidget(self.reset)
        vlayout.addLayout(hlayout_reset)
        vlayout.addItem(vspacer)

    def create_about_tab(self):
        self.label = QLabel()
        self.label.setAlignment(Qt.AlignCenter)
        current_year = datetime.now().year
        self.label.setText(
            f"""<h1>FastSD CPU {APP_VERSION}</h1> 
               <h3>(c)2023 - {current_year} Rupesh Sreeraman</h3>
                <h3>Faster stable diffusion on CPU</h3>
                 <h3>Based on Latent Consistency Models</h3>
                <h3>GitHub : https://github.com/rupeshs/fastsdcpu/</h3>"""
        )

        vlayout = QVBoxLayout()
        vlayout.addWidget(self.label)
        self.tab_about.setLayout(vlayout)

    def show_image(self, pixmap):
        image_width = self.config.settings.lcm_diffusion_setting.image_width
        image_height = self.config.settings.lcm_diffusion_setting.image_height
        if image_width > 512 or image_height > 512:
            new_width = 512 if image_width > 512 else image_width
            new_height = 512 if image_height > 512 else image_height
            self.img.setPixmap(
                pixmap.scaled(
                    new_width,
                    new_height,
                    Qt.KeepAspectRatio,
                )
            )
        else:
            self.img.setPixmap(pixmap)

    def on_show_next_image(self):
        if self.image_index != len(self.gen_images) - 1 and len(self.gen_images) > 0:
            self.previous_img_btn.setEnabled(True)
            self.image_index += 1
            self.show_image(self.gen_images[self.image_index])
            if self.image_index == len(self.gen_images) - 1:
                self.next_img_btn.setEnabled(False)

    def on_open_results_folder(self):
        QDesktopServices.openUrl(
            QUrl.fromLocalFile(self.config.settings.generated_images.path)
        )

    def on_show_previous_image(self):
        if self.image_index != 0:
            self.next_img_btn.setEnabled(True)
            self.image_index -= 1
            self.show_image(self.gen_images[self.image_index])
            if self.image_index == 0:
                self.previous_img_btn.setEnabled(False)

    def on_path_changed(self, text):
        self.config.settings.generated_images.path = text

    def on_browse_folder(self):
        options = QFileDialog.Options()
        options |= QFileDialog.ShowDirsOnly

        folder_path = QFileDialog.getExistingDirectory(
            self, "Select a Folder", "", options=options
        )

        if folder_path:
            self.config.settings.generated_images.path = folder_path
            self.results_path.setText(folder_path)

    def on_width_changed(self, index):
        width_txt = self.width.itemText(index)
        self.config.settings.lcm_diffusion_setting.image_width = int(width_txt)

    def on_height_changed(self, index):
        height_txt = self.height.itemText(index)
        self.config.settings.lcm_diffusion_setting.image_height = int(height_txt)

    def on_lcm_model_changed(self, index):
        model_id = self.lcm_model.itemText(index)
        self.config.settings.lcm_diffusion_setting.lcm_model_id = model_id

    def on_base_model_id_changed(self, index):
        model_id = self.base_model_id.itemText(index)
        self.config.settings.lcm_diffusion_setting.lcm_lora.base_model_id = model_id

    def on_lcm_lora_id_changed(self, index):
        model_id = self.lcm_lora_id.itemText(index)
        self.config.settings.lcm_diffusion_setting.lcm_lora.lcm_lora_id = model_id

    def on_openvino_lcm_model_id_changed(self, index):
        model_id = self.openvino_lcm_model_id.itemText(index)
        self.config.settings.lcm_diffusion_setting.openvino_lcm_model_id = model_id

    def use_openvino_changed(self, state):
        if state == 2:
            self.lcm_model.setEnabled(False)
            self.use_lcm_lora.setEnabled(False)
            self.lcm_lora_id.setEnabled(False)
            self.base_model_id.setEnabled(False)
            self.openvino_lcm_model_id.setEnabled(True)
            self.config.settings.lcm_diffusion_setting.use_openvino = True
        else:
            self.lcm_model.setEnabled(True)
            self.use_lcm_lora.setEnabled(True)
            self.lcm_lora_id.setEnabled(True)
            self.base_model_id.setEnabled(True)
            self.openvino_lcm_model_id.setEnabled(False)
            self.config.settings.lcm_diffusion_setting.use_openvino = False
        self.settings_changed.emit()

    def use_tae_sd_changed(self, state):
        if state == 2:
            self.config.settings.lcm_diffusion_setting.use_tiny_auto_encoder = True
        else:
            self.config.settings.lcm_diffusion_setting.use_tiny_auto_encoder = False

    def use_offline_model_changed(self, state):
        if state == 2:
            self.config.settings.lcm_diffusion_setting.use_offline_model = True
        else:
            self.config.settings.lcm_diffusion_setting.use_offline_model = False

    def use_lcm_lora_changed(self, state):
        if state == 2:
            self.lcm_model.setEnabled(False)
            self.lcm_lora_id.setEnabled(True)
            self.base_model_id.setEnabled(True)
            self.config.settings.lcm_diffusion_setting.use_lcm_lora = True
        else:
            self.lcm_model.setEnabled(True)
            self.lcm_lora_id.setEnabled(False)
            self.base_model_id.setEnabled(False)
            self.config.settings.lcm_diffusion_setting.use_lcm_lora = False
        self.settings_changed.emit()

    def update_clip_skip_label(self, value):
        self.clip_skip_value.setText(f"CLIP Skip: {value}")
        self.config.settings.lcm_diffusion_setting.clip_skip = value

    def update_token_merging_label(self, value):
        val = round(int(value) / 100, 1)
        self.token_merging_value.setText(f"Token Merging: {val}")
        self.config.settings.lcm_diffusion_setting.token_merging = val

    def use_safety_checker_changed(self, state):
        if state == 2:
            self.config.settings.lcm_diffusion_setting.use_safety_checker = True
        else:
            self.config.settings.lcm_diffusion_setting.use_safety_checker = False

    def update_steps_label(self, value):
        self.inference_steps_value.setText(f"Number of inference steps: {value}")
        self.config.settings.lcm_diffusion_setting.inference_steps = value

    def update_num_images_label(self, value):
        self.num_images_value.setText(f"Number of images: {value}")
        self.config.settings.lcm_diffusion_setting.number_of_images = value

    def update_guidance_label(self, value):
        val = round(int(value) / 10, 1)
        self.guidance_value.setText(f"Guidance scale: {val}")
        self.config.settings.lcm_diffusion_setting.guidance_scale = val

    def seed_changed(self, state):
        if state == 2:
            self.seed_value.setEnabled(True)
            self.config.settings.lcm_diffusion_setting.use_seed = True
        else:
            self.seed_value.setEnabled(False)
            self.config.settings.lcm_diffusion_setting.use_seed = False

    def get_seed_value(self) -> int:
        use_seed = self.config.settings.lcm_diffusion_setting.use_seed
        seed_value = int(self.seed_value.text()) if use_seed else -1
        return seed_value

    # def text_to_image(self):
    #    self.img.setText("Please wait...")
    #    worker = ImageGeneratorWorker(self.generate_image)
    #    self.threadpool.start(worker)

    def closeEvent(self, event):
        self.config.settings.lcm_diffusion_setting.seed = self.get_seed_value()
        print(self.config.settings.lcm_diffusion_setting)
        print("Saving settings")
        self.config.save()

    def reset_all_settings(self):
        self.use_local_model_folder.setChecked(False)
        self.width.setCurrentText("512")
        self.height.setCurrentText("512")
        self.inference_steps.setValue(4)
        self.guidance.setValue(10)
        self.clip_skip.setValue(1)
        self.token_merging.setValue(0)
        self.use_openvino_check.setChecked(False)
        self.seed_check.setChecked(False)
        self.safety_checker.setChecked(False)
        self.results_path.setText(FastStableDiffusionPaths().get_results_path())
        self.use_tae_sd.setChecked(False)
        self.use_lcm_lora.setChecked(False)

    def prepare_generation_settings(self, config):
        """Populate config settings with the values set by the user in the GUI"""
        config.settings.lcm_diffusion_setting.seed = self.get_seed_value()
        config.settings.lcm_diffusion_setting.lcm_lora.lcm_lora_id = (
            self.lcm_lora_id.currentText()
        )
        config.settings.lcm_diffusion_setting.lcm_lora.base_model_id = (
            self.base_model_id.currentText()
        )

        if config.settings.lcm_diffusion_setting.use_openvino:
            model_id = self.openvino_lcm_model_id.currentText()
            config.settings.lcm_diffusion_setting.openvino_lcm_model_id = model_id
        else:
            model_id = self.lcm_model.currentText()
            config.settings.lcm_diffusion_setting.lcm_model_id = model_id

        config.reshape_required = False
        config.model_id = model_id
        if config.settings.lcm_diffusion_setting.use_openvino:
            # Detect dimension change
            config.reshape_required = is_reshape_required(
                self.previous_width,
                config.settings.lcm_diffusion_setting.image_width,
                self.previous_height,
                config.settings.lcm_diffusion_setting.image_height,
                self.previous_model,
                model_id,
                self.previous_num_of_images,
                config.settings.lcm_diffusion_setting.number_of_images,
            )
        config.settings.lcm_diffusion_setting.diffusion_task = (
            DiffusionTask.text_to_image.value
        )

    def store_dimension_settings(self):
        """These values are only needed for OpenVINO model reshape"""
        self.previous_width = self.config.settings.lcm_diffusion_setting.image_width
        self.previous_height = self.config.settings.lcm_diffusion_setting.image_height
        self.previous_model = self.config.model_id
        self.previous_num_of_images = (
            self.config.settings.lcm_diffusion_setting.number_of_images
        )
