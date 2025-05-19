# 자동 매매 프로그램 프로젝트 개요

## 1. 프로젝트 목표

본 프로젝트는 키움증권 OpenAPI를 활용하여 사용자가 설정한 매매 전략에 따라 자동으로 주식 거래를 수행하는 것을 목표로 합니다. 사용자는 설정 파일을 통해 계좌 정보, 매매 전략, 관심 종목 등을 지정할 수 있으며, 프로그램은 이에 따라 시장 상황을 감시하고 주문을 실행합니다. 모든 거래 내역, 매매 결정 근거, 계좌 상태 등은 데이터베이스에 기록되어 추후 분석 및 관리에 활용될 수 있습니다.

## 2. 주요 기능

*   **자동 로그인 및 API 연동:** 키움증권 서버에 자동으로 로그인하고 API와 연동합니다.
*   **설정 관리:** `settings.json` 파일을 통해 프로그램의 주요 설정을 관리하며, 유효성 검사 및 기본값 처리를 수행합니다.
*   **실시간 데이터 수신:** 관심 종목의 실시간 시세 및 체결 정보를 수신합니다.
*   **매매 전략 실행:** 사용자가 설정한 조건에 따라 매수/매도 주문을 자동으로 실행합니다.
*   **데이터 로깅 및 저장:**
    *   프로그램 실행 로그, 오류 로그 등을 파일 및 콘솔에 기록합니다.
    *   거래 내역, 매매 결정 근거, 일별 계좌 스냅샷, OHLCV 데이터 등을 SQLite 데이터베이스에 저장합니다.
*   **화면 번호 관리:** 키움 API의 화면 번호를 효율적으로 관리하여 API 요청 제한을 준수합니다.
*   **안전 종료:** Ctrl+C 입력 시 안전하게 리소스를 해제하고 프로그램을 종료합니다.

## 3. 모듈별 설명 및 의존성

### 3.1. `main.py`

*   **역할:** 프로그램의 메인 진입점. 전체 모듈 초기화, 실행 흐름 제어, 시그널 핸들링 등을 담당합니다.
*   **주요 기능:**
    *   PyQt5 `QApplication` 생성 및 이벤트 루프 실행.
    *   각 모듈(`ConfigManager`, `Logger`, `Database`, `KiwoomAPI`, `TradingStrategy`, `ScreenManager`)의 객체 생성 및 의존성 주입.
    *   키움 OpenAPI 설치 여부 확인.
    *   로그인 처리.
    *   설정 파일에서 관심 종목 로드.
    *   매매 전략 시작.
    *   SIGINT (Ctrl+C) 시그널 핸들러 설정 및 안전 종료 처리.
*   **의존성:** `PyQt5`, `kiwoom_api`, `config`, `strategy`, `logger`, `database`, `util`, `signal`, `logging`, `os`, `sys`, `time`, `functools`, `asyncio`.

### 3.2. `config.py` - `ConfigManager` 클래스

*   **역할:** 프로그램 설정을 관리합니다. `settings.json` 파일과 상호작용합니다.
*   **주요 기능:**
    *   기본 설정값(`DEFAULT_SETTINGS`) 정의.
    *   `settings.json` 파일 로드, 저장, 생성.
    *   설정값 유효성 검사 및 기본값 자동 적용.
    *   다른 모듈에서 설정값을 쉽게 가져오거나 설정할 수 있는 인터페이스 제공 (`get_setting`, `set_setting`).
*   **의존성:** `json`, `os`.

### 3.3. `settings.json`

*   **역할:** 실제 프로그램 실행에 사용되는 사용자 설정값을 JSON 형식으로 저장합니다.
*   **주요 내용:** 계좌 정보, 매수 금액, 매매 전략 (익절/손절률, 시장 시간 등), 관심 종목 목록, 데이터베이스 경로, 로깅 설정, API 제한 설정 등.

### 3.4. `logger.py` - `Logger` 클래스

*   **역할:** 프로그램 전반의 로깅 기능을 제공하는 싱글톤 클래스입니다.
*   **주요 기능:**
    *   콘솔 및 파일(`logs/app.log`) 로깅.
    *   로그 레벨(DEBUG, INFO, WARNING, ERROR, CRITICAL) 설정.
    *   `RotatingFileHandler`를 사용한 로그 파일 관리 (크기 기반 로테이션 및 백업).
    *   표준화된 로그 포맷 적용.
*   **의존성:** `logging`, `os`, `datetime`.

### 3.5. `database.py` - `Database` 클래스

*   **역할:** SQLite 데이터베이스를 사용하여 프로그램의 주요 데이터를 저장하고 관리합니다.
*   **주요 기능 및 테이블:**
    *   `watchlist`: 관심 종목 정보.
    *   `trades`: 실제 거래 내역.
    *   `decisions`: 매매 결정 근거 및 관련 데이터.
    *   `daily_snapshots`: 일별 계좌 상태 스냅샷.
    *   `ohlcv_data`: 주식의 일/주/월봉 OHLCV 데이터.
    *   데이터베이스 초기화, 테이블 생성, 데이터 추가/조회/삭제 기능 제공.
*   **의존성:** `sqlite3`, `json`, `datetime`, `os`.

### 3.6. `kiwoom_api.py` - `KiwoomAPI` 클래스

*   **역할:** 키움증권 OpenAPI와의 모든 통신을 담당합니다. PyQt5의 `QAxWidget`을 사용하여 COM 객체와 상호작용합니다.
*   **주요 기능:**
    *   로그인/로그아웃 처리.
    *   계좌 정보 조회.
    *   TR(Transaction Request) 요청 및 수신 (예: 현재가, 계좌 잔고, 일봉 데이터 조회).
    *   실시간 데이터 구독 및 수신 (시세, 체결 정보 등).
    *   주문 실행 (매수, 매도, 취소).
    *   체결/잔고 데이터(`OnChejanData`) 처리 및 `TradingStrategy`로 전달.
    *   API 관련 오류 처리 및 로깅.
    *   화면 번호 관리 (`ScreenManager` 사용).
*   **의존성:** `PyQt5.QAxContainer`, `PyQt5.QtCore`, `time`, `re`, `logger`, `config`, `strategy`, `util`.

### 3.7. `strategy.py` - `TradingStrategy` 클래스

*   **역할:** 실제 자동 매매 로직을 구현합니다. 시장 상황과 사용자 설정에 따라 매매 결정을 내리고 주문을 요청합니다.
*   **주요 기능:**
    *   관심 종목 관리 (추가, 삭제, 상태 추적 - `StockTrackingData`).
    *   매매 전략 설정 로드 (`StrategySettings`).
    *   계좌 상태 관리 (`AccountState`).
    *   실시간 시세 및 체결 데이터 기반으로 매매 조건 판단.
    *   매수/매도 주문 실행 요청 (`KiwoomAPI` 사용).
    *   손절, 익절, 트레일링 스탑 등 매매 규칙 적용.
    *   일일 매수 횟수 제한.
    *   주기적인 상태 보고 및 일일 계좌 스냅샷 기록.
*   **의존성:** `PyQt5.QtCore`, `time`, `datetime`, `logger`, `config`, `database`, `util`, `enum`, `dataclasses`, `copy`, `re`.

### 3.8. `util.py`

*   **역할:** 프로그램 전반에서 사용되는 유틸리티 함수 및 `ScreenManager` 클래스를 제공합니다.
*   **주요 기능:**
    *   **유틸리티 함수:** 숫자/날짜 포맷팅, 시장 개장 여부 확인, 종목코드 유효성 검사, 손익률 계산 등.
    *   **`ScreenManager` 클래스:**
        *   키움 API 화면 번호 관리 (할당, 해제, 정리).
        *   화면 번호 부족 문제 방지.
        *   `KiwoomAPI`와 연동하여 화면 연결 해제.
*   **의존성:** `re`, `pandas`, `datetime`, `threading`, `logging`, `typing`.

## 4. 주요 데이터 흐름 및 상호작용

1.  **프로그램 시작 (`main.py`):**
    *   각 모듈 초기화 (Config → Logger → DB → ScreenManager → Strategy → KiwoomAPI).
    *   설정 로드 (`ConfigManager` → `settings.json`).
    *   로그인 (`KiwoomAPI`).
2.  **데이터 로딩 (`KiwoomAPI` → `TradingStrategy`):**
    *   로그인 성공 후, `KiwoomAPI`는 계좌 정보, 예수금, 포트폴리오 정보 등을 조회하여 `TradingStrategy`에 전달.
    *   `TradingStrategy`는 이 정보를 바탕으로 초기화.
3.  **관심 종목 및 전략 시작 (`main.py` → `TradingStrategy` → `KiwoomAPI`):**
    *   `main.py`는 `settings.json`에서 관심 종목을 읽어 `TradingStrategy`에 추가.
    *   `TradingStrategy.start()` 호출:
        *   관심 종목에 대한 실시간 시세 구독 요청 (`KiwoomAPI.set_real_reg`).
        *   매매 조건 판단 타이머 시작.
4.  **실시간 데이터 처리 (`KiwoomAPI` → `TradingStrategy`):**
    *   `KiwoomAPI`는 실시간 시세(`OnReceiveRealData`) 및 체결/잔고 데이터(`OnReceiveChejanData`)를 수신.
    *   수신된 데이터를 파싱하여 `TradingStrategy`의 해당 콜백 함수 호출.
5.  **매매 조건 판단 및 주문 (`TradingStrategy` → `KiwoomAPI`):**
    *   `TradingStrategy`는 수신된 데이터와 설정된 전략에 따라 매수/매도 조건 판단.
    *   조건 충족 시, `KiwoomAPI.send_order()`를 호출하여 주문 실행.
6.  **주문 결과 처리 (`KiwoomAPI` → `TradingStrategy` → `Database`):**
    *   `KiwoomAPI`는 주문 접수 및 체결 결과를 `OnChejanData`를 통해 수신.
    *   `TradingStrategy`는 이 결과를 바탕으로 포트폴리오 업데이트, 전략 상태 변경, `Database`에 거래 내역 기록.
7.  **로깅 및 DB 기록 (모든 모듈 → `Logger`, `Database`):**
    *   프로그램 실행 중 발생하는 주요 이벤트, 오류, 상태 변경 등은 `Logger`를 통해 기록.
    *   거래 내역, 매매 결정, 스냅샷 등은 `Database`에 저장.
8.  **프로그램 종료 (사용자 Ctrl+C → `main.py` 시그널 핸들러):**
    *   `TradingStrategy` 중지 (신규 주문 방지, 미체결 주문 취소).
    *   `KiwoomAPI` 연결 해제 (실시간 데이터 구독 해제, 화면 정리, API 종료).
    *   `Database` 연결 종료.
    *   `QApplication` 종료.

## 5. 주요 클래스 및 데이터 구조

*   **`ConfigManager`:** 설정을 담는 `self.settings` (dict).
*   **`Logger`:** `logging.Logger` 객체 활용.
*   **`Database`:** `sqlite3.Connection` 객체 활용.
*   **`KiwoomAPI`:** `QAxWidget` (COM 객체) 과의 상호작용. TR 데이터 캐싱(`self.tr_data_cache`).
*   **`TradingStrategy`:**
    *   `AccountState` (dataclass): 계좌번호, 포트폴리오, 미체결 주문, 계좌 요약.
    *   `StrategySettings` (dataclass): 각종 매매 전략 파라미터.
    *   `StockTrackingData` (dataclass): 관심 종목별 추적 데이터 (현재가, 상태, 매수/매도 관련 정보).
    *   `watchlist` (dict): `{stock_code: StockTrackingData}`.
*   **`ScreenManager`:** `available_screens` (list), `screen_map` (dict), `used_screens` (dict)를 사용하여 화면 번호 관리.

## 6. 초기 오류 해결 (`TypeError` in `on_chejan_data_received`)

*   **문제 원인:** `kiwoom_api.py`의 `on_receive_chejan_data` 메서드에서 `strategy.py`의 `on_chejan_data_received` 메서드를 호출할 때, `strategy.py`에서 정의한 세 개의 인자(`gubun`, `item_cnt`, `fid_list_str`) 대신 두 개의 인자(`gubun`, `current_chejan_data`)를 전달하여 발생했습니다.
*   **해결:** `kiwoom_api.py`의 해당 호출 부분을 `self.strategy_instance.on_chejan_data_received(gubun, item_cnt, fid_list_str)`로 수정하여 올바른 인자를 전달하도록 변경했습니다.

## 7. 향후 개선 방향 (제안)

*   **GUI 구현:** 현재 콘솔 기반 프로그램에 PyQt5 등을 활용한 GUI를 추가하여 사용자 편의성 증대.
*   **다양한 매매 전략 지원:** 사용자가 직접 전략을 쉽게 추가하거나 수정할 수 있는 플러그인 형태의 구조 고려.
*   **백테스팅 기능:** 과거 데이터를 사용하여 매매 전략의 성과를 검증할 수 있는 기능 추가.
*   **상세한 오류 처리 및 알림:** 예외 상황 발생 시 사용자에게 보다 명확한 알림 (예: 시스템 트레이 알림, 이메일 알림) 제공.
*   **성능 최적화:** 대량의 데이터 처리 또는 다수 종목 동시 거래 시 성능 최적화.
*   **보안 강화:** 계좌 비밀번호 등 민감 정보 암호화 저장.

이 문서는 프로젝트의 현재 상태를 기준으로 작성되었으며, 지속적인 개발 및 유지보수를 통해 기능이 변경되거나 추가될 수 있습니다.
