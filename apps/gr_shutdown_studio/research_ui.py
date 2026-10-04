"""Community research intake, separate from the camera installation workflow."""
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog, QGridLayout, QHBoxLayout,
                              QInputDialog, QLabel, QMessageBox, QPushButton, QVBoxLayout)
from .compatibility import PROFILES, research_versions
from .research import OBSERVATIONS, ResearchRecord


TEXT = {
    'title': ('Compatibility testing', '适配测试'),
    'intro': ('Choose your camera and firmware, create a record, then save the report. No camera modification is needed. Missing files can be skipped.',
              '选机型与固件 → 建立记录 → 保存报告。不用修改相机，没有资料文件也能提交。'),
    'camera_section': ('Camera details', '相机信息'),
    'evidence_section': ('Local evidence · optional', '本地资料 · 可选'),
    'observations_section': ('Your observations · optional', '实际观察 · 可选'),
    'camera': ('Camera', '相机'), 'firmware': ('Menu firmware', '菜单固件'),
    'choose': ('Choose the version shown on your camera', '选择相机菜单显示的版本'),
    'other': ('Other version…', '其他版本…'),
    'history': ('Use the version shown in the camera menu. Update history is not compatibility evidence.',
                '请核对相机菜单版本。历史更新列表不代表已适配。'),
    'create': ('Create record…', '建立记录…'), 'open': ('Open record…', '打开记录…'),
    'local': ('Choose a folder on your computer', '选择电脑上的记录文件夹'),
    'none': ('Create or open a record to continue.', '建立或打开记录后继续。'),
    'firmware_file': ('Inspect update file…', '分析更新文件…'),
    'original': ('Preserve extracted original…', '保存已读出的原图…'),
    'factory': ('Factory menu', '工厂菜单'), 'graphic': ('Shutdown graphic', '关机图片'),
    'not_checked': ('Not checked', '未检查'), 'visible': ('Opened successfully', '已成功打开'),
    'unavailable': ('Could not open', '未能打开'), 'present': ('Image visible', '有图片'),
    'absent': ('No image visible', '没有显示图片'),
    'source': ('No update file or extracted original? Skip these buttons. This page cannot extract an unsupported camera’s picture; importing an ordinary photo does not enable installation.',
               '没有更新文件或已读出原图？跳过这两项即可。此页面不能自动提取未支持机型的图片，导入普通照片不会开放安装。'),
    'export': ('Save report…', '保存报告…'), 'close': ('Close', '关闭'),
    'pending': ('Share the JSON report in a GitHub issue. Pictures and body identifiers are excluded; keep firmware and originals private.',
                'JSON 报告可附到 GitHub issue，不含图片或机身标识。固件与原图留在自己电脑上。'),
    'kept': ('Original saved and both computer copies verified. Copy this entire folder to another drive.',
             '原图已保存，电脑上的两份副本已核对。请将整个目录再复制到另一存储位置。'),
    'no_original': ('Original not supplied.', '尚未提供原图。'),
    'file_checked': ('Update header inspected; installed firmware is not authenticated.', '已分析更新包头；未验证相机实际安装的固件。'),
    'no_file': ('Update file not supplied.', '尚未提供更新文件。'),
    'saved': ('Report saved. Send this JSON to the person who gave you the app, or attach it to a compatibility issue. This first test is complete; wait for a method naming your exact camera and firmware. Nothing was sent automatically.',
              '报告已保存。把这个 JSON 发给提供软件的人，或附到兼容性 issue。第一轮测试到这里结束，后续等明确对应你机型和固件的方法。没有自动发送任何文件。'),
    'failed': ('Could not complete operation', '操作未完成'),
    'version_error': ('Enter a menu version such as 2.10 or 1.60.', '请填写菜单版本，例如 2.10 或 1.60。'),
}


class ResearchDialog(QDialog):
    def __init__(self, parent, language):
        super().__init__(parent)
        self.language = language
        self.record = None
        self.setWindowTitle(self.t('title'))
        self.setMinimumWidth(700)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)
        self.add_label(layout, 'intro')
        self.add_label(layout, 'camera_section', True)
        form = QGridLayout()
        form.setHorizontalSpacing(20)
        form.setVerticalSpacing(12)
        self.camera = QComboBox()
        for profile in PROFILES:
            self.camera.addItem(profile.name, profile.id)
        self.firmware = QComboBox()
        form.addWidget(QLabel(self.t('camera')), 0, 0)
        form.addWidget(self.camera, 0, 1)
        form.addWidget(QLabel(self.t('firmware')), 1, 0)
        form.addWidget(self.firmware, 1, 1)
        form.setColumnStretch(1, 1)
        layout.addLayout(form)
        self.add_label(layout, 'history')
        row = QHBoxLayout()
        self.create_button = self.add_button(row, 'create', self.create_record)
        self.add_button(row, 'open', self.open_record)
        row.addStretch()
        layout.addLayout(row)
        self.add_label(layout, 'evidence_section', True)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.PlainText)
        layout.addWidget(self.summary)
        row = QHBoxLayout()
        self.file_button = self.add_button(row, 'firmware_file', self.add_firmware)
        self.original_button = self.add_button(row, 'original', self.add_original)
        row.addStretch()
        layout.addLayout(row)
        self.add_label(layout, 'source')
        self.add_label(layout, 'observations_section', True)
        observations = QGridLayout()
        self.observations = {}
        for row, (key, options) in enumerate(OBSERVATIONS.items()):
            choice = QComboBox()
            for option in options:
                choice.addItem(self.t(option), option)
            choice.currentIndexChanged.connect(lambda _, key=key: self.observe(key))
            self.observations[key] = choice
            observations.addWidget(QLabel(self.t('factory' if key == 'factory_menu' else 'graphic')), row, 0)
            observations.addWidget(choice, row, 1)
        observations.setColumnStretch(1, 1)
        observations.setHorizontalSpacing(20)
        layout.addLayout(observations)
        self.add_label(layout, 'pending')
        row = QHBoxLayout()
        row.addStretch()
        self.export_button = self.add_button(row, 'export', self.export_report)
        self.add_button(row, 'close', self.accept)
        layout.addLayout(row)
        self.camera.currentIndexChanged.connect(self.reset_versions)
        self.firmware.currentIndexChanged.connect(self.choose_version)
        self.reset_versions()
        self.refresh()

    def t(self, key):
        return TEXT[key][0 if self.language == 'en' else 1]

    def add_label(self, layout, key, section=False):
        label = QLabel(self.t(key))
        label.setWordWrap(True)
        if section:
            label.setObjectName('section')
            font = label.font()
            font.setBold(True)
            label.setFont(font)
        layout.addWidget(label)

    def add_button(self, layout, key, action):
        button = QPushButton(self.t(key))
        button.clicked.connect(action)
        layout.addWidget(button)
        return button

    def fail(self, error):
        QMessageBox.warning(self, self.t('failed'), str(error))

    def reset_versions(self):
        self.firmware.blockSignals(True)
        self.firmware.clear()
        self.firmware.addItem(self.t('choose'), None)
        for version in research_versions(self.camera.currentData()):
            self.firmware.addItem(version, version)
        self.firmware.addItem(self.t('other'), 'other')
        self.firmware.blockSignals(False)
        self.refresh()

    def choose_version(self):
        if self.firmware.currentData() == 'other':
            import re
            value, accepted = QInputDialog.getText(self, self.t('firmware'), self.t('version_error'))
            value = value.strip()
            if accepted and re.fullmatch(r'\d{1,2}\.\d{2}', value):
                self.firmware.insertItem(self.firmware.count()-1, value, value)
                self.firmware.setCurrentIndex(self.firmware.count()-2)
            else:
                self.firmware.setCurrentIndex(0)
                if accepted:
                    self.fail(self.t('version_error'))
        self.refresh()

    def create_record(self):
        version = self.firmware.currentData()
        if self.record or not version or version == 'other':
            return
        folder = QFileDialog.getExistingDirectory(self, self.t('local'), str(Path.home()/'Documents'))
        if folder:
            try:
                name = 'GR-Research-'+datetime.now().strftime('%Y%m%d-%H%M%S')
                self.record = ResearchRecord.create(Path(folder)/name, self.camera.currentData(), version)
                self.refresh()
            except Exception as error:
                self.fail(error)

    def open_record(self):
        path, _ = QFileDialog.getOpenFileName(self, self.t('open'), '', 'Research (research.json)')
        if not path:
            return
        try:
            record = ResearchRecord(Path(path).parent)
            self.camera.setCurrentIndex(self.camera.findData(record.data['profile_id']))
            index = self.firmware.findData(record.data['firmware'])
            if index < 0:
                index = self.firmware.count()-1
                self.firmware.insertItem(index, record.data['firmware'], record.data['firmware'])
            self.firmware.setCurrentIndex(index)
            self.record = record
            for key, choice in self.observations.items():
                choice.blockSignals(True)
                choice.setCurrentIndex(choice.findData(record.data['observations'].get(key, 'not_checked')))
                choice.blockSignals(False)
            self.refresh()
        except Exception as error:
            self.fail(error)

    def add_firmware(self):
        path, _ = QFileDialog.getOpenFileName(self, self.t('firmware_file'), '', 'Update (*.bin)')
        if path and self.record:
            try:
                self.record.add_firmware(Path(path))
                self.refresh()
            except Exception as error:
                self.fail(error)

    def add_original(self):
        path, _ = QFileDialog.getOpenFileName(self, self.t('original'), '', 'JPEG (*.jpg *.jpeg *.JPG)')
        if path and self.record:
            try:
                self.record.add_original(Path(path))
                self.refresh()
            except Exception as error:
                self.fail(error)

    def observe(self, key):
        if self.record:
            try:
                self.record.observe(key, self.observations[key].currentData())
            except Exception as error:
                self.fail(error)

    def export_report(self):
        if not self.record:
            return
        path, _ = QFileDialog.getSaveFileName(self, self.t('export'), str(self.record.directory/'research-report.json'), 'JSON (*.json)')
        if path:
            try:
                self.record.export(Path(path))
                QMessageBox.information(self, self.t('title'), self.t('saved'))
            except Exception as error:
                self.fail(error)

    def refresh(self):
        exists = self.record is not None
        self.camera.setEnabled(not exists)
        self.firmware.setEnabled(not exists)
        self.create_button.setEnabled(not exists and bool(self.firmware.currentData()) and self.firmware.currentData() != 'other')
        for widget in [self.file_button, self.original_button, self.export_button, *self.observations.values()]:
            widget.setEnabled(exists)
        if exists:
            self.summary.setText('\n'.join([self.record.directory.name,
                self.t('kept' if self.record.data.get('original_evidence') else 'no_original'),
                self.t('file_checked' if self.record.data.get('firmware_evidence') else 'no_file')]))
        else:
            self.summary.setText(self.t('none'))
