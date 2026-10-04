"""GR Shutdown Studio desktop interface."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image
from PySide6.QtCore import Qt, QThread, Signal, QSettings, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap, QImage
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QComboBox, QLineEdit, QFileDialog, QMessageBox,
    QCheckBox, QFrame, QSlider, QDialog, QProgressBar,
)
from .core import Session, render_image, WorkflowError

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
 'empty_preview': ('Your shutdown image\n720 × 480', '你的关机画面\n720 × 480'),
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
 'restore_confirm': ('Prepare a restore script for this session’s original? Use the same camera and run it once after safely ejecting the card.', '准备恢复此记录保存的原图？请使用同一台相机，安全弹出卡后正常开机执行一次。'),
 'backup': ('Back up', '备份原图'), 'design': ('Make it yours', '选择画面'), 'verify': ('Install & verify', '安装与校验'),
 'instructions': ('Next step', '下一步'),
 'setup_help': ('Copy the generated entry files to the card using Prepare card check. Hold MENU while powering on to enter the factory menu; enable only Script. Then start normally once, wait for storage activity to stop, shut down, and reconnect the card.', '点“准备 SD 卡检查”会写入入口文件。按住 MENU 开机进入工厂菜单，仅开启 Script。随后正常开机一次，等读写结束再关机，把卡接回电脑。'),
 'session_help': ('Save one session folder per camera on your computer. Reopen it to continue or restore later. Never put your only backup on the SD card.', '为每台相机在电脑上保存独立的操作记录。下次可打开记录继续或恢复，原图备份不要只留在 SD 卡上。'),
 'support': ('GR IV-family selection is automatic after backup. Urban support is limited to 1.60 and its verified original. The app does not format cards or flash firmware.', '备份后自动识别 GR IV 系列机型。Urban 仅支持 1.60 及已验证的原图。App 不格式化卡，不刷写固件。'),
 'leave_busy': ('Wait for the current operation to finish before closing.', '请等当前操作结束再关闭。'),
}
STATES = {
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


class Studio(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings('Radium', 'GR Shutdown Studio')
        self.language = self.settings.value('language', 'zh')
        self.session = None
        self.image = None
        self.worker = None
        self.resize(1080, 820)
        self.setMinimumSize(940, 760)
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
        outer = QVBoxLayout(root)
        outer.setContentsMargins(32, 24, 32, 24)
        outer.setSpacing(16)
        header = QHBoxLayout()
        brand = QVBoxLayout()
        self.label(brand, 'title', 'brand')
        self.label(brand, 'subtitle', 'subtitle')
        header.addLayout(brand, 1)
        # Always bilingual so this entry remains discoverable after switching languages.
        self.settings_button = QPushButton('Settings / 设置')
        self.settings_button.clicked.connect(self.show_settings)
        header.addWidget(self.settings_button, alignment=Qt.AlignTop)
        outer.addLayout(header)
        steps = QHBoxLayout()
        for n, key in enumerate(['backup','design','verify'],1):
            frame=QFrame();frame.setObjectName('step')
            row=QHBoxLayout(frame);row.addWidget(QLabel(f'0{n}'))
            self.label(row,key);steps.addWidget(frame)
        outer.addLayout(steps)
        body=QHBoxLayout();body.setSpacing(22)
        controls=QVBoxLayout();controls.setSpacing(10)
        self.label(controls,'camera','section')
        self.camera=QComboBox();controls.addWidget(self.camera)
        self.label(controls,'card','section')
        cardrow=QHBoxLayout();self.card_input=QLineEdit();self.card_input.setReadOnly(True)
        cardrow.addWidget(self.card_input,1);cardrow.addWidget(self.button('choose',self.choose_card))
        controls.addLayout(cardrow)
        self.label(controls,'card_hint','hint')
        self.label(controls,'image','section')
        controls.addWidget(self.button('choose_image',self.choose_image))
        self.image_name=QLabel('—');self.image_name.setObjectName('hint');controls.addWidget(self.image_name)
        self.mode=QComboBox();self.mode.currentIndexChanged.connect(self.preview);controls.addWidget(self.mode)
        for key in ['horizontal','vertical']:
            self.label(controls,key,'hint')
            slider=QSlider(Qt.Horizontal);slider.setRange(0,100);slider.setValue(50)
            slider.valueChanged.connect(self.preview);setattr(self,key,slider);controls.addWidget(slider)
        self.label(controls,'session','section')
        sessionrow=QHBoxLayout();self.new_button=self.button('new',self.new_session);sessionrow.addWidget(self.new_button)
        self.open_button=self.button('open',self.open_session);sessionrow.addWidget(self.open_button)
        controls.addLayout(sessionrow)
        self.session_label=QLabel('—');self.session_label.setWordWrap(True);self.session_label.setObjectName('hint');controls.addWidget(self.session_label)
        self.folder_button=self.button('folder',self.show_folder);controls.addWidget(self.folder_button)
        self.ack=QCheckBox();self.ack.setProperty('text_key','ack');self.ack.setStyleSheet('font-size:11px;');controls.addWidget(self.ack)
        controls.addStretch()
        body.addLayout(controls,4)
        right=QVBoxLayout();right.setSpacing(10)
        self.label(right,'preview','section')
        self.preview_label=QLabel();self.preview_label.setObjectName('preview')
        self.preview_label.setAlignment(Qt.AlignCenter);self.preview_label.setMinimumSize(480,320)
        right.addWidget(self.preview_label)
        self.badge=QLabel();self.badge.setObjectName('badge');right.addWidget(self.badge)
        self.label(right,'instructions','section')
        self.instruction=QLabel();self.instruction.setWordWrap(True);self.instruction.setObjectName('instructions');right.addWidget(self.instruction)
        self.action=QPushButton();self.action.setObjectName('primary');self.action.clicked.connect(self.next_step);right.addWidget(self.action)
        self.restore_button=self.button('restore',self.restore);right.addWidget(self.restore_button)
        self.display=QCheckBox();self.display.setProperty('text_key','display');right.addWidget(self.display)
        self.progress=QProgressBar();self.progress.setRange(0,0);self.progress.hide();right.addWidget(self.progress)
        right.addStretch()
        body.addLayout(right,5);outer.addLayout(body,1)
        self.label(outer,'beta','hint')
        self.setStyleSheet('''
            QMainWindow, QWidget { background:#f6f5f1; color:#242726; font-size:13px; }
            QLabel#brand { font-size:27px; font-weight:700; }
            QLabel#subtitle { color:#727974; font-size:14px; }
            QLabel#section { font-size:13px; font-weight:600; margin-top:4px; }
            QLabel#hint { color:#777e79; font-size:11px; }
            QFrame#step { background:#eaece6; border-radius:8px; }
            QFrame#step QLabel { background:transparent; }
            QPushButton { background:white; border:1px solid #d9ded6; border-radius:7px; padding:10px 12px; }
            QPushButton:hover { border-color:#3e6b51; background:#eff4ee; }
            QPushButton:disabled { color:#afb5ae; background:#eeefea; }
            QPushButton#primary { background:#294e3b; color:white; border:0; font-weight:600; padding:14px; }
            QPushButton#primary:disabled { background:#adb9af; }
            QLineEdit, QComboBox { background:white; border:1px solid #d9ded6; border-radius:6px; padding:9px; }
            QLabel#preview { background:#191e1b; color:#b6c0b9; border-radius:12px; font-size:19px; }
            QLabel#badge { color:#2f6946; font-size:12px; }
            QLabel#instructions { line-height:1.5; color:#555f57; min-height:52px; }
            QSlider::groove:horizontal { background:#d9ded6; height:4px; border-radius:2px; }
            QSlider::handle:horizontal { background:#365c44; width:14px; margin:-5px 0; border-radius:7px; }
            QProgressBar { background:#e6eae3; border:0; border-radius:4px; height:7px; }
            QProgressBar::chunk { background:#365c44; }
        ''')

    def translate(self):
        for widget in self.findChildren(QWidget):
            key=widget.property('text_key')
            if key and hasattr(widget,'setText'):
                widget.setText(self.t(key))
        index=self.camera.currentIndex()
        self.camera.clear();self.camera.addItems([self.t('family'),self.t('urban')]);self.camera.setCurrentIndex(max(index,0))
        index=self.mode.currentIndex()
        self.mode.blockSignals(True);self.mode.clear();self.mode.addItems([self.t('crop'),self.t('contain')]);self.mode.setCurrentIndex(max(index,0));self.mode.blockSignals(False)

    def show_settings(self):
        dialog=QDialog(self);dialog.setWindowTitle('Settings / 设置');dialog.setMinimumWidth(420)
        layout=QVBoxLayout(dialog);layout.setContentsMargins(24,24,24,24);layout.setSpacing(16)
        layout.addWidget(QLabel('Language / 语言'))
        language=QComboBox();language.addItems(['English','简体中文']);language.setCurrentIndex(0 if self.language=='en' else 1);layout.addWidget(language)
        support=QLabel(self.t('support'));support.setWordWrap(True);layout.addWidget(support)
        setup=QLabel(self.t('setup_help'));setup.setWordWrap(True);layout.addWidget(setup)
        save=QPushButton('Save / 保存');layout.addWidget(save)
        def apply():
            self.language='en' if language.currentIndex()==0 else 'zh'
            self.settings.setValue('language',self.language)
            self.translate();self.refresh();dialog.accept()
        save.clicked.connect(apply)
        dialog.exec()

    def choose_card(self):
        path=QFileDialog.getExistingDirectory(self,self.t('card'),'/Volumes' if sys.platform=='darwin' else '')
        if path:self.card_input.setText(path)

    def choose_image(self):
        path,_=QFileDialog.getOpenFileName(self,self.t('choose_image'),'','Images (*.jpg *.jpeg *.png *.webp *.tif *.tiff *.bmp)')
        if path:
            self.image=Path(path);self.image_name.setText(self.image.name);self.preview()

    def preview(self):
        try:
            if self.session and (self.session.state in ('wait_restore','restored') or self.session.state=='complete' and self.session.data.get('last_result')=='restored'):
                with Image.open(self.session.directory/'original.jpg') as image:result=image.convert('RGB')
            elif self.session and self.session.state in ('prepared','wait_stage1','wait_install','verified','complete') and (self.session.directory/'prepared.jpg').exists():
                with Image.open(self.session.directory/'prepared.jpg') as image:result=image.convert('RGB')
            elif self.image:
                result=render_image(self.image,'crop' if self.mode.currentIndex()==0 else 'contain',self.horizontal.value()/100,self.vertical.value()/100)
            elif self.session and (self.session.directory/'original.jpg').exists():
                with Image.open(self.session.directory/'original.jpg') as image:result=image.convert('RGB')
            else:
                self.preview_label.clear();self.preview_label.setText(self.t('empty_preview'));return
            raw=result.tobytes();qimage=QImage(raw,result.width,result.height,result.width*3,QImage.Format_RGB888).copy()
            pix=QPixmap.fromImage(qimage).scaled(480,320,Qt.KeepAspectRatio,Qt.SmoothTransformation)
            self.preview_label.setPixmap(pix)
        except Exception as error:
            self.error(str(error))

    def new_session(self):
        parent=QFileDialog.getExistingDirectory(self,self.t('session'),str(Path.home()/'Documents'))
        if not parent:return
        from datetime import datetime
        name='GR-Shutdown-'+datetime.now().strftime('%Y%m%d-%H%M%S')
        try:
            self.session=Session.create(Path(parent)/name,'FAMILY' if self.camera.currentIndex()==0 else 'URBAN')
            self.ack.setChecked(False);self.display.setChecked(False);self.refresh()
        except Exception as error:self.error(str(error))

    def open_session(self):
        path,_=QFileDialog.getOpenFileName(self,self.t('open'),'','Session (session.json)')
        if not path:return
        try:
            self.session=Session(Path(path).parent)
            self.camera.setCurrentIndex(0 if self.session.data['kind']=='FAMILY' else 1)
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
        for widget in [self.action,self.restore_button,self.new_button,self.open_button,self.settings_button,self.camera,self.mode,self.horizontal,self.vertical,self.ack,self.display]:widget.setEnabled(not value)
        self.progress.setVisible(value)
        if value:self.instruction.setText(self.t('working'))
        else:self.refresh()

    def next_step(self):
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
                        'wait_restore':self.session.verify_restore,'verified':self.session.finish,'restored':self.session.finish}
            if state in operations:self.run(lambda:operations[state](card))
        except Exception as error:self.error(str(error))

    def restore(self):
        try:
            if not self.session:raise WorkflowError(self.t('select_session'))
            if not self.ack.isChecked():raise WorkflowError(self.t('confirm_camera'))
            card=self.card()
            if QMessageBox.question(self,self.t('restore'),self.t('restore_confirm'))==QMessageBox.Yes:
                self.display.setChecked(False);self.run(lambda:self.session.begin_restore(card))
        except Exception as error:self.error(str(error))

    def refresh(self):
        state=self.session.state if self.session else 'new'
        text=STATES.get(state,STATES['deployment_incomplete'])
        self.instruction.setText(text[0 if self.language=='en' else 1])
        actions={'new':'setup','wait_preflight':'check_preflight','wait_backup':'check_backup','backed_up':'prepare',
                 'prepared':'install','wait_stage1':'check_stage1','wait_install':'check_install','wait_restore':'check_restore',
                 'verified':'finish','restored':'finish','complete':'finish','deployment_incomplete':'setup'}
        self.action.setText(self.t(actions.get(state,'setup')))
        self.action.setEnabled(bool(self.session) and state not in ['complete','deployment_incomplete'])
        self.restore_button.setEnabled(bool(self.session) and state in ['backed_up','prepared','wait_stage1','wait_install','verified','complete'])
        self.folder_button.setEnabled(bool(self.session));self.camera.setEnabled(not bool(self.session))
        self.display.setVisible(state in ['verified','restored'])
        self.mode.setEnabled(state in ['new','backed_up'])
        self.horizontal.setEnabled(state in ['new','backed_up']);self.vertical.setEnabled(state in ['new','backed_up'])
        if self.session:
            self.session_label.setText(self.t('saved')+str(self.session.directory))
            if 'original_sha256' in self.session.data:
                self.badge.setText(self.t('backup_badge')+' · '+self.session.data['model']+' · '+str(self.session.data['original_size'])+' B')
            else:self.badge.clear()
        self.preview()

    def closeEvent(self,event):
        if self.worker and self.worker.isRunning():
            self.error(self.t('leave_busy'));event.ignore()
        else:event.accept()


def main():
    application=QApplication(sys.argv)
    application.setApplicationName('GR Shutdown Studio')
    window=Studio();window.show()
    sys.exit(application.exec())

if __name__=='__main__':main()
