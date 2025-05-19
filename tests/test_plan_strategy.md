# TradingStrategy 테스트 계획 (`test_strategy.py` 재사용 기반)

## 1. 기존 `test_strategy.py` 재사용으로 확인 가능한 시나리오 (수정 후)

### 1.1. `TradingStrategy` 핵심 메서드 단위 테스트
- **대상:** `initialize_stock_data`, `remove_from_watchlist`, `on_actual_real_data_received`, `on_chejan_data_received` 등 주요 메서드.
- **목표:** 각 메서드의 기본 기능, 상태 변경, 데이터 업데이트 로직을 현재 코드 구조에 맞게 수정하여 검증.
- **수정 사항:**
    - `QApplication` 의존성 제거.
    - `TradingStrategy` 초기화 시 `ExternalModules` (config_manager, logger, db_manager, kiwoom_api) 주입 방식 반영.
    - `watchlist` 접근 시 `StockTrackingData` 객체 직접 사용 반영 (예: `self.strategy.watchlist[code].current_price`).
    - Enum 상태 값(`TradingState`) 직접 비교.
    - `MockKiwoomAPI` 시그널 방식을 콜백 또는 직접적인 메서드 호출 결과 반환으로 변경 (필요시).

### 1.2. 모의 객체(`MockKiwoomAPI`, `MockConfigManager`, `MockDB`) 활용
- **`MockKiwoomAPI`:**
    - TR 요청 (`get_stock_basic_info`, `get_daily_chart`, `send_order`, `comm_rq_data` 등)에 대한 모의 응답 생성 기능 유지 및 개선.
    - 실시간 데이터 (`real_data_updated` 시그널) 및 체결 데이터 (`chejan_data_received` 시그널) 발생 로직을 콜백 호출 또는 테스트 코드에서의 직접 주입 방식으로 변경.
- **`MockConfigManager`:**
    - 테스트용 설정값(`매수금액`, `익절_수익률` 등) 제공 기능 유지.
- **`MockDB` (또는 `MockDatabaseManager`):**
    - 거래 내역 저장/조회, 관심종목 저장/조회 등 DB 상호작용 모의 기능 유지 및 현재 `DatabaseManager` 인터페이스와 일치.

## 2. 추가 및 구현이 필요한 시나리오 (매수/매도 로직 우선 점검)

### 2.1. `StockTrackingData` 및 `StrategySettings` 기반 로직 검증
- **목표:** `TradingStrategy`의 주요 로직들이 `StockTrackingData` 인스턴스의 필드와 `StrategySettings` 인스턴스의 설정값을 올바르게 참조하여 동작하는지 집중 검증.
- **테스트 케이스 예시:**
    - `initialize_stock_data` 후 `StockTrackingData` 필드 (초기 가격 정보, 상태 등) 정확성 검증.
    - 실시간 데이터 수신(`on_actual_real_data_received`) 후 `StockTrackingData`의 `current_price`, `daily_high_price` 등 업데이트 검증.

### 2.2. 매수 조건 판단 및 주문 실행 검증
- **`check_initial_conditions`:**
    - `StockTrackingData`의 초기 가격 정보(`is_gap_up_today`, `yesterday_close_price`, `today_open_price` 등)를 바탕으로 정확한 초기 `strategy_state` (예: `TradingState.READY_FOR_BUY_CONDITION` 또는 `TradingState.OBSERVING_GAP_CLOSURE`) 설정 여부 검증.
- **`_handle_waiting_state`:** (또는 이와 유사한 매수 조건 판단 로직)
    - 설정된 매수 조건 (`settings.buy_condition_logic` 등)에 따라 `StockTrackingData`의 실시간 가격 정보를 사용하여 매수 시점을 정확히 포착하는지 검증.
    - 매수 조건 만족 시 `execute_buy` 호출로 이어지는지 확인.
- **`execute_buy`:**
    - `AccountState.available_buy_power`, `StrategySettings.order_total_amount_limit` 등을 참조하여 주문 가능 금액 및 수량 계산 정확성 검증.
    - `MockKiwoomAPI.send_order` 호출 시 파라미터(종목코드, 주문유형, 수량, 가격, 호가구분) 정확성 검증.
    - 주문 후 `StockTrackingData` 또는 `AccountState.active_orders`에 주문 정보 기록 및 상태 변경(예: `TradingState.ORDER_SENT_BUY`) 정확성 검증.

### 2.3. 매도 조건 판단 및 주문 실행 검증
- **`_handle_holding_state`:** (또는 이와 유사한 매도 조건 판단 로직)
    - **손절:** `StrategySettings.stop_loss_rate`, `StockTrackingData.avg_buy_price`를 기준으로 손절 조건 판단 및 `execute_sell` 호출 검증.
    - **익절:** `StrategySettings.profit_taking_rate`, `StockTrackingData.avg_buy_price`를 기준으로 익절 조건 판단 및 `execute_sell` 호출 검증. `StrategySettings.profit_taking_sell_ratio`에 따른 매도 수량 계산 검증.
    - **트레일링 스탑:** `StrategySettings.trailing_stop_activation_rate`, `StrategySettings.trailing_stop_drawdown_rate`, `StockTrackingData.current_high_price_after_buy`를 기준으로 트레일링 스탑 조건 판단 및 `execute_sell` 호출 검증.
- **`execute_sell`:**
    - `StockTrackingData.current_quantity` (보유수량), 매도 비율 등을 고려한 주문 수량 계산 정확성 검증.
    - `MockKiwoomAPI.send_order` 호출 시 파라미터 정확성 검증.
    - 주문 후 `StockTrackingData` 또는 `AccountState.active_orders`에 주문 정보 기록 및 상태 변경(예: `TradingState.ORDER_SENT_SELL`) 정확성 검증.

### 2.4. 체결 데이터 처리 및 상태 업데이트 검증
- **`on_chejan_data_received` (및 하위 헬퍼: `_handle_order_execution_report`, `_handle_balance_update_report`):**
    - **매수 체결:**
        - `MockKiwoomAPI`가 모의 매수 체결 데이터를 제공했을 때, `active_orders`에서 해당 주문 제거.
        - `StockTrackingData`의 `avg_buy_price`, `current_quantity`, `strategy_state` (예: `TradingState.BOUGHT`) 업데이트 정확성 검증.
        - `AccountState.portfolio`에 해당 종목 편입 및 정보 (매입가, 수량 등) 업데이트 정확성 검증.
        - `AccountState.available_buy_power` 업데이트 (수수료/세금 고려).
        - `DatabaseManager.add_trade` 호출 검증.
    - **매도 체결:**
        - `MockKiwoomAPI`가 모의 매도 체결 데이터를 제공했을 때, `active_orders`에서 해당 주문 제거.
        - `StockTrackingData`의 `current_quantity`, `strategy_state` (예: `TradingState.PARTIAL_SOLD` 또는 `TradingState.COMPLETE` 또는 `TradingState.IDLE`) 업데이트 정확성 검증.
        - `AccountState.portfolio`에서 해당 종목 정보 (수량, 평단가 등) 업데이트 또는 제거 정확성 검증.
        - `AccountState.available_buy_power` 업데이트 (수수료/세금 고려).
        - `DatabaseManager.add_trade` 호출 검증.
    - **주문 실패/거부:**
        - `MockKiwoomAPI`가 모의 주문 실패/거부 데이터를 제공했을 때, `active_orders`에서 해당 주문 제거.
        - `StockTrackingData`의 `strategy_state`를 이전 상태(예: `TradingState.READY_FOR_BUY_CONDITION`)로 복귀시키거나 적절한 오류 상태로 변경하는지 검증.
        - 관련 오류 로깅 검증.

## 3. 과거 문제점 점검을 위한 특화 테스트 시나리오

### 3.1. 계좌 정보 로드 실패 시나리오
- **테스트 목표:** `KiwoomAPI` 로그인 후 또는 TR 요청 시 계좌 정보를 정상적으로 가져오지 못하는 상황을 모의하여, 프로그램의 방어 로직 및 오류 처리 능력 검증.
- **`MockKiwoomAPI` 설정:**
    - `get_login_info("ACCNO")` 호출 시 빈 문자열 또는 잘못된 형식의 계좌번호 반환.
    - `opw00001` (예수금) 또는 `opw00018` (계좌평가잔고) TR 요청에 대해 빈 데이터, 오류 코드, 또는 필수 필드가 누락된 데이터 반환.
- **검증 항목:**
    - `TradingStrategy._on_login_completed` 또는 계좌 정보 요청 메서드에서 계좌번호 부재/오류를 인지하고 적절한 로그(WARNING/ERROR)를 남기는지 확인.
    - `AccountState.account_number`가 설정되지 않거나, `AccountState.deposit` 등의 정보가 유효하지 않을 때, 매수/매도 주문 로직(`execute_buy`, `execute_sell`)이 실행되지 않고 안전하게 중단되는지 확인 (예: 주문 시도 전 계좌 정보 유효성 검사).
    - 프로그램이 비정상 종료되지 않고, 사용자(또는 시스템)에게 계좌 정보 문제를 알릴 수 있는 메커니즘(현재는 로깅)이 동작하는지 확인.

### 3.2. 관심종목 일봉 데이터 로드 실패 시나리오
- **테스트 목표:** `initialize_stock_data` 과정에서 특정 종목의 일봉 데이터를 가져오지 못하는 상황을 모의하여, 해당 종목에 대한 처리 및 전체 프로그램 안정성 검증.
- **`MockKiwoomAPI` 설정:**
    - 특정 종목 코드에 대한 `opt10081` (일봉) TR 요청 시 빈 데이터 리스트, 오류 코드, 또는 필수 가격 필드(`종가`, `시가` 등)가 누락/손상된 데이터 반환.
- **검증 항목:**
    - `TradingStrategy.initialize_stock_data` 또는 `on_tr_data_received` (opt10081 처리 부분)에서 일봉 데이터 로드 실패를 인지하는지 확인.
    - 해당 `StockTrackingData` 객체에 오류 상태(예: `daily_chart_error = True`)가 기록되고, 필수 가격 정보(`yesterday_close_price`, `today_open_price` 등)가 유효하지 않은 값으로 남지 않는지 확인.
    - 해당 종목에 대해 매수/매도 조건 검사(`check_initial_conditions`, `process_strategy` 등)가 진행되지 않거나, 적절히 건너뛰는지 확인.
    - 다른 정상적인 종목들의 데이터 처리 및 매매 로직에는 영향을 주지 않는지 확인.
    - 관련 오류 로깅 확인.

## 4. 테스트 환경 및 실행
- Python `unittest` 프레임워크 사용.
- 각 테스트는 격리되어 실행되며, `setUp`과 `tearDown`을 통해 상태를 초기화/정리.
- 필요시 `settings_test.json`과 같은 테스트용 설정 파일 사용.
- DB 테스트 시 인메모리 SQLite 또는 테스트 전용 파일 사용 및 매번 초기화.
