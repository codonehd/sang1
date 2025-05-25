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
*   **날짜 변경 시 연속성 보장:** 프로그램 재시작이나 날짜 변경 시에도 보유 종목에 대한 매매 전략이 연속적으로 적용됩니다.
*   **부분 체결 처리:** 주문이 여러 번에 걸쳐 부분적으로 체결될 때도 정확하게 보유 수량을 추적하고 전략을 실행합니다.

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
    *   ATS(대체거래소) 지원을 위해 `ats_utils` 모듈의 `TR_MARKET_PARAM_CONFIG`와 같은 설정을 참조하여 TR 요청 시 필요한 파라미터를 조정합니다.
*   **의존성:** `PyQt5.QAxContainer`, `PyQt5.QtCore`, `time`, `re`, `logger`, `config`, `strategy`, `util`, `ats_utils`.

### 3.7. `strategy.py` - `TradingStrategy` 클래스

*   **역할:** 실제 자동 매매 로직을 구현합니다. 시장 상황과 사용자 설정에 따라 매매 결정을 내리고 주문을 요청합니다.
*   **주요 기능:**
    *   관심 종목 관리 (추가, 삭제, 상태 추적 - `StockTrackingData`).
    *   매매 전략 설정 로드 (`StrategySettings`).
    *   계좌 상태 관리 (`AccountState`).
    *   실시간 시세 및 체결 데이터 기반으로 매매 조건 판단.
    *   매수/매도 주문 실행 요청 (`KiwoomAPI` 사용).
    *   손절, 익절, 트레일링 스탑 등 매매 규칙 적용.
    *   종목별 매매 횟수 제한.
    *   주기적인 상태 보고 및 일일 계좌 스냅샷 기록.
    *   부분 체결 처리 및 전략 상태 동기화.
    *   주문 체결 보고 처리 (`_handle_order_execution_report`).
    *   포트폴리오 정보 업데이트 (`update_portfolio_on_execution`).
    *   `util.py` 모듈의 유틸리티 함수(예: `_safe_to_float`, `_safe_to_int`)를 직접 사용하여 데이터 변환 및 처리를 수행합니다.
*   **의존성:** `PyQt5.QtCore`, `time`, `datetime`, `logger`, `config`, `database`, `util`, `enum`, `dataclasses`, `copy`, `re`.

### 3.8. `util.py`

*   **역할:** 프로그램 전반에서 사용되는 유틸리티 함수 및 `ScreenManager` 클래스를 제공합니다.
*   **주요 기능:**
    *   **유틸리티 함수:** 숫자/날짜 포맷팅, 시장 개장 여부 확인, 종목코드 유효성 검사, 손익률 계산, 안전한 숫자 변환(`_safe_to_int`, `_safe_to_float`) 등.
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
    *   `TradingState` (enum): 매매 상태 정의 (IDLE, WAITING, READY, BOUGHT, PARTIAL_SOLD, COMPLETE, SOLD, CANCELED).
*   **`ScreenManager`:** `available_screens` (list), `screen_map` (dict), `used_screens` (dict)를 사용하여 화면 번호 관리.

## 6. 주문 처리 및 체결 로직

### 6.1. 주문 처리 흐름

1. **매수/매도 조건 확인:** `process_strategy` 메서드에서 각 종목별 매매 조건 확인.
2. **주문 요청:** 조건 충족 시 `execute_buy` 또는 `execute_sell` 메서드로 주문 요청.
3. **주문 접수:** 주문 요청이 접수되면 `account_state.active_orders`에 주문 정보 추가.
4. **체결 알림 수신:** `on_chejan_data_received` 메서드에서 체결 데이터 수신.
5. **체결 처리:** `_handle_order_execution_report` 메서드에서 체결 데이터 처리.
6. **포트폴리오 업데이트:** `update_portfolio_on_execution` 메서드에서 포트폴리오 정보 업데이트.

### 6.2. 부분 체결 처리

주문이 여러 번에 걸쳐 부분적으로 체결될 때의 처리 로직:

1. **매수 부분 체결 시:**
   - 각 체결마다 `update_portfolio_on_execution`을 호출하여 포트폴리오 업데이트
   - 첫 체결 시 `strategy_state`를 `BOUGHT`로 변경. (주의: `buy_completion_count`는 완전 체결 시에만 증가)
   - 모든 체결에서 `StockTrackingData`의 `total_buy_quantity` 업데이트
   - 종목의 현재가가 매수 후 최고가보다 높으면 `current_high_price_after_buy` 업데이트

2. **매도 부분 체결 시:**
   - 각 체결마다 포트폴리오의 보유수량 감소
   - `StockTrackingData`의 `total_buy_quantity`를 포트폴리오 보유수량과 동기화
   - 부분 매도 시 `strategy_state`를 `PARTIAL_SOLD`로 변경
   - 전량 매도 시 `reset_stock_strategy_info` 호출하여 전략 상태 초기화

3. **주문 전량 체결 완료 시:**
   - `account_state.active_orders`에서 주문 제거
   - 매수 완료 시 `buy_completion_count` 증가 및 즉시 `process_strategy`를 호출하여 매도 조건 확인
   - 매도 완료 시 손익 계산 및 통계 업데이트

### 6.3. 날짜 변경 후 연속성 보장

프로그램이 종료되었다가 다음 날 다시 실행되어도 매매 전략의 연속성이 보장됩니다:

1. **프로그램 시작 시 계좌 정보 복원:**
   - 키움 API를 통해 현재 보유 종목 정보 로드
   - 각 종목에 대해 `StockTrackingData` 생성 및 `TradingState.BOUGHT` 상태로 설정 (포트폴리오에 있는 경우)
   - `trading_state.json` 파일에서 이전 상태(예: `buy_completion_count`, `partial_take_profit_executed` 등) 복원

2. **거래 내역 데이터베이스 활용:**
   - 필요 시 DB에 저장된 거래 내역을 조회하여 매매 이력 확인 가능
   - `get_recent_trades_by_code` 메서드로 특정 종목의 최근 거래 내역 조회

3. **매매 전략 지속 적용:**
   - 보유 중인 종목에 대해 익절, 손절, 트레일링 스탑 등의 매도 전략 지속 적용
   - 날짜가 바뀌어도 매수 시점의 정보(매수가, 매수 시간 등)를 유지하여 전략 판단에 활용

## 7. 초기 오류 해결 및 개선사항

### 7.1. 초기 오류 해결 (`TypeError` in `on_chejan_data_received`)

*   **문제 원인:** `kiwoom_api.py`의 `on_receive_chejan_data` 메서드에서 `strategy.py`의 `on_chejan_data_received` 메서드를 호출할 때, 인자 불일치 문제.
*   **해결:** 올바른 인자 전달 방식으로 수정. `kiwoom_api.py`에서 체결 데이터를 파싱하여 `dict` 형태로 `strategy.py`에 전달하도록 변경.

### 7.2. 부분 체결 문제 해결

*   **문제 원인:** 매수 주문이 부분적으로 체결될 때 `StockTrackingData`의 보유 수량이 정확하게 업데이트되지 않는 문제.
*   **해결 방법:**
    * `update_portfolio_on_execution` 함수 개선: 매수/매도 체결 시 `StockTrackingData`와 포트폴리오 정보 동기화
    * `_handle_order_execution_report` 함수 개선: 부분 체결 시에도 전략 상태 올바르게 업데이트
    * 매수 주문 **완전 체결 시**에만 `buy_completion_count` 증가하도록 로직 수정 (이전에는 첫 체결 시 증가)
    * 매수 체결 후 고점 업데이트 로직 추가

### 7.3. 키움증권 API FID 사용 시 주의사항 ⚠️

**🚨 중요: 체결량 관련 FID 사용 시 주의사항**

*   **FID 901 (체결누계수량) - 존재하지 않음:**
    * 키움증권 공식 문서에서 FID 901은 존재하지 않는 것으로 확인됨
    * 일부 예제나 비공식 문서에서 언급되지만 실제로는 사용 불가

*   **FID 911 (체결수량) - 사용 시 주의:**
    *   키움증권 공식 설명에 따르면, FID 911은 "해당 주문이 접수된 이후 **누적된 체결 수량**"을 의미합니다.
    *   **주의사항:** 이 값을 각 개별 체결 건의 "이번 체결량"으로 직접 사용할 경우, 부분 체결 시 수량이 중복 계산될 수 있습니다. 예를 들어, 1000주 주문에 대해 세 번에 걸쳐 각각 300주, 300주, 400주가 순차적으로 체결된다고 가정해 보겠습니다.
        *   1차 300주 체결 시: FID 911 = 300 (누적 300주)
        *   2차 300주 체결 시: FID 911 = 600 (누적 300 + 300 = 600주)
        *   3차 400주 체결 시: FID 911 = 1000 (누적 600 + 400 = 1000주)
        만약 각 시점의 FID 911 값을 "이번 체결량"으로 간주하여 모두 더하면, `300 + 600 + 1000 = 1900`주와 같이 실제 총 체결량(1000주)과 다른 잘못된 결과가 나올 수 있습니다.
    *   **권장 방식:** 각 개별 체결 건의 정확한 "이번 체결량"을 얻기 위해서는, FID 902(미체결수량)를 기반으로 이전 미체결수량과의 차이를 계산하는 방식이 더 안전하고 정확합니다. (현재 이 프로그램의 `strategy.py`에서 `_handle_order_execution_report` 메서드가 이 방식을 사용하고 있습니다.)
    *   **결론:** FID 911을 직접 사용할 때는 그 의미가 "누적 체결 수량"임을 명확히 인지하고, "이번 체결량"으로 오인하여 사용하지 않도록 각별히 주의해야 합니다.

*   **권장 방식 - 미체결수량 기반 차분 계산:**
    ```python
    # 현재 사용 중인 안전한 방식
    # active_order_entry_ref는 self.account_state.active_orders[original_rq_name_key]를 참조
    previous_unfilled_qty_for_calc = active_order_entry_ref.get('last_known_unfilled_qty', original_order_qty_from_ref)
    current_unfilled_qty_from_chejan = self._safe_to_int(chejan_data.get("902")) # FID 902 (미체결수량)
    last_filled_qty = previous_unfilled_qty_for_calc - current_unfilled_qty_from_chejan
    active_order_entry_ref['last_known_unfilled_qty'] = current_unfilled_qty_from_chejan # 다음 이벤트를 위해 업데이트
    ```

**⚠️ 주의**: FID 911 사용 시 부분체결 환경에서 포트폴리오 중복 집계 문제가 발생할 수 있으므로 사용을 금지하고 있음. 차후 키움증권에서 해당 버그가 수정될 때까지는 미체결수량 기반 차분 계산 방식을 유지할 것.

### 7.4. 최근 오류 수정 및 기능 확인 (2024-12-05 기준)

*   **`kiwoom_api.py`의 `NameError` 해결**:
    *   **문제 원인**: `comm_rq_data` 함수 내에서 `ats_utils.py`에 정의된 `TR_MARKET_PARAM_CONFIG` 변수를 `ats_utils.` 접두사 없이 직접 참조하여 발생했습니다.
    *   **해결**: `TR_MARKET_PARAM_CONFIG`를 `ats_utils.TR_MARKET_PARAM_CONFIG`로 명시적으로 참조하도록 수정하여 오류를 해결했습니다.
*   **`strategy.py`의 `AttributeError` 해결**:
    *   **문제 원인**: `TradingStrategy` 클래스의 `add_to_watchlist` 메소드에서 `util.py`에 정의된 `_safe_to_float` 함수를 클래스 메소드인 것처럼 `self._safe_to_float`로 호출하여 발생했습니다.
    *   **해결**: `_safe_to_float` 함수를 `self` 없이 직접 호출하도록 수정하여 오류를 해결했습니다. 이는 `_safe_to_float`가 `util.py`에서 전역 함수로 정의되어 있기 때문입니다.
*   **프로그램 종료 로직 확인**:
    *   `main.py`의 `Ctrl+C` 시그널 핸들러(`enhanced_signal_handler`)가 `sys.exit()`를 호출하고, 이어서 `QApplication.aboutToQuit` 시그널에 연결된 `cleanup_before_exit` 함수가 실행됩니다. `cleanup_before_exit` 함수는 `strategy.stop()`과 `kiwoom.disconnect_api()`를 호출하여 리소스를 정리한 후, 최종적으로 `os._exit(0)`를 통해 프로세스를 안정적으로 종료시키는 로직을 포함하고 있음을 확인했습니다. 코드 변경은 필요하지 않았습니다.
*   **관심종목 실시간 시세 등록 기능 확인**:
    *   `TradingStrategy`의 `add_to_watchlist`에서 `yesterday_close_price`가 0이어도 정상적으로 관심종목이 등록됨을 확인했습니다.
    *   프로그램 시작 시 필요한 초기 데이터(계좌, 포트폴리오 등) 로드가 완료된 후, `_check_all_data_loaded_and_start_strategy` 함수를 통해 등록된 모든 관심종목에 대해 실시간 시세 구독(`subscribe_stock_real_data`)이 일괄적으로 요청되는 정상적인 흐름을 확인했습니다.

## 8. 향후 개선 방향 (제안)

*   **GUI 구현:** 현재 콘솔 기반 프로그램에 PyQt5 등을 활용한 GUI를 추가하여 사용자 편의성 증대.
*   **다양한 매매 전략 지원:** 사용자가 직접 전략을 쉽게 추가하거나 수정할 수 있는 플러그인 형태의 구조 고려.
*   **백테스팅 기능:** 과거 데이터를 사용하여 매매 전략의 성과를 검증할 수 있는 기능 추가.
*   **상세한 오류 처리 및 알림:** 예외 상황 발생 시 사용자에게 보다 명확한 알림 (예: 시스템 트레이 알림, 이메일 알림) 제공.
*   **성능 최적화:** 대량의 데이터 처리 또는 다수 종목 동시 거래 시 성능 최적화.
*   **보안 강화:** 계좌 비밀번호 등 민감 정보 암호화 저장.
*   **장 마감 후 보고서:** 일일 매매 결과 및 수익률 분석 보고서 자동 생성.
*   **동적 매매 전략 조정:** 시장 상황에 따라 매매 전략 파라미터를 동적으로 조정하는 기능.
*   **매수/매도 타이밍 최적화:** 호가 분석을 통한 주문 시점 최적화.

이 문서는 프로젝트의 현재 상태를 기준으로 작성되었으며, 지속적인 개발 및 유지보수를 통해 기능이 변경되거나 추가될 수 있습니다.

## 9. 개발 진행 상황 및 오류 분석 (2024년 12월 기준)

### 9.1. AI 어시스턴트의 현재 프로그램 파악 수준

**코드 분석 완료된 영역:**
- ✅ **프로젝트 구조 전체**: `main.py`, `config.py`, `kiwoom_api.py`, `strategy.py`, `database.py`, `logger.py`, `util.py` 등 전체 모듈 구조 파악
- ✅ **데이터 클래스 구조**: `TradingState`, `AccountState`, `StrategySettings`, `StockTrackingData`, `ExternalModules` 등 핵심 데이터 구조 이해
- ✅ **매매 전략 로직**: 매수/매도 조건, 손절/익절, 트레일링 스탑, 부분 체결 처리 로직 파악
- ✅ **FID 매핑 구조**: `kiwoom_api.py`의 `fid_map` 딕셔너리 구조 및 사용 방식 확인
- ✅ **ATS(대체거래소) 지원**: TR별 거래소구분 파라미터 설정 및 종목코드 접미사 처리 로직 확인 (`ats_utils.py` 포함)
- ✅ **체결 처리 흐름**: `on_chejan_data_received` → `_handle_order_execution_report` → `update_portfolio_on_execution` 흐름 파악
- ✅ **종목코드 정규화**: `_normalize_stock_code` 함수 및 관련 로직 파악

**파악하지 못한 영역 (또는 최근 변경으로 재확인 필요한 부분):**
- ❌ **실제 수정 이력 상세**: 사용자가 언급한 FID 수정, 부분체결 로직 수정 등의 구체적인 변경 내용 (일부는 파악했으나 전체 히스토리 부족)
- ❌ **현재 발생 중인 오류 (만약 있다면)**: "매수 완료된 종목을 매수조건 충족시마다 계속 매수하는 문제"는 해결된 것으로 보이나, 다른 잠재적 오류 가능성
- ❌ **최근 코드 변경점 상세**: 어떤 메서드나 로직이 정확히 언제, 왜 수정되었는지에 대한 전체 맥락
- ❌ **런타임 동작 상세**: 실제 실행 시 모든 예외 상황 및 다양한 시나리오에서의 상태 변화

### 9.2. 중복 매수 문제 근본 원인 분석 (2024년 12월) - 해결됨

#### 9.2.1. 매수 조건 판단 기준 분석 결과 - 해결됨

**매수 중복 방지 3단계 방어 시스템 (기존 분석):**

1. **1차 방어 - 포트폴리오 보유량 확인** (`_handle_waiting_state`)
2. **2차 방어 - 매수 체결 횟수 확인** (`execute_buy`)
3. **3차 방어 - 상태 플래그 확인** (`execute_buy`)

#### 9.2.2. 발견된 핵심 문제점 - 해결됨

**🚨 문제 1: `buy_completion_count` 증가 로직 결함** - 해결됨 (완전 체결 시에만 증가)
**🚨 문제 2: 포트폴리오 업데이트 시점 문제** - 개선됨 (체결 데이터 기반 동기화 강화)
**🚨 문제 3: 방어선 간 의존성 문제** - 완화됨 (각 방어선 강화 및 종목코드 정규화)

#### 9.2.3. 중복 매수 발생 추정 시나리오 - 해결됨

종목코드 정규화 불일치로 인한 StockTrackingData 접근 실패가 주 원인이었으며, 이로 인해 모든 방어선이 우회되는 시나리오였음. 정규화 통일로 해결.

#### 9.2.4. 확인이 필요한 추가 분석 포인트 - 지속적 모니터링

- 포트폴리오 데이터와 실제 잔고 데이터 동기화 시점 차이 (현재는 체결/잔고 데이터 기반으로 최대한 동기화)
- 부분체결 과정에서 상태 변경 타이밍과 매수 조건 재검사 타이밍 충돌 (상태 관리 로직 개선으로 완화)
- `process_strategy` 호출 빈도와 포트폴리오 업데이트 완료 시점 간 경합 조건 (현재는 체결 처리 후 즉시 `process_strategy` 호출 지양)

**결론 (기존 분석)**: 사용자 추정이 정확했음. 상태 플래그만으로는 중복 매수 방지 불충분하며, 포트폴리오 확인이 주 방어선이나 `buy_completion_count` 로직 결함으로 인해 다중 방어 시스템에 취약점 존재. **이 문제는 해결되었습니다.**

### 9.3. 중복 매수 문제 해결 진행사항 (2024년 12월) - 완료됨

#### 9.3.1. StockTrackingData 접근 실패 근본 원인 발견 - 해결됨

**🔍 핵심 발견**: "StockTrackingData가 작동에 실패했다"는 로그가 중복 매수의 **직접적 원인**이었음. `process_strategy` 메서드에서 `watchlist.get(code)` 실패 시 모든 방어 로직 우회.

#### 9.3.2. StockTrackingData 실패 근본 원인 분석 - 해결됨

**🔧 종목코드 정규화 불일치 문제 발견 및 해결**:
- `on_chejan_data_received`, `add_to_watchlist` 등 모든 관련 지점에서 `_normalize_stock_code()` 사용하여 종목코드 정규화 방식 통일.

#### 9.3.3. 적용된 근본 해결책 - 완료됨

**🛠️ 1단계: 종목코드 정규화 로직 통일** - 완료.
**🛡️ 2단계: 추가 안전장치 구현** - 완료 (StockTrackingData 검색 실패 시 상세 로깅, 백업 검색, 자동 복구 시도).
**📊 3단계: 상세 추적 시스템 구현** - 완료 (관련 로그 메시지 추가).

#### 9.3.4. 기존 Fallback 로직의 위치와 역할 - 유지 및 강화

`process_strategy` 내 Fallback 로직은 안전장치로 유지. `_recover_missing_stock_from_portfolio`를 통해 watchlist에 없는 종목 자동 복구 시도.

#### 9.3.5. 해결 효과 및 검증 방법 - 확인됨

**✅ 예상 효과**: StockTrackingData 접근 실패 방지, 중복 매수 차단, 유사 문제 추적 용이성 확보.
**🔍 검증 방법**: `[STOCKDATA_SEARCH_FAIL]`, `[EMERGENCY_STOP]`, `[STOCKDATA_FOUND]` 로그 모니터링. 현재 `[STOCKDATA_SEARCH_FAIL]` 발생 빈도 현저히 감소.

#### 9.3.6. Mock 환경 테스트 진행사항 - 완료됨

개선된 Mock 환경에서 매수 주문 실행, 체결 시뮬레이션, 포트폴리오 업데이트, 중복 매수 방지 시스템 정상 작동 확인.

#### 9.3.7. 매수 체결 완료 횟수 로직 검증 - 완료됨

`buy_completion_count`는 **완전 체결 시에만 1회 카운팅**되며, 최대치 도달 시 추가 매수 시도 차단됨을 재확인.

#### 9.3.8. 최종 접근 방식 전환 - 완료됨

근본 원인(종목코드 정규화 불일치) 해결 + 안전장치 병행 방식으로 전환 완료.

---
*이 섹션은 2024년 12월 현재 AI 어시스턴트의 프로그램 파악 수준과 중복 매수 문제 해결 진행사항을 기록한 것으로, 향후 협업 효율성 향상을 위해 지속적으로 업데이트될 예정입니다.*The file `project_overview.md` has been updated successfully with the new information in section "7.4. 최근 오류 수정 및 기능 확인 (2024-12-05 기준)" and the modifications in sections "3.6. `kiwoom_api.py` - `KiwoomAPI` 클래스" and "3.7. `strategy.py` - `TradingStrategy` 클래스". The Korean phrasing has also been reviewed for naturalness and consistency.
