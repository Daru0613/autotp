# autOTP v2.0

캠퍼스 헬퍼 자동 로그인 프로그램

## 📋 개요

캠퍼스 헬퍼 사이트의 자동 로그인을 지원하는 Windows 데스크톱 애플리케이션입니다.
OCR 기술을 활용하여 이미지 기반 로그인 버튼을 자동으로 인식하고 클릭합니다.

## ✨ 주요 기능

- 🔐 자동 로그인 (ID/PW 저장 및 자동 입력)
- 🖱️ OCR 기반 버튼 자동 인식 및 클릭
- 🌓 다크모드/라이트모드 지원
- 🔄 로그인 실패 시 자동 재시도
- ⏸️ 진행 중 작업 취소 기능
- 💾 Windows 자격 증명 관리자를 통한 안전한 비밀번호 저장

## 🚀 사용 방법

### 설치

1. [Releases](https://github.com/Daru0613/autotp/releases)에서 최신 버전 다운로드
2. `autOTP_v2.0.zip` 압축 해제
3. `autOTP.exe` 실행

### 실행

1. 프로그램 실행
2. 로그인 정보 입력 (최초 1회)
3. "자동 시작" 버튼 클릭
4. 자동으로 캠퍼스 헬퍼 로그인 진행

## 🛠️ 기술 스택

- **Python 3.13**
- **PyQt5** - GUI 프레임워크
- **EasyOCR** - 이미지 텍스트 인식
- **pywinauto** - Windows UI 자동화
- **pyautogui** - 마우스/키보드 제어
- **keyring** - 안전한 비밀번호 저장

## 📦 빌드 방법

```bash
# 의존성 설치
pip install PyQt5 easyocr pywinauto pyautogui keyring opencv-python numpy torch torchvision

# PyInstaller로 빌드
pyinstaller --onefile --windowed --icon=autotpicon.ico --add-data "autotpicon.ico;." --add-data "free-icon-moon-3287906.png;." --add-data "free-icon-sun-7712166.png;." --name autOTP mouse.py
```

## 📝 버전 정보

### v2.0 (2024-11-24)

- 로그인 재시도 로직 추가
- 다크모드 지원
- 로그인 진행 중 취소 기능
- UI 개선 및 안정성 향상

## ⚠️ 주의사항

- Windows 10/11 전용
- 네트워크 연결 필요
- 최초 실행 시 OCR 모델 다운로드로 시간 소요 가능
- 개인 정보 보호를 위해 비밀번호는 Windows 자격 증명 관리자에 안전하게 저장됩니다

## 🔒 보안

- 비밀번호는 Windows Credential Manager에 암호화되어 저장
- 로컬에서만 동작하며 외부 서버로 정보 전송 없음

## 📄 라이선스

이 프로젝트는 개인 사용 목적으로 제작되었습니다.

## 👤 개발자

Daru0613

---

**문의사항이나 버그 리포트는 [Issues](https://github.com/Daru0613/autotp/issues)에 등록해주세요.**
