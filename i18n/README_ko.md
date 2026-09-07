<h1 align="center">
  <br>
  <strong> 패턴 생성기——반응-확산 방정식 시각화 도구</strong>
  <br>
</h1>

<p align="center">
  <a href="../LICENSE"><img src="https://img.shields.io/badge/License-GPL--3.0-blue"></a>
  <a href="#"><img src="https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white"></a>
  <a href="#"><img src="https://img.shields.io/badge/FastAPI-0.110+-009688?logo=fastapi&logoColor=white"></a>
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

### 프론트엔드 시각화
| 기능 | 설명 |
|------|------|
| GPU 가속 | PyTorch CUDA 백엔드, CUDA/CPU 자동 감지 및 남은 VRAM 기준 멀티 GPU 선택 |
| 다차원 시각화 | Plotly.js 2D 히트맵 / 3D 표면도 / 시간 진화 곡선 |
| 애니메이션 재생 | 패턴 진화 과정을 프레임별 재생, 일시정지·속도 조절·프레임 이동 지원, 프레임 기록은 호스트 메모리에 유지 |
| 매개변수 조정 | 모델별 7~8개 매개변수 자유 조절, 실시간 전환, 원클릭 기본값 복원 및 개별 초기화 |
| 사용자 추적 지점 | 그리드 임의 위치(0-99)에 최대 8개의 관측 지점 설정, 개체군 밀도의 시간 변화 추적 |
| 메모리 관리 | 시뮬레이션 완료 후 GPU 메모리와 호스트 캐시 자동 정리, 메모리 누수 방지 |

### 작업 및 스케줄링
| 기능 | 설명 |
|------|------|
| 비동기 작업 큐 | FIFO 스케줄링, 대기 위치와 실행 진행률을 로딩 오버레이에 실시간 표시, "작업 취소" 지원 |
| 타임아웃 및 재시도 | 타임아웃(기본 300초) 시 자동 취소, 실패 시 자동 재시도(기본 1회), 재시도 초과 시 dead-letter 큐로 이동 |
| VRAM 사전 검사 | 작업 투입 전 남은 VRAM + 예약 임계값으로 GPU 선택, 부족 시 큐에 대기 |
| 캐시 복원 | 페이지 새로고침 시 매개변수와 차트 자동 복원, 2D/애니메이션 주문형 복원 |

### 관리 센터 (`http://127.0.0.1:5001` 로컬 전용)

| 모듈 | 설명 |
|------|------|
| 개요 | 전역 상태, 누적 통계, 빠른 작업 및 보고서 내보내기 |
| 실시간 모니터링 | CPU / 메모리 / GPU 사용률 / VRAM / 온도 / 전력 / 디스크 / 네트워크 실시간 곡선(3분 롤링) 및 피크 집계 |
| 작업 큐 | 실행 중 / 대기 중 / 기록 / dead-letter 관리, 취소·재시도·비우기·삭제 지원 |
| 클라이언트 관리 | 온라인 / 오프라인 / 일시정지 / 대기 / 계산 상태 추적, 일시정지·킥(동시 IP 차단)·캐시 삭제·비고 및 태그 |
| 접근 제어 | IP / client_id 블랙리스트·화이트리스트, LAN 제한, IP+client_id 속도 제한, 거부 기록 |
| 알림 | Windows 토스트, 시스템 사운드, PushPlus WeChat 푸시, 임계값 및 이벤트 설정 가능 |
| 로그 | 실행마다 별도 생성되는 `log/YYYY-MM-DD_HH-mm-ss_PID.log`, 실시간 보기, 필터·검색·다운로드 |
| 시스템 설정 | 포트, 동시성, 타임아웃, 재시도, 속도 제한, 캐시 제한 등, 기본값 복원 지원 |

### 운영 및 보고
| 기능 | 설명 |
|------|------|
| WebSocket 푸시 | 메트릭 / 클라이언트 / 작업 / 로그를 매초 푸시, 끊기면 3초 내 자동 재연결 |
| 온라인 상태 | 프론트엔드 WebSocket 온라인 연결(`/api/presence`), 끊기면 즉시 오프라인, 5분 타임아웃 폴백 |
| 보고서 내보내기 | 클라이언트 활동 / 작업 실행 / 시스템 리소스 피크 / 접근 제어 / 알림 이벤트를 CSV/XLSX/JSON으로 내보내기 |
| 포트 검사 | 시작 시 메인 및 관리 포트 점유 검사, 대화형 정리 및 3초 카운트다운 자동 시작 |

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
| GPU (선택) | NVIDIA GPU + CUDA 12.x+, VRAM 4GB 이상 (GPU 없으면 CPU로 자동 폴백) |
| 브라우저 | Edge / Chrome / Firefox (웹 인터페이스 접속용) |
| 네트워크 | 관리 센터는 로컬 전용 `127.0.0.1:5001`, 메인 화면은 LAN `0.0.0.0:5000` 지원 |

## 빠른 시작

### 다운로드 및 실행

1. [Releases](https://github.com/MqKeYan/pattern-generator/releases) 페이지에서 최신 `.zip` 압축 파일을 다운로드
2. 임의의 디렉터리에 압축 해제 (**관리자 권한이 필요한 디렉터리는 피하세요**, 예: `C:\Program Files`)
3. 압축 해제된 `pattern-generator.exe`는 `_internal/` 폴더와 같은 디렉터리에 있어야 합니다
4. 별도로 `Pytorch` 의존성을 설치합니다. `CUDA 13.2+` 지원 버전 설치 명령은 `pip3 install torch --index-url https://download.pytorch.org/whl/cu132`, 또는[공식 사이트](https://pytorch.org/get-started/locally/) 참조
5. `pattern-generator.exe`를 더블클릭하고, 포트 검사 및 브라우저 자동 열기 안내를 따릅니다
6. 메인 화면: `http://LAN_IP:5000`, 관리 센터: `http://127.0.0.1:5001`(로컬 전용)

### 소스 코드에서 실행

```bash
# 환경 요구 사항: Python 3.13+
git clone https://github.com/MqKeYan/pattern-generator.git
cd pattern-generator
pip install -r requirements.txt

# GPU 가속 (선택)
# CUDA 버전 정보 확인
nvidia-smi
# 해당 CUDA 버전의 Pytorch 설치
pip install torch --index-url https://download.pytorch.org/whl/cu132

# 서비스 시작 (메인 + 관리 함께 시작)
python run.py
```

시작 후 브라우저에서 메인 화면 http://localhost:5000, 관리 센터 http://127.0.0.1:5001 에 접속하세요.

> 개발자 참고: `run.py`는 두 개의 Uvicorn 서비스를 함께 시작합니다. 관리 센터에서 `config/settings.json`을 변경한 뒤에는 재시작이 필요합니다.

## 사용 방법

1. **모델 선택**：드롭다운에서 5가지 모델 중 하나를 선택, 매개변수 패널이 기본값을 자동으로 로드합니다
2. **매개변수 조정**：매개변수 값을 수정, ↺ 버튼으로 개별 매개변수 초기화, "매개변수 초기화"로 전체 기본값 복원
3. **초기값 범위 설정**：X/Y 개체군의 초기 밀도 범위 조정
4. **추적 지점 추가** (선택)：그리드 좌표 (0-99) 입력, 지정 위치의 개체군 변화 관찰
5. **시뮬레이션 실행**：반복 횟수 조정, "시뮬레이션 실행" 클릭, 로딩 오버레이의 대기 위치와 실시간 진행률(`실행 중, 진행률 xx%`) 확인, 필요 시 "작업 취소"
6. **결과 확인**：
   - **2D 패턴**：X 개체군 / Y 개체군 히트맵 + 결합 패턴 + 시간 진화 곡선
   - **3D 패턴**：개체군 밀도 3D 표면도 (회전 가능)
   - **애니메이션**：패턴 형성 과정의 프레임별 재생, 재생/일시정지·프레임 슬라이더·속도 조절 지원

## 관리 센터

로컬 전용 `http://127.0.0.1:5001` 에서만 접근 가능. 왼쪽 전역 상태 카드에 가동 시간, 포트, 온라인 클라이언트, 실행/대기 작업 수가 실시간으로 표시됩니다.

- **개요**: 주요 메트릭, 온라인 통계, 누적 계산 시간, 빠른 작업 및 보고서 내보내기.
- **실시간 모니터링**: CPU/메모리/프로세스 메모리, GPU 사용률/VRAM, GPU 온도/전력/CPU 온도, 디스크/네트워크 4개 그룹 곡선 및 온라인 클라이언트 수 로컬 곡선.
- **작업 큐**: 실행 중 / 대기 중 / 기록 / dead-letter 4개 테이블, 작업별 동작, GPU 할당 및 재시도 횟수.
- **클라이언트 관리**: UUID, 이름, IP, 상태, 현재 작업, 요청 및 성공/실패/취소 통계, 온라인 시간, 태그 및 비고, 일시정지/재개, 킥 및 차단, 캐시 삭제, 비고.
- **접근 제어**: IP 및 client_id 블랙리스트/화이트리스트, LAN 사설 대역 제한 및 속도 제한 설정.
- **알림**: `system_toast` / `system_sound` / `pushplus` 설정 가능, 큐 적체 및 GPU 온도 등 임계값.
- **로그**: 라이브 스트림 및 기록 파일 다운로드, 레벨 및 키워드 필터.
- **시스템 설정**: 포트, 동시성, 타임아웃, 재시도, 속도 제한, VRAM 예약, 결과 유지 기간, 캐시 제한, 알림 등.

## 프로젝트 구조

```
src/                                 # 소프트웨어 코드
├── core/                            # 핵심 계산 엔진
│   ├── config.py                    # 모델 매개변수 설정
│   ├── models.py                    # 5가지 반응-확산 방정식 + 라플라시안
│   ├── simulation.py                # 시뮬레이션 엔진 — 그리드 초기화, 반복, 메모리 관리
│   └── visualization.py             # 시각화 데이터 생성 — Plotly JSON 형식
├── admin/                           # 관리 센터
│   ├── server.py                    # 관리 FastAPI 서비스
│   ├── clients.py                   # 클라이언트 상태와 통계
│   ├── tasks.py                     # 비동기 작업 큐와 스케줄링
│   ├── monitor.py                   # 시스템 리소스 모니터링
│   ├── access_control.py            # 접근 제어
│   ├── notifications.py             # 알림
│   ├── reports.py                   # 보고서 내보내기
│   ├── logger.py                    # 로그 시스템
│   ├── websocket.py                 # WebSocket 푸시
│   ├── static/                      # 관리 정적 파일
│   └── templates/admin.html         # 관리 페이지
├── web/                             # 웹 서비스 계층
│   ├── server.py                    # 메인 FastAPI 서비스 — API + 페이지 라우팅
│   ├── static/
│   │   ├── css/style.css            # 다크 테크 스타일 테마
│   │   ├── fonts/NotoSansCJK-VF.otf.ttc # Noto Sans CJK 가변 폰트
│   │   ├── js/app.js                # 프론트엔드 로직 — Plotly.js 차트 렌더링
│   │   ├── js/i18n.js               # 국제화 번역 모듈
│   │   ├── js/plotly.min.js         # 로컬 Plotly.js 라이브러리
│   │   └── favicon.ico              # 사이트 아이콘
│   └── templates/
│       └── index.html               # 메인 페이지
├── common/                          # 공통 모듈
│   ├── app_context.py               # 공유 런타임 컨텍스트
│   ├── config.py                    # 설정, 버전 및 런타임 경로
│   ├── persistence.py               # JSON 원자적 영속화
│   ├── security.py                  # 출처, 세션 및 접근 키 검증
│   └── startup.py                   # 시작 검사 (포트 점유 + 단일 인스턴스 감지)

run.py                               # 시작 스크립트 (듀얼 서비스)
pattern-generator.spec                # PyInstaller 빌드 설정
requirements.txt                      # 의존성 목록
```

## 토론 및 교류

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;사용 중 문제가 발생하거나, 새로운 기능 요청·개선 제안이 있다면 [GitHub Issues](https://github.com/MqKeYan/pattern-generator/issues)에서 알려주세요. 해결 방법이 있다면 Pull Request를 제출해 프로젝트 개선에 함께해 주시면 매우 감사하겠습니다!

## 행동 강령

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;이 프로젝트는 [**Contributor Covenant Code of Conduct**](../CODE_OF_CONDUCT.md)를 따릅니다. 개방적이고 친근하며 상호 존중하는 커뮤니티 환경 조성을 위해 노력하고 있습니다.

## 라이선스

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;이 프로젝트는 **GPL-3.0 License**로 제공됩니다. 자세한 내용은 [LICENSE](../LICENSE) 파일을 참조하세요.
