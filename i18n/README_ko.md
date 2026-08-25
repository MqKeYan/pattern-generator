<h1 align="center">
  <br>
  <strong> 패턴 생성기——반응-확산 방정식 시각화 도구</strong>
  <br>
</h1>

<p align="center">
  <a href="../LICENSE"><img src="https://img.shields.io/badge/License-GPL--3.0-blue"></a>
  <a href="#"><img src="https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white"></a>
  <a href="#"><img src="https://img.shields.io/badge/Flask-3.0+-000000?logo=flask&logoColor=white"></a>
  <a href="#"><img src="https://img.shields.io/badge/PyTorch-2.0+-EE4C2C?logo=pytorch&logoColor=white"></a>
  <a href="#"><img src="https://img.shields.io/badge/Plotly.js-2.32+-3F4F75?logo=plotly&logoColor=white"></a>
</p>

<p align="center">
  Languages:
  <a href="../README.md"> 简体中文 </a> ·
  <a href="./README_en.md"> English </a> ·
  <a href="./README_zh-Hant.md"> 繁體中文 </a> ·
  <a href="./README_ja.md"> 日本語 </a> ·
  <a href="./README_ko.md"> 한국어 </a>
</p>

<p align="center">
  참고: 인터페이스 언어는 기계 번역으로 생성되었습니다. 부정확한 부분이 있으면 <a href="https://github.com/MqKeYan/pattern-generator/issues">Issues</a>에서 알려주세요.
</p>

## 소개

패턴 생성기는 반응-확산 방정식에 기반한 시각화 도구로, 생태계에서 포식자-피식자 개체군의 시공간 역학을 시뮬레이션하고 관찰하기 위한 것입니다. 5가지 고전적인 반응-확산 모델을 내장하고 PyTorch CUDA 기반 GPU 가속을 활용하여 소용돌이파, 반점, 줄무늬 등의 전형적인 패턴을 빠르게 생성할 수 있습니다. 2D 히트맵, 3D 표면도, 시간 진화 곡선 등 다양한 시각화 형식을 제공하며, 패턴 진화 애니메이션의 프레임별 재생도 지원합니다.

## 기능 개요

| 기능 | 설명 |
|------|------|
|  GPU 가속 | PyTorch CUDA 백엔드 |
|  다차원 시각화 | Plotly.js 2D 히트맵 / 3D 표면도 / 시간 진화 곡선 |
|  애니메이션 재생 | 패턴 진화 과정을 프레임별 재생, 일시정지·속도 조절·프레임 이동 지원 |
|  매개변수 조정 | 7~8개 매개변수 자유 조절, 모델 실시간 전환, 원클릭 기본값 복원 |
|  사용자 추적 지점 | 그리드 임의 위치에 관측점 설정, 개체군 밀도의 시간 변화 추적 |
|  메모리 관리 | 시뮬레이션 완료 후 GPU 메모리 자동 정리, 메모리 누수 방지 |

## 모델과 패턴

| 모델 | 대표 패턴 | 매개변수 수 | 권장 반복 |
|------|---------|---------|---------|
| 모델1 · Rosenzweig-MacArthur | 소용돌이파, 반점 패턴 | 7 | 9,000 |
| 모델2 · Holling II | 줄무늬 패턴, 미로 패턴 | 8 | 15,000 |
| 모델3 · Ratio-dependent | 소용돌이파, 표적파 | 8 | 15,000 |
| 모델4 · 대칭 경쟁 | 반점 패턴, 상분리 패턴 | 3 | 10,000 |
| 모델5 · 연속화 이산 | 복잡한 동적 패턴, 혼돈 패턴 | 8 | 4,000 |

## 시스템 요구 사항

| 항목 | 최소 요구 사항 |
|------|---------|
| 운영 체제 | Windows 10 버전 1809 이상 / Windows 11 |
| 아키텍처 | 64비트 (x64) |
| 메모리 | 8GB 이상 권장 |
| GPU (선택) | NVIDIA GPU + CUDA 12.x+, VRAM 4GB 이상 |
| 브라우저 | Edge / Chrome / Firefox (웹 인터페이스 접속용) |

## 빠른 시작

### 다운로드 & 실행

1. [Releases](https://github.com/MqKeYan/pattern-generator/releases) 페이지에서 최신 `.zip` 압축 파일을 다운로드
2. 임의의 디렉터리에 압축 해제 (**관리자 권한이 필요한 디렉터리는 피하세요**, 예: `C:\Program Files`)
3. 압축 해제된 `pattern-generator.exe`는 `_internal/` 폴더와 같은 디렉터리에 있어야 합니다
4. 별도로 `Pytorch` 의존성을 설치합니다. `CUDA 13.2+` 지원 버전 설치 명령은 `pip3 install torch torchvision --index-url https://download.pytorch.org/whl/cu132`, 또는[공식 사이트](https://pytorch.org/get-started/locally/) 참조
5. `pattern-generator.exe`를 더블클릭하고, 명령줄의 URL을 클릭하면 페이지가 자동으로 열립니다

### 소스 코드에서 실행

```bash
# 환경 요구 사항: Python 3.13+
git clone https://github.com/MqKeYan/pattern-generator.git
cd pattern-generator
pip install -r requirements.txt

# GPU 가속
# CUDA 버전 정보 확인
nvidia-smi
# 해당 CUDA 버전의 Pytorch 설치
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu132

# 서버 시작
python start.py --host 0.0.0.0
```

시작 후 브라우저에서 **http://localhost:5000** 에 접속하세요.

## 사용 방법

1. **모델 선택**：드롭다운에서 5가지 모델 중 하나를 선택, 매개변수 패널이 기본값을 자동으로 로드합니다
2. **매개변수 조정**：매개변수 값을 수정, ↺ 버튼으로 개별 매개변수 초기화, 「매개변수 초기화」로 전체 기본값 복원
3. **초기값 범위 설정**：X/Y 개체군의 초기 밀도 범위 조정
4. **추적 지점 추가** (선택)：그리드 좌표 (0-99) 입력, 지정 위치의 개체군 변화 관찰
5. **시뮬레이션 실행**：반복 횟수 조정, 「시뮬레이션 실행」 클릭, 결과 확인
6. **결과 확인**：
   - **2D 패턴**：X 개체군 / Y 개체군 히트맵 + 결합 패턴 + 시간 진화 곡선
   - **3D 패턴**：개체군 밀도 3D 표면도
   - **애니메이션**：패턴 형성 과정의 프레임별 재생

## 프로젝트 구조

```
src/                                 # 소프트웨어 코드
├── core/                            # 핵심 계산 엔진
│   ├── config.py                    # 모델 매개변수 설정
│   ├── models.py                    # 5가지 반응-확산 방정식 + 라플라시안
│   ├── simulation.py                # 시뮬레이션 엔진 — 그리드 초기화, 반복, 메모리 관리
│   └── visualization.py             # 시각화 데이터 생성 — Plotly JSON 형식
├── web/                             # 웹 서비스 계층
│   ├── server.py                    # Flask 웹 서비스 — API + 페이지 라우팅
│   ├── static/
│   │   ├── css/style.css            # 다크 테크 스타일 테마
│   │   ├── fonts/NotoSansCJK-VF.otf.ttc # Noto Sans CJK 가변 폰트
│   │   ├── js/app.js                # 프론트엔드 로직 — Plotly.js 차트 렌더링
│   │   ├── js/i18n.js               # 국제화 번역 모듈
│   │   ├── js/plotly.min.js         # 로컬 Plotly.js 라이브러리
│   │   └── favicon.ico              # 사이트 아이콘
│   └── templates/
│       └── index.html               # 메인 페이지
├── port_check.py                    # 포트 점유 확인
├── settings.py                      # 포트 및 브라우저 자동 실행 설정 관리
└── version.py                       # 버전 관리

run.py                               # 시작 스크립트
settings.json                        # 소프트웨어 실행 설정
```

## 토론과 교류

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;사용 중 문제가 발생하거나, 새로운 기능 요청·개선 제안이 있다면 [GitHub Issues](https://github.com/MqKeYan/pattern-generator/issues)에서 알려주세요. 해결 방법이 있다면 Pull Request를 제출해 프로젝트 개선에 함께해 주시면 매우 감사하겠습니다!

## 행동 강령

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;이 프로젝트는 **Contributor Covenant Code of Conduct**를 따릅니다. 개방적이고 친근하며 상호 존중하는 커뮤니티 환경 조성을 위해 노력하고 있습니다.

## 라이선스

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;이 프로젝트는 **GPL-3.0 License**로 제공됩니다. 자세한 내용은 [LICENSE](../LICENSE) 파일을 참조하세요.
