import sys
import os
import time
import re
import numpy as np
import cv2
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QSize
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QHBoxLayout,
    QLineEdit, QCheckBox, QPushButton, QMessageBox, QSystemTrayIcon, QMenu, QAction
)
from PyQt5.QtGui import QIcon
import keyring
from pywinauto import Desktop, Application
import pyautogui
from PIL import ImageGrab, ImageEnhance
import easyocr

reader = easyocr.Reader(['ko', 'en'], gpu=False)

STARTUP_FOLDER = os.path.join(os.getenv('APPDATA'), r'Microsoft\Windows\Start Menu\Programs\Startup')

def resource_path(relative_path):
    """PyInstaller로 빌드된 실행 파일에서 리소스 파일 경로 가져오기"""
    try:
        # PyInstaller로 생성된 임시 폴더 경로
        base_path = sys._MEIPASS
    except Exception:
        # 개발 환경에서 실행할 때
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)
SHORTCUT_NAME = "MyOTPApp.lnk"
EXE_PATH = sys.executable

def add_to_startup():
    try:
        import winshell
        shortcut_path = os.path.join(STARTUP_FOLDER, SHORTCUT_NAME)
        winshell.CreateShortcut(
            Path=shortcut_path,
            Target=EXE_PATH,
            Description="AUTOTP"
        )
    except Exception as e:
        raise e

def remove_from_startup():
    shortcut_path = os.path.join(STARTUP_FOLDER, SHORTCUT_NAME)
    if os.path.exists(shortcut_path):
        os.remove(shortcut_path)

def find_isign_button(max_retries=5, delay=1.0):
    desktop = Desktop(backend="uia")
    for attempt in range(max_retries):
        try:
            # 작업표시줄을 여러 방법으로 시도
            taskbar = None
            try:
                taskbar = desktop.window(class_name="Shell_TrayWnd", top_level_only=True)
            except:
                # 첫 번째 방법 실패 시 두 번째 방법
                try:
                    taskbar = desktop.window(class_name="Shell_TrayWnd")
                except:
                    # 세 번째 방법: 모든 윈도우에서 작업표시줄 찾기
                    for win in desktop.windows():
                        if win.class_name() == "Shell_TrayWnd":
                            taskbar = win
                            break
            
            if taskbar:
                buttons = taskbar.descendants(control_type="Button")
                for btn in buttons:
                    btn_text = btn.window_text()
                    if "ISign" in btn_text:
                        print(f"ISign+ 버튼 찾음: '{btn_text}' (시도 {attempt + 1})")
                        return btn
                print(f"ISign+ 버튼 못 찾음 - 작업표시줄에서 버튼 미발견 (시도 {attempt + 1})")
            else:
                print(f"작업표시줄을 찾을 수 없음 (시도 {attempt + 1})")
        except Exception as e:
            print(f"작업표시줄 탐색 오류: {str(e)[:100]} (시도 {attempt + 1})")
        time.sleep(delay)
    return None

def get_otp_code_from_app(watcher=None):
    print("[1] 어플 실행중.. 마우스를 움직이지 마세요 !")
    btn = find_isign_button()
    if not btn:
        print("[2-err] ISign+ OTP 버튼을 찾지 못했습니다.")
        return None
    rect = btn.rectangle()
    print(f"[2] ISign+ OTP 버튼 클릭: {rect}")
    pyautogui.click(rect.left + 5, rect.top + 5)
    time.sleep(1.2)

    start_time = time.time()
    app_window = None
    while time.time() - start_time < 60:
        # 중단 신호 확인
        if watcher and watcher.cancel_login:
            print("[OTP 중단] OTP 창 연결 대기 중 중단")
            return None
        try:
            app = Application(backend="uia").connect(title_re=r".*ISign\+ OTP.*")
            app_window = app.window(title_re=r".*ISign\+ OTP.*")
            app_window.set_focus()
            print("[3] OTP 창 connect 성공")
            break
        except Exception:
            time.sleep(0.5)
    if not app_window:
        print("[3-err] 60초 내에 OTP 창 연결 실패")
        return None

    print("[4] 휴대폰 화면 컨트롤 찾기 대기")
    start_time = time.time()
    otp_box = None
    while time.time() - start_time < 60:
        # 중단 신호 확인
        if watcher and watcher.cancel_login:
            print("[OTP 중단] 휴대폰 화면 찾기 중 중단")
            return None
        try:
            otp_box = app_window.child_window(title="휴대폰 화면", control_type="Custom")
            otp_rect = otp_box.rectangle()
            break
        except Exception:
            time.sleep(0.5)
    if not otp_box:
        print("[4-err] 60초 내에 휴대폰 화면 컨트롤 못 찾음")
        return None

    width = otp_rect.right - otp_rect.left
    height = otp_rect.bottom - otp_rect.top
    x1 = otp_rect.left + int(width * 0.35)
    x2 = otp_rect.left + int(width * 0.85)
    y1 = otp_rect.top + int(height * 0.15)
    y2 = otp_rect.top + int(height * 0.27)
    otp_bbox = (x1, y1, x2, y2)

    start_time = time.time()
    while time.time() - start_time < 60:
        img_crop = ImageGrab.grab(bbox=otp_bbox)
        
        # 이미지 전처리 - 1과 7 구분 개선
        from PIL import ImageEnhance
        import cv2
        
        # 1. 그레이스케일 변환
        img_gray = img_crop.convert('L')
        
        # 2. 대비 강화 (contrast enhancement)
        enhancer = ImageEnhance.Contrast(img_gray)
        img_contrast = enhancer.enhance(2.0)  # 대비 2배 증가
        
        # 3. 선명도 강화 (sharpness enhancement)
        enhancer = ImageEnhance.Sharpness(img_contrast)
        img_sharp = enhancer.enhance(2.0)  # 선명도 2배 증가
        
        # 4. numpy 배열로 변환
        img_np = np.array(img_sharp)
        
        # 5. 적응형 이진화 (Adaptive Thresholding) - 숫자를 더 명확하게
        img_binary = cv2.adaptiveThreshold(
            img_np, 255, 
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
            cv2.THRESH_BINARY, 
            11, 2
        )
        
        # 6. OCR 인식 (이진화된 이미지 사용)
        results = reader.readtext(img_binary, detail=0, allowlist='0123456789')
        text = ''.join(results)
        numbers = re.findall(r'\d+', text)
        otp_code = ''.join(numbers)
        
        if len(otp_code) == 8:
            print(f"[5] 인식된 OTP 코드: {otp_code}")
            return otp_code
        time.sleep(1.5)
    print("[5-err] 60초 내에 OTP 코드 인식 실패")
    return None

def input_otp_direct(otp_code):
    print("[6] 통합로그인 창 포커스 시도")
    desktop = Desktop(backend="uia")
    start_time = time.time()
    window = None
    while time.time() - start_time < 60:
        try:
            window = desktop.window(title_re=".*통합로그인.*")
            window.set_focus()
            break
        except Exception:
            time.sleep(0.5)
    if not window:
        print("[6-err] 60초 내에 통합로그인 창 포커스 실패")
        return
    print("[7] OTP 코드 입력 및 엔터")
    pyautogui.write(otp_code, interval=0.03)
    pyautogui.press('enter')

def automated_login_input():
    """통합로그인 창에서 Edit 컨트롤(입력 필드)을 직접 찾아서
    학번과 비밀번호를 입력"""
    desktop = Desktop(backend="uia")
    start_time = time.time()
    window = None
    
    # 통합로그인 창 찾기
    while time.time() - start_time < 60:
        try:
            window = desktop.window(title_re=".*통합로그인.*")
            window.set_focus()
            break
        except Exception:
            time.sleep(0.5)
    
    if not window:
        print("[로그인 입력-err] 60초 내에 통합로그인 창을 찾지 못함")
        return

    # 학번 가져오기
    school_id = keyring.get_password("otp_app", "school_id")
    if not school_id:
        print("[오류] 저장된 학번(id)이 없음")
        return
    
    # 비밀번호 가져오기
    school_pw = keyring.get_password("otp_app", "school_pw")
    if not school_pw:
        print("[오류] 저장된 비밀번호 없음")
        return

    # Edit 컨트롤 찾기 (입력 필드) - 주소창 제외
    try:
        edit_controls = []
        for ctrl in window.descendants(control_type="Edit"):
            try:
                if ctrl.is_visible() and ctrl.is_enabled():
                    # 주소창 제외 (AutomationId나 Name에 'address', 'url' 등이 포함된 경우)
                    ctrl_id = ctrl.automation_id().lower() if ctrl.automation_id() else ""
                    ctrl_name = ctrl.window_text().lower()
                    
                    # 주소창 관련 키워드가 있으면 스킵
                    # URL 경로(https://, http://, .html, .kr 등)도 체크
                    if any(keyword in ctrl_id or keyword in ctrl_name 
                           for keyword in ['address', 'url', 'search', 'http', '주소', '.html', '.kr', '.com', 'sso.']):
                        print(f"[스킵] 주소창으로 보이는 컨트롤: ID={ctrl.automation_id()}, Text={ctrl.window_text()[:50]}")
                        continue
                    
                    edit_controls.append(ctrl)
                    print(f"[발견] Edit 컨트롤: ID={ctrl.automation_id()}, Name={ctrl.window_text()[:30]}")
            except Exception:
                continue
        
        if len(edit_controls) < 2:
            print(f"[로그인 입력-err] 입력 필드를 충분히 찾지 못함 (찾은 개수: {len(edit_controls)})")
            return
        
        # 첫 번째 Edit 컨트롤에 학번 입력
        print(f"[1] 학번 입력 필드 찾음")
        id_field = edit_controls[0]
        id_field.set_focus()
        time.sleep(0.1)
        id_field.set_edit_text("")  # 기존 텍스트 지우기
        time.sleep(0.2)
        id_field.type_keys(school_id, with_spaces=True)
        print(f"[2] 학번 입력 완료")
        time.sleep(0.1)
        
        # 두 번째 Edit 컨트롤에 비밀번호 입력
        print(f"[3] 비밀번호 입력 필드 찾음")
        pw_field = edit_controls[1]
        pw_field.set_focus()
        time.sleep(0.3)
        pw_field.set_edit_text("")  # 기존 텍스트 지우기
        time.sleep(0.2)
        pw_field.type_keys(school_pw, with_spaces=True)
        print(f"[4] 비밀번호 입력 완료")
        time.sleep(0.3)
        
        # 로그인 버튼 찾아서 클릭
        login_button = None
        for btn in window.descendants(control_type="Button"):
            try:
                btn_text = btn.window_text()
                if "로그인" in btn_text or "Login" in btn_text:
                    login_button = btn
                    break
            except Exception:
                continue
        
        if login_button:
            print(f"[5] 로그인 버튼 클릭")
            login_button.click()
        else:
            # 버튼을 못 찾으면 엔터키로 시도
            print(f"[5] 로그인 버튼 못 찾음, 엔터키로 시도")
            pyautogui.press('enter')
        
        # 로그인 버튼 클릭 후 창이 전환될 시간 대기
        print("[6] 로그인 후 창 전환 대기 (2초)")
        time.sleep(1)
        
        print("[자동 로그인입력] id/pw/로그인 입력 완료")
        
    except Exception as e:
        print(f"[로그인 입력-err] 입력 중 오류 발생: {e}")
        return

class CustomConfirmDialog(QWidget):
    yes_clicked = pyqtSignal()
    no_clicked = pyqtSignal()
    
    def __init__(self, parent=None, title="확인", message="계속하시겠습니까?", is_dark=False):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setFixedSize(420, 200)
        self.setWindowFlags(Qt.Dialog | Qt.WindowStaysOnTopHint)
        
        # 메인 레이아웃
        layout = QVBoxLayout()
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(20)
        
        # 메시지 라벨
        self.message_label = QLabel(message)
        self.message_label.setWordWrap(True)
        self.message_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.message_label)
        
        layout.addStretch()
        
        # 버튼 레이아웃
        button_layout = QHBoxLayout()
        button_layout.setSpacing(15)
        
        self.yes_button = QPushButton("예")
        self.yes_button.setFixedSize(80, 35)
        self.yes_button.clicked.connect(self.on_yes_clicked)
        
        self.no_button = QPushButton("아니오")
        self.no_button.setFixedSize(80, 35)
        self.no_button.clicked.connect(self.on_no_clicked)
        
        button_layout.addStretch()
        button_layout.addWidget(self.yes_button)
        button_layout.addWidget(self.no_button)
        button_layout.addStretch()
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
        
        # 테마 적용
        self.apply_theme(is_dark)
    
    def apply_theme(self, is_dark):
        if is_dark:
            self.setStyleSheet("""
                CustomConfirmDialog {
                    background-color: #2B2B2B;
                    border: 2px solid #555555;
                    border-radius: 10px;
                }
                QLabel {
                    color: #E0E0E0;
                    font-size: 14px;
                    background: transparent;
                    padding: 10px;
                }
                QPushButton {
                    background-color: #64B5F6;
                    color: white;
                    border: none;
                    border-radius: 6px;
                    font-size: 13px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #42A5F5;
                }
                QPushButton:pressed {
                    background-color: #2196F3;
                }
            """)
        else:
            self.setStyleSheet("""
                CustomConfirmDialog {
                    background-color: #FFFFFF;
                    border: 2px solid #CCCCCC;
                    border-radius: 10px;
                }
                QLabel {
                    color: #333333;
                    font-size: 14px;
                    background: transparent;
                    padding: 10px;
                }
                QPushButton {
                    background-color: #2196F3;
                    color: white;
                    border: none;
                    border-radius: 6px;
                    font-size: 13px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #1976D2;
                }
                QPushButton:pressed {
                    background-color: #1565C0;
                }
            """)
    
    def on_yes_clicked(self):
        self.yes_clicked.emit()
        self.accept()
    
    def on_no_clicked(self):
        self.no_clicked.emit()
        self.reject()
    
    def accept(self):
        self.close()
    
    def reject(self):
        self.close()

class LoginProgressDialog(QWidget):
    cancel_requested = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('로그인 진행 중')
        self.setFixedSize(400, 250)
        self.setWindowFlags(Qt.Dialog)
        self.parent_window = parent
        
        # 다크모드 확인
        is_dark = keyring.get_password("otp_app", "dark_mode") == "true"
        
        # 레이아웃 설정
        layout = QVBoxLayout()
        layout.setSpacing(20)
        layout.setContentsMargins(30, 30, 30, 30)
        
        # 진행 상태 라벨
        self.status_label = QLabel('로그인을 진행하고 있습니다...')
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setWordWrap(True)  # 텍스트 자동 줄바꿈
        
        # 안내 메시지
        self.info_label = QLabel('마우스를 움직이지 마세요.\n잠시만 기다려주세요...')
        self.info_label.setAlignment(Qt.AlignCenter)
        self.info_label.setWordWrap(True)  # 텍스트 자동 줄바꿈
        
        layout.addWidget(self.status_label)
        layout.addWidget(self.info_label)
        layout.addStretch()
        
        # 중단 버튼
        self.cancel_button = QPushButton('로그인 중단')
        self.cancel_button.setFixedHeight(40)
        self.cancel_button.clicked.connect(self.on_cancel_clicked)
        layout.addWidget(self.cancel_button)
        
        self.setLayout(layout)
        
        # 다크모드 스타일 적용
        self.apply_theme(is_dark)
    
    def apply_theme(self, is_dark):
        """다크모드/라이트모드 스타일 적용"""
        if is_dark:
            # 다크모드
            self.setStyleSheet("""
                QWidget {
                    background-color: #263238;
                }
            """)
            self.status_label.setStyleSheet("""
                QLabel {
                    font-size: 16px;
                    font-weight: bold;
                    color: #64B5F6;
                    padding: 10px;
                    background: none;
                    border: none;
                }
            """)
            self.info_label.setStyleSheet("""
                QLabel {
                    font-size: 12px;
                    color: #B0BEC5;
                    padding: 5px;
                    background: none;
                    border: none;
                }
            """)
            self.cancel_button.setStyleSheet("""
                QPushButton {
                    background-color: #E53935;
                    color: white;
                    border: none;
                    border-radius: 8px;
                    font-size: 14px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #D32F2F;
                }
                QPushButton:pressed {
                    background-color: #C62828;
                }
            """)
        else:
            # 라이트모드
            self.setStyleSheet("""
                QWidget {
                    background-color: #FFFFFF;
                }
            """)
            self.status_label.setStyleSheet("""
                QLabel {
                    font-size: 16px;
                    font-weight: bold;
                    color: #2196F3;
                    padding: 10px;
                    background: none;
                    border: none;
                }
            """)
            self.info_label.setStyleSheet("""
                QLabel {
                    font-size: 12px;
                    color: #666666;
                    padding: 5px;
                    background: none;
                    border: none;
                }
            """)
            self.cancel_button.setStyleSheet("""
                QPushButton {
                    background-color: #FF5722;
                    color: white;
                    border: none;
                    border-radius: 8px;
                    font-size: 14px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #E64A19;
                }
                QPushButton:pressed {
                    background-color: #D84315;
                }
            """)
    
    def on_cancel_clicked(self):
        print("[중단 요청] 로그인 중단 버튼 클릭")
        
        # 확인 대화상자 - 부모 윈도우의 스타일 상속
        parent = self.parent_window if self.parent_window else None
        reply = QMessageBox.question(
            parent,
            '로그인 중단 확인',
            '로그인 진행을 중단하시겠습니까?\n\n중단 후 처음부터 다시 탐지를 시작합니다.',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            print("[중단 확인] 사용자가 중단을 선택했습니다.")
            self.cancel_requested.emit()
        else:
            print("[중단 취소] 사용자가 로그인을 계속하기로 했습니다.")
    
    def update_status(self, status):
        self.status_label.setText(status)

class LoginWindowWatcher(QThread):
    show_login_alert = pyqtSignal()
    show_otp_result = pyqtSignal(str)
    show_progress_dialog = pyqtSignal()
    hide_progress_dialog = pyqtSignal()
    update_progress_status = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.running = True
        self.login_start_flag = False
        self.alert_showing = False  # 알림창 중복 방지 플래그
        self.retry_detection = False  # No 선택 시 재탐지 플래그
        self.alert_answered = False  # 알림창 응답 완료 플래그
        self.cancel_login = False  # 로그인 중단 플래그

    def run(self):
        print("통합로그인 창 감시 시작")
        while self.running:
            try:
                # 루프 시작 시 중단 플래그 확인
                if self.cancel_login:
                    print("[중단 감지] 루프 시작 시 중단 플래그 발견 - 상태 초기화")
                    self.reset_to_initial_state()
                
                start_time = time.time()
                print(f"\n[타이머] 새 루프 시작: {time.strftime('%H:%M:%S')}")
                
                desktop = Desktop(backend="uia")
                window = None
                
                while self.running:
                    try:
                        window = desktop.window(title_re=".*통합로그인.*")
                        if window.exists():
                            elapsed = time.time() - start_time
                            print(f"[타이머] 통합로그인 창 발견 (경과: {elapsed:.2f}초)")
                            break
                    except Exception:
                        pass
                    time.sleep(1)
                if not self.running:
                    break

                # 알림창이 이미 떠 있으면 스킵
                if self.alert_showing:
                    print("[알림 중복 방지] 이미 로그인 알림창이 떠 있음")
                    time.sleep(2)
                    continue

                self.login_start_flag = False
                self.alert_answered = False  # 알림창 응답 대기
                self.alert_showing = True  # 알림창 표시 중으로 설정
                
                before_alert = time.time()
                print(f"[타이머] 알림창 표시 중...")
                self.show_login_alert.emit()
                
                timeout = time.time() + 40
                while not self.alert_answered and time.time() < timeout and self.running:
                    time.sleep(0.1)
                
                after_alert = time.time()
                print(f"[타이머] 알림창 응답 대기 완료 (소요: {after_alert - before_alert:.2f}초)")
                
                self.alert_showing = False  # 알림창 종료
                
                if not self.running:
                    break
                
                # No를 눌렀거나 중단된 경우 빠른 재탐지
                if not self.login_start_flag or self.cancel_login:
                    if self.cancel_login:
                        print("[중단 재탐지] 중단 후 즉시 새 루프 시작")
                        # 중단된 경우 즉시 재탐지
                        time.sleep(0.5)  # 최소 대기
                    elif self.retry_detection:
                        print("[재탐지] 2초 후 다시 통합로그인 창 감시 시작")
                        time.sleep(2)  # 5초에서 2초로 단축
                        self.retry_detection = False
                    else:
                        print("[타이머] No 선택, 즉시 루프 재시작")
                    
                    total_elapsed = time.time() - start_time
                    print(f"[타이머] 이번 루프 총 소요 시간: {total_elapsed:.2f}초\n")
                    continue

                print("[알림] 2초 대기 후 로그인 진행")
                time.sleep(2)
                
                # 로그인 진행 창 표시
                self.show_progress_dialog.emit()
                time.sleep(0.5)
                
                try:
                    if self.cancel_login:
                        print("[로그인 중단] 사용자가 로그인을 중단했습니다.")
                        self.hide_progress_dialog.emit()
                        self.reset_to_initial_state()
                        continue
                    
                    self.update_progress_status.emit("로그인 정보를 입력하고 있습니다...")
                    automated_login_input()
                    
                    # 로그인 버튼 클릭 후 창 전환 확인
                    time.sleep(1.5)
                    try:
                        login_window = desktop.window(title_re=".*통합로그인.*")
                        if login_window.exists():
                            print("[로그인 재시도] 창이 전환되지 않음, 아이디 필드 재클릭 후 재시도")
                            # 아이디 입력 필드를 다시 클릭하여 재활성화
                            edit_controls = login_window.descendants(control_type="Edit")
                            filtered_edits = []
                            for ctrl in edit_controls:
                                try:
                                    if ctrl.is_visible() and ctrl.is_enabled():
                                        ctrl_id = ctrl.automation_id().lower() if ctrl.automation_id() else ""
                                        ctrl_name = ctrl.window_text().lower()
                                        if not any(keyword in ctrl_id or keyword in ctrl_name 
                                                 for keyword in ['address', 'url', 'search', 'http', '주소', '.html', '.kr', '.com', 'sso.']):
                                            filtered_edits.append(ctrl)
                                except Exception:
                                    continue
                            
                            if filtered_edits:
                                id_field = filtered_edits[0]
                                id_field.click_input()
                                time.sleep(0.5)
                                print("[로그인 재시도] 아이디 필드 클릭 완료, 다시 로그인 시도")
                                automated_login_input()
                                time.sleep(0.5)
                    except Exception as e:
                        print(f"[로그인 재시도 확인] {e}")
                        
                except Exception as e:
                    print(f"[로그인 입력 오류] {e}")
                    time.sleep(2)
                    continue

                # 비밀번호 변경 확인창 자동 닫기 (로그인 직후 나타날 수 있음)
                if self.cancel_login:
                    print("[로그인 중단] 비밀번호 변경 처리 중 중단")
                    self.hide_progress_dialog.emit()
                    self.reset_to_initial_state()
                    continue
                
                self.update_progress_status.emit("방해 창을 닫고 있습니다...")
                print("[창 정리] ESC를 눌러 모든 방해 창 닫기")
                # ESC를 여러 번 눌러서 비밀번호 변경 창 등 모든 팝업 닫기
                for i in range(3):
                    pyautogui.press('esc')
                    time.sleep(0.3)
                print("[창 정리] ESC 3회 전송 완료")
                time.sleep(0.5)

                if self.cancel_login:
                    print("[로그인 중단] OTP 처리 전 중단")
                    self.hide_progress_dialog.emit()
                    self.reset_to_initial_state()
                    continue
                
                self.update_progress_status.emit("OTP 코드를 가져오고 있습니다...")
                
                max_otp_retries = 3
                for attempt in range(max_otp_retries):
                    if self.cancel_login:
                        print("[로그인 중단] OTP 처리 중 중단")
                        self.hide_progress_dialog.emit()
                        self.reset_to_initial_state()
                        print("[빠른 재탐색] OTP 루프에서 빠른 종료 - 즉시 메인 루프 재시작")
                        # 메인 루프를 재시작하기 위해 전체 브렉 사용
                        return
                    try:
                        otp_code = get_otp_code_from_app(watcher=self)
                        if otp_code:
                            if self.cancel_login:
                                print("[로그인 중단] OTP 입력 중 중단")
                                self.hide_progress_dialog.emit()
                                self.reset_to_initial_state()
                                print("[빠른 재탐색] OTP 입력 중 빠른 종료")
                                break
                            
                            self.update_progress_status.emit(f"OTP 코드를 입력하고 있습니다... ({otp_code})")
                            input_otp_direct(otp_code)
                            self.show_otp_result.emit(otp_code)
                            
                            self.update_progress_status.emit("로그인 완료를 확인하고 있습니다...")
                            time.sleep(5)  # OTP 입력 후 대기
                            
                            # OTP 입력 후에도 통합로그인 창이 남아 있으면 재시도
                            try:
                                login_window = desktop.window(title_re=".*통합로그인.*")
                                if login_window.exists():
                                    print(f"[OTP 재시도] 통합로그인 창 여전히 존재, {attempt+1}회 재시도")
                                    time.sleep(2)
                                    continue
                                else:
                                    print("[OTP 성공] 통합로그인 창 사라짐")
                                    break
                            except Exception:
                                break
                        else:
                            self.show_otp_result.emit("")
                            break
                    except Exception as e:
                        print(f"[OTP 처리 오류] {e}")
                        self.show_otp_result.emit("")
                        break
                else:
                    print("[OTP 최대 재시도 초과] OTP 인식 실패")

                # 로그인 진행 창 숨기기
                self.hide_progress_dialog.emit()
                
                # 중단된 경우 빠른 재시작, 정상 완료시만 10초 대기
                if self.cancel_login:
                    print("[중단 감지] 빠른 재탐지 시작 - 즉시 새 루프로 이동")
                    self.reset_to_initial_state()  # 상태 초기화
                    print("[재탐지 시작] 상태 초기화 완료 - 새 루프 시작")
                    time.sleep(0.5)  # 짧은 대기 후 재시작
                    continue  # 즉시 새 루프 시작
                else:
                    time.sleep(10)
            except Exception as e:
                print(f"감시 쓰레드 예외: {e}")
                # 예외 발생 시에도 중단 확인
                if self.cancel_login:
                    print("[예외 처리 중 중단] 빠른 재탐지 - 상태 초기화 후 새 루프")
                    self.reset_to_initial_state()
                    time.sleep(0.5)
                    continue
                time.sleep(1)

    def stop(self):
        self.running = False
    
    def cancel_login_process(self):
        """로그인 중단 요청 처리"""
        try:
            print("[중단 처리] 로그인 중단 요청 수신")
            self.cancel_login = True
            # 진행 창 즉시 숨기기
            self.hide_progress_dialog.emit()
            # 상태 초기화는 메인 루프에서 처리
            print("[중단 완료] 중단 신호 설정 완료 - 메인 루프에서 재탐지 시작됨")
        except Exception as e:
            print(f"[중단 처리 오류] {e}")
    
    def reset_to_initial_state(self):
        """초기 탐지 상태로 복원"""
        self.cancel_login = False
        self.login_start_flag = False
        self.alert_showing = False
        self.retry_detection = False
        self.alert_answered = False
        print("[상태 초기화] 초기 탐지 상태로 복원됨")

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("autOTP")
        self.setFixedSize(500, 520)
        
        # 앱 아이콘 설정 (ico 파일 사용)
        icon_path = resource_path("autotpicon.ico")
        if os.path.exists(icon_path):
            app_icon = QIcon(icon_path)
            self.setWindowIcon(app_icon)
        
        # 시스템 트레이 아이콘 설정
        self.tray_icon = QSystemTrayIcon(self)
        if os.path.exists(icon_path):
            self.tray_icon.setIcon(QIcon(icon_path))
        else:
            self.tray_icon.setIcon(self.style().standardIcon(self.style().SP_ComputerIcon))
        self.tray_icon.setToolTip("autOTP")
        
        # 트레이 아이콘 메뉴 생성
        tray_menu = QMenu()
        show_action = QAction("프로그램 열기", self)
        show_action.triggered.connect(self.show_window)
        quit_action = QAction("종료", self)
        quit_action.triggered.connect(self.quit_application)
        
        tray_menu.addAction(show_action)
        tray_menu.addSeparator()
        tray_menu.addAction(quit_action)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.tray_icon_activated)
        self.tray_icon.show()
        
        # 다크모드 설정 로드
        self.is_dark_mode = self.load_dark_mode_setting()
        
        layout = QVBoxLayout()
        layout.setContentsMargins(35, 35, 35, 35)
        layout.setSpacing(15)

        # 상단 헤더 (타이틀 + 다크모드 토글)
        header_layout = QHBoxLayout()
        header_layout.setSpacing(0)
        
        # 왼쪽 빈 공간 (중앙 정렬을 위한 투명 스페이서)
        left_spacer = QWidget()
        left_spacer.setFixedSize(40, 40)
        left_spacer.setStyleSheet("background: transparent;")
        header_layout.addWidget(left_spacer)
        
        # 타이틀 레이블 (중앙)
        title_label = QLabel("AUTOTP")
        title_label.setObjectName("title")
        title_label.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(title_label, 1)
        
        # 다크모드 토글 버튼 (오른쪽)
        self.dark_mode_btn = QPushButton()
        self.dark_mode_btn.setObjectName("dark-mode-toggle")
        self.dark_mode_btn.setFixedSize(40, 40)
        self.dark_mode_btn.clicked.connect(self.toggle_dark_mode)
        self.dark_mode_btn.setCursor(Qt.PointingHandCursor)
        header_layout.addWidget(self.dark_mode_btn)
        
        layout.addLayout(header_layout)
        
        # 다크모드 토글 아이콘 경로 설정
        self.moon_icon_path = resource_path("free-icon-moon-3287906.png")
        self.sun_icon_path = resource_path("free-icon-sun-7712166.png")

        # 구분선
        line = QLabel()
        line.setFixedHeight(2)
        line.setObjectName("line")
        layout.addWidget(line)

        layout.addSpacing(10)

        # 안내 레이블
        info_label = QLabel(
            "학교 계정 정보를 입력하면\n"
            "통합로그인 시 자동으로 로그인 합니다."
        )
        info_label.setObjectName("info")
        info_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(info_label)

        layout.addSpacing(10)

        self.id_input = QLineEdit()
        self.id_input.setPlaceholderText("학번 (학교 계정)")
        self.id_input.setFixedHeight(45)
        layout.addWidget(self.id_input)

        self.pw_input = QLineEdit()
        self.pw_input.setEchoMode(QLineEdit.Password)
        self.pw_input.setPlaceholderText("비밀번호")
        self.pw_input.setFixedHeight(45)
        layout.addWidget(self.pw_input)

        layout.addSpacing(5)

        self.startup_checkbox = QCheckBox("윈도우 시작시 자동 실행")
        layout.addWidget(self.startup_checkbox)

        layout.addSpacing(10)

        self.save_button = QPushButton("설정 저장")
        self.save_button.setFixedHeight(50)
        self.save_button.clicked.connect(self.save_settings)
        layout.addWidget(self.save_button)

        self.delete_button = QPushButton("계정 정보 삭제")
        self.delete_button.setFixedHeight(45)
        self.delete_button.clicked.connect(self.delete_account)
        self.delete_button.setObjectName("delete-btn")
        layout.addWidget(self.delete_button)

        self.setLayout(layout)
        self.load_settings()
        self.startup_checkbox.stateChanged.connect(self.toggle_startup)
        
        # 다크모드 적용
        self.apply_theme()

        # 로그인 진행 창 초기화
        self.progress_dialog = None
        
        self.watcher = LoginWindowWatcher()
        self.watcher.show_login_alert.connect(self.on_show_login_alert)
        self.watcher.show_otp_result.connect(self.on_otp_finished)
        self.watcher.show_progress_dialog.connect(self.show_login_progress)
        self.watcher.hide_progress_dialog.connect(self.hide_login_progress)
        self.watcher.update_progress_status.connect(self.update_login_status)
        self.watcher.start()

    def load_dark_mode_setting(self):
        """다크모드 설정 불러오기"""
        try:
            setting = keyring.get_password("otp_app", "dark_mode")
            return setting == "true"
        except:
            return False

    def save_dark_mode_setting(self, is_dark):
        """다크모드 설정 저장하기"""
        try:
            keyring.set_password("otp_app", "dark_mode", "true" if is_dark else "false")
        except:
            pass

    def toggle_dark_mode(self):
        """다크모드 토글"""
        self.is_dark_mode = not self.is_dark_mode
        self.save_dark_mode_setting(self.is_dark_mode)
        self.apply_theme()

    def apply_theme(self):
        """테마 적용 (라이트/다크)"""
        if self.is_dark_mode:
            # 다크모드 아이콘 설정
            if os.path.exists(self.sun_icon_path):
                self.dark_mode_btn.setIcon(QIcon(self.sun_icon_path))
                self.dark_mode_btn.setIconSize(QSize(24, 24))
                self.dark_mode_btn.setText("")
            else:
                self.dark_mode_btn.setText("☀️")
            
            # 다크모드 스타일
            self.setStyleSheet("""
                QWidget {
                    background: qlineargradient(
                        x1:0, y1:0, x2:1, y2:0,
                        stop:0 #1a1a2e, 
                        stop:1 #16213e
                    );
                    font-family: "맑은 고딕", "Malgun Gothic", sans-serif;
                }
                
                QLabel#title {
                    color: #64B5F6;
                    font-size: 28px;
                    font-weight: bold;
                    padding: 10px 5px;
                    letter-spacing: 8px;
                    margin: 0px;
                    text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.5);
                }
                
                QLabel#line {
                    background: qlineargradient(
                        x1:0, y1:0, x2:1, y2:0,
                        stop:0 #42A5F5, 
                        stop:1 #1E88E5
                    );
                    border-radius: 1px;
                }
                
                QLabel#info {
                    color: #90CAF9;
                    font-size: 13px;
                    padding: 5px;
                }
                
                QLineEdit {
                    font-size: 14px;
                    background-color: #263238;
                    border: 2px solid #455A64;
                    border-radius: 8px;
                    padding: 10px 15px;
                    color: #E3F2FD;
                }
                
                QLineEdit:focus {
                    border: 2px solid #64B5F6;
                    background-color: #37474F;
                    border-bottom: 3px solid #64B5F6;
                }
                
                QLineEdit::placeholder {
                    color: #607D8B;
                }
                
                QCheckBox {
                    font-size: 14px;
                    color: #90CAF9;
                    font-weight: 500;
                    spacing: 8px;
                }
                
                QCheckBox::indicator {
                    width: 20px;
                    height: 20px;
                    border-radius: 4px;
                    border: 2px solid #455A64;
                    background-color: #263238;
                }
                
                QCheckBox::indicator:checked {
                    background-color: #42A5F5;
                    border-color: #42A5F5;
                }
                
                QCheckBox::indicator:hover {
                    border-color: #64B5F6;
                }
                
                QPushButton {
                    font-size: 15px;
                    font-weight: bold;
                    background-color: #1E88E5;
                    color: white;
                    border: none;
                    border-radius: 10px;
                    padding: 12px 20px;
                }
                
                QPushButton:hover {
                    background-color: #1976D2;
                    padding-bottom: 10px;
                }
                
                QPushButton:pressed {
                    background-color: #1565C0;
                    padding-top: 14px;
                    padding-bottom: 10px;
                }
                
                QPushButton#delete-btn {
                    background-color: #E53935;
                }
                
                QPushButton#delete-btn:hover {
                    background-color: #D32F2F;
                    padding-bottom: 10px;
                }
                
                QPushButton#delete-btn:pressed {
                    background-color: #C62828;
                    padding-top: 14px;
                    padding-bottom: 10px;
                }
                
                QPushButton#dark-mode-toggle {
                    background-color: transparent;
                    border: 2px solid #455A64;
                    border-radius: 20px;
                }
                
                QPushButton#dark-mode-toggle:hover {
                    background-color: #37474F;
                    border-color: #64B5F6;
                }
                
                QPushButton#dark-mode-toggle:pressed {
                    background-color: #263238;
                }
                
                QMessageBox {
                    background-color: #263238;
                }
                
                QMessageBox QLabel {
                    color: #E3F2FD;
                    background-color: #263238;
                    border: none;
                    text-decoration: none;
                }
                
                QMessageBox QPushButton {
                    background-color: #1E88E5;
                    color: white;
                    border: none;
                    border-radius: 5px;
                    padding: 8px 15px;
                    min-width: 70px;
                    text-decoration: none;
                }
                
                QMessageBox QPushButton:hover {
                    background-color: #1976D2;
                }
            """)
        else:
            # 라이트모드 아이콘 설정
            if os.path.exists(self.moon_icon_path):
                self.dark_mode_btn.setIcon(QIcon(self.moon_icon_path))
                self.dark_mode_btn.setIconSize(QSize(24, 24))
                self.dark_mode_btn.setText("")
            else:
                self.dark_mode_btn.setText("🌙")
            
            # 라이트모드 스타일
            self.setStyleSheet("""
                QWidget {
                    background: qlineargradient(
                        x1:0, y1:0, x2:1, y2:0,
                        stop:0 #E3F2FD, 
                        stop:1 #FFFFFF
                    );
                    font-family: "맑은 고딕", "Malgun Gothic", sans-serif;
                }
                
                QLabel#title {
                    color: #1976D2;
                    font-size: 28px;
                    font-weight: bold;
                    padding: 10px 5px;
                    letter-spacing: 8px;
                    margin: 0px;
                    text-shadow: 1px 1px 3px rgba(25, 118, 210, 0.3);
                }
                
                QLabel#line {
                    background: qlineargradient(
                        x1:0, y1:0, x2:1, y2:0,
                        stop:0 #42A5F5, 
                        stop:1 #90CAF9
                    );
                    border-radius: 1px;
                }
                
                QLabel#info {
                    color: #1976D2;
                    font-size: 13px;
                    padding: 5px;
                }
                
                QLineEdit {
                    font-size: 14px;
                    background-color: #FFFFFF;
                    border: 2px solid #90CAF9;
                    border-radius: 8px;
                    padding: 10px 15px;
                    color: #1565C0;
                }
                
                QLineEdit:focus {
                    border: 2px solid #42A5F5;
                    background-color: #E3F2FD;
                    border-bottom: 3px solid #42A5F5;
                }
                
                QLineEdit::placeholder {
                    color: #90CAF9;
                }
                
                QCheckBox {
                    font-size: 14px;
                    color: #1976D2;
                    font-weight: 500;
                    spacing: 8px;
                }
                
                QCheckBox::indicator {
                    width: 20px;
                    height: 20px;
                    border-radius: 4px;
                    border: 2px solid #90CAF9;
                    background-color: #FFFFFF;
                }
                
                QCheckBox::indicator:checked {
                    background-color: #42A5F5;
                    border-color: #42A5F5;
                }
                
                QCheckBox::indicator:hover {
                    border-color: #42A5F5;
                }
                
                QPushButton {
                    font-size: 15px;
                    font-weight: bold;
                    background-color: #42A5F5;
                    color: white;
                    border: none;
                    border-radius: 10px;
                    padding: 12px 20px;
                }
                
                QPushButton:hover {
                    background-color: #1E88E5;
                    padding-bottom: 10px;
                }
                
                QPushButton:pressed {
                    background-color: #1976D2;
                    padding-top: 14px;
                    padding-bottom: 10px;
                }
                
                QPushButton#delete-btn {
                    background-color: #EF5350;
                }
                
                QPushButton#delete-btn:hover {
                    background-color: #E53935;
                    padding-bottom: 10px;
                }
                
                QPushButton#delete-btn:pressed {
                    background-color: #D32F2F;
                    padding-top: 14px;
                    padding-bottom: 10px;
                }
                
                QPushButton#dark-mode-toggle {
                    background-color: transparent;
                    border: 2px solid #90CAF9;
                    border-radius: 20px;
                    font-size: 20px;
                }
                
                QPushButton#dark-mode-toggle:hover {
                    background-color: #E3F2FD;
                    border-color: #42A5F5;
                }
                
                QPushButton#dark-mode-toggle:pressed {
                    background-color: #BBDEFB;
                }
                
                QMessageBox {
                    background-color: #FFFFFF;
                }
                
                QMessageBox QLabel {
                    color: #1976D2;
                    background-color: #FFFFFF;
                    border: none;
                    text-decoration: none;
                }
                
                QMessageBox QPushButton {
                    background-color: #42A5F5;
                    color: white;
                    border: none;
                    border-radius: 5px;
                    padding: 8px 15px;
                    min-width: 70px;
                    text-decoration: none;
                }
                
                QMessageBox QPushButton:hover {
                    background-color: #1E88E5;
                }
            """)

    def save_settings(self):
        keyring.set_password("otp_app", "school_id", self.id_input.text())
        keyring.set_password("otp_app", "school_pw", self.pw_input.text())
        QMessageBox.information(self, "저장됨", "계정 정보와 설정이 저장되었습니다.")

    def load_settings(self):
        try:
            self.id_input.setText(keyring.get_password("otp_app", "school_id") or "")
            self.pw_input.setText(keyring.get_password("otp_app", "school_pw") or "")
        except Exception:
            pass

    def toggle_startup(self):
        if self.startup_checkbox.isChecked():
            try:
                add_to_startup()
                QMessageBox.information(self, "자동 실행", "윈도우 시작시 자동 실행이 설정되었습니다.")
            except Exception as e:
                QMessageBox.warning(self, "오류", f"설정 실패: {e}")
        else:
            remove_from_startup()
            QMessageBox.information(self, "자동 실행", "윈도우 시작시 자동 실행이 해제되었습니다.")

    def delete_account(self):
        reply = QMessageBox.question(self, '계정 완전히 삭제', '정말 계정 정보를 완전히 삭제하시겠습니까?', 
                                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            try:
                keyring.delete_password("otp_app", "school_id")
            except Exception:
                pass
            try:
                keyring.delete_password("otp_app", "school_pw")
            except Exception:
                pass
            self.id_input.setText("")
            self.pw_input.setText("")
            QMessageBox.information(self, "삭제 완료", "저장된 계정/비밀번호가 완전히 삭제되었습니다.")

    def on_show_login_alert(self):
        try:
            # 창이 트레이에 숨겨져 있으면 일시적으로 표시
            was_hidden = not self.isVisible()
            if was_hidden:
                self.show()
            
            # 알림창 표시
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.NoIcon)  # 아이콘 제거
            msg_box.setWindowTitle('로그인 진행')
            msg_box.setText('로그인 진행하시겠습니까?\n이후 로그인이 완료될 때 까지 마우스를 움직이지 마세요.')
            msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            msg_box.setDefaultButton(QMessageBox.Yes)
            
            reply = msg_box.exec_()
            
            # 응답 완료 플래그 설정 (즉시 타임아웃 루프 종료)
            self.watcher.alert_answered = True
            
            # No를 눌렀을 때 - 즉시 플래그 설정
            if reply == QMessageBox.No:
                self.watcher.login_start_flag = False
                self.watcher.retry_detection = True
                print("[디버그] No 선택 - 플래그 즉시 설정 완료")
            else:
                self.watcher.login_start_flag = True
                print("[디버그] Yes 선택 - 로그인 진행")
            
        except Exception as e:
            print(f"[로그인 알림 오류] {e}")
            self.watcher.login_start_flag = False

    def on_otp_finished(self, otp_code):
        try:
            # 창이 트레이에 숨겨져 있으면 알림창만 표시 (메인 창은 숨긴 채로)
            if otp_code:
                # 트레이 알림으로 표시
                self.tray_icon.showMessage(
                    "OTP 자동 입력 완료",
                    f"OTP 코드가 자동 입력되었습니다: {otp_code}",
                    QSystemTrayIcon.Information,
                    3000
                )
            else:
                # 오류는 메시지박스로 표시 (더 중요하므로)
                was_hidden = not self.isVisible()
                if was_hidden:
                    self.show()
                QMessageBox.warning(self, "OTP 오류", "OTP 코드를 인식하지 못했습니다.")
                if was_hidden:
                    self.hide()
        except Exception as e:
            print(f"[OTP 완료 알림 오류] {e}")
    
    def show_login_progress(self):
        """로그인 진행 창 표시"""
        if not self.progress_dialog:
            self.progress_dialog = LoginProgressDialog(self)
            self.progress_dialog.cancel_requested.connect(self.watcher.cancel_login_process)
        
        # 화면 중앙에 배치
        screen = QApplication.desktop().screenGeometry()
        x = (screen.width() - self.progress_dialog.width()) // 2
        y = (screen.height() - self.progress_dialog.height()) // 2
        self.progress_dialog.move(x, y)
        
        self.progress_dialog.show()
        self.progress_dialog.raise_()
        self.progress_dialog.activateWindow()
    
    def hide_login_progress(self):
        """로그인 진행 창 숨기기"""
        if self.progress_dialog:
            self.progress_dialog.hide()
    
    def update_login_status(self, status):
        """로그인 진행 상태 업데이트"""
        if self.progress_dialog:
            self.progress_dialog.update_status(status)

    def show_window(self):
        """트레이에서 창 복원"""
        self.show()
        self.activateWindow()

    def tray_icon_activated(self, reason):
        """트레이 아이콘 더블클릭 시 창 복원"""
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_window()

    def quit_application(self):
        """완전히 프로그램 종료"""
        reply = QMessageBox.question(self, '종료 확인', 
            '프로그램을 완전히 종료하시겠습니까?\n(OTP 자동 입력이 중지됩니다)',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.tray_icon.hide()
            self.watcher.stop()
            self.watcher.wait()
            QApplication.quit()

    def closeEvent(self, event):
        """X 버튼 클릭 시 트레이로 최소화 (알림 없음)"""
        event.ignore()
        self.hide()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
