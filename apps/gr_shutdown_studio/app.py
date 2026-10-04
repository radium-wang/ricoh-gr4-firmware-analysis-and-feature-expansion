"""GR Shutdown Studio desktop interface."""
from __future__ import annotations

import sys
import re
from pathlib import Path

from PIL import Image
from PySide6.QtCore import Qt, QThread, Signal, QSettings, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap, QImage, QPalette
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QFileDialog, QMessageBox,
    QCheckBox, QFrame, QSlider, QDialog, QProgressBar, QRadioButton,
    QButtonGroup, QScrollArea, QSizePolicy, QTableWidget, QTableWidgetItem, QHeaderView, QInputDialog,
)
from .core import Session, render_image, WorkflowError
from .compatibility import PROFILES, installation_allowed
from . import __version__

TEXT = {
 'title': ('GR Shutdown Studio', 'GR Shutdown Studio'),
 'subtitle': ('Your own image. A new goodbye.', '让每次关机，都有自己的画面。'),
 'camera': ('Camera', '相机'),
 'family': ('GR IV / HDF / Monochrome', 'GR IV / HDF / Monochrome'),
 'urban': ('GR IIIx Urban Edition · 1.60', 'GR IIIx Urban Edition · 1.60'),
 'card': ('SD card', 'SD 卡'), 'choose': ('Choose…', '选择…'),
 'card_hint': ('Choose the FAT32 card root from your card reader.', '选择读卡器中 FAT32 SD 卡的根目录。'),
 'image': ('Image', '图片'), 'choose_image': ('Choose an image', '选择自己的图片'),
 'image_hint': ('JPEG, PNG, WebP or TIFF. Crop and preview before preparing.', '支持 JPEG、PNG、WebP、TIFF，选图后可裁剪和预览。'),
 'crop': ('Fill frame', '填满画面'), 'contain': ('Fit with borders', '完整显示，保留边框'),
 'horizontal': ('Horizontal position', '水平位置'), 'vertical': ('Vertical position', '垂直位置'),
 'empty_preview': ('Choose a photo to preview\n720 × 480', '选择图片后在这里预览\n720 × 480'),
 'preview': ('Camera preview · 3:2', '相机画面预览 · 3:2'),
 'session': ('Session', '操作记录'), 'new': ('New session', '新建操作记录'),
 'open': ('Open saved session', '打开已有记录'), 'folder': ('Show backup folder', '打开备份文件夹'),
 'setup': ('Prepare card check', '准备 SD 卡检查'),
 'check_preflight': ('Check result & prepare backup', '校验结果并准备备份'),
 'check_backup': ('Save & verify original', '保存并核对原图'),
 'prepare': ('Prepare my image', '处理我的图片'),
 'install': ('Prepare installation', '准备安装'),
 'check_stage1': ('Verify temporary image & prepare installation', '校验临时图并准备安装'),
 'check_install': ('Verify camera readback', '校验相机读回'),
 'restore': ('Restore original image', '恢复原始画面'),
 'check_restore': ('Verify restored original', '校验恢复的原图'),
 'finish': ('Finish', '完成'),
 'ack': ('I will use the same camera and follow the Script instructions.', '我会使用同一台相机，并按提示开启 Script。'),
 'display': ('The camera displays the expected shutdown image, and I disabled Script.', '相机实际显示正确的关机画面，并已把 Script 设回 Disable。'),
 'beta': ('Preview release · camera validation pending', '预览版 · 完整 App 流程待实机验证'),
 'backup_badge': ('Computer backup saved', '原图已保存到电脑'),
 'saved': ('Saved session: ', '操作记录：'),
 'working': ('Working… keep the card connected.', '正在处理，请保持 SD 卡连接。'),
 'failed': ('Could not finish this step', '这一步尚未完成'),
 'select_card': ('Choose your SD card first.', '请先选择 SD 卡。'),
 'select_image': ('Choose an image first.', '请先选择图片。'),
 'select_session': ('Create or open a saved session first.', '请先新建或打开操作记录。'),
 'confirm_camera': ('Confirm the camera and Script setting before preparing the card.', '准备卡前，请确认使用同一台相机并已开启 Script。'),
 'confirm_display': ('Check the real shutdown screen and disable Script first.', '请先检查相机实际关机画面，并关闭 Script。'),
 'original_confirm': ('Does the backed-up image open correctly and represent the original you want to keep? An already modified camera cannot provide a lost factory original.', '请确认备份图片可正常打开，并且是你要保留的原图。已经修改且未备份的出厂原图无法找回。'),
 'restore_confirm': ('This backup belongs to its original camera. Confirm you are using that same body. After preparing the card, safely eject it and power on normally once to restore.', '请确认使用此备份对应的原机身。准备 SD 卡后，安全弹出卡，插回相机正常开机一次，恢复保存的原图。'),
 'backup': ('Back up', '备份原图'), 'design': ('Make it yours', '选择画面'), 'verify': ('Install & verify', '安装与校验'),
 'instructions': ('Next step', '下一步'),
 'setup_help': ('Copy the generated entry files to the card using Prepare card check. Hold MENU while powering on to enter the factory menu; enable only Script. Then start normally once, wait for storage activity to stop, shut down, and reconnect the card.', '点“准备 SD 卡检查”会写入入口文件。按住 MENU 开机进入工厂菜单，仅开启 Script。随后正常开机一次，等读写结束再关机，把卡接回电脑。'),
 'session_help': ('Save one session folder per camera on your computer. Reopen it to continue or restore later. Never put your only backup on the SD card.', '为每台相机在电脑上保存独立的操作记录。下次可打开记录继续或恢复，原图备份不要只留在 SD 卡上。'),
 'support': ('Preview installation: GR IV / HDF 1.11 and Urban 1.60. Other combinations need validation. Keep the original backup on your computer.', '预览版安装流程：GR IV / HDF 1.11、Urban 1.60。其他组合尚待验证。请保留电脑上的原图备份。'),
 'leave_busy': ('Wait for the current operation to finish before closing.', '请等当前操作结束再关闭。'),
}
TEXT.update({
 'firmware': ('Firmware shown in camera menu', '相机菜单中的固件版本'),
 'firmware_hint': ('For example 1.11. Keep this body and firmware unchanged throughout the session.', '例如 1.11。操作期间保持同一台机身及固件版本。'),
 'firmware_missing': ('Record firmware…', '记录固件版本…'),
 'test_report': ('Save test report…', '保存测试报告…'),
 'compatibility': ('Camera support / 兼容机型', 'Camera support / 兼容机型'),
 'pending': ('Pending validation', '待验证'),
 'experimental': ('Preview workflow', '预览版流程'),
 'blocked_profile': ('Backup kept. This model/firmware needs validation before installation. Save a test report to help extend support.', '原图备份已保存。此机型与固件组合尚待验证，安装已关闭。可保存测试报告，协助补充兼容性证据。'),

 'subtitle': ('Custom shutdown images for Ricoh GR', 'Ricoh GR 关机画面工具'),
 'backup': ('Back up original', '备份原图'), 'design': ('Choose image', '选择画面'),
 'verify': ('Install & verify', '安装校验'),
 'backup_detail': ('Keep a copy on your computer', '将相机原图保存到电脑'),
 'design_detail': ('Choose and frame your photo', '选图并调整构图'),
 'verify_detail': ('Run on camera, then check', '相机执行，再读回核对'),
 'workflow': ('WORKFLOW', '操作流程'),
 'current': ('Current step', '当前步骤'), 'done': ('Done', '已完成'), 'later': ('Later', '待完成'),
 'computer': ('ON YOUR COMPUTER', '在电脑上'), 'on_camera': ('ON YOUR CAMERA', '在相机上'),
 'backup_location': ('Original backup', '原图备份'),
 'backup_location_hint': ('Choose a folder on your computer to keep the original and your progress.', '选择电脑上的文件夹，保存原图和操作进度。'),
 'start': ('Choose backup folder…', '选择备份文件夹…'),
 'session_help_short': ('You can close the app and resume from this folder.', '可关闭 App，之后打开此记录继续。'),
 'framing': ('Framing', '构图方式'),
 'ack': ('This session and SD card are for the same camera.', '我确认此记录和 SD 卡用于同一台相机。'),
 'confirm_camera': ('Confirm that this session and card are for the same camera.', '请确认此记录和 SD 卡用于同一台相机。'),
 'display': ('The screen looks correct. Script is now disabled.', '关机画面显示正确，Script 已设回 Disable。'),
 'beta': ('Preview · camera testing pending', '预览版 · 待实机验证'),
 'card_ready': ('The card is ready. Follow these steps on the camera.', 'SD 卡已准备好，请按下面顺序操作相机。'),
 'return_card': ('After the camera steps, reconnect the card to verify.', '完成相机操作后，把 SD 卡接回电脑校验。'),
 'ready_card': ('Reconnect the same SD card before continuing.', '继续前，请将同一张 SD 卡接回电脑。'),
 'setup_title': ('Back up your original first', '先备份相机里的原图'),
 'setup_subtitle': ('Save the original before checking installation support.', '先将原图保存到电脑，再检查是否支持安装。'),
 'new_title': ('Prepare the SD card check', '准备 SD 卡检查'),
 'new_subtitle': ('First, check that the camera can run the card script.', '先确认相机能够执行卡上的脚本，再备份原图。'),
 'wait_preflight_title': ('Run the check on your camera', '在相机上执行检查'),
 'wait_backup_title': ('Back up on your camera', '在相机上执行备份'),
 'backed_up_title': ('Choose your shutdown image', '选择你的关机画面'),
 'backed_up_subtitle': ('Your original is safe. Choose a photo and adjust its framing.', '原图已保存。选择图片，调整画面范围。'),
 'prepared_title': ('Ready to install', '画面已准备好'),
 'prepared_subtitle': ('This is the actual encoded image. Check it before continuing.', '下方是处理后的实际图片，确认后准备安装。'),
 'wait_stage1_title': ('Check the temporary image', '执行临时图检查'),
 'wait_install_title': ('Install on your camera', '在相机上安装画面'),
 'verified_title': ('Confirm the shutdown screen', '确认相机上的关机画面'),
 'verified_subtitle': ('The readback matches. Finish the final check on your camera.', '读回内容一致。请完成最后的实机显示检查。'),
 'wait_restore_check_title': ('Check the internal restore source', '先核对相机里的原图备份'),
 'check_restore_source': ('Verify backup & prepare restoration', '核对备份并准备恢复'),
 'wait_restore_title': ('Restore on your camera', '在相机上恢复原图'),
 'restored_title': ('Confirm the restored screen', '确认恢复后的画面'),
 'restored_subtitle': ('The readback matches your saved original.', '读回内容与保存的原图一致。'),
 'complete_title': ('All done', '操作完成'),
 'complete_subtitle': ('Keep your backup folder. You can restore the original from it later.', '保留电脑上的备份文件夹，以后可用它恢复原图。'),
 'deployment_incomplete_title': ('Card preparation interrupted', 'SD 卡准备中断'),
 'deployment_incomplete_subtitle': ('Keep the card and session files. Do not run the camera script.', '请保留卡和记录中的文件，暂不执行相机脚本。'),
 'image': ('Your photo', '你的图片'), 'choose_image': ('Choose photo…', '选择图片…'),
 'folder': ('Show in folder', '打开备份文件夹'),
 'original_preview': ('Saved original · 720 × 480', '已保存的原图 · 720 × 480'),
 'preview': ('Shutdown screen · 720 × 480', '关机画面 · 720 × 480'),
 'review_backup': ('View original backup', '查看原图备份'),
 'same_camera_hint': ('Keep this backup with its original camera.', '请让此备份始终对应原来的机身。'),
})

# Camera work is deliberately separate from computer work. Each waiting screen
# gives the exact sequence, rather than mixing every stage into a single form.
CAMERA_STEPS = {
 'wait_preflight': [
   ('Safely eject the card and insert it into the camera.', '安全弹出 SD 卡，插入相机。'),
   ('Hold MENU and power on. Enable only Script, then power off.', '按住 MENU 开机，仅将 Script 设为 Enable，然后关机。'),
   ('Power on normally. Wait for card activity to stop, then power off.', '正常开机，等待卡读写结束，再关机。'),
   ('Reconnect the card to this computer and check the result below.', '把卡接回电脑，点击下方按钮校验。'),
 ],
 'wait_backup': [
   ('Safely eject the card and insert it into the same camera.', '安全弹出卡，插回同一台相机。'),
   ('Power on normally once. Wait for card activity to stop, then power off.', '正常开机一次，等待卡读写结束，再关机。'),
   ('Reconnect the card. Save and inspect the original on this computer.', '把卡接回电脑，保存并查看原图。'),
 ],
 'wait_stage1': [
   ('Safely eject the card and insert it into the same Urban camera.', '安全弹出卡，插回同一台 Urban 相机。'),
   ('Power on normally once. Wait for card activity to stop, then power off.', '正常开机一次，等待卡读写结束，再关机。'),
   ('Reconnect the card. The app must verify the temporary image before installation.', '把卡接回电脑，临时图校验通过后才会准备安装。'),
 ],
 'wait_install': [
   ('Safely eject the card and insert it into the same camera.', '安全弹出卡，插回同一台相机。'),
   ('Power on normally once. Wait for card activity to stop, then power off.', '正常开机一次，等待卡读写结束，再关机。'),
   ('Look at the shutdown screen. Reconnect the card for verification.', '查看实际关机画面，再把卡接回电脑校验。'),
 ],
 'wait_restore': [
   ('Safely eject the card and insert it into the original camera.', '安全弹出卡，插回此备份对应的相机。'),
   ('Power on normally once. Wait for card activity to stop, then power off.', '正常开机一次，等待卡读写结束，再关机。'),
   ('Reconnect the card to verify the restored original.', '把卡接回电脑，核对恢复后的原图。'),
 ],
 'verified': [
   ('Hold MENU while powering on. Set Script to Disable.', '按住 MENU 开机，将 Script 设回 Disable。'),
   ('Power off and confirm the shutdown image looks correct.', '关机，确认实际关机画面显示正确。'),
 ],
 'restored': [
   ('Hold MENU while powering on. Set Script to Disable.', '按住 MENU 开机，将 Script 设回 Disable。'),
   ('Power off and confirm the original shutdown image is back.', '关机，确认原始关机画面已恢复。'),
 ],
}

CAMERA_STEPS['wait_restore_check'] = [
    ('Safely eject the card and insert it into the same camera.', '安全弹出卡，插回同一台相机。'),
    ('Power on normally once to export the backup. This step does not restore yet.', '正常开机一次，读出机内备份。此时尚未执行恢复。'),
    ('Wait for card activity to stop, power off and reconnect. The app checks the entire backup before preparing restoration.', '等读写结束后关机，把卡接回电脑。完整备份核对通过后才会准备恢复。'),
]
STATES = {
 'wait_restore_check': ('Export and verify the internal original before restoration.', '先读出并核对机内原图备份，再准备恢复。'),
 'new': ('Create a computer backup session, then prepare a small SD copy check.', '新建电脑端记录，再准备一次小文件 SD 复制检查。'),
 'wait_preflight': ('Safely eject the card. Hold MENU while powering on, enable only Script, then shut down. Start normally once to run the check. When storage activity stops, shut down and reconnect the card.', '安全弹出卡。按住 MENU 开机，在工厂菜单仅开启 Script 后关机。再正常开机执行检查，等读写结束后关机，把卡接回电脑。'),
 'wait_backup': ('Run the backup script once on the same camera. Reconnect the card to save and inspect the original.', '在同一台相机上运行一次备份脚本，关机后接回卡，保存并查看原图。'),
 'backed_up': ('Original saved on your computer. Choose an image and adjust its framing.', '原图已另存到电脑。选择图片并调整构图。'),
 'prepared': ('Preview the encoded JPEG below. Prepare installation when ready.', '下方显示处理后的实际 JPEG，确认画面后准备安装。'),
 'wait_stage1': ('Urban: run the temporary-image script once. Reconnect to verify it before installation.', 'Urban：先执行一次临时图脚本，接回电脑校验，通过后再安装。'),
 'wait_install': ('Safely eject, run once, check the shutdown screen, then reconnect for verification.', '安全弹出卡，正常开机执行一次，关机后检查画面，再把卡接回电脑校验。'),
 'verified': ('Full readback matches. Startup script removed. Disable Script on the camera and confirm the visible screen.', '完整读回一致，启动脚本已移除。请在相机上关闭 Script，并确认实际关机显示。'),
 'wait_restore': ('Run the restore script once on the same camera, then reconnect the card.', '在同一台相机上执行一次恢复脚本，关机后把卡接回电脑。'),
 'restored': ('Restored readback matches the original. Disable Script and confirm the screen.', '恢复读回与原图一致。请关闭 Script，并确认实际关机画面。'),
 'complete': ('Finished. Keep this session folder to restore the original later.', '完成。请保留此文件夹，之后可以恢复原图。'),
 'deployment_incomplete': ('Card preparation was interrupted. Keep the session and card files for inspection; do not run the camera script.', '准备卡时发生中断。请保留记录和卡上文件进行排查，暂不运行相机脚本。'),
}


class Worker(QThread):
    success = Signal()
    failure = Signal(str)
    def __init__(self, operation):
        super().__init__()
        self.operation = operation
    def run(self):
        try:
            self.operation()
        except Exception as error:
            self.failure.emit(str(error))
        else:
            self.success.emit()


class Choice(QWidget):
    """Two visible alternatives using the platform's radio-button style."""
    currentIndexChanged = Signal(int)

    def __init__(self, keys, translate, vertical=False):
        super().__init__()
        self.keys = keys
        self.group = QButtonGroup(self)
        self.options = []
        row = QVBoxLayout(self) if vertical else QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)
        for index, key in enumerate(keys):
            button = QRadioButton(translate(key))
            self.group.addButton(button, index)
            self.options.append(button)
            row.addWidget(button)
        if not vertical:
            row.addStretch()
        self.options[0].setChecked(True)
        self.group.idClicked.connect(self.currentIndexChanged.emit)

    def currentIndex(self):
        return self.group.checkedId()

    def setCurrentIndex(self, index):
        if index != self.currentIndex():
            self.options[index].setChecked(True)
            self.currentIndexChanged.emit(index)

    def translate(self, translate):
        for button, key in zip(self.options, self.keys):
            button.setText(translate(key))


class StepPages(QWidget):
    """Only the visible step participates in layout sizing."""
    def __init__(self):
        super().__init__()
        self.current = None
        self.pages = []
        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(0, 0, 0, 0)

    def addWidget(self, page):
        self.pages.append(page)
        self.box.addWidget(page)
        page.hide()
        if self.current is None:
            self.setCurrentWidget(page)

    def currentWidget(self):
        return self.current

    def setCurrentWidget(self, page):
        if self.current is not None:
            self.current.hide()
        self.current = page
        page.show()
        self.updateGeometry()


class Preview(QLabel):
    """Keep a true 3:2 canvas as the window changes size."""
    def __init__(self):
        super().__init__()
        self.source = None
        self.setAlignment(Qt.AlignCenter)
        self.setFixedSize(450, 300)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setObjectName('preview')

    def setPixmap(self, pixmap):
        self.source = pixmap
        self.scale_image()

    def scale_image(self):
        if self.source:
            super().setPixmap(self.source.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def clear(self):
        self.source = None
        super().clear()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.scale_image()


class Studio(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings('Radium', 'GR Shutdown Studio')
        self.language = self.settings.value('language', 'zh')
        self.session = None
        self.image = None
        self.worker = None
        self.resize(1060, 800)
        self.setMinimumSize(960, 720)
        self.setWindowTitle('GR Shutdown Studio')
        self.build()
        self.translate()
        self.refresh()

    def t(self, key):
        return TEXT[key][0 if self.language == 'en' else 1]

    def label(self, layout, key, object_name=None):
        label = QLabel()
        label.setWordWrap(True)
        label.setProperty('text_key', key)
        if object_name:
            label.setObjectName(object_name)
        layout.addWidget(label)
        return label

    def button(self, key, callback):
        button = QPushButton()
        button.setProperty('text_key', key)
        button.clicked.connect(callback)
        return button

    def build(self):
        root = QWidget()
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName('sidebar')
        sidebar.setFixedWidth(228)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(20, 28, 20, 20)
        side.setSpacing(16)
        logo = QLabel('GR')
        logo.setObjectName('brand')
        side.addWidget(logo)
        name = QLabel('Shutdown Studio')
        name.setObjectName('app_name')
        side.addWidget(name)
        side.addSpacing(16)
        self.label(side, 'workflow', 'eyebrow')
        self.steps = []
        for index, key in enumerate(['backup', 'design', 'verify']):
            frame = QFrame()
            frame.setObjectName('step')
            row = QHBoxLayout(frame)
            row.setContentsMargins(10, 12, 10, 12)
            row.setSpacing(10)
            number = QLabel(str(index + 1))
            number.setObjectName('step_number')
            number.setFixedSize(25, 25)
            number.setAlignment(Qt.AlignCenter)
            row.addWidget(number, alignment=Qt.AlignTop)
            labels = QVBoxLayout()
            labels.setSpacing(4)
            self.label(labels, key, 'step_title')
            status = QLabel()
            status.setObjectName('step_status')
            labels.addWidget(status)
            row.addLayout(labels, 1)
            self.steps.append((frame, number, status))
            side.addWidget(frame)
        side.addStretch()
        self.session_label = QLabel()
        self.session_label.setObjectName('hint')
        self.session_label.setWordWrap(True)
        side.addWidget(self.session_label)
        self.folder_button = self.button('folder', self.show_folder)
        side.addWidget(self.folder_button)
        self.new_button = self.button('new', self.new_session)
        side.addWidget(self.new_button)
        self.open_button = self.button('open', self.open_session)
        side.addWidget(self.open_button)
        self.firmware_button = self.button('firmware_missing', self.record_firmware)
        side.addWidget(self.firmware_button)
        self.report_button = self.button('test_report', self.export_report)
        side.addWidget(self.report_button)
        side.addSpacing(8)
        side.addWidget(self.button('compatibility', self.show_compatibility))
        self.settings_button = QPushButton('Settings / 设置')
        self.settings_button.clicked.connect(self.show_settings)
        side.addWidget(self.settings_button)
        self.label(side, 'beta', 'hint')
        outer.addWidget(sidebar)

        main = QVBoxLayout()
        main.setContentsMargins(32, 28, 32, 20)
        main.setSpacing(18)
        self.location = QLabel()
        self.location.setObjectName('eyebrow')
        main.addWidget(self.location)
        self.heading = QLabel()
        self.heading.setObjectName('heading')
        self.heading.setWordWrap(True)
        main.addWidget(self.heading)
        self.description = QLabel()
        self.description.setObjectName('description')
        self.description.setWordWrap(True)
        main.addWidget(self.description)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        body = QVBoxLayout(content)
        body.setContentsMargins(0, 0, 8, 0)
        body.setSpacing(20)
        self.pages = StepPages()
        self.pages.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        # Computer setup: no image editing or installation controls yet.
        self.setup_page = QWidget()
        setup = QVBoxLayout(self.setup_page)
        setup.setContentsMargins(0, 0, 0, 0)
        setup.setSpacing(18)
        self.camera_panel = QWidget()
        camera_layout = QVBoxLayout(self.camera_panel)
        camera_layout.setContentsMargins(0, 0, 0, 0)
        camera_layout.setSpacing(12)
        self.label(camera_layout, 'camera', 'section')
        self.camera = Choice(['family', 'urban'], self.t, vertical=True)
        camera_layout.addWidget(self.camera)
        self.label(camera_layout, 'firmware', 'section')
        self.firmware_input = QLineEdit()
        self.firmware_input.setPlaceholderText('1.11 / 1.60')
        self.firmware_input.setMaximumWidth(180)
        self.firmware_input.textChanged.connect(self.update_action)
        camera_layout.addWidget(self.firmware_input)
        self.label(camera_layout, 'firmware_hint', 'hint')
        setup.addWidget(self.camera_panel)
        self.backup_panel = QFrame()
        self.backup_panel.setObjectName('panel')
        backup = QVBoxLayout(self.backup_panel)
        backup.setContentsMargins(18, 18, 18, 18)
        backup.setSpacing(8)
        self.label(backup, 'backup_location', 'section')
        self.backup_path = QLabel()
        self.backup_path.setWordWrap(True)
        backup.addWidget(self.backup_path)
        self.label(backup, 'session_help_short', 'hint')
        setup.addWidget(self.backup_panel)
        setup.addStretch()
        self.pages.addWidget(self.setup_page)

        # Only this page exposes framing controls.
        self.design_page = QWidget()
        design = QVBoxLayout(self.design_page)
        design.setContentsMargins(0, 0, 0, 0)
        design.setSpacing(14)
        photo_row = QHBoxLayout()
        self.image_button = self.button('choose_image', self.choose_image)
        photo_row.addWidget(self.image_button)
        self.image_name = QLabel('—')
        self.image_name.setObjectName('hint')
        photo_row.addWidget(self.image_name, 1)
        self.label(design, 'framing', 'section')
        self.mode = Choice(['crop', 'contain'], self.t)
        self.mode.currentIndexChanged.connect(self.preview)
        design.addWidget(self.mode)
        self.position_panel = QWidget()
        positions = QGridLayout(self.position_panel)
        positions.setContentsMargins(0, 0, 0, 0)
        positions.setHorizontalSpacing(16)
        positions.setVerticalSpacing(10)
        for row, key in enumerate(['horizontal', 'vertical']):
            label = QLabel()
            label.setProperty('text_key', key)
            label.setObjectName('hint')
            positions.addWidget(label, row, 0)
            slider = QSlider(Qt.Horizontal)
            slider.setRange(0, 100)
            slider.setValue(50)
            slider.valueChanged.connect(self.preview)
            setattr(self, key, slider)
            positions.addWidget(slider, row, 1)
        design.addWidget(self.position_panel)
        self.pages.addWidget(self.design_page)

        self.camera_page = QWidget()
        camera_steps = QVBoxLayout(self.camera_page)
        camera_steps.setContentsMargins(0, 0, 0, 0)
        camera_steps.setSpacing(14)
        self.task_rows = []
        for index in range(4):
            frame = QFrame()
            frame.setObjectName('task')
            row = QHBoxLayout(frame)
            row.setContentsMargins(16, 14, 16, 14)
            row.setSpacing(14)
            number = QLabel(str(index + 1))
            number.setObjectName('task_number')
            number.setAlignment(Qt.AlignCenter)
            number.setFixedSize(24, 24)
            row.addWidget(number, alignment=Qt.AlignTop)
            text = QLabel()
            text.setWordWrap(True)
            row.addWidget(text, 1)
            camera_steps.addWidget(frame)
            self.task_rows.append((frame, text))
        camera_steps.addStretch()
        self.pages.addWidget(self.camera_page)

        self.result_page = QWidget()
        result = QVBoxLayout(self.result_page)
        result.setContentsMargins(0, 0, 0, 0)
        result.setSpacing(12)
        self.result_message = QLabel()
        self.result_message.setWordWrap(True)
        result.addWidget(self.result_message)
        self.pages.addWidget(self.result_page)
        body.addWidget(self.pages)

        self.preview_panel = QWidget()
        preview = QVBoxLayout(self.preview_panel)
        preview.setContentsMargins(0, 0, 0, 0)
        preview.setSpacing(10)
        self.photo_row = QWidget()
        self.photo_row.setLayout(photo_row)
        preview.addWidget(self.photo_row)
        self.preview_caption = QLabel()
        self.preview_caption.setObjectName('hint')
        preview.addWidget(self.preview_caption)
        self.preview_label = Preview()
        preview.addWidget(self.preview_label, alignment=Qt.AlignHCenter)
        self.badge = QLabel()
        self.badge.setObjectName('hint')
        self.badge.setWordWrap(True)
        self.badge.hide()
        self.original_button = self.button('review_backup', self.show_original)
        side.insertWidget(side.indexOf(self.folder_button) + 1, self.original_button)
        body.insertWidget(0, self.preview_panel)

        self.card_panel = QWidget()
        card = QVBoxLayout(self.card_panel)
        card.setContentsMargins(0, 0, 0, 0)
        card.setSpacing(8)
        self.label(card, 'card', 'section')
        row = QHBoxLayout()
        self.card_input = QLineEdit()
        self.card_input.setReadOnly(True)
        self.card_input.setPlaceholderText(self.t('card_hint'))
        self.card_input.textChanged.connect(self.update_action)
        row.addWidget(self.card_input, 1)
        self.card_button = self.button('choose', self.choose_card)
        row.addWidget(self.card_button)
        card.addLayout(row)
        self.card_hint = QLabel()
        self.card_hint.setObjectName('hint')
        self.card_hint.setWordWrap(True)
        card.addWidget(self.card_hint)
        body.addWidget(self.card_panel)
        self.ack = QCheckBox()
        self.ack.setProperty('text_key', 'ack')
        self.ack.toggled.connect(self.update_action)
        body.addWidget(self.ack)
        self.display = QCheckBox()
        self.display.setProperty('text_key', 'display')
        self.display.toggled.connect(self.update_action)
        body.addWidget(self.display)
        body.addStretch()
        scroll.setWidget(content)
        main.addWidget(scroll, 1)

        # One default action, in the same place at every stage.
        self.instruction = QLabel()
        self.instruction.setWordWrap(True)
        self.instruction.setObjectName('hint')
        main.addWidget(self.instruction)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        main.addWidget(self.progress)
        line = QFrame()
        line.setObjectName('separator')
        line.setFixedHeight(1)
        main.addWidget(line)
        footer = QHBoxLayout()
        self.restore_button = self.button('restore', self.restore)
        footer.addWidget(self.restore_button)
        footer.addStretch()
        self.action = QPushButton()
        self.action.setDefault(True)
        self.action.clicked.connect(self.next_step)
        footer.addWidget(self.action)
        main.addLayout(footer)
        outer.addLayout(main, 1)

        # Style only surfaces and typography. Leave buttons, choices, sliders,
        # text fields and popup menus to Qt's macOS / Windows platform style.
        dark = self.palette().color(QPalette.Window).lightness() < 128
        surface = '#272729' if dark else '#f2f2f4'
        secondary = '#aaaaaf' if dark else '#6c6c72'
        selected = '#2c4260' if dark else '#e2ecfb'
        border = '#404044' if dark else '#dedee3'
        self.setStyleSheet(f"""
            QFrame#separator {{ background:{border}; }}
            QFrame#sidebar {{ background:{surface}; border-right:1px solid {border}; }}
            QLabel#brand {{ font-size:32px; font-weight:700; }}
            QLabel#app_name {{ font-size:14px; font-weight:600; }}
            QLabel#heading {{ font-size:25px; font-weight:600; }}
            QLabel#description {{ color:{secondary}; font-size:13px; }}
            QLabel#eyebrow {{ color:{secondary}; font-size:11px; font-weight:600; }}
            QLabel#section, QLabel#step_title {{ font-weight:600; }}
            QLabel#hint, QLabel#step_status {{ color:{secondary}; font-size:12px; }}
            QFrame#step {{ border-radius:8px; }}
            QFrame#step[active="true"] {{ background:{selected}; }}
            QLabel#step_number, QLabel#task_number {{ border:1px solid {border}; border-radius:12px; }}
            QFrame#panel, QFrame#task {{ background:{surface}; border-radius:8px; }}
            QLabel#preview {{ background:#141416; color:#b4b4b9; border-radius:8px; font-size:16px; }}
        """)

    def translate(self):
        for widget in self.findChildren(QWidget):
            key = widget.property('text_key')
            if key and hasattr(widget, 'setText'):
                widget.setText(self.t(key) + (' · ' + __version__ if key == 'beta' else ''))
        self.camera.translate(self.t)
        self.mode.translate(self.t)
        self.card_input.setPlaceholderText(self.t('card_hint'))

    def show_settings(self):
        dialog = QDialog(self)
        dialog.setWindowTitle('Settings / 设置')
        dialog.setWindowModality(Qt.WindowModal)
        if sys.platform == 'darwin':
            dialog.setWindowFlag(Qt.Sheet)
        dialog.setMinimumWidth(400)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)
        layout.addWidget(QLabel('Language / 语言'))
        languages = QButtonGroup(dialog)
        row = QHBoxLayout()
        for index, label in enumerate(['English', '简体中文']):
            button = QRadioButton(label)
            languages.addButton(button, index)
            button.setChecked(index == (0 if self.language == 'en' else 1))
            row.addWidget(button)
        row.addStretch()
        layout.addLayout(row)
        support = QLabel(self.t('support'))
        support.setWordWrap(True)
        layout.addWidget(support)
        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton('Cancel / 取消')
        cancel.clicked.connect(dialog.reject)
        buttons.addWidget(cancel)
        save = QPushButton('Save / 保存')
        save.setDefault(True)
        buttons.addWidget(save)
        layout.addLayout(buttons)
        def apply():
            self.language = 'en' if languages.checkedId() == 0 else 'zh'
            self.settings.setValue('language', self.language)
            self.translate()
            self.refresh()
            dialog.accept()
        save.clicked.connect(apply)
        dialog.exec()

    def show_compatibility(self):
        dialog = QDialog(self)
        dialog.setWindowTitle(self.t('compatibility'))
        dialog.resize(900, 520)
        layout = QVBoxLayout(dialog)
        note = QLabel('Preview workflows need camera testing. Empty firmware entries are not installation support.' if self.language == 'en' else '预览版流程尚待整套实机测试。未记录固件版本的机型不开放安装。')
        note.setWordWrap(True)
        layout.addWidget(note)
        table = QTableWidget(len(PROFILES), 3)
        table.setHorizontalHeaderLabels(['Camera', 'Evidence firmware', 'Status'] if self.language == 'en' else ['机型', '已有证据的固件', '状态'])
        table.verticalHeader().hide()
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        for row, profile in enumerate(PROFILES):
            cells = [profile.name, ', '.join(profile.tested_versions) or '—', self.t('experimental' if profile.tested_versions else 'pending')]
            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setToolTip(profile.evidence)
                table.setItem(row, column, item)
        layout.addWidget(table)
        close = QPushButton('OK')
        close.clicked.connect(dialog.accept)
        layout.addWidget(close, alignment=Qt.AlignRight)
        dialog.exec()

    def record_firmware(self):
        if not self.session:
            return
        version, accepted = QInputDialog.getText(self, self.t('firmware'), self.t('firmware_hint'))
        if accepted:
            try:
                self.session.set_firmware(version.strip())
                self.refresh()
            except Exception as error:
                self.error(str(error))

    def export_report(self):
        if not self.session:
            return
        path, _ = QFileDialog.getSaveFileName(self, self.t('test_report'), str(self.session.directory / 'test-report.json'), 'JSON (*.json)')
        if path:
            try:
                self.session.export_test_report(Path(path))
            except Exception as error:
                self.error(str(error))

    def show_original(self):
        if not self.session:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(self.t('review_backup'))
        layout = QVBoxLayout(dialog)
        label = QLabel()
        label.setPixmap(QPixmap(str(self.session.directory / 'original.jpg')).scaled(600, 400, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        layout.addWidget(label)
        self.label(layout, 'same_camera_hint', 'hint').setText(self.t('same_camera_hint'))
        close = QPushButton('OK')
        close.clicked.connect(dialog.accept)
        layout.addWidget(close, alignment=Qt.AlignRight)
        dialog.exec()

    def choose_card(self):
        path=QFileDialog.getExistingDirectory(self,self.t('card'),'/Volumes' if sys.platform=='darwin' else '')
        if path:self.card_input.setText(path)

    def choose_image(self):
        path,_=QFileDialog.getOpenFileName(self,self.t('choose_image'),'','Images (*.jpg *.jpeg *.png *.webp *.tif *.tiff *.bmp)')
        if path:
            self.image=Path(path);self.image_name.setText(self.image.name);self.preview();self.update_action()

    def preview(self):
        self.position_panel.setVisible(self.mode.currentIndex() == 0)
        if self.preview_panel.isHidden():
            return
        try:
            if self.session and (self.session.state in ('wait_restore','restored') or self.session.state=='complete' and self.session.data.get('last_result')=='restored'):
                with Image.open(self.session.directory/'original.jpg') as image:result=image.convert('RGB')
            elif self.session and self.session.state in ('prepared','wait_stage1','wait_install','verified','complete') and (self.session.directory/'prepared.jpg').exists():
                with Image.open(self.session.directory/'prepared.jpg') as image:result=image.convert('RGB')
            elif self.image:
                result=render_image(self.image,'crop' if self.mode.currentIndex()==0 else 'contain',self.horizontal.value()/100,self.vertical.value()/100)
            elif self.session and self.session.state != 'backed_up' and (self.session.directory/'original.jpg').exists():
                with Image.open(self.session.directory/'original.jpg') as image:result=image.convert('RGB')
            else:
                self.preview_label.clear();self.preview_label.setText(self.t('empty_preview'));return
            raw=result.tobytes();qimage=QImage(raw,result.width,result.height,result.width*3,QImage.Format_RGB888).copy()
            pix=QPixmap.fromImage(qimage)
            self.preview_label.setPixmap(pix)
        except Exception as error:
            self.error(str(error))

    def new_session(self):
        version = self.firmware_input.text().strip()
        if not re.fullmatch(r'\d{1,2}\.\d{2}', version):
            self.error(self.t('firmware_hint'))
            return
        parent=QFileDialog.getExistingDirectory(self,self.t('session'),str(Path.home()/'Documents'))
        if not parent:return
        from datetime import datetime
        name='GR-Shutdown-'+datetime.now().strftime('%Y%m%d-%H%M%S')
        try:
            self.session=Session.create(Path(parent)/name,'FAMILY' if self.camera.currentIndex()==0 else 'URBAN', version)
            self.image=None;self.image_name.setText('—')
            self.ack.setChecked(False);self.display.setChecked(False);self.refresh()
        except Exception as error:self.error(str(error))

    def open_session(self):
        path,_=QFileDialog.getOpenFileName(self,self.t('open'),'','Session (session.json)')
        if not path:return
        try:
            self.session=Session(Path(path).parent)
            self.camera.setCurrentIndex(0 if self.session.data['kind']=='FAMILY' else 1)
            self.image=None;self.image_name.setText('—')
            self.ack.setChecked(False);self.display.setChecked(False);self.refresh()
        except Exception as error:self.error(str(error))

    def show_folder(self):
        if self.session:QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.session.directory)))

    def card(self):
        if not self.card_input.text():raise WorkflowError(self.t('select_card'))
        return Path(self.card_input.text())

    def error(self,message):
        QMessageBox.warning(self,self.t('failed'),message)

    def run(self,operation):
        self.busy(True)
        self.worker=Worker(operation)
        self.worker.success.connect(self.succeeded)
        self.worker.failure.connect(self.failed)
        self.worker.finished.connect(lambda:self.busy(False))
        self.worker.start()

    def succeeded(self):self.refresh()
    def failed(self,message):self.refresh();self.error(message)

    def busy(self,value):
        for widget in [self.action,self.restore_button,self.new_button,self.open_button,self.settings_button,self.camera,self.mode,self.horizontal,self.vertical,self.ack,self.display,self.image_button,self.card_button,self.original_button,self.folder_button,self.firmware_button,self.report_button,self.firmware_input]:widget.setEnabled(not value)
        self.progress.setVisible(value)
        if value:self.instruction.setText(self.t('working'))
        else:self.refresh()

    def next_step(self):
        if not self.session:
            self.new_session()
            return
        try:
            if not self.session:raise WorkflowError(self.t('select_session'))
            state=self.session.state
            if state in ['new','wait_preflight','prepared','wait_stage1'] and not self.ack.isChecked():
                raise WorkflowError(self.t('confirm_camera'))
            if state=='backed_up':
                if not self.image:raise WorkflowError(self.t('select_image'))
                if QMessageBox.question(self,self.t('backup'),self.t('original_confirm'))!=QMessageBox.Yes:return
                image,mode,x,y=self.image,'crop' if self.mode.currentIndex()==0 else 'contain',self.horizontal.value()/100,self.vertical.value()/100
                self.run(lambda:self.session.prepare(image,mode,x,y));return
            card=self.card()
            if state in ['verified','restored'] and not self.display.isChecked():raise WorkflowError(self.t('confirm_display'))
            operations={'new':self.session.begin_backup,'wait_preflight':self.session.verify_preflight,
                        'wait_backup':self.session.verify_backup,'prepared':self.session.begin_install,
                        'wait_stage1':self.session.verify_stage1,'wait_install':self.session.verify_install,
                        'wait_restore_check':self.session.verify_restore_check,'wait_restore':self.session.verify_restore,'verified':self.session.finish,'restored':self.session.finish}
            if state in operations:self.run(lambda:operations[state](card))
        except Exception as error:self.error(str(error))

    def restore(self):
        try:
            if not self.session:raise WorkflowError(self.t('select_session'))
            if not self.card_input.text():
                self.choose_card()
                if not self.card_input.text():return
            card=self.card()
            if QMessageBox.question(self,self.t('restore'),self.t('restore_confirm'))==QMessageBox.Yes:
                self.display.setChecked(False);self.run(lambda:self.session.begin_restore(card))
        except Exception as error:self.error(str(error))

    def stage(self, state):
        if state == 'deployment_incomplete' and self.session:
            state = self.session.data.get('previous_state', state)
        if state in ('new', 'wait_preflight', 'wait_backup'):
            return 0
        if state == 'backed_up':
            return 1
        return 2

    def update_action(self):
        if not hasattr(self, 'action'):
            return
        busy = bool(self.worker and self.worker.isRunning())
        state = self.session.state if self.session else 'new'
        enabled = not busy and state not in ('complete', 'deployment_incomplete')
        if not self.session:
            enabled = enabled and bool(re.fullmatch(r'\d{1,2}\.\d{2}', self.firmware_input.text().strip()))
        if self.session:
            if state in ('backed_up', 'prepared', 'wait_stage1'):
                enabled = enabled and installation_allowed(self.session.data['kind'], self.session.data.get('model'), self.session.data.get('firmware'))
            if state == 'backed_up':
                enabled = enabled and bool(self.image)
            else:
                enabled = enabled and bool(self.card_input.text())
            if state in ('new', 'wait_preflight', 'prepared', 'wait_stage1'):
                enabled = enabled and self.ack.isChecked()
            if state in ('verified', 'restored'):
                enabled = enabled and self.display.isChecked()
        self.action.setEnabled(enabled)

    def refresh(self):
        state = self.session.state if self.session else 'new'
        waiting = state in CAMERA_STEPS
        stage = self.stage(state)
        for index, (frame, number, status) in enumerate(self.steps):
            frame.setProperty('active', index == stage)
            frame.style().unpolish(frame)
            frame.style().polish(frame)
            number.setText('✓' if index < stage or state == 'complete' else str(index + 1))
            status.setText(self.t('done' if index < stage or state == 'complete' else 'current' if index == stage else 'later'))
        title_key = state + '_title' if self.session else 'setup_title'
        self.heading.setText(self.t(title_key))
        self.location.setText(self.t('on_camera' if waiting else 'computer'))
        if not self.session:
            self.description.setText(self.t('setup_subtitle'))
        elif state + '_subtitle' in TEXT:
            self.description.setText(self.t(state + '_subtitle'))
        else:
            self.description.setText(self.t('card_ready' if waiting else 'ready_card'))
        if waiting:
            self.pages.setCurrentWidget(self.camera_page)
            steps = CAMERA_STEPS[state]
            for index, (frame, text) in enumerate(self.task_rows):
                frame.setVisible(index < len(steps))
                if index < len(steps):
                    text.setText(steps[index][0 if self.language == 'en' else 1])
        elif state == 'new':
            self.pages.setCurrentWidget(self.setup_page)
        elif state == 'backed_up':
            self.pages.setCurrentWidget(self.design_page)
        else:
            self.pages.setCurrentWidget(self.result_page)
            text = STATES.get(state, STATES['deployment_incomplete'])
            self.result_message.setText(text[0 if self.language == 'en' else 1])
            self.result_message.setVisible(state == 'deployment_incomplete')
        self.pages.updateGeometry()
        self.photo_row.setVisible(state == 'backed_up')
        self.camera_panel.setVisible(state == 'new')
        self.preview_panel.setVisible(state in ('backed_up', 'prepared', 'complete'))
        self.card_panel.setVisible(bool(self.session) and state not in ('backed_up', 'deployment_incomplete'))
        self.card_hint.setText(self.t('card_hint'))
        self.ack.setVisible(bool(self.session) and state in ('new', 'wait_preflight', 'prepared', 'wait_stage1'))
        self.display.setVisible(state in ('verified', 'restored'))
        self.position_panel.setVisible(self.mode.currentIndex() == 0)
        self.camera.setEnabled(not bool(self.session))
        self.firmware_input.setEnabled(not bool(self.session))
        self.firmware_button.setVisible(bool(self.session) and not self.session.data.get('firmware'))
        self.report_button.setVisible(bool(self.session))
        self.mode.setEnabled(state == 'backed_up')
        self.horizontal.setEnabled(state == 'backed_up')
        self.vertical.setEnabled(state == 'backed_up')
        self.new_button.setVisible(bool(self.session))
        self.folder_button.setVisible(bool(self.session))
        self.folder_button.setEnabled(bool(self.session))
        self.session_label.setVisible(bool(self.session))
        self.restore_button.setVisible(bool(self.session) and state in ('backed_up', 'prepared', 'wait_stage1', 'wait_install', 'verified', 'complete'))
        self.restore_button.setEnabled(bool(self.session) and state in ('backed_up', 'prepared', 'wait_stage1', 'wait_install', 'verified', 'complete') and installation_allowed(self.session.data['kind'], self.session.data.get('model'), self.session.data.get('firmware')))
        self.original_button.setVisible(bool(self.session) and 'original_sha256' in self.session.data and state != 'complete')
        restored = bool(self.session and (self.session.state == 'complete' and self.session.data.get('last_result') == 'restored'))
        self.preview_caption.setText(self.t('original_preview' if restored else 'preview'))
        actions = {'new':'setup', 'wait_preflight':'check_preflight', 'wait_backup':'check_backup',
                   'backed_up':'prepare', 'prepared':'install', 'wait_stage1':'check_stage1',
                   'wait_install':'check_install', 'wait_restore_check':'check_restore_source', 'wait_restore':'check_restore',
                   'verified':'finish', 'restored':'finish', 'complete':'finish', 'deployment_incomplete':'setup'}
        self.action.setText(self.t(actions.get(state, 'setup')) if self.session else self.t('start'))
        self.action.setVisible(state != 'complete')
        if self.session:
            self.session_label.setText(self.session.directory.name)
            self.session_label.setToolTip(str(self.session.directory))
            self.backup_path.setText(str(self.session.directory))
            self.backup_path.setTextInteractionFlags(Qt.TextSelectableByMouse)
            if 'original_sha256' in self.session.data:
                self.badge.setText(self.t('backup_badge') + ' · ' + self.session.data['model'])
            else:
                self.badge.clear()
        else:
            self.backup_path.setText(self.t('backup_location_hint'))
            self.badge.clear()
        hints = {'new':'backup_location_hint' if not self.session else 'setup_subtitle',
                 'backed_up':'image_hint', 'prepared':'same_camera_hint',
                 'complete':'session_help_short', 'deployment_incomplete':'deployment_incomplete_subtitle'}
        self.instruction.setText(self.t(hints.get(state, 'return_card' if waiting else 'ready_card')))
        self.instruction.setVisible(bool(self.session))
        if self.session and state in ('backed_up', 'prepared') and not installation_allowed(self.session.data['kind'], self.session.data.get('model'), self.session.data.get('firmware')):
            self.description.setText(self.t('blocked_profile'))
        self.preview()
        self.update_action()

    def closeEvent(self,event):
        if self.worker and self.worker.isRunning():
            self.error(self.t('leave_busy'));event.ignore()
        else:event.accept()


def main():
    application=QApplication(sys.argv)
    application.setApplicationName('GR Shutdown Studio')
    application.setApplicationVersion(__version__)
    window=Studio();window.show()
    sys.exit(application.exec())

if __name__=='__main__':main()
