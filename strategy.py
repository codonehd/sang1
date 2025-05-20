#!/usr/bin/env python
# -*- coding: utf-8 -*-

import time
from datetime import datetime, timedelta # timedelta 추가
from PyQt5.QtCore import QTimer, QObject
from logger import Logger
import copy
import re
from util import ScreenManager, get_current_time_str
from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

# --- 데이터 클래스 정의 시작 ---
class TradingState(Enum):
    IDLE = auto()
    WAITING = auto()
    READY = auto()
    BOUGHT = auto()
    PARTIAL_SOLD = auto()
    COMPLETE = auto()

    def __format__(self, format_spec):
        return str(self.name)

@dataclass
class AccountState:
    account_number: Optional[str] = None
    portfolio: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    active_orders: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    account_summary: Dict[str, Any] = field(default_factory=dict)

@dataclass
class StrategySettings:
    buy_amount_per_stock: float = 1000000.0
    stop_loss_rate_from_yesterday_close: float = 2.0  # 전일 종가 기준 손절률
    partial_take_profit_rate: float = 5.0  # 부분 익절 수익률 (settings.json의 "익절_수익률")
    full_take_profit_target_rate: float = 10.0 # 최종 익절 수익률 (settings.json의 "최종_익절_수익률")
    partial_sell_ratio: float = 0.5 # 부분 익절 시 매도 비율 (settings.json의 "익절_매도비율")
    trailing_stop_activation_profit_rate: float = 2.0 # 트레일링 스탑 활성화 수익률 (settings.json의 "트레일링_활성화_수익률")
    trailing_stop_fall_rate: float = 1.8 # 트레일링 스탑 하락률 (settings.json의 "트레일링_하락률")
    market_open_time_str: str = "09:00:00"
    market_close_time_str: str = "15:30:00"
    periodic_report_enabled: bool = True
    periodic_report_interval_seconds: int = 60
    max_daily_buy_count: int = 10  # 하루 최대 매수 실행 횟수
    cancel_pending_orders_on_exit: bool = True  # 프로그램 종료 시 미체결 주문 자동 취소 여부
    auto_liquidate_after_minutes_enabled: bool = False # 일정 시간 경과 시 자동 청산 기능 활성화 여부
    auto_liquidate_after_minutes: int = 60  # 자동 청산 기준 시간 (분)

@dataclass
class StockTrackingData:
    code: str
    stock_name: str = ""
    current_price: float = 0.0
    yesterday_close_price: float = 0.0
    today_open_price: float = 0.0
    strategy_state: TradingState = TradingState.WAITING # 기본 상태를 WAITING으로 변경
    avg_buy_price: float = 0.0
    total_buy_quantity: int = 0
    current_high_price_after_buy: float = 0.0
    last_order_rq_name: Optional[str] = None
    is_gap_up_today: bool = False
    is_yesterday_close_broken_today: bool = False
    trailing_stop_partially_sold: bool = False # 트레일링 스탑 50% 매도 여부
    is_trailing_stop_active: bool = False # 트레일링 스탑 활성화 여부 (2% 수익 달성 시 True)
    partial_take_profit_executed: bool = False # 5% 부분 익절 실행 여부
    buy_timestamp: Optional[datetime] = None # 매수 체결 시간 기록
    api_data: Dict[str, Any] = field(default_factory=dict)
    # daily_chart_error: bool = False # REMOVED: No longer fetching daily chart via opt10081

@dataclass
class ExternalModules:
    kiwoom_api: Any
    config_manager: Any
    logger: Any
    db_manager: Any
    screen_manager: Any
# --- 데이터 클래스 정의 끝 ---

class TradingStrategy(QObject):
    def _safe_to_int(self, value, default=0):
        try:
            cleaned_value = str(value).strip().replace('+', '').replace('-', '')
            if not cleaned_value:
                return default
            return int(cleaned_value)
        except (ValueError, TypeError):
            return default

    def _safe_to_float(self, value, default=0.0):
        try:
            cleaned_value = str(value).strip().replace('+', '').replace('-', '')
            if not cleaned_value:
                return default
            return float(cleaned_value)
        except (ValueError, TypeError):
            return default

    def __init__(self, kiwoom_api, config_manager, logger, db_manager, screen_manager=None):
        super().__init__()
        self.modules = ExternalModules(
            kiwoom_api=kiwoom_api,
            config_manager=config_manager,
            logger=logger,
            db_manager=db_manager,
            screen_manager=screen_manager if screen_manager else ScreenManager(logger=logger) 
        )
        self.pending_daily_data_stocks = set() # 일봉 데이터 수신 대기 종목 관리용 세트 추가
        # 초기화 상태 플래그
        self.is_initialized_successfully = False # 최종 초기화 성공 여부
        self.initialization_status = {
            "account_info_loaded": False,
            "deposit_info_loaded": False, # 예수금 정보
            "portfolio_loaded": False,    # 보유 종목 정보
            "settings_loaded": False,
            "market_hours_initialized": False
        }
        self.current_status_message = "초기화 중..."

        self.account_state = AccountState()
        self.settings = StrategySettings()
        self._load_strategy_settings() # 설정 로드는 여기서 먼저 수행
        if self.initialization_status["settings_loaded"]: # _load_strategy_settings 성공 여부 반영 (내부에서 로깅)
             self.log("전략 설정 로드 완료.", "INFO")
        else:
            self.log("전략 설정 로드 실패. 기본값으로 진행될 수 있습니다.", "WARNING")


        self.watchlist: Dict[str, StockTrackingData] = {}
        self.current_async_calls = set()
        # self.pending_daily_chart_requests = {} # REMOVED: No longer fetching daily chart via opt10081
        self.is_running = False
        self.check_timer = QTimer()
        self.check_timer.setInterval(2000)
        self.check_timer.timeout.connect(self.check_conditions)
        self.status_report_timer = QTimer()
        self.status_report_timer.timeout.connect(self.report_periodic_status)
        self.daily_snapshot_timer = QTimer()
        self.daily_snapshot_timer.timeout.connect(self.record_daily_snapshot_if_needed)
        self.daily_snapshot_timer.setInterval(3600 * 1000) # 1시간 간격
        self.last_snapshot_date = None
        self.today_date_for_buy_limit: Optional[str] = None # 일일 매수 제한용 오늘 날짜
        self.daily_buy_executed_count: int = 0 # 오늘 실행된 매수 횟수

        # Market open/close time 객체 초기화
        try:
            self.market_open_time = datetime.strptime(self.settings.market_open_time_str, "%H:%M:%S").time()
            self.market_close_time = datetime.strptime(self.settings.market_close_time_str, "%H:%M:%S").time()
            self.log(f"장운영시간 초기화: {self.settings.market_open_time_str} - {self.settings.market_close_time_str}", "INFO")
            self.initialization_status["market_hours_initialized"] = True
        except ValueError as e:
            self.log(f"설정에서 장운영시간 파싱 오류: {e}. 기본값 09:00-15:30 사용.", "ERROR")
            self.market_open_time = datetime.strptime("09:00:00", "%H:%M:%S").time()
            self.market_close_time = datetime.strptime("15:30:00", "%H:%M:%S").time()
            # 이 경우에도 초기화는 된 것으로 간주 (기본값으로)
            self.initialization_status["market_hours_initialized"] = True 
        
        self.current_real_data_count = 0 # 실시간 데이터 수신 카운터
        self.log("TradingStrategy 객체 생성 완료. 추가 초기화가 필요합니다.", "INFO")
        self.watchlist_data_requested = False # 관심종목 데이터 요청 시작 여부 플래그
        self.current_status_message = "TradingStrategy 객체 생성됨. API 연결 및 데이터 로딩 대기 중."

    def _load_strategy_settings(self):
        self.log("전략 설정 로딩 시작...", "INFO")
        cfg = self.modules.config_manager
        s = self.settings
        s.buy_amount_per_stock = cfg.get_setting("매매전략", "종목당매수금액", s.buy_amount_per_stock)
        s.stop_loss_rate_from_yesterday_close = cfg.get_setting("매매전략", "손절손실률_전일종가기준", s.stop_loss_rate_from_yesterday_close)
        s.partial_take_profit_rate = cfg.get_setting("매매전략", "익절_수익률", s.partial_take_profit_rate)
        s.full_take_profit_target_rate = cfg.get_setting("매매전략", "최종_익절_수익률", s.full_take_profit_target_rate)
        s.partial_sell_ratio = cfg.get_setting("매매전략", "익절_매도비율", s.partial_sell_ratio)
        s.trailing_stop_activation_profit_rate = cfg.get_setting("매매전략", "트레일링_활성화_수익률", s.trailing_stop_activation_profit_rate)
        s.trailing_stop_fall_rate = cfg.get_setting("매매전략", "트레일링_하락률", s.trailing_stop_fall_rate)
        s.market_open_time_str = cfg.get_setting("매매전략", "MarketOpenTime", s.market_open_time_str)
        s.market_close_time_str = cfg.get_setting("매매전략", "MarketCloseTime", s.market_close_time_str)
        s.periodic_report_enabled = cfg.get_setting("PeriodicStatusReport", "enabled", s.periodic_report_enabled)
        s.periodic_report_interval_seconds = cfg.get_setting("PeriodicStatusReport", "interval_seconds", s.periodic_report_interval_seconds)
        try:
            _ = datetime.strptime(s.market_open_time_str, "%H:%M:%S").time()
            _ = datetime.strptime(s.market_close_time_str, "%H:%M:%S").time()
            self.log(f"장운영시간 설정: 시작({s.market_open_time_str}), 종료({s.market_close_time_str})")
        except Exception as e:
            self.log(f"장운영시간 설정 문자열 파싱 오류: {e}. 기본값({s.market_open_time_str}, {s.market_close_time_str}) 사용 중.", "ERROR")
            self.initialization_status["settings_loaded"] = False # 오류 발생 시 명시적 실패
            return # 실패 시 더 이상 진행하지 않음 (선택적)

        self.log(f"전략 설정 로드 완료: {self.settings}", "INFO")
        self.initialization_status["settings_loaded"] = True

    def log(self, message, level="INFO"):
        if hasattr(self, 'modules') and self.modules and hasattr(self.modules, 'logger') and self.modules.logger:
            timestamp = get_current_time_str()
            log_func = getattr(self.modules.logger, level.lower(), self.modules.logger.info)
            log_func(f"[Strategy][{timestamp}] {message}")
        else:
            timestamp = get_current_time_str()
            print(f"[{level.upper()}][Strategy_FALLBACK_LOG][{timestamp}] {message}")

    def _on_login_completed(self, account_number_from_signal):
        self.log(f"[STRATEGY_LOGIN_DEBUG] _on_login_completed 호출됨. account_number_from_signal: '{account_number_from_signal}'", "DEBUG")
        self.current_status_message = "로그인 완료. 계좌 정보 로딩 중..."
        api_account_number = account_number_from_signal.strip() if account_number_from_signal else None
        chosen_account_number = None
        if api_account_number:
            chosen_account_number = api_account_number
            self.log(f"API로부터 계좌번호 수신: '{chosen_account_number}'", "INFO")
        else:
            self.log(f"API로부터 유효한 계좌번호를 받지 못했습니다. 설정 파일에서 계좌번호를 시도합니다.", "WARNING")
            cfg_acc_num = self.modules.config_manager.get_setting("계좌정보", "계좌번호", "")
            if cfg_acc_num and cfg_acc_num.strip():
                chosen_account_number = cfg_acc_num.strip()
                self.log(f"설정 파일에서 계좌번호 로드: '{chosen_account_number}'", "INFO")
            else:
                self.log("API 및 설정 파일 모두에서 유효한 계좌번호를 찾을 수 없습니다.", "ERROR")

        if chosen_account_number:
            self.account_state.account_number = chosen_account_number
            if self.modules.kiwoom_api:
                self.modules.kiwoom_api.account_number = chosen_account_number 
            self.log(f"최종 계좌번호 설정(TradingStrategy & KiwoomAPI): '{chosen_account_number}'. 계좌 정보 요청 시작.", "INFO")
            self.initialization_status["account_info_loaded"] = True # 계좌번호 자체는 로드됨
            self.request_account_info() # 예수금 정보 요청
            self.request_portfolio_info() # 포트폴리오 정보 요청
        else:
            self.log("계좌번호가 최종적으로 설정되지 않아 계좌 관련 작업을 진행할 수 없습니다.", "CRITICAL")
            self.initialization_status["account_info_loaded"] = False
            self.current_status_message = "오류: 계좌번호 설정 실패. 프로그램 기능 제한됨."
            # 이 경우 is_initialized_successfully는 False로 유지됨

    def on_actual_real_data_received(self, code, real_type, real_data):
        self.current_real_data_count += 1
        if not self.is_running:
            return

        stock_info = self.watchlist.get(code)
        if not stock_info:
            if self.current_real_data_count % 500 == 0:
                self.log(f"수신된 실시간 데이터({code})가 관심종목에 없어 무시합니다. (500건마다 로깅)", "DEBUG")
            return

        update_occurred = False
        for key, value in real_data.items():
            if key == 'code' or key == 'real_type': continue
            processed_value = value
            if isinstance(value, (str, int, float)):
                if key in ['현재가', '등락률', '전일대비', '시가', '고가', '저가', '매수호가', '매도호가', '거래량', '누적거래량', '누적거래대금', '체결량']:
                    temp_dict_for_conversion = {key: value}
                    converted_temp_dict = self._ensure_numeric_fields(temp_dict_for_conversion)
                    processed_value = converted_temp_dict.get(key, value)

            # processed_value를 stock_info.api_data에 저장
            if key in stock_info.api_data and stock_info.api_data[key] != processed_value:
                stock_info.api_data[key] = processed_value
                update_occurred = True
            elif key not in stock_info.api_data:
                stock_info.api_data[key] = processed_value
                update_occurred = True

        # StockTrackingData의 명시적 필드 업데이트 (current_price 등)
        new_current_price = self._safe_to_float(stock_info.api_data.get('현재가', stock_info.current_price))
        if stock_info.current_price != new_current_price:
            stock_info.current_price = new_current_price
            update_occurred = True
        
        # 등락률 및 등락폭 계산 (stock_info의 필드 사용)
        if stock_info.current_price > 0 and stock_info.yesterday_close_price > 0:
            change = stock_info.current_price - stock_info.yesterday_close_price
            change_rate = (change / stock_info.yesterday_close_price) * 100
            if stock_info.api_data.get('전일대비') != change or stock_info.api_data.get('등락률') != change_rate: # api_data에도 저장 (선택적)
                stock_info.api_data['전일대비'] = change
                stock_info.api_data['등락률'] = change_rate
                # update_occurred = True # current_price 변경 시 이미 true일 가능성 높음
        elif stock_info.current_price > 0 and stock_info.yesterday_close_price == 0: # 전일 종가 없을 시
            if stock_info.api_data.get('전일대비') != stock_info.current_price or stock_info.api_data.get('등락률') != 0.0:
                stock_info.api_data['전일대비'] = stock_info.current_price
                stock_info.api_data['등락률'] = 0.0
                # update_occurred = True

        if update_occurred:
            if self.current_real_data_count % 100 == 0:
                 self.log(f"실시간 데이터 업데이트 ({code}): 현재가({stock_info.current_price}), API데이터({stock_info.api_data.get('현재가', 'N/A')})", "DEBUG")

        if update_occurred and stock_info.strategy_state != TradingState.IDLE :
            self.process_strategy(code)

    def start(self):
        self.log("TradingStrategy 시작 요청 접수...", "INFO")
        self.log(f"[STRATEGY_DEBUG] ENTERING start() method. is_running={self.is_running}, init_status={self.initialization_status}, watchlist_items={len(self.watchlist)}", "DEBUG")
        self.current_status_message = "전략 시작 중..."
        if self.is_running:
            self.log("Trading strategy is already running.", "WARNING")
            self.current_status_message = "전략 이미 실행 중."
            return

        # 모든 초기화 단계 확인
        if not self.initialization_status["account_info_loaded"]:
            self.log("시작 실패: 계좌번호가 로드되지 않았습니다.", "ERROR")
            self.current_status_message = "오류: 계좌번호 미로드. 전략 시작 불가."
            self.is_running = False
            return
        
        if not (self.initialization_status["deposit_info_loaded"] and self.initialization_status["portfolio_loaded"]):
            self.log("시작 보류: 예수금 또는 포트폴리오 정보가 아직 로드되지 않았습니다. TR 수신 대기 중일 수 있습니다.", "WARNING")
            self.current_status_message = "예수금/포트폴리오 로딩 대기 중... (TR 데이터 수신 후 자동 시작 시도)"
            # 여기서 바로 return 하지 않고, TR 응답 후 다시 start를 시도하거나,
            # 또는 TR 응답 핸들러에서 모든 데이터가 준비되면 is_running = True로 설정할 수 있습니다.
            # 현재는 start()가 다시 호출될 것으로 예상하고, 만약 TR응답이 상태를 직접 변경한다면 그 로직을 따릅니다.
            # 여기서는 일단 is_running을 True로 설정하지 않고 반환하여, 데이터 로드 후 사용자가/시스템이 다시 start를 호출하도록 유도합니다.
            # 혹은, 타이머를 설정하여 주기적으로 확인하고 자동 시작할 수 있습니다.
            # 지금은 명시적 시작만 가정.
            # TR 데이터 수신 후 관련 status 플래그 업데이트 필요
            return 

        if not self.watchlist:
            self.log("시작 보류: 관심종목이 없습니다. 최소 하나 이상의 관심종목을 추가해주세요.", "WARNING")
            self.current_status_message = "관심종목 없음. 전략 시작 보류."
            # self.is_running = False # 아직 True로 설정 안 함
            return

        # 관심종목 데이터 초기화 (일봉 데이터 등)
        self.log("관심종목 데이터 초기화 시작...", "INFO")
        all_watchlist_data_ok = True
        for code, stock_data in self.watchlist.items():
            if stock_data.yesterday_close_price == 0 and not stock_data.daily_chart_error: # 아직 전일 종가 없고, 오류도 아니면 요청
                self.log(f"관심종목 '{stock_data.stock_name}({code})'의 일봉 데이터 요청이 필요합니다.", "INFO")
                # initialize_stock_data는 add_to_watchlist에서 호출되거나, 여기서 직접 호출할 수 있습니다.
                # 여기서는 이미 add_to_watchlist 시점에서 요청되었다고 가정하고, 데이터 로드 상태만 체크.
                # 만약 데이터가 없다면, 비동기 로드를 기다려야 함.
                # 지금은 단순 플래그로 처리. 실제로는 콜백 또는 상태 확인 필요.
                # self.initialize_stock_data(code, stock_data.stock_name) # 필요 시 여기서 호출
                all_watchlist_data_ok = False # 하나라도 데이터 없으면 False
                self.log(f"'{stock_data.stock_name}({code})' 데이터 로딩 대기 중...", "WARNING")

        if not all_watchlist_data_ok:
            self.log("일부 관심종목 데이터가 아직 로드되지 않았습니다. 데이터 로딩 완료 후 전략이 활성화됩니다.", "WARNING")
            self.current_status_message = "관심종목 데이터 로딩 중..."
            # self.is_running = False
            return # 아직 시작 안 함

        self.is_running = True
        self.is_initialized_successfully = True # 모든 검사를 통과하고 실제 시작됨
        self.log("TradingStrategy 시작됨. 모든 초기 데이터 검증 완료. 실시간 조건 확인 시작.", "INFO")
        self.current_status_message = "전략 실행 중. 실시간 조건 감시."
        
        # 타이머 시작 전에 금일 매수 횟수 초기화
        today_str = datetime.now().strftime("%Y-%m-%d")
        if self.today_date_for_buy_limit != today_str:
            self.log(f"날짜 변경 감지: {self.today_date_for_buy_limit} -> {today_str}. 일일 매수 횟수 초기화.", "INFO")
            self.today_date_for_buy_limit = today_str
            self.daily_buy_executed_count = 0
        
        self.check_timer.start()
        self.log(f"조건 확인 타이머 시작 (주기: {self.check_timer.interval() / 1000}초).", "INFO")
        if self.settings.periodic_report_enabled:
            self.status_report_timer.setInterval(self.settings.periodic_report_interval_seconds * 1000)
            self.status_report_timer.start()
            self.log(f"주기적 상태 보고 타이머 시작 (주기: {self.settings.periodic_report_interval_seconds}초).", "INFO")
        
        self.daily_snapshot_timer.start()
        self.log(f"일일 스냅샷 타이머 시작 (주기: {self.daily_snapshot_timer.interval() / (3600 * 1000)}시간).", "INFO")
        self.log(f"[STRATEGY_DEBUG] start() method called. Current is_running: {self.is_running}, initialization_status: {self.initialization_status}", "DEBUG")
        self.current_status_message = "전략 시작 요청 접수. 초기 데이터 로드 상태 확인 중..."

        if self.is_running:
            self.log("전략이 이미 실행 중입니다. start() 중복 호출 방지.", "WARNING")
            return

        # 0. 로그인 및 계좌번호 로드 확인 (가장 기본적인 선결 조건)
        if not self.initialization_status["account_info_loaded"]:
            self.log("계좌번호가 아직 로드되지 않았습니다. 로그인 및 계좌번호 설정이 선행되어야 합니다.", "WARNING")
            self.current_status_message = "계좌번호 로딩 대기 중..."
            # KiwoomAPI의 _on_connect 또는 사용자의 로그인 액션 후 _on_login_completed가 호출되어 이 상태가 변경될 것임.
            return

        # 1. 예수금 및 포트폴리오 정보 로드 확인
        if not (self.initialization_status["deposit_info_loaded"] and self.initialization_status["portfolio_loaded"]):
            self.log("예수금 또는 포트폴리오 정보가 아직 모두 로드되지 않았습니다. 관련 TR 응답 대기 중.", "INFO")
            self.current_status_message = "예수금/포트폴리오 정보 로딩 대기 중..."
            # 이 정보들은 KiwoomAPI 연결 후 자동으로 요청되거나, request_account_info()를 통해 요청됨.
            # on_tr_data_received에서 해당 정보 수신 시 status가 업데이트되고, 모든 조건 만족 시 _initialize_all_watchlist_data가 호출될 것임.
            # 따라서 여기서는 추가적인 요청을 보내지 않고 대기.
            return
        
        # 2. 관심종목이 있는지 확인
        if not self.watchlist:
            self.log("관심종목이 설정되어 있지 않습니다. 관심종목 추가 후 전략 시작 가능.", "WARNING")
            self.current_status_message = "관심종목 없음. 전략 시작 불가."
            # 이 경우에도 _check_all_data_loaded_and_start_strategy에서 최종적으로 is_running = False 처리.
            return

        # 3. 계좌/포트폴리오 정보 로드 완료 시, 관심종목 데이터 로딩 시작 (아직 시작 안했다면)
        self.log("계좌/포트폴리오 정보 로드 확인됨. 관심종목 데이터 로딩 절차 확인/시작.", "INFO")
        if not self.watchlist_data_requested:
            self._initialize_all_watchlist_data() # 내부에서 watchlist_data_requested = True 설정
        else:
            self.log("관심종목 데이터 요청은 이미 시작되었거나 진행 중입니다.", "DEBUG")

        # 실제 전략 타이머 시작 등은 모든 일봉 데이터 로딩 완료 후 _check_all_data_loaded_and_start_strategy에서 담당.
        self.log(f"start() 메소드 실행 완료. 데이터 로딩 상태에 따라 비동기적으로 전략이 활성화됩니다. 현재 상태: {self.current_status_message}", "INFO")

    def cancel_all_pending_orders(self):
        """모든 미체결 주문을 취소합니다."""
        if not self.settings.cancel_pending_orders_on_exit:
            self.log("프로그램 종료 시 미체결 주문 자동 취소 기능이 비활성화되어 있습니다.", "INFO")
            return

        self.log("미체결 주문 취소 시작...", "INFO")
        # active_orders의 복사본을 순회 (딕셔너리 변경 중 오류 방지)
        active_orders_copy = dict(self.account_state.active_orders)
        
        if not active_orders_copy:
            self.log("취소할 미체결 주문이 없습니다.", "INFO")
            return

        for rq_name, order_details in active_orders_copy.items():
            if order_details.get('unfilled_qty', 0) > 0 and order_details.get('order_no'):
                original_order_type = order_details.get('order_type') # '매수' 또는 '매도'
                order_code = order_details.get('code')
                original_order_no = order_details.get('order_no')
                unfilled_qty = order_details.get('unfilled_qty')
                stock_name = order_details.get('stock_name', order_code)

                # KiwoomAPI의 send_order 파라미터:
                # (rqname, screenno, accno, orderType, code, qty, price, hogagb, orgOrderNo)
                # 주문유형: 3(매수취소), 4(매도취소)
                cancel_order_type = -1
                if original_order_type == '매수':
                    cancel_order_type = 3
                elif original_order_type == '매도':
                    cancel_order_type = 4
                else:
                    self.log(f"알 수 없는 주문 유형({original_order_type})의 주문({rq_name}, {order_code})은 취소할 수 없습니다.", "WARNING")
                    continue

                cancel_rq_name = f"미체결취소_{order_code}_{get_current_time_str(format='%H%M%S%f')}"
                screen_no = self.modules.screen_manager.get_available_screen(cancel_rq_name)
                if not screen_no:
                    self.log(f"주문 취소 실패({order_code}): 사용 가능한 화면 번호 없음.", "ERROR")
                    continue
                
                # 취소 주문 시 가격은 0 또는 빈 문자열, 수량은 미체결 수량 또는 0 (API 명세 확인 필요, 보통 0)
                # 여기서는 send_order의 가격과 수량 필드는 취소 시 의미 없을 수 있으므로 0으로 전달
                self.log(f"주문 취소 시도: {stock_name}({order_code}), 원주문번호({original_order_no}), 미체결량({unfilled_qty}), 주문유형({cancel_order_type})", "INFO")
                
                # kiwoom_api.send_order의 hogagb는 "00"(지정가) 등을 사용했었음. 취소시에는 큰 의미 없을 수 있으나 기존대로 전달.
                # 원주문번호(orgOrderNo)는 마지막 파라미터로 전달해야 함.
                ret = self.modules.kiwoom_api.send_order(
                    cancel_rq_name, 
                    screen_no, 
                    self.account_state.account_number, 
                    cancel_order_type, 
                    order_code, 
                    0, # 취소 주문 시 수량은 0 또는 미체결수량 (API 확인필요, 일반적으로 0)
                    0, # 취소 주문 시 가격은 0 또는 의미 없음
                    "00", # 호가구분 (지정가로 설정했었음, 취소시 영향 없을 수 있음)
                    original_order_no # 원주문번호
                )

                if ret == 0:
                    self.log(f"주문 취소 요청 성공: {stock_name}({order_code}), 원주문번호({original_order_no}), RQName({cancel_rq_name})", "INFO")
                    # 실제 취소 성공 여부는 OnChejanData를 통해 확인됨
                    # active_orders에서 즉시 제거하지 않고, 체결 이벤트에서 처리하도록 함.
                    # 다만, 여기서는 요청은 보냈다는 것을 표시는 할 수 있음.
                    if rq_name in self.account_state.active_orders: # 아직 active_orders에 있다면
                        self.account_state.active_orders[rq_name]['order_status'] = '취소요청중'
                else:
                    self.log(f"주문 취소 요청 실패: {stock_name}({order_code}), 원주문번호({original_order_no}), 반환값({ret})", "ERROR")
                    self.modules.screen_manager.release_screen(screen_no, cancel_rq_name) # 실패 시 화면번호 반환
            elif order_details.get('unfilled_qty', 0) > 0 and not order_details.get('order_no'):
                 self.log(f"주문({order_details.get('stock_name')}, {order_details.get('code')}, RQ:{rq_name})은 API 주문번호가 없어 취소할 수 없습니다. 상태: {order_details.get('order_status')}", "WARNING")       

        self.log("모든 미체결 주문에 대한 취소 요청 완료.", "INFO")

    def stop(self):
        self.log("TradingStrategy.stop() 메소드 시작됨.", "INFO")
        if not self.is_running:
            self.log("전략이 이미 중지된 상태입니다. stop() 중복 호출 방지.", "WARNING")
            # return # 이미 중지되었어도 정리 로직은 실행하도록 할 수 있음 (선택)

        self.is_running = False
        self.log("전략 실행 플래그 (is_running)를 False로 설정했습니다.", "INFO")
        
        self.log("미체결 주문 취소 시도...", "INFO")
        self.cancel_all_pending_orders()
        
        self.log("타이머 중지 시도...", "INFO")
        if self.check_timer.isActive():
            self.check_timer.stop()
            self.log("조건 확인 타이머 중지됨.", "DEBUG")
        if self.status_report_timer.isActive():
            self.status_report_timer.stop()
            self.log("주기적 상태 보고 타이머 중지됨.", "DEBUG")
        if self.daily_snapshot_timer.isActive():
            self.daily_snapshot_timer.stop()
            self.log("일일 스냅샷 타이머 중지됨.", "DEBUG")
        
        self.log("관심 종목 실시간 데이터 구독 해제 시도...", "INFO")
        for code in list(self.watchlist.keys()): # dict 변경 중 순회 에러 방지
            self.remove_from_watchlist(code, unsubscribe_real=True)
        
        if self.modules.screen_manager:
            self.log("ScreenManager 화면 정리 시도...", "INFO")
            self.modules.screen_manager.cleanup_screens()
            self.log("모든 화면 사용 해제 완료.")

        # DB 연결 종료 등 리소스 정리
        if self.modules.db_manager:
            # self.modules.db_manager.close() # db_manager에 close 메서드가 있다면 호출
            self.log("DB Manager 관련 리소스 정리 시도 (필요시 close 구현)")

        self.log("TradingStrategy.stop() 메소드 완료됨.", "INFO")

    # def initialize_stock_data(self, code, stock_name_param, screen_no=None): # REMOVED: Function no longer needed as daily chart data is not fetched from API
    #     self.log(f"[STRATEGY_DEBUG_INIT_STOCK] ENTERING initialize_stock_data for code: {code}, stock_name: {stock_name_param}, screen_no_arg: {screen_no}", "DEBUG")
    #     # ... (rest of the function code commented out or removed)
    #     pass

    def add_to_watchlist(self, code, stock_name, yesterday_close_price=0.0): # yesterday_close_price 추가
        self.log(f"[WATCHLIST_ADD_START] 관심종목 추가/업데이트 시작: 코드({code}), 이름({stock_name}), 설정된 전일종가({yesterday_close_price})", "DEBUG")
        
        safe_yesterday_cp = self._safe_to_float(yesterday_close_price)

        if code not in self.watchlist:
            self.watchlist[code] = StockTrackingData(
                code=code, 
                stock_name=stock_name,
                yesterday_close_price=safe_yesterday_cp
            )
            self.log(f"관심종목 신규 추가: {stock_name}({code}), 전일종가: {safe_yesterday_cp}, 초기상태: {self.watchlist[code].strategy_state.name}", "INFO")
        else:
            self.watchlist[code].stock_name = stock_name
            self.watchlist[code].yesterday_close_price = safe_yesterday_cp
            self.log(f"관심종목 정보 업데이트: {stock_name}({code}), 전일종가: {safe_yesterday_cp}, 현재상태: {self.watchlist[code].strategy_state.name}", "INFO")
        
        # 전일 종가가 0인 경우 추가 로깅
        if safe_yesterday_cp == 0:
            self.log(f"주의: 관심종목 {stock_name}({code})의 전일종가가 0으로 설정되었습니다. 매매 전략에 영향을 줄 수 있습니다.", "WARNING")

        self.log(f"[WATCHLIST_ADD_END] 관심종목 추가/업데이트 완료: 코드({code}) - 현재 self.watchlist에 {len(self.watchlist)}개 항목", "DEBUG")

    def remove_from_watchlist(self, code, screen_no=None, unsubscribe_real=True):
        self.log(f"Removing {code} from watchlist... Unsubscribe real data: {unsubscribe_real}", "INFO")
        stock_info = self.watchlist.get(code)

        if stock_info and unsubscribe_real:
            # 실시간 데이터 구독 해지
            # KiwoomAPI에 특정 종목 또는 전체 실시간 데이터 구독 해지 메서드가 필요
            # 예: self.modules.kiwoom_api.unsubscribe_stock_real_data(code)
            # 화면번호 기반으로 해지한다면:
            real_data_screen_no = stock_info.api_data.get('real_screen_no') # 실시간 데이터용 화면번호 필드가 있다고 가정
            if real_data_screen_no:
                self.modules.kiwoom_api.disconnect_real_data(real_data_screen_no)
                self.modules.screen_manager.release_screen(real_data_screen_no)
                self.log(f"Unsubscribed real data for {code} using screen_no: {real_data_screen_no}", "DEBUG")
            else:
                # 전체 해지 후 재구독 방식 또는 종목별 해지 기능이 없다면 경고 로깅
                self.log(f"Real data screen number for {code} not found. Cannot unsubscribe specific real data. Consider global unsubscription or check KiwoomAPI.", "WARNING")
        
        # TR 요청 등에 사용된 화면 번호 해제 (opt10081 요청 시 사용된 화면번호)
        tr_screen_no = stock_info.api_data.get('screen_no') if stock_info else None
        if tr_screen_no:
            self.modules.screen_manager.release_screen(tr_screen_no)
            self.log(f"Released TR screen_no: {tr_screen_no} for {code}.", "DEBUG")
        elif screen_no: # 인자로 직접 받은 screen_no가 있다면 그것도 해제 시도
             self.modules.screen_manager.release_screen(screen_no)
             self.log(f"Released screen_no (from arg): {screen_no} for {code}.", "DEBUG")

        if code in self.watchlist:
            del self.watchlist[code]
            self.log(f"{code} removed from watchlist.", "INFO")
        else:
            self.log(f"{code} not found in watchlist for removal.", "WARNING")

    # def on_daily_chart_data_ready(self, rq_name, code, chart_data): # REMOVED: Function no longer needed as daily chart data is not fetched from API
    #     # ... (rest of the function code commented out or removed)
    #     pass

    def subscribe_stock_real_data(self, code):
        stock_info = self.watchlist.get(code)
        if not stock_info:
            self.log(f"Cannot subscribe real data for {code}: not in watchlist.", "ERROR")
            return

        if stock_info.api_data.get('real_subscribed', False):
            self.log(f"Real data for {code} is already subscribed.", "DEBUG")
            return

        screen_no = self.modules.screen_manager.get_available_screen(f"real_{code}")
        if not screen_no:
            self.log(f"Failed to get a screen number for real data subscription of {code}.", "ERROR")
            return

        # KiwoomAPI의 실시간 데이터 구독 메서드 호출 (예시)
        # SetRealReg 메서드 사용. FID 목록은 설정 파일이나 상수로 관리 가능
        # 예: fids = "9001;10;13" # 종목코드, 현재가, 누적거래량 등 (실제 필요한 FID로 구성)
        # 여기서는 KiwoomAPI wrapper가 FID 관리를 내부적으로 한다고 가정하거나, 직접 전달.
        # kiwoom_api.subscribe_real_stock_data(screen_no, code, fids)
        
        # 일반적인 FID 리스트 (현재가, 등락률, 거래량 등) - 필요에 따라 설정에서 가져오거나 확장
        # 실제 키움 API의 SetRealReg 함수는 FID를 ;로 구분된 문자열로 받습니다.
        # FID_LIST = "10;11;12;13;14;15;16;17;18;20;25;26;27;28;30;293;294;295;296;297;298;299;300;301;302;311;691;791;891"
        # 위 FID 리스트는 예시이며, 실제 필요한 FID만 선별하여 사용하는 것이 효율적입니다.
        # 여기서는 KiwoomAPI 모듈에 FID 관리 로직이 있다고 가정하고, 종목코드만 넘깁니다.

        ret = self.modules.kiwoom_api.set_real_reg(screen_no, code, self.modules.config_manager.get_setting("API", "RealTimeFID", "10;11;12;13"), "1") # "1"은 최초 등록, "0"은 추가
        # set_real_reg의 반환값은 성공 여부가 아닐 수 있음 (API 설계에 따라 다름)
        # 보통 성공/실패는 이벤트나 다른 방식으로 전달됨.
        # 여기서는 일단 요청을 보낸 것으로 간주.

        if ret == 0: # 일부 API는 성공시 0을 반환하나, 키움은 아님. 이벤트로 확인.
            self.log(f"실시간 데이터 구독 요청 성공 (화면: {screen_no}, 종목: {code}) - SetRealReg 호출 자체는 성공으로 간주. 실제 구독 성공은 이벤트로 확인.", "INFO")
            stock_info.api_data['real_screen_no'] = screen_no # 실시간 데이터용 화면번호 저장
            stock_info.api_data['real_subscribed'] = True
        else: # SetRealReg 호출이 실패한 경우 (거의 발생하지 않음, 파라미터 오류 등)
            self.log(f"실시간 데이터 구독 요청 실패 (화면: {screen_no}, 종목: {code}). SetRealReg 반환값: {ret}", "ERROR")
            self.modules.screen_manager.release_screen(screen_no)

    def check_initial_conditions(self, code):
        # stock_info = self.watchlist.get(code)
        # if not stock_info:
        #     self.log(f"Cannot check initial conditions for {code}: not in watchlist.", "ERROR")
        #     return

        # # 이미 매매가 진행 중이거나 완료된 상태면 초기 조건 검사 불필요
        # if stock_info.strategy_state not in [TradingState.IDLE, TradingState.READY]:
        #     self.log(f"Skipping initial condition check for {code}. Current state: {stock_info.strategy_state}", "DEBUG")
        #     return

        # self.log(f"Checking initial conditions for {code}... Current state: {stock_info.strategy_state}", "INFO")
        # # 예시: 갭 상승 후 시가 위로 올라오면 WAITING 상태로 변경
        # # 이 로직은 실제 전략에 따라 매우 다양해질 수 있음

        # # 필요한 데이터가 모두 로드되었는지 확인 (예: 전일종가, 당일시가)
        # if stock_info.yesterday_close_price == 0 or stock_info.today_open_price == 0:
        #     self.log(f"Initial condition check for {code} deferred: yesterday_close_price or today_open_price is zero.", "WARNING")
        #     # stock_info.daily_chart_error 가 True일 수 있음. 이 경우 재시도 로직 필요.
        #     if stock_info.daily_chart_error:
        #          self.log(f"{code}의 일봉 데이터 로드에 오류가 있어 초기 조건 검사를 진행할 수 없습니다. 재시도 필요.", "ERROR")
        #     return
        
        # # --- 사용자 정의 초기 진입 조건 시작 ---
        # # 예시 1: 특정 가격 조건 (여기서는 단순 예시로, 실제 사용 시 구체적인 전략 로직으로 대체)
        # # if stock_info.current_price > stock_info.today_open_price * 1.01: # 시가보다 1% 이상 상승 시
        # # stock_info.strategy_state = TradingState.WAITING
        # # self.log(f"{code} state changed to WAITING based on initial price condition.", "INFO")

        # # 예시 2: 갭 상승 종목에 대한 기본 전략 상태 설정
        # # (on_daily_chart_data_ready 에서 is_gap_up_today가 설정되었다고 가정)
        # if stock_info.is_gap_up_today:
        #     self.log(f"{code} is identified as a gap-up stock. Initial strategy state might be set to WAITING or READY.", "INFO")
        #     # 기본적으로 WAITING 상태로 설정하고, process_strategy에서 추가 조건 확인 후 매수 시도
        #     stock_info.strategy_state = TradingState.WAITING 
        #     self.log(f"{code} (갭상승) state changed to {stock_info.strategy_state}. is_gap_up_today: {stock_info.is_gap_up_today}", "INFO")
        # else:
        #     # 갭 상승이 아닌 경우, 다른 조건을 보거나 IDLE 상태 유지
        #     # 필요하다면 다른 초기 조건 검사 로직 추가
        #     # 여기서는 IDLE 상태를 유지하고, 실시간 데이터 기반으로 process_strategy에서 판단.
        #     if stock_info.strategy_state == TradingState.IDLE:
        #          self.log(f"{code} (갭상승 아님) state remains {stock_info.strategy_state}. is_gap_up_today: {stock_info.is_gap_up_today}", "INFO")
        #     # else: # IDLE이 아닌 다른 상태 (예: READY)라면 특별한 로깅 없이 넘어감 (필요시 추가)
        #     #     pass
        # # --- 사용자 정의 초기 진입 조건 끝 ---

        # # 초기 조건 만족 시 DB에 상태 업데이트 (필요시)
        # # self.modules.db_manager.update_stock_strategy_state(code, stock_info.strategy_state)

        # # 조건 검사 후, process_strategy를 호출하여 즉시 다음 액션 고려
        # if stock_info.strategy_state != TradingState.IDLE:
        #     self.process_strategy(code)
        pass # 함수 내용을 비우고 pass만 남김

    def check_conditions(self):
        # 일일 매수 횟수 제한을 위한 날짜 확인 및 카운트 초기화
        current_date_str = datetime.now().strftime("%Y-%m-%d")
        if self.today_date_for_buy_limit != current_date_str:
            self.log(f"날짜 변경 감지: {self.today_date_for_buy_limit} -> {current_date_str}. 일일 매수 횟수 초기화.", "INFO")
            self.today_date_for_buy_limit = current_date_str
            self.daily_buy_executed_count = 0
        
        if not self.is_running or not self.is_market_hours():
            return

        for code in list(self.watchlist.keys()):
            if code in self.watchlist:
                self.process_strategy(code)

    def is_market_hours(self):
        """현재 시간이 장운영 시간인지 확인합니다."""
        now = datetime.now().time()
        is_open = self.market_open_time <= now <= self.market_close_time
        return is_open

    def _check_and_execute_stop_loss(self, code, stock_info: StockTrackingData, current_price, avg_buy_price, holding_quantity):
        """손절 로직을 검사하고 실행합니다. (전일 종가 기준)"""
        if stock_info.yesterday_close_price == 0:
            self.log(f"[{code}] 손절 조건 검토 중단: 전일 종가 정보 없음.", "WARNING")
            return False

        stop_loss_price = stock_info.yesterday_close_price * (1 - self.settings.stop_loss_rate_from_yesterday_close / 100)
        self.log(f"[{code}] 손절 조건 검토(전일종가기준): 현재가({current_price:.2f}) vs 손절가({stop_loss_price:.2f}) (전일종가: {stock_info.yesterday_close_price:.2f}, 손절률설정: {self.settings.stop_loss_rate_from_yesterday_close}%) - 보유량({holding_quantity})", "DEBUG")
        if current_price <= stop_loss_price:
            self.log(f"손절 조건 충족(전일종가기준): {code} ({stock_info.stock_name}), 현재가({current_price:.2f}) <= 손절가({stop_loss_price:.2f}). 기준(전일종가: {stock_info.yesterday_close_price:.2f}), 보유량({holding_quantity}).", "INFO")
            if self.execute_sell(code, reason="손절(전일종가기준)", quantity_type="전량"):
                return True # 주문 실행됨
        return False # 주문 실행 안됨

    def _check_and_execute_full_take_profit(self, code, stock_info: StockTrackingData, current_price, avg_buy_price, holding_quantity):
        """최종 목표 수익률 도달 시 전량 매도 로직을 검사하고 실행합니다."""
        if holding_quantity <= 0:
            return False

        target_price = avg_buy_price * (1 + self.settings.full_take_profit_target_rate / 100.0)
        self.log(f"[{code}] 최종 익절 조건 검토: 현재가({current_price:.2f}) vs 최종목표가({target_price:.2f}) (매입가: {avg_buy_price:.2f}, 최종익절률: {self.settings.full_take_profit_target_rate}%) - 보유량({holding_quantity})", "DEBUG")

        if current_price >= target_price:
            self.log(f"최종 익절 조건 충족: {code} ({stock_info.stock_name}), 현재가({current_price:.2f}) >= 최종목표가({target_price:.2f}). 전량매도 시도.", "INFO")
            if self.execute_sell(code, reason="최종익절(전량)", quantity_type="전량"):
                return True
            else:
                self.log(f"[{code}] 최종 익절 조건 충족했으나 매도 주문 실패.", "ERROR")
        return False

    def _check_and_execute_partial_take_profit(self, code, stock_info: StockTrackingData, current_price, avg_buy_price, holding_quantity):
        """부분 익절(5% 수익 시 50% 매도) 로직을 검사하고 실행합니다."""
        if holding_quantity <= 0 or stock_info.partial_take_profit_executed:
            return False

        target_price = avg_buy_price * (1 + self.settings.partial_take_profit_rate / 100.0)
        self.log(f"[{code}] 부분 익절 조건 검토: 현재가({current_price:.2f}) vs 부분익절가({target_price:.2f}) (매입가: {avg_buy_price:.2f}, 부분익절률: {self.settings.partial_take_profit_rate}%) - 보유량({holding_quantity})", "DEBUG")

        if current_price >= target_price:
            sell_qty = int(holding_quantity * (self.settings.partial_sell_ratio / 100.0))
            if sell_qty <= 0 and holding_quantity > 0:
                sell_qty = holding_quantity
                self.log(f"[{code}] 부분 익절: 계산된 매도 수량 0이나 보유량 있어 전량({sell_qty}) 매도 시도.", "WARNING")
            elif sell_qty <= 0:
                 self.log(f"[{code}] 부분 익절: 계산된 매도 수량 0. 진행 안함.", "DEBUG")
                 return False

            self.log(f"부분 익절 조건 충족: {code} ({stock_info.stock_name}), 현재가({current_price:.2f}) >= 부분익절가({target_price:.2f}). 매도수량({sell_qty} / 현재보유량 {holding_quantity}) 시도.", "INFO")
            
            if self.execute_sell(code, reason="부분익절(5%)", quantity_type="수량", quantity_val=sell_qty):
                stock_info.partial_take_profit_executed = True
                self.log(f"[{code}] 부분 익절 주문 접수 성공. partial_take_profit_executed 플래그 True 설정.", "INFO")
                return True
            else:
                self.log(f"[{code}] 부분 익절 조건 충족했으나 매도 주문 실패.", "ERROR")
        return False

#    def _check_and_execute_profit_taking(self, code, stock_info: StockTrackingData, current_price, portfolio_item, avg_buy_price, holding_quantity):
#        """목표 수익률 도달 시 전량 매도 로직을 검사하고 실행합니다. (BOUGHT 상태에서만 호출 가정)"""
#        target_profit_price = avg_buy_price * (1 + self.settings.target_profit_rate / 100)
#        # self.settings.partial_sell_ratio는 더 이상 이 로직에서 사용되지 않음.
#        self.log(f"[{code}] 목표수익률(전량매도) 조건 검토 (BOUGHT): 현재가({current_price:.2f}) vs 목표가({target_profit_price:.2f}) (매입가: {avg_buy_price:.2f}, 목표수익률설정: {self.settings.target_profit_rate}%) - 보유량({holding_quantity})", "DEBUG")
#        if current_price >= target_profit_price:
#            self.log(f"목표수익률(전량매도) 조건 충족: {code} ({stock_info.stock_name}), 현재가({current_price:.2f}) >= 목표가({target_profit_price:.2f}). 기준매입가({avg_buy_price:.2f}), 보유량({holding_quantity}). 전량매도 시도.", "INFO")
#            if self.execute_sell(code, reason="목표수익률달성(전량)", quantity_type="전량"):
#                return True # 주문 실행됨
#            else:
#                self.log(f"[{code}] 목표수익률(전량매도) 조건 충족했으나 매도 주문 실패.", "ERROR")
#        return False # 주문 실행 안됨

    def _check_and_execute_trailing_stop(self, code, stock_info: StockTrackingData, current_price, avg_buy_price, holding_quantity):
        """트레일링 스탑 로직을 검사하고 실행합니다 (활성화된 경우에만)."""
        if not stock_info.is_trailing_stop_active or holding_quantity <= 0:
            return False

        high_since_buy_or_activation = stock_info.current_high_price_after_buy
        trailing_stop_trigger_price = high_since_buy_or_activation * (1 - self.settings.trailing_stop_fall_rate / 100.0)

        self.log(f"[{code}] 트레일링 스탑 조건 검토 (활성상태: {stock_info.is_trailing_stop_active}, 부분매도여부: {stock_info.trailing_stop_partially_sold}): 현재가({current_price:.2f}) vs 발동가({trailing_stop_trigger_price:.2f}). 기준고점({high_since_buy_or_activation:.2f}), 하락률({self.settings.trailing_stop_fall_rate}%)", "DEBUG")

        if current_price <= trailing_stop_trigger_price:
            if not stock_info.trailing_stop_partially_sold: # 첫 번째 트레일링 스탑 발동
                sell_qty = int(holding_quantity * (self.settings.partial_sell_ratio / 100.0)) # 현재 보유량의 50%
                if sell_qty <= 0 and holding_quantity > 0 : 
                    sell_qty = holding_quantity
                    self.log(f"[{code}] 트레일링 스탑 (첫 발동): 계산된 매도 수량 0이나 보유량({holding_quantity}) 있어 전량 매도 시도.", "WARNING")
                elif sell_qty <=0:
                    self.log(f"[{code}] 트레일링 스탑 (첫 발동): 계산된 매도 수량 0. 진행 안함.", "DEBUG")
                    return False

                self.log(f"트레일링 스탑 (첫 발동 50%) 조건 충족: {code} ({stock_info.stock_name}), 현재가({current_price:.2f}) <= 발동가({trailing_stop_trigger_price:.2f}). 매도수량({sell_qty}) 시도.", "INFO")
                if self.execute_sell(code, reason="트레일링스탑(50%)", quantity_type="수량", quantity_val=sell_qty):
                    stock_info.trailing_stop_partially_sold = True
                    self.log(f"[{code}] 트레일링 스탑 (50%) 매도 주문 접수. trailing_stop_partially_sold 플래그 True 설정.", "INFO")
                    return True
                else:
                    self.log(f"[{code}] 트레일링 스탑 (50%) 매도 주문 실패.", "ERROR")
            else: # 이미 부분 매도된 상태 (두 번째 트레일링 스탑 발동)
                self.log(f"트레일링 스탑 (잔량 전량) 조건 충족: {code} ({stock_info.stock_name}), 현재가({current_price:.2f}) <= 발동가({trailing_stop_trigger_price:.2f}). 전량매도 시도.", "INFO")
                if self.execute_sell(code, reason="트레일링스탑(잔량)", quantity_type="전량"):
                    return True
                else:
                    self.log(f"[{code}] 트레일링 스탑 (잔량 전량) 매도 주문 실패.", "ERROR")
        return False

    def _handle_waiting_state(self, code, stock_info: StockTrackingData, current_price):
        """매수 조건을 검사하고 매수 주문을 실행합니다 (WAITING 상태)."""
        #is_gap_up = stock_info.is_gap_up_today
        yesterday_cp = stock_info.yesterday_close_price 
        is_broken = stock_info.is_yesterday_close_broken_today

        #if not is_gap_up:
        #    return False

        if yesterday_cp == 0:
            return False

        if current_price < yesterday_cp and not is_broken: # (3) 현재가가 전일 종가 미만이고, 아직 하회 기록이 없으면
            stock_info.is_yesterday_close_broken_today = True # 하회 기록 플래그 설정
            self.log(f"[{code}] 전일 종가 하회 기록 (전일종가: {yesterday_cp}, 현재가: {current_price})", "INFO")
            return False

        elif is_broken and current_price > yesterday_cp: # (4) 하회 기록이 있고, 현재가가 전일 종가 초과 시 (돌파)
            self.log(f"[{code}] 전일 종가 재돌파, 매수 조건 충족 (전일종가: {yesterday_cp}, 현재가: {current_price})", "INFO")
            if self.execute_buy(code): # 매수 실행
                stock_info.is_yesterday_close_broken_today = False # 매수 성공 시 플래그 리셋
                self.log(f"[{code}] 매수 주문 접수 성공 후 'is_yesterday_close_broken_today' 플래그 리셋.", "DEBUG")
                return True
        return False

    def _handle_holding_state(self, code, stock_info: StockTrackingData, current_price):
        """매도 조건을 검사하고 매도 주문을 실행합니다 (BOUGHT 또는 PARTIAL_SOLD 상태)."""
        portfolio_item = self.account_state.portfolio.get(code)
        if not portfolio_item:
            self.log(f"매도 조건 검사 중단 ({code}): 포트폴리오 정보 없음.", "WARNING")
            return False

        avg_buy_price = self._safe_to_float(portfolio_item.get('매입가'))
        holding_quantity = self._safe_to_int(portfolio_item.get('보유수량'))

        if avg_buy_price == 0 or holding_quantity == 0:
            self.log(f"매도 조건 검사 중단 ({code}): 매수가(0) 또는 보유수량(0) (매입가: {avg_buy_price}, 보유량: {holding_quantity}).", "WARNING")
            return False

        # 1. 고점 업데이트 (매수 후 또는 트레일링 스탑 활성화 후)
        if stock_info.strategy_state == TradingState.BOUGHT or stock_info.strategy_state == TradingState.PARTIAL_SOLD:
            stock_info.current_high_price_after_buy = max(stock_info.current_high_price_after_buy, current_price)
        
        # 2. 트레일링 스탑 활성화 조건 체크
        if not stock_info.is_trailing_stop_active and \
           (stock_info.strategy_state == TradingState.BOUGHT or stock_info.strategy_state == TradingState.PARTIAL_SOLD):
            activation_target_price = avg_buy_price * (1 + self.settings.trailing_stop_activation_profit_rate / 100.0)
            if current_price >= activation_target_price:
                stock_info.is_trailing_stop_active = True
                stock_info.current_high_price_after_buy = current_price 
                self.log(f"[{code}] 트레일링 스탑 활성화! 현재가({current_price:.2f}) >= 활성화 목표가({activation_target_price:.2f}). 기준 고점({stock_info.current_high_price_after_buy:.2f})으로 설정.", "INFO")

        # --- 매도 우선순위 적용 ---
        # 1. 손절 (가장 먼저 체크)
        if self._check_and_execute_stop_loss(code, stock_info, current_price, avg_buy_price, holding_quantity):
            return True

        # 2. 최종 익절
        if self._check_and_execute_full_take_profit(code, stock_info, current_price, avg_buy_price, holding_quantity):
            return True

        # 3. 부분 익절 (아직 실행 안했고, BOUGHT 또는 PARTIAL_SOLD 상태일 때)
        if not stock_info.partial_take_profit_executed and \
           (stock_info.strategy_state == TradingState.BOUGHT or stock_info.strategy_state == TradingState.PARTIAL_SOLD):
            if self._check_and_execute_partial_take_profit(code, stock_info, current_price, avg_buy_price, holding_quantity):
                return True

        # 4. 트레일링 스탑 (활성화된 경우에만 작동)
        if stock_info.is_trailing_stop_active:
            if self._check_and_execute_trailing_stop(code, stock_info, current_price, avg_buy_price, holding_quantity):
                return True
        
        # 5. 시간 경과 자동 청산
        if self.settings.auto_liquidate_after_minutes_enabled and \
           stock_info.buy_timestamp and \
           (stock_info.strategy_state == TradingState.BOUGHT or stock_info.strategy_state == TradingState.PARTIAL_SOLD) :
            
            elapsed_time = datetime.now() - stock_info.buy_timestamp
            elapsed_minutes = elapsed_time.total_seconds() / 60
            buy_time_str = stock_info.buy_timestamp.strftime('%Y-%m-%d %H:%M:%S') if stock_info.buy_timestamp else 'N/A'

            self.log(f"[{code}] 시간 경과 자동 청산 조건 검토: 경과 시간({elapsed_minutes:.2f}분) vs 설정 시간({self.settings.auto_liquidate_after_minutes}분), 매수시간({buy_time_str})", "DEBUG")

            if elapsed_minutes >= self.settings.auto_liquidate_after_minutes:
                self.log(f"시간 경과 자동 청산 조건 충족: {code} ({stock_info.stock_name}), 경과 시간({elapsed_minutes:.2f}분) >= 설정 시간({self.settings.auto_liquidate_after_minutes}분). 전량 매도 시도.", "INFO")
                if self.execute_sell(code, reason="시간경과자동청산", quantity_type="전량"):
                    return True
                else:
                    self.log(f"[{code}] 시간 경과 자동 청산 조건 충족했으나 매도 주문 실패.", "ERROR")
            
        return False

    def process_strategy(self, code):
        # self.log(f"[Strategy_DEBUG] ENTERING process_strategy for {code}.", "DEBUG") # 상태 정보는 stock_info에서 직접 참조
        
        stock_info = self.watchlist.get(code)
        if not stock_info:
            # self.log(f"{code} not in watchlist, skipping process_strategy.", "DEBUG")
            return

        current_state = stock_info.strategy_state
        current_price = stock_info.current_price 
        yesterday_close = stock_info.yesterday_close_price

        if current_price == 0 or yesterday_close == 0:
            return

        order_executed = False
        if current_state == TradingState.WAITING:
            order_executed = self._handle_waiting_state(code, stock_info, current_price)
        elif current_state == TradingState.BOUGHT or current_state == TradingState.PARTIAL_SOLD:
            order_executed = self._handle_holding_state(code, stock_info, current_price)
        elif current_state in [TradingState.IDLE, TradingState.READY, TradingState.COMPLETE]:
            pass # 의도적으로 아무 작업도 하지 않음
        else:
            self.log(f"[{code}] process_strategy: 알 수 없는 전략 상태({current_state}). 확인 필요.", "WARNING")


    def execute_buy(self, code):
        # 일일 매수 횟수 제한 확인
        if self.daily_buy_executed_count >= self.settings.max_daily_buy_count:
            self.log(f"일일 매수 횟수 제한({self.settings.max_daily_buy_count}회) 도달. 금일 추가 매수 불가. (현재: {self.daily_buy_executed_count}회)", "WARNING")
            return False

        stock_info = self.watchlist.get(code)
        if not stock_info:
            self.log(f"매수 주문 실패: {code} StockTrackingData 정보를 찾을 수 없습니다.", "ERROR")
            return False

        self.log(f"[Strategy_EXECUTE_BUY_DEBUG] execute_buy 호출. 계좌번호: '{self.account_state.account_number}', 오늘 매수횟수: {self.daily_buy_executed_count}/{self.settings.max_daily_buy_count}", "DEBUG")
        
        pure_code, market_ctx = self.modules.kiwoom_api.get_code_market_info(code)

        if stock_info.last_order_rq_name:
            self.log(f"매수 주문 건너뜀: {pure_code}(원본:{code})에 대해 이미 주문({stock_info.last_order_rq_name})이 전송되었거나 처리 중입니다.", "INFO")
            return False

        order_type_to_send = 1 # 기본 KRX 매수
        if market_ctx == 'NXT':
            order_type_to_send = 11 # Nextrade 신규매수
            self.log(f"ATS 주문 감지 ({code}): 시장 NXT, order_type을 {order_type_to_send}로 설정합니다.", "INFO")
        # ... (기타 시장 컨텍스트 처리) ...

        if not self.account_state.account_number:
            self.log("매수 주문 실패: 계좌번호가 설정되지 않았습니다.", "ERROR")
            return False

        current_price = stock_info.current_price # StockTrackingData 에서 현재가 사용
        if current_price == 0:
            self.log(f"매수 주문 실패 ({pure_code}, 원본:{code}): 현재가 정보 없음.", "ERROR")
            return False
        
        decision_reason = f"사용자 정의 매수 전략: 갭상승({stock_info.is_gap_up_today}), 전일종가({stock_info.yesterday_close_price}), 현재가({current_price}), 전일종가하회기록({stock_info.is_yesterday_close_broken_today}) -> 재돌파"
        related_data_for_decision = {
            "current_price": current_price,
            "original_code": code, 
            "pure_code_for_order": pure_code,
            "market_context_for_order": market_ctx,
            "order_type_determined": order_type_to_send,
            "stock_info": copy.deepcopy(stock_info.api_data), # api_data만 복사 또는 필요한 정보만
            "strategy_settings": {
                "buy_amount_per_stock": self.settings.buy_amount_per_stock
            }
        }
        self.modules.db_manager.add_decision_record(get_current_time_str(), pure_code, "매수", decision_reason, related_data_for_decision)
            
        quantity = int(self.settings.buy_amount_per_stock / current_price)
        if quantity == 0:
            self.log(f"매수 주문 실패 ({pure_code}, 원본:{code}): 주문 가능 수량 0 (종목당매수금액: {self.settings.buy_amount_per_stock}, 현재가: {current_price})", "WARNING")
            return False
            
        price_to_order = current_price 
        rq_name = f"매수_{pure_code}_{get_current_time_str(format='%H%M%S%f')}" 
        screen_no = self.modules.screen_manager.get_available_screen(rq_name) # 화면번호 요청 수정

        self.log(f"매수 주문 시도: {stock_info.stock_name} ({pure_code}, 원본:{code}), 시장컨텍스트: {market_ctx}, 주문유형: {order_type_to_send}, 수량: {quantity}, 가격: {price_to_order}, 화면: {screen_no}", "INFO")
        
        order_ret = self.modules.kiwoom_api.send_order(rq_name, screen_no, self.account_state.account_number, order_type_to_send, pure_code, quantity, int(price_to_order), "03", "") 

        if order_ret == 0: 
            self.log(f"매수 주문 접수 성공: {pure_code} (원본:{code}), RQName: {rq_name}", "INFO")
            stock_info.last_order_rq_name = rq_name # StockTrackingData에 RQName 저장
            self.account_state.active_orders[rq_name] = {
                'order_no': None, 
                'code': pure_code,
                'stock_name': stock_info.stock_name,
                'order_type': '매수',
                'order_qty': quantity,
                'unfilled_qty': quantity, 
                'order_price': price_to_order,
                'order_status': '접수요청', 
                'timestamp': get_current_time_str()
            }
            self.log(f"active_orders에 매수 주문 추가: {rq_name}, 상세: {self.account_state.active_orders[rq_name]}", "DEBUG")
            
            # 매수 주문 성공 시 일일 매수 횟수 증가
            self.daily_buy_executed_count += 1
            self.log(f"일일 매수 횟수 증가: {self.daily_buy_executed_count}/{self.settings.max_daily_buy_count} ({code})", "INFO")
            return True
        else: 
            self.log(f"매수 주문 접수 실패: {pure_code} (원본:{code}), 반환값: {order_ret}", "ERROR")
            if screen_no: self.modules.screen_manager.release_screen(screen_no, rq_name)
            return False


    def execute_sell(self, code, reason="", quantity_type="전량", quantity_val=0):
        stock_info = self.watchlist.get(code)
        if not stock_info:
            self.log(f"매도 주문 실패: {code} StockTrackingData 정보를 찾을 수 없습니다.", "ERROR")
            return False

        self.log(f"[Strategy_EXECUTE_SELL_DEBUG] execute_sell 호출. 계좌번호: '{self.account_state.account_number}'", "DEBUG")
        
        pure_code, market_ctx = self.modules.kiwoom_api.get_code_market_info(code)

        if stock_info.last_order_rq_name:
            self.log(f"매도 주문 건너뜀: {pure_code}(원본:{code})에 대해 이미 주문({stock_info.last_order_rq_name})이 전송되었거나 처리 중입니다.", "INFO")
            return False

        order_type_to_send = 2 # 기본 KRX 매도
        if market_ctx == 'NXT':
            order_type_to_send = 12 # Nextrade 신규매도
            self.log(f"ATS 주문 감지 ({code}): 시장 NXT, order_type을 {order_type_to_send}로 설정합니다.", "INFO")
        # ... (기타 시장 컨텍스트 처리) ...

        if not self.account_state.account_number:
            self.log("매도 주문 실패: 계좌번호가 설정되지 않았습니다.", "ERROR")
            return False

        portfolio_item = self.account_state.portfolio.get(pure_code)
        if not portfolio_item: 
            self.log(f"매도 주문 실패: {pure_code}(원본:{code}) 포트폴리오에 없음.", "ERROR")
            return False
            
        current_price = stock_info.current_price # StockTrackingData 에서 현재가 사용
        if current_price == 0:
            self.log(f"매도 주문 실패 ({pure_code}, 원본:{code}): 현재가 정보 없음.", "ERROR")
            return False

        available_quantity = self._safe_to_int(portfolio_item.get('보유수량')) 

        decision_reason_full = f"매도 ({reason}): 현재가({current_price}), 보유수량({available_quantity}), 시장({market_ctx}), 주문타입({order_type_to_send})"
        related_data_for_decision = {
            "current_price": current_price,
            "original_code": code,
            "pure_code_for_order": pure_code,
            "market_context_for_order": market_ctx,
            "order_type_determined": order_type_to_send,
            "stock_info_api_data": copy.deepcopy(stock_info.api_data),
            "portfolio_item": copy.deepcopy(portfolio_item), 
            "reason_param": reason, 
            "quantity_type_param": quantity_type,
            "quantity_val_param": quantity_val,
            "strategy_settings": {
                "stop_loss_rate_from_yesterday_close": self.settings.stop_loss_rate_from_yesterday_close,
                "target_profit_rate": self.settings.target_profit_rate,
                "partial_sell_ratio": self.settings.partial_sell_ratio,
                "trailing_stop_fall_rate": self.settings.trailing_stop_fall_rate,
                "high_price_for_trailing": stock_info.current_high_price_after_buy
            }
        }
        self.modules.db_manager.add_decision_record(get_current_time_str(), pure_code, "매도", decision_reason_full, related_data_for_decision)

        if available_quantity == 0:
            self.log(f"매도 주문 실패 ({pure_code}, 원본:{code}): 매도 가능 수량 0.", "WARNING")
            return False

        sell_quantity = 0
        if quantity_type == "전량":
            sell_quantity = available_quantity
        elif quantity_type == "비율": 
            sell_quantity = int(available_quantity * (self._safe_to_float(quantity_val) / 100.0))
        elif quantity_type == "수량":
            sell_quantity = min(self._safe_to_int(quantity_val), available_quantity)
        
        if sell_quantity <= 0: 
            self.log(f"매도 주문 실패 ({pure_code}, 원본:{code}): 계산된 매도 수량 {sell_quantity} (타입: {quantity_type}, 값: {quantity_val}, 보유량: {available_quantity})", "WARNING")
            return False

        price_to_order = current_price 
        rq_name = f"매도_{pure_code}_{get_current_time_str(format='%H%M%S%f')}_{reason}" 
        screen_no = self.modules.screen_manager.get_available_screen(rq_name) 

        self.log(f"매도 주문 시도 (사유: {reason}): {stock_info.stock_name} ({pure_code}, 원본:{code}), 시장컨텍스트: {market_ctx}, 주문유형: {order_type_to_send}, 수량: {sell_quantity}, 가격: {price_to_order}, 화면: {screen_no}", "INFO")
        
        order_ret = self.modules.kiwoom_api.send_order(rq_name, screen_no, self.account_state.account_number, order_type_to_send, pure_code, sell_quantity, int(price_to_order), "03", "") 

        if order_ret == 0:
            self.log(f"매도 주문 접수 성공: {pure_code} (원본:{code}), RQName: {rq_name}", "INFO")
            stock_info.last_order_rq_name = rq_name # StockTrackingData에 RQName 저장
            self.account_state.active_orders[rq_name] = {
                'order_no': None, 
                'code': pure_code,
                'stock_name': stock_info.stock_name,
                'order_type': '매도',
                'order_qty': sell_quantity,
                'unfilled_qty': sell_quantity, 
                'order_price': price_to_order,
                'order_status': '접수요청', 
                'timestamp': get_current_time_str(),
                'reason': reason
            }
            self.log(f"active_orders에 매도 주문 추가: {rq_name}, 상세: {self.account_state.active_orders[rq_name]}", "DEBUG")
            return True
        else:
            self.log(f"매도 주문 접수 실패: {pure_code} (원본:{code}), 반환값: {order_ret}", "ERROR")
            if screen_no: self.modules.screen_manager.release_screen(screen_no, rq_name) 
            return False

    def reset_stock_strategy_info(self, code):
        """특정 종목의 전략 관련 정보를 초기화합니다."""
        stock_data = self.watchlist.get(code)
        if stock_data:
            stock_data.strategy_state = TradingState.WAITING # 매매 대상이므로 WAITING으로 초기화
            stock_data.avg_buy_price = 0.0
            stock_data.total_buy_quantity = 0
            stock_data.current_high_price_after_buy = 0.0
            stock_data.last_order_rq_name = None
            stock_data.trailing_stop_partially_sold = False # 트레일링 스탑 부분 매도 플래그 초기화
            stock_data.is_trailing_stop_active = False # 트레일링 스탑 활성화 플래그 초기화
            stock_data.partial_take_profit_executed = False # 부분 익절 실행 플래그 초기화
            stock_data.buy_timestamp = None # 매수 시간 초기화
            # stock_data.is_yesterday_close_broken_today = False # 필요시 초기화
            self.log(f"{code} ({stock_data.stock_name}) 전략 정보 초기화 완료. 상태: {stock_data.strategy_state}, 트레일링부분매도: {stock_data.trailing_stop_partially_sold}", "INFO")
        else:
            self.log(f"전략 정보 초기화 실패: {code} 관심종목에 없음.", "WARNING")


    def update_portfolio_on_execution(self, code, stock_name, trade_price, quantity, trade_type):
        """
        주문 체결 시 포트폴리오 정보를 업데이트합니다.
        trade_type: '매수', '매도'
        """
        trade_price = self._safe_to_float(trade_price)
        quantity = self._safe_to_int(quantity)
        portfolio = self.account_state.portfolio # portfolio 참조 수정

        if trade_type == '매수':
            if code not in portfolio:
                portfolio[code] = {
                    'stock_name': stock_name,
                    '보유수량': 0,
                    '매입가': 0, 
                    '매입금액': 0, 
                    '평가금액': 0,
                    '평가손익': 0,
                    '수익률': 0.0
                }
            
            current_quantity = self._safe_to_int(portfolio[code].get('보유수량',0))
            current_total_buy_amount = self._safe_to_float(portfolio[code].get('매입금액',0))
            
            new_total_quantity = current_quantity + quantity
            new_total_buy_amount = current_total_buy_amount + (trade_price * quantity)
            
            portfolio[code]['보유수량'] = new_total_quantity
            portfolio[code]['매입금액'] = new_total_buy_amount
            if new_total_quantity > 0 :
                portfolio[code]['매입가'] = new_total_buy_amount / new_total_quantity
            else:
                 portfolio[code]['매입가'] = 0

        elif trade_type == '매도':
            if code in portfolio:
                portfolio[code]['보유수량'] -= quantity
                if portfolio[code]['보유수량'] <= 0:
                    self.log(f"{stock_name}({code}) 전량 매도 완료. 포트폴리오 항목 유지 (수량 0).", "INFO")
                    portfolio[code]['보유수량'] = 0 
                    portfolio[code]['매입가'] = 0 
                    portfolio[code]['매입금액'] = 0 
            else:
                self.log(f"매도 체결 처리 오류: {code}가 포트폴리오에 없음.", "WARNING")
                return 

        stock_data = self.watchlist.get(code)
        if stock_data and code in portfolio and portfolio[code]['보유수량'] > 0:
            current_price = stock_data.current_price # watchlist의 StockTrackingData에서 현재가 사용
            avg_buy_price = self._safe_to_float(portfolio[code]['매입가'])
            held_quantity = self._safe_to_int(portfolio[code]['보유수량'])

            portfolio[code]['평가금액'] = current_price * held_quantity
            portfolio[code]['평가손익'] = (current_price - avg_buy_price) * held_quantity
            if avg_buy_price > 0:
                portfolio[code]['수익률'] = ((current_price - avg_buy_price) / avg_buy_price) * 100
            else:
                portfolio[code]['수익률'] = 0.0
        elif code in portfolio and portfolio[code]['보유수량'] == 0 :
            portfolio[code]['평가금액'] = 0
            portfolio[code]['평가손익'] = 0
            portfolio[code]['수익률'] = 0.0

        self.log(f"포트폴리오 업데이트 ({trade_type}): {code} - 보유수량: {portfolio.get(code, {}).get('보유수량')}, 매입가: {portfolio.get(code, {}).get('매입가', 0):.2f}", "INFO")

    def get_account_summary(self):
        """계좌 요약 정보를 반환합니다."""
        summary = {
            "총매입금액": self._safe_to_float(self.account_state.account_summary.get('총매입금액')),
            "총평가금액": self._safe_to_float(self.account_state.account_summary.get('총평가금액')),
            "총평가손익금액": self._safe_to_float(self.account_state.account_summary.get('총평가손익금액')),
            "총수익률": self._safe_to_float(self.account_state.account_summary.get('총수익률(%)')),
            "추정예탁자산": self._safe_to_float(self.account_state.account_summary.get('추정예탁자산')),
            "예수금": self._safe_to_float(self.account_state.account_summary.get('예수금', self.account_state.account_summary.get('d+2추정예수금')))
        }
        self.log(f"계좌 요약 정보: {summary}", "DEBUG")
        return summary

    def request_account_info(self):
        """예수금 상세정보(opw00001)를 요청합니다."""
        if not self.account_state.account_number:
            self.log("계좌번호가 설정되지 않아 예수금 정보를 요청할 수 없습니다.", "ERROR")
            return

        self.log(f"예수금 상세정보 요청 시작 (opw00001). 계좌번호: {self.account_state.account_number}", "INFO")
        inputs = {
            "계좌번호": self.account_state.account_number,
            "비밀번호": self.modules.config_manager.get_setting("계좌정보", "비밀번호", ""), 
            "비밀번호입력매체구분": "00", 
            "조회구분": "2"
        }
        screen_num_account_info = self.modules.screen_manager.get_available_screen("account_info")
        self.modules.kiwoom_api.comm_rq_data(
            rq_name="예수금상세현황요청",
            tr_code="opw00001",
            prev_next=0,
            screen_no=screen_num_account_info,
            input_values_override=inputs
        )
        self.log(f"opw00001 TR 요청 전송 완료. 요청명: 예수금상세현황요청, 화면번호: {screen_num_account_info}", "DEBUG")

    def request_portfolio_info(self, account_number_to_use=None):
        """계좌평가잔고내역(opw00018)을 요청합니다."""
        if account_number_to_use is None:
            account_number_to_use = self.account_state.account_number
        
        if not account_number_to_use:
            self.log("계좌번호가 없어 포트폴리오 정보를 요청할 수 없습니다.", "ERROR")
            return

        self.log(f"계좌 포트폴리오 정보 요청 시작 (opw00018). 계좌번호: {account_number_to_use}", "INFO")
        rq_name = f"계좌잔고조회_{account_number_to_use}"
        inputs = {
            "계좌번호": account_number_to_use,
            "비밀번호": self.modules.config_manager.get_setting("계좌정보", "비밀번호", ""), 
            "비밀번호입력매체구분": "00",
            "조회구분": "1"  # 또는 "2" 등 필요에 따라
        }
        screen_num_portfolio = self.modules.screen_manager.get_available_screen("portfolio_info") # 화면 용도에 맞는 이름 사용
        self.modules.kiwoom_api.comm_rq_data(
            rq_name=rq_name,
            tr_code="opw00018",
            prev_next=0,
            screen_no=screen_num_portfolio,
            input_values_override=inputs
        )
        self.log(f"opw00018 TR 요청 전송 완료. 요청명: {rq_name}, 화면번호: {screen_num_portfolio}", "DEBUG")

    def request_daily_chart_data(self, code, stock_name, base_date_str=None, market_context=None):
        """지정된 종목의 일봉 데이터를 요청합니다 (opt10081)."""
        self.log(f"일봉 데이터 요청 시작 (opt10081). 종목: {stock_name}({code}), 기준일자: {base_date_str if base_date_str else '오늘'}, 시장: {market_context if market_context else '기본'}", "INFO")
        
        # self.log(f"일봉 데이터 요청 시작 (opt10081). 종목: {stock_name}({code}), 기준일자: {base_date_str}, 시장: {market_context}", "INFO")
        if not code:
            self.log(f"종목코드가 없어 {stock_name}의 일봉 데이터를 요청할 수 없습니다.", "ERROR")
            if stock_name in self.watchlist and self.watchlist[stock_name].initial_request_failed_count < self.MAX_INITIAL_REQUEST_FAILURES:
                self.watchlist[stock_name].initial_request_failed_count += 1
                self.log(f"{stock_name} 초기 요청 실패 횟수 증가: {self.watchlist[stock_name].initial_request_failed_count}", "WARNING")
            return

        rq_name = f"일봉조회_{code}_{base_date_str if base_date_str else 'TODAY'}" # 요청 이름에 날짜 포함하여 구분
        # screen_no = self.screen_manager.get_screen_number(f"chart_{code}") # 종목별 화면번호 사용 가능
        # 화면번호 관리를 ScreenManager에 위임 (get_available_screen 사용)
        screen_no = self.modules.screen_manager.get_available_screen(f"chart_{code}")
        if not screen_no:
            self.log(f"{stock_name}({code}) 일봉 데이터 요청 실패: 사용 가능한 화면 번호 없음.", "ERROR")
            # 실패 처리: 관심종목 상태 업데이트 또는 재시도 로직
            if code in self.watchlist:
                self.watchlist[code].daily_chart_error = True
                self.watchlist[code].last_error_message = "사용 가능한 화면 번호 없음"
            self._check_all_data_loaded_and_start_strategy() # 화면번호 부족도 데이터 로드 실패로 간주하고 전략 시작 조건 재확인
            return
        
        self.log(f"opt10081 TR 요청 준비. 요청명: {rq_name}, 종목코드: {code}, 화면번호: {screen_no}, 기준일: {base_date_str if base_date_str else '생략(오늘)'}", "DEBUG")

        # KiwoomAPI의 get_daily_chart 메소드 사용
        # 이 메소드는 내부적으로 input 설정 및 comm_rq_data 호출을 처리합니다.
        self.modules.kiwoom_api.get_daily_chart(
            code=code,
            date_to=base_date_str if base_date_str else "", # KiwoomAPI는 빈 문자열을 오늘 날짜로 처리
            screen_no_override=screen_no, # ScreenManager에서 받은 화면번호 직접 전달
            rq_name_override=rq_name,      # 생성한 요청 이름 전달
            market_context=market_context  # ATS 시장 컨텍스트 전달
        )
        self.log(f"opt10081 TR 요청 전송 (get_daily_chart 호출) 완료. 요청명: {rq_name}, 화면번호: {screen_no}", "DEBUG")

    def _on_daily_chart_data_received(self, rq_name, code, data, is_continuous):
        # ... (rest of the function code commented out or removed)
        pass

    def on_tr_data_received(self, rq_name: str, tr_code: str, data: dict, 연속조회='0'): # 연속조회 파라미터는 KiwoomAPI에서 처리
        self.log(f"TR 데이터 수신 시작 - rq_name: {rq_name}, tr_code: {tr_code}, 연속조회: {연속조회}", "DEBUG")
        self.current_status_message = f"TR 데이터 수신: {tr_code} ({rq_name})"

        if tr_code == "opt10001": 
            code_match = re.search(r"_([A-Za-z0-9]+)$", rq_name)
            if code_match:
                code = code_match.group(1)
                self.log(f"TR 수신 (opt10001) - 종목코드: {code}, 데이터: {data.get('종목명', 'N/A')}, 현재가: {data.get('현재가', 'N/A')}", "INFO")
                self._handle_opt10001_response(rq_name, data) 
            else:
                self.log(f"TR 수신 (opt10001) - rq_name({rq_name})에서 종목코드를 추출하지 못했습니다.", "WARNING")

        elif tr_code == "opw00001": 
            self.log(f"TR 수신 (opw00001) - 예수금 데이터 (요약 로깅)", "INFO") 
            self._handle_opw00001_response(rq_name, data)
            self.initialization_status["deposit_info_loaded"] = True
            self.log("예수금 정보 로드 완료.", "INFO")
            if self.initialization_status["portfolio_loaded"] and not self.watchlist_data_requested:
                self.log("예수금 로드 완료, 포트폴리오도 이미 로드됨. 설정에서 관심종목 로드 시도.", "INFO")
                # self._load_watchlist_from_settings() # 삭제된 라인
            elif not self.initialization_status["portfolio_loaded"]:
                self.log("예수금 로드 완료. 포트폴리오 정보 로딩 대기 중...", "INFO")
            self._check_all_data_loaded_and_start_strategy() # <--- 추가
            
        elif tr_code == "opw00018":
            self.log(f"TR 수신 (opw00018) - 계좌잔고 데이터 (요약 로깅)", "INFO") 
            self._handle_opw00018_response(rq_name, data) 
            
            if 연속조회 != '2': 
                self.initialization_status["portfolio_loaded"] = True
                self.log("계좌 포트폴리오 정보 로드 완료 (최종).", "INFO")
                if self.initialization_status["deposit_info_loaded"] and not self.watchlist_data_requested:
                    self.log("포트폴리오 로드 완료, 예수금도 이미 로드됨. 설정에서 관심종목 로드 시도.", "INFO")
                    # self._load_watchlist_from_settings() # 삭제된 라인
                elif not self.initialization_status["deposit_info_loaded"]:
                    self.log("포트폴리오 로드 완료. 예수금 정보 로딩 대기 중...", "INFO")
                self._check_all_data_loaded_and_start_strategy() # <--- 추가
            else: 
                self.log(f"계좌 포트폴리오 정보 로드 중... (연속조회 진행 중 - rq_name: {rq_name})", "INFO")
        
        # opt10081 관련 로직은 완전히 제거됨
        
        else:
            self.log(f"미처리 TR 데이터 수신 - rq_name: {rq_name}, tr_code: {tr_code}", "DEBUG")

        if rq_name in self.current_async_calls:
            self.current_async_calls.remove(rq_name)
            self.log(f"비동기 TR 요청 완료: {rq_name}", "DEBUG")

        self.current_status_message = f"TR 데이터 처리 완료: {tr_code} ({rq_name})"
        
    # def _initialize_all_watchlist_data(self): # REMOVED
    #     pass

    def _check_all_data_loaded_and_start_strategy(self):
        self.log(f"[STRATEGY_INTERNAL] _check_all_data_loaded_and_start_strategy 호출됨. is_running: {self.is_running}", "DEBUG")
        # self.pending_daily_chart_requests 확인 로직 제거

        if self.is_running: 
            self.log("전략이 이미 실행 중입니다. _check_all_data_loaded_and_start_strategy 중복 호출 방지.", "DEBUG")
            return

        if not (self.initialization_status["account_info_loaded"] and \
                self.initialization_status["deposit_info_loaded"] and \
                self.initialization_status["portfolio_loaded"]):
            self.log("계좌, 예수금 또는 포트폴리오 정보가 아직 모두 로드되지 않아 전략을 시작할 수 없습니다.", "WARNING")
            missing_items = []
            if not self.initialization_status["account_info_loaded"]: missing_items.append("계좌정보")
            if not self.initialization_status["deposit_info_loaded"]: missing_items.append("예수금")
            if not self.initialization_status["portfolio_loaded"]: missing_items.append("포트폴리오")
            self.log(f"누락된 초기 정보: {', '.join(missing_items)}", "DEBUG")
            return

        if not self.watchlist: 
            self.log("관심종목이 없어 전략을 시작할 수 없습니다. (설정 파일 확인 필요)", "WARNING")
            self.current_status_message = "오류: 관심종목 없음. 전략 시작 불가."
            return
        else: # 관심종목이 있을 경우 상세 로깅
            self.log(f"현재 관심종목 {len(self.watchlist)}개 로드됨. 목록:", "DEBUG")
            for c, sd in self.watchlist.items():
                self.log(f"  - {sd.stock_name}({c}): 전일종가({sd.yesterday_close_price}), 상태({sd.strategy_state.name})", "DEBUG")

        # daily_chart_error 및 yesterday_close_price == 0 에 대한 전체 전략 시작 중단 로직 제거
        # yesterday_close_price == 0인 종목은 개별적으로 매매 전략에서 제외될 수 있음 (경고 로깅만 함)
        for code, stock_data in self.watchlist.items():
            if stock_data.yesterday_close_price == 0:
                self.log(f"관심종목 {stock_data.stock_name}({code})의 설정된 'yesterday_close_price'가 0입니다. 해당 종목은 매매 전략에서 제외될 수 있습니다.", "WARNING")
        
        self.log("모든 계좌/포트폴리오/관심종목(설정) 데이터 준비 완료. 실제 전략 시작 로직 수행.", "INFO")
        
        for code in self.watchlist.keys():
            self.subscribe_stock_real_data(code)
        self.log(f"{len(self.watchlist)}개 관심종목에 대한 실시간 시세 구독 요청 완료.", "INFO")

        self.is_running = True
        self.is_initialized_successfully = True 
        
        today_str = datetime.now().strftime("%Y-%m-%d")
        if self.today_date_for_buy_limit != today_str:
            self.log(f"날짜 변경 감지: {self.today_date_for_buy_limit} -> {today_str}. 일일 매수 횟수 초기화.", "INFO")
            self.today_date_for_buy_limit = today_str
            self.daily_buy_executed_count = 0

        self.check_timer.start()
        self.log(f"조건 확인 타이머 시작 (주기: {self.check_timer.interval() / 1000}초).", "INFO")
        if self.settings.periodic_report_enabled:
            self.status_report_timer.setInterval(self.settings.periodic_report_interval_seconds * 1000)
            self.status_report_timer.start()
            self.log(f"주기적 상태 보고 타이머 시작 (주기: {self.settings.periodic_report_interval_seconds}초).", "INFO")
        
        self.daily_snapshot_timer.start()
        self.log(f"일일 스냅샷 타이머 시작 (주기: {self.daily_snapshot_timer.interval() / (3600 * 1000)}시간).", "INFO")
        self.log(f"[STRATEGY_INTERNAL] _check_all_data_loaded_and_start_strategy: Timers started. is_running={self.is_running}, is_initialized_successfully={self.is_initialized_successfully}", "INFO")
        self.record_daily_snapshot_if_needed() 

        if self.modules.kiwoom_api and hasattr(self.modules.kiwoom_api, 'signal_strategy_ready'):
            self.modules.kiwoom_api.signal_strategy_ready()
            self.log("KiwoomAPI에 전략 준비 완료 신호 전송.", "INFO")
        
        self.current_status_message = "전략 실행 중. 시장 데이터 감시 및 조건 확인 중."
        self.log(f"=== 전략이 성공적으로 시작되었습니다. is_running: {self.is_running} ===", "IMPORTANT")


    def _parse_chejan_data(self, chejan_data_param):
        """수신된 체결 데이터를 파싱하여 내부 형식으로 변환합니다."""
        parsed_data = {}
        for fid_str, value_str in chejan_data_param.items():
            # 숫자형 FID 목록 (정수형, 실수형 구분하여 처리)
            # KiwoomAPI FID 명세 참조 필요
            # 예시: 주문/체결 관련 FID 중 숫자형으로 처리해야 할 것들
            # 정수형 FID 예시
            int_fids = ['904', '905', '906', '911', '930', '932', '13', '14'] 
            # 실수형 FID 예시 (가격, 수익률 등)
            float_fids = ['910', '931', '933', '950', '951', '10', '938', '939'] # 수수료(938), 세금(939) 추가

            if fid_str in int_fids:
                parsed_data[fid_str] = self._safe_to_int(value_str)
            elif fid_str in float_fids:
                parsed_data[fid_str] = self._safe_to_float(value_str)
            else:
                parsed_data[fid_str] = str(value_str).strip() if value_str is not None else ''
        return parsed_data

    def _find_active_order_entry(self, code_from_chejan, chejan_data_dict):
        """
        체결 데이터에 해당하는 활성 주문 항목을 self.account_state.active_orders에서 찾습니다.
        주문번호(FID 9203)를 우선적으로 사용합니다.
        """
        order_no_from_chejan = chejan_data_dict.get('9203') # 주문번호

        self.log(f"_find_active_order_entry: 체결데이터 주문번호({order_no_from_chejan}), 종목코드({code_from_chejan})", "DEBUG")

        if not self.account_state or not self.account_state.active_orders:
            self.log("_find_active_order_entry: self.account_state.active_orders가 비어있거나 없습니다.", "WARNING")
            return None

        # 주문번호로 검색
        if order_no_from_chejan:
            for rq_name, order_details in self.account_state.active_orders.items():
                # 체결 데이터의 종목코드는 'A' 접두사가 있을 수 있으므로, 비교 시에는 순수 코드를 사용해야 할 수 있음
                # 여기서는 order_details.get('code')가 순수 코드라고 가정
                if order_details.get('order_no') == order_no_from_chejan and order_details.get('code') == code_from_chejan:
                    self.log(f"_find_active_order_entry: 주문번호({order_no_from_chejan})와 종목코드({code_from_chejan})로 활성 주문 발견 (RQName: {rq_name})", "INFO")
                    found_order = order_details.copy()
                    found_order['rq_name_key'] = rq_name 
                    return found_order
        
        self.log(f"_find_active_order_entry: 주문번호({order_no_from_chejan}) 및 종목코드({code_from_chejan})로 일치하는 활성 주문을 찾지 못했습니다.", "WARNING")
        return None

    def on_chejan_data_received(self, gubun, chejan_data):  # item_cnt, fid_list_str 제거, chejan_data는 dict
        self.log(f"체결/잔고 데이터 수신 - 구분: {gubun}", "DEBUG")  # item_cnt 관련 로그 제거
        self.current_status_message = f"체결/잔고 수신 (구분: {gubun})"
        
        # fid_list_str을 이용한 파싱 로직은 KiwoomAPI에서 처리하고 결과를 chejan_data로 전달받으므로 여기서는 불필요.
        if not chejan_data or not isinstance(chejan_data, dict):
            self.log(f"수신된 체결 데이터(chejan_data)가 없거나 딕셔너리 형태가 아닙니다. 타입: {type(chejan_data)}", "WARNING")
            return

        self.log(f"체결/잔고 상세: {chejan_data}", "DEBUG")

        rq_name = chejan_data.get('주문번호', '') # TR 요청명이 아닌 주문번호를 사용
        code = chejan_data.get('종목코드', '')
        if code.startswith('A'): code = code[1:] # 'A' 제거

        stock_info = self.watchlist.get(code)
        stock_name = stock_info.stock_name if stock_info else chejan_data.get('종목명', 'N/A')
        if not stock_name and stock_info: stock_name = stock_info.stock_name # 다시 한번 확인

        active_order_entry = self._find_active_order_entry(code, chejan_data)
        
        original_rq_name_from_order = None
        if active_order_entry:
            original_rq_name_from_order = active_order_entry.get('rq_name')
            self.log(f"체결 데이터({code}, 주문번호 {rq_name})에 대한 활성 주문 항목 발견: RQName='{original_rq_name_from_order}'", "DEBUG")
        else:
            self.log(f"체결 데이터({code}, 주문번호 {rq_name})에 대한 활성 주문 항목을 찾지 못했습니다. 신규 주문 또는 부분 체결일 수 있습니다.", "DEBUG")


        if gubun == '0':  # 주문체결통보
            self.log(f"주문 체결 통보 - 종목: {stock_name}({code}), 주문번호: {rq_name}", "INFO")
            self._handle_order_execution_report(chejan_data, active_order_entry, original_rq_name_from_order or rq_name, code, stock_name, stock_info)
        elif gubun == '1':  # 국내주식 잔고통보
            self.log(f"계좌 잔고 변경 통보 - 종목: {stock_name}({code})", "INFO")
            self._handle_balance_update_report(chejan_data, active_order_entry, original_rq_name_from_order or rq_name, code, stock_name, stock_info)
        else:
            self.log(f"알 수 없는 체결 구분 값: {gubun}", "WARNING")
        
        self.current_status_message = f"체결/잔고 처리 완료 (구분: {gubun}, 종목: {code})"

    def _handle_order_execution_report(self, chejan_data, active_order_entry, rq_name, code, stock_name, stock_info: StockTrackingData):
        """gubun='0' (주문접수/확인) 시 체결 데이터를 처리합니다."""
        if active_order_entry is None: # active_order_entry가 None인지 확인
            self.log(f"주문 접수/확인 처리 중단 ({code}): 연관된 활성 주문 정보를 찾을 수 없습니다 (active_order_entry is None). 체결 데이터: {chejan_data}", "WARNING")
            # 이 경우, 해당 체결이 어떤 주문에 대한 것인지 알 수 없으므로 추가 처리가 어려울 수 있음.
            # 필요하다면, chejan_data의 주문번호(9203)를 기반으로 별도의 로그를 남기거나,
            # 또는 active_orders에 없는 주문번호에 대한 체결로 간주하고 다른 방식으로 처리할 수 있음.
            # 현재는 경고 로깅 후 함수 종료.
            return

        # active_order_entry가 None이 아님이 보장되므로 아래 코드 실행 가능
        # === 주문번호 업데이트 로직 추가 시작 ===
        if active_order_entry.get('order_no') is None and chejan_data.get("9203"):
            active_order_entry['order_no'] = chejan_data.get("9203")
            # rq_name_key를 찾아서 로그에 포함 (디버깅 용이성)
            rq_name_for_log = active_order_entry.get('rq_name_key', 'N/A') 
            if rq_name_for_log == 'N/A' and 'rq_name' in active_order_entry: # 이전 버전 호환 또는 다른 경로로 설정된 경우
                 rq_name_for_log = active_order_entry['rq_name']

            self.log(f"활성 주문에 API 주문번호 업데이트: {active_order_entry['order_no']} (RQName: {rq_name_for_log}, Code: {code})", "INFO")
        # === 주문번호 업데이트 로직 추가 끝 ===

        order_status = chejan_data.get("913") 
        order_qty = self._safe_to_int(chejan_data.get("900"))
        filled_qty_total = self._safe_to_int(chejan_data.get("902"))
        unfilled_qty_api = self._safe_to_int(chejan_data.get("901"))
        
        # active_order_entry가 None이 아님이 보장되므로 아래 코드 실행 가능
        calculated_unfilled_qty = active_order_entry['order_qty'] - filled_qty_total
        unfilled_qty = calculated_unfilled_qty # API의 901보다 계산값을 우선
        if unfilled_qty_api != calculated_unfilled_qty:
            self.log(f"미체결수량 ({code}): API값({unfilled_qty_api}) vs 계산값({calculated_unfilled_qty}). 계산값 사용.", "DEBUG")

        active_order_entry['unfilled_qty'] = unfilled_qty
        active_order_entry['order_status'] = order_status

        self.log(f"주문 접수/확인 ({code}): 주문번호({active_order_entry['order_no']}), 상태({order_status}), 주문수량({order_qty}), 체결({filled_qty_total}), 미체결({unfilled_qty})", "INFO")

        if filled_qty_total > 0:
            last_filled_price = self._safe_to_float(chejan_data.get("10")) 
            last_filled_qty = self._safe_to_int(chejan_data.get("911"))

            if last_filled_qty > 0:
                trade_type = active_order_entry['order_type']
                self.log(f"부분/전체 체결 발생 ({code}, {stock_name}): 유형({trade_type}), 체결가({last_filled_price}), 체결량({last_filled_qty})", "INFO")
                
                self.update_portfolio_on_execution(code, stock_name, last_filled_price, last_filled_qty, trade_type)

                self.modules.db_manager.add_trade_record(
                    timestamp=get_current_time_str(),
                    order_no=active_order_entry['order_no'],
                    original_rq_name=rq_name,
                    code=code,
                    stock_name=stock_name,
                    trade_type=trade_type,
                    quantity=last_filled_qty,
                    price=last_filled_price,
                    reason=active_order_entry.get('reason', '')
                )
                self.log(f"DB에 체결 기록 저장 완료: {code}, {trade_type}, {last_filled_qty}주 @ {last_filled_price}원", "DEBUG")

        if unfilled_qty == 0 and order_status == '체결':
            self.log(f"주문 전량 체결 완료 ({code}, {stock_name}): 주문번호({active_order_entry['order_no']})", "INFO")
            if active_order_entry['order_type'] == '매수':
                stock_info.strategy_state = TradingState.BOUGHT
                # 포트폴리오에서 최종 평균 매입가와 수량 가져오기
                portfolio_item = self.account_state.portfolio.get(code)
                if portfolio_item:
                    stock_info.avg_buy_price = self._safe_to_float(portfolio_item.get('매입가'))
                    stock_info.total_buy_quantity = self._safe_to_int(portfolio_item.get('보유수량'))
                    stock_info.current_high_price_after_buy = stock_info.avg_buy_price # 매수 완료 시 고점은 매수가로 초기화
                    stock_info.buy_timestamp = datetime.now() # 매수 완료 시간 기록
                    self.log(f"매수 완료 후 StockTrackingData 업데이트 ({code}): 매수가({stock_info.avg_buy_price}), 수량({stock_info.total_buy_quantity}), 초기 고점({stock_info.current_high_price_after_buy}), 매수시간({stock_info.buy_timestamp})", "DEBUG")
                else:
                    self.log(f"매수 완료 후 포트폴리오 항목을 찾을 수 없어 StockTrackingData 업데이트 실패 ({code})", "ERROR")
            elif active_order_entry['order_type'] == '매도':
                 portfolio_item = self.account_state.portfolio.get(code)
                 if portfolio_item and portfolio_item.get('보유수량', 0) == 0:
                     self.log(f"{code} 전량 매도 완료. 관련 전략 정보 초기화.", "INFO")
                     self.reset_stock_strategy_info(code) 
                 else: 
                     stock_info.strategy_state = TradingState.PARTIAL_SOLD
                     self.log(f"{code} 부분 매도 완료. 상태 변경: -> {stock_info.strategy_state}", "INFO")
            else: # 매수/매도가 아닌 다른 주문 유형 (이론상 없어야 함)
                self.log(f"주문 전량 체결 완료 후 상태 변경 로직에서 알 수 없는 주문 유형: {active_order_entry['order_type']} ({code})", "WARNING")
            self.log(f"{code} ({stock_name}) 상태 변경: -> {stock_info.strategy_state} (사유: 전량체결)", "INFO")

        # === 추가된 로직 시작 ===
        # 주문이 어떤 형태로든 종료되었는지 (미체결 0) 확인하여 last_order_rq_name 정리
        # active_order_entry가 None이 아니고, stock_info도 None이 아닌 경우에만 실행
        if active_order_entry and stock_info and active_order_entry.get('unfilled_qty', -1) == 0:
            current_rq_name_key = active_order_entry.get('rq_name_key') # _find_active_order_entry에서 설정한 키
            
            # 현재 처리 중인 주문의 rq_name과 stock_info에 기록된 last_order_rq_name이 일치할 때만 초기화
            if stock_info.last_order_rq_name == current_rq_name_key:
                stock_info.last_order_rq_name = None
                self.log(f"{code}의 last_order_rq_name을 None으로 설정 (unfilled_qty 0 처리). 이전 RQName: {current_rq_name_key}", "INFO")
            elif stock_info.last_order_rq_name and stock_info.last_order_rq_name != current_rq_name_key:
                self.log(f"{code}의 last_order_rq_name ({stock_info.last_order_rq_name})이 현재 처리 중인 주문의 RQName ({current_rq_name_key})과 다릅니다. last_order_rq_name 변경 안함.", "DEBUG")
            elif not stock_info.last_order_rq_name:
                 self.log(f"{code}의 last_order_rq_name이 이미 None입니다. 추가 변경 없음 (unfilled_qty 0 처리).", "DEBUG")


            # active_orders 딕셔너리에서도 해당 주문 제거
            if current_rq_name_key and current_rq_name_key in self.account_state.active_orders:
                self.log(f"active_orders에서 {current_rq_name_key} 제거 시도 (unfilled_qty 0 처리)", "DEBUG")
                del self.account_state.active_orders[current_rq_name_key]
                self.log(f"active_orders에서 {current_rq_name_key} 제거 완료.", "INFO")
            elif current_rq_name_key:
                self.log(f"active_orders에서 {current_rq_name_key}를 찾을 수 없어 제거 못함 (unfilled_qty 0 처리). active_orders: {list(self.account_state.active_orders.keys())}", "WARNING")
            # else: current_rq_name_key가 없는 경우, active_orders에서 제거할 키 특정 불가
        # === 추가된 로직 끝 ===


    def _handle_balance_update_report(self, chejan_data, active_order_entry, rq_name, code, stock_name, stock_info: StockTrackingData):
        """gubun='1' (잔고변경) 시 체결 데이터를 처리합니다."""
        if active_order_entry is None:
            self.log(f"잔고 변경 보고 처리 중단 ({code}, {stock_name}): 연관된 활성 주문 정보를 찾을 수 없습니다 (active_order_entry is None). 체결 데이터: {chejan_data}", "WARNING")
            # self.log(f"잔고 변경 보고 ({code}, {stock_name}): 연관 주문 없음, 실현손익({realized_pnl}), 수수료({commission}), 세금({tax})", "INFO") # 이 로그는 active_order_entry가 None일 때 order_no를 가져올 수 없으므로 수정 필요
            # realized_pnl, commission, tax 등은 active_order_entry와 무관하게 로깅 가능
            realized_pnl_val = self._safe_to_float(chejan_data.get("950"))
            commission_val = self._safe_to_float(chejan_data.get("938"))
            tax_val = self._safe_to_float(chejan_data.get("939"))
            self.log(f"잔고 변경 보고 ({code}, {stock_name}): 연관 주문 없음. 실현손익({realized_pnl_val}), 수수료({commission_val}), 세금({tax_val})", "INFO")
            return

        realized_pnl = self._safe_to_float(chejan_data.get("950"))
        commission = self._safe_to_float(chejan_data.get("938")) 
        tax = self._safe_to_float(chejan_data.get("939"))
        
        # 이제 active_order_entry가 None이 아님이 보장되므로 .get('order_no') 호출 안전
        self.log(f"잔고 변경 보고 ({code}, {stock_name}): 주문번호({active_order_entry.get('order_no')}), 실현손익({realized_pnl}), 수수료({commission}), 세금({tax})", "INFO")

        if realized_pnl != 0 or commission != 0 or tax != 0 :
            self.log(f"DB Trade Record 업데이트 필요 (미구현 - 실현손익/수수료/세금): {code}, 주문({active_order_entry.get('order_no')})", "DEBUG")




    def report_periodic_status(self):
        if not self.is_running and not self.is_initialized_successfully:
            self.log(f"주기적 상태 보고: 초기화 진행 중 또는 실패. 현재 상태: {self.current_status_message}", "INFO")
            self.log(f"초기화 단계별 상태: {self.initialization_status}", "DEBUG")
            # 초기화 실패 또는 지연 시 관련 정보 추가 로깅
            if not self.initialization_status["account_info_loaded"]:
                self.log("계좌 정보 로드를 기다리고 있거나 실패했습니다.", "WARNING")
            elif not self.initialization_status["deposit_info_loaded"]:
                self.log("예수금 정보 TR 응답을 기다리고 있습니다 (opw00001).", "INFO")
            elif not self.initialization_status["portfolio_loaded"]:
                self.log("포트폴리오 정보 TR 응답을 기다리고 있습니다 (opw00018).", "INFO")
            
            pending_charts = self.get_pending_daily_chart_requests_count()
            if pending_charts > 0:
                self.log(f"{pending_charts}건의 관심종목 일봉 데이터 요청이 처리 중입니다.", "INFO")
            return
        
        self.log(f"===== 주기적 상태 보고 ({get_current_time_str()}) =====", "INFO")
        self.log(
            f"전략 실행 상태: {'실행 중' if self.is_running else '중지됨'}, "
            f"최종 초기화 성공: {self.is_initialized_successfully}",
            "INFO"
        )
        self.log(f"현재 상태 메시지: {self.current_status_message}", "INFO")
        
        if self.account_state.account_number:
            self.log(f"계좌번호: {self.account_state.account_number}", "INFO")
            # 예수금 정보 간단히 로깅 (상세 정보는 TR 수신 시 로깅됨)
            if (self.initialization_status["deposit_info_loaded"] and 
                    self.account_state.account_summary.get('예수금')):
                self.log(f"예수금: {self.account_state.account_summary.get('예수금')}", "INFO")
            else:
                self.log("예수금 정보 로딩 중이거나 사용 불가.", "INFO")
        else:
            self.log("계좌번호가 설정되지 않았습니다.", "WARNING")

        # 보유 종목 요약
        portfolio_summary = self.get_current_portfolio_summary()
        if portfolio_summary:
            self.log(f"보유 종목 ({len(portfolio_summary)}개):", "INFO")
            if portfolio_summary != ["보유 종목 없음"]:
                for item_summary_str in portfolio_summary:
                    self.log(f"  - {item_summary_str}", "INFO")
            elif portfolio_summary == ["보유 종목 없음"]:
                self.log("  - 보유 종목 없음.", "INFO")
        else:
            self.log("보유 종목 없음.", "INFO")

        # 미체결 주문 요약
        active_orders_summary = self.get_active_orders_summary()
        if active_orders_summary and active_orders_summary != ["활성 주문 없음"]:
            self.log(f"미체결 주문 ({len(active_orders_summary)}건):", "INFO")
            for order_summary_str in active_orders_summary:
                self.log(f"  - {order_summary_str}", "INFO")
        elif active_orders_summary == ["활성 주문 없음"]:
            self.log("미체결 주문 없음.", "INFO")
        else:  # active_orders_summary가 비어있는 경우 (None 또는 빈 리스트)
            self.log("미체결 주문 없음.", "INFO")

        # 관심 종목 상태 요약
        watchlist_summary_list = self.get_watchlist_summary()
        if watchlist_summary_list and watchlist_summary_list != ["관심 종목 없음"]:
            self.log(f"관심 종목 ({len(watchlist_summary_list)}개):", "INFO")
            for summary_str in watchlist_summary_list:
                # get_watchlist_summary에서 생성된 문자열을 그대로 로깅
                self.log(f"  - {summary_str}", "INFO")
        elif watchlist_summary_list == ["관심 종목 없음"]:
            self.log("  - 관심 종목 없음.", "INFO")  # 일관성을 위해 들여쓰기 추가
        else:  # watchlist_summary_list가 비어있는 경우 (None 또는 빈 리스트)
            self.log("  - 관심 종목 없음.", "INFO")  # 일관성을 위해 들여쓰기 추가
        
        pending_charts = self.get_pending_daily_chart_requests_count()
        if pending_charts > 0:
            self.log(f"{pending_charts}건의 관심종목 일봉 데이터 요청이 백그라운드 처리 중입니다.", "INFO")

        self.log(f"일일 매수 실행 횟수: {self.daily_buy_executed_count} / {self.settings.max_daily_buy_count}", "INFO")
        self.log("===========================================", "INFO")

    def record_daily_snapshot_if_needed(self):
        today_date_str = datetime.now().strftime("%Y-%m-%d")
        if self.last_snapshot_date == today_date_str:
            self.log(f"일별 계좌 스냅샷은 오늘({today_date_str}) 이미 기록되었습니다.", "DEBUG")
            return

        if not self.is_market_hours() and datetime.now().hour >= 15: # 장 종료 후 (오후 3시 이후)에만 기록 시도
            self.log(f"장 종료 확인, 일별 계좌 스냅샷 기록 시도: {today_date_str}", "INFO")
            summary = self.get_account_summary() # 예수금, 총매입, 총평가, 손익, 수익률, 추정예탁자산 포함
            portfolio_snapshot = copy.deepcopy(self.account_state.portfolio)

            # add_daily_snapshot 호출 시, database.py에 정의된 파라미터 순서와 내용에 맞게 전달
            if self.modules.db_manager.add_daily_snapshot(
                date=today_date_str,
                deposit=summary.get('예수금', 0),
                total_purchase_amount=summary.get('총매입금액', 0),
                total_evaluation_amount=summary.get('총평가금액', 0),
                total_profit_loss_amount=summary.get('총평가손익금액', 0),
                total_return_rate=summary.get('총수익률', 0),
                portfolio_details_dict=portfolio_snapshot, 
                total_asset_value=summary.get('추정예탁자산') # total_asset_value는 optional, deposit + total_evaluation_amount으로도 계산될 수 있음
            ):
                self.log(f"일별 계좌 스냅샷 DB 저장 완료: {today_date_str}", "INFO")
                self.last_snapshot_date = today_date_str
            else:
                self.log(f"일별 계좌 스냅샷 DB 저장 실패 또는 이미 존재: {today_date_str}", "ERROR") # 메시지 명확화
        else:
            now_time = datetime.now()
            self.log(f"일별 계좌 스냅샷 기록 조건 미충족: 현재시간({now_time.strftime('%H:%M:%S')}), 장운영여부({self.is_market_hours()})", "DEBUG")


    def _ensure_numeric_fields(self, data_dict):
        """주어진 딕셔너리의 특정 필드들을 숫자형(int, float)으로 변환 시도합니다."""
        if not isinstance(data_dict, dict):
            # self.log(f"_ensure_numeric_fields: 입력값이 딕셔너리가 아님 ({type(data_dict)}). 원본 반환.", "WARNING")
            return data_dict

        # 숫자형으로 변환할 가능성이 있는 필드명 목록 (API 응답 참고)
        # 정수형 필드 (수량, 횟수 등)
        INT_FIELDS = ["보유수량", "주문수량", "체결수량", "미체결수량", "상한가수량", "하한가수량", "누적거래량", "거래량", "체결량",
                      "매도호가수량1", "매수호가수량1", "매도호가총잔량", "매수호가총잔량", "총주문수량", "총체결수량",
                      "상장주식수", "외국인현재보유수량", "프로그램순매수", "시간외매도잔량", "시간외매수잔량"]
        # 실수형 필드 (가격, 비율, 금액 등)
        FLOAT_FIELDS = ["현재가", "시가", "고가", "저가", "기준가", "전일대비", "등락률", "상한가", "하한가", "매입가", "평가금액",
                        "평가손익", "수익률", "매도호가1", "매수호가1", "누적거래대금", "총매입금액", "총평가금액", "총평가손익금액",
                        "총수익률(%)", "추정예탁자산", "예수금", "d+2추정예수금", "주당액면가", "PER", "EPS", "PBR", "BPS",
                        "시가총액", "52주최고가", "52주최저가", "연중최고가", "연중최저가", "외국인소진율", "체결강도",
                        "시간외단일가", "시간외등락률"]
        
        # 기타 숫자형 필드 (KiwoomAPI FID 직접 사용 시)
        # 예: 체결데이터 FID (900:주문수량, 901:미체결수량, 902:체결누계수량, 903:평균체결가, 910:체결가, 911:체결량 등)
        # 이 함수는 주로 텍스트 기반 필드명에 대해 작동. FID는 parse_chejan_data 등에서 이미 처리될 수 있음.

        cleaned_dict = {}
        for key, value in data_dict.items():
            if isinstance(value, str): # 문자열일 때만 변환 시도
                cleaned_value_str = value.strip().replace('+', '').replace('-', '').replace('%', '').replace(',', '')
                if not cleaned_value_str: # 빈 문자열 또는 공백만 있는 경우
                    if key in INT_FIELDS:
                        cleaned_dict[key] = 0
                    elif key in FLOAT_FIELDS:
                        cleaned_dict[key] = 0.0
                    else:
                        cleaned_dict[key] = value 
                    continue

                try:
                    if key in INT_FIELDS:
                        cleaned_dict[key] = int(cleaned_value_str)
                    elif key in FLOAT_FIELDS:
                        cleaned_dict[key] = float(cleaned_value_str)
                    else: 
                        cleaned_dict[key] = value
                except ValueError:
                    cleaned_dict[key] = value 
            else: 
                cleaned_dict[key] = value
        
        return cleaned_dict

    def _on_disconnected(self):
        self.log("Kiwoom API 연결 끊김.", "CRITICAL")
        self.is_running = False
        if self.check_timer.isActive(): self.check_timer.stop()
        if self.status_report_timer.isActive(): self.status_report_timer.stop()
        if self.daily_snapshot_timer.isActive(): self.daily_snapshot_timer.stop()
        # 필요한 경우, UI에 상태 업데이트 또는 재연결 시도 로직 추가

    def _on_error(self, error_code, error_message):
        self.log(f"Kiwoom API 오류 발생: 코드({error_code}), 메시지({error_message})", "ERROR")
        # 오류 코드에 따른 처리 (예: OP_ERR_SISE_OVERFLOW 등)
        if error_code == -207: # "-207": "시세과부하보호", // OP_ERR_SISE_OVERFLOW
            self.log("시세 과부하 보호 상태입니다. 잠시 후 재시도 필요.", "WARNING")
            # TR 요청 간격 증가 또는 일시 중지 등의 조치 고려

    def get_pending_daily_chart_requests_count(self):
        return 0 # 일봉 요청은 더 이상 사용하지 않음

    def get_active_orders_summary(self):
        summary = []
        if hasattr(self, 'account_state') and self.account_state and hasattr(self.account_state, 'active_orders') and self.account_state.active_orders:
            for rq_name, order in self.account_state.active_orders.items(): # self.active_orders -> self.account_state.active_orders
                # order 딕셔너리에서 키 존재 여부 확인 추가
                stock_name = order.get('stock_name', 'N/A')
                code = order.get('code', 'N/A')
                order_type = order.get('order_type', 'N/A')
                order_qty = order.get('order_qty', 0)
                order_price = order.get('order_price', 0)
                unfilled_qty = order.get('unfilled_qty', 0)
                order_status = order.get('order_status', 'N/A')
                summary.append(f"RQ:{rq_name}, {stock_name}({code}), {order_type} {order_qty}@{order_price}, 미체결:{unfilled_qty}, 상태:{order_status}")
        return summary if summary else ["활성 주문 없음"]

    def get_watchlist_summary(self):
        summary = []
        for code, stock_data in self.watchlist.items(): # stock -> stock_data로 변수명 변경하여 명확화
            state_name = stock_data.strategy_state.name if stock_data.strategy_state else 'N/A' # Enum의 이름 사용
            summary.append(f"{stock_data.stock_name or code}({code}): 현재가 {stock_data.current_price if stock_data.current_price != 0 else 'N/A'}, 상태: {state_name}")
        return summary if summary else ["관심 종목 없음"]

    def get_current_portfolio_summary(self):
        summary = []
        if self.account_state.portfolio: # self.portfolio -> self.account_state.portfolio
            for code, item in self.account_state.portfolio.items(): # self.portfolio -> self.account_state.portfolio
                if item.get('보유수량', 0) > 0:
                     summary.append(f"{item.get('stock_name', code)}({code}): {item.get('보유수량')}주, 평가액 {item.get('평가금액', 0):,.0f} (수익률 {item.get('수익률', 0):.2f}%)")
        return summary if summary else ["보유 종목 없음"]

    def get_pending_orders(self) -> List[Dict[str, Any]]:
        """
        현재 활성화된 (미체결) 주문 목록을 반환합니다.
        enhanced_signal_handler가 기대하는 형태로 가공합니다.
        """
        pending_orders_details = []
        if not self.account_state or not self.account_state.active_orders:
            self.log("활성 주문 정보(account_state.active_orders)가 없습니다.", "DEBUG")
            return pending_orders_details

        self.log(f"get_pending_orders 호출됨. 현재 active_orders: {self.account_state.active_orders}", "DEBUG")

        for order_key, order_data in self.account_state.active_orders.items():
            # active_orders의 각 항목이 주문 정보를 담고 있다고 가정합니다.
            # 필요한 필드: 'order_no', 'code', 'is_buy_order' (True/False)
            # 'is_buy_order'는 주문 유형(order_type 또는gubun 등)을 통해 판단해야 할 수 있습니다.
            # 예시: order_data에 '주문번호', '종목코드', '주문구분' (매수/매도 문자열) 필드가 있다고 가정
            
            original_order_no = order_data.get('주문번호') # 실제 필드명 확인 필요
            code = order_data.get('종목코드')             # 실제 필드명 확인 필요
            order_type_str = order_data.get('주문구분')     # 실제 필드명 확인 필요 (예: "매수", "매도")

            if not original_order_no or not code or not order_type_str:
                self.log(f"주문 상세 정보 부족 (order_key: {order_key}): {order_data}", "WARNING")
                continue

            is_buy_order = True if "매수" in order_type_str else False # 실제 조건 확인 필요

            pending_orders_details.append({
                'order_no': original_order_no,
                'code': code,
                'is_buy_order': is_buy_order,
                'raw_order_data': order_data # 디버깅 및 추가 정보 활용을 위해 원본 데이터 포함
            })
            
        self.log(f"반환될 미체결 주문 상세: {pending_orders_details}", "DEBUG")
        return pending_orders_details

    def _handle_opt10001_response(self, rq_name, data):
        """ opt10001 (주식기본정보) 응답 처리 """
        self.log(f"TR 데이터 수신 (opt10001 - {rq_name}): 처리는 get_stock_basic_info 내부에서 완료.", "DEBUG")
        # get_stock_basic_info 또는 이와 유사한 함수 호출 결과로 이미 처리되었을 수 있음.
        # KiwoomAPI에서 캐시에 저장하므로, Strategy에서 별도 처리 안 할 수도 있음.
        # 필요시 여기서 추가 로직 (예: stock_data 업데이트)
        code_match = re.search(r"opt10001_([A-Za-z0-9]+)_", rq_name) # RQName의 종목코드 부분만 추출하도록 수정
        if code_match:
            code = code_match.group(1)
            stock_info = self.watchlist.get(code) # self.stock_data -> self.watchlist.get(code)
            if stock_info:
                # 예시: 현재가, 종목명 등 주요 정보 업데이트
                single_data = data.get('single_data', {})
                if single_data:
                    stock_info.stock_name = single_data.get('종목명', stock_info.stock_name) # stock_data[code] -> stock_info
                    stock_info.current_price = self._safe_to_float(single_data.get('현재가', stock_info.current_price)) # stock_data[code] -> stock_info
                    self.log(f"opt10001 응답으로 {code} 기본 정보 일부 업데이트: {stock_info.stock_name}, 현재가: {stock_info.current_price}", "DEBUG")
            else:
                self.log(f"opt10001 응답 처리 중: RQName {rq_name}에 해당하는 종목({code})이 watchlist에 없음", "WARNING")
        else:
            self.log(f"opt10001 응답 처리 중: RQName {rq_name}에서 종목코드를 추출할 수 없음", "WARNING")

    def _handle_opw00001_response(self, rq_name, data):
        """ opw00001 (예수금 상세현황) 응답 처리 """
        if 'single_data' in data:
            deposit_info = self._ensure_numeric_fields(data['single_data'])
            self.account_state.account_summary.update(deposit_info)
            self.log(f"예수금 정보 업데이트 (opw00001): {deposit_info}", "INFO")
            self.account_info_requested_time = None # 요청 완료 처리

    def _handle_opw00018_response(self, rq_name, data):
        """ opw00018 (계좌평가잔고내역) 응답 처리 """
        if 'single_data' in data:
            summary_info = self._ensure_numeric_fields(data['single_data'])
            self.account_state.account_summary.update(summary_info)
            self.log(f"계좌 평가 요약 정보 업데이트 (opw00018): {summary_info}", "INFO")

        if 'multi_data' in data:
            current_portfolio = {}
            for item_raw in data['multi_data']:
                item = self._ensure_numeric_fields(item_raw)
                code = item.get("종목번호")
                if code:
                    code = code.replace('A', '').strip() # 종목코드 클리닝 (A 제거)
                    if '수익률(%)' in item: # API 응답 필드명 확인 필요
                        item['수익률'] = self._safe_to_float(item['수익률(%)'])
                    current_portfolio[code] = {
                        'stock_name': item.get("종목명"),
                        '보유수량': self._safe_to_int(item.get("보유수량")),
                        '매입가': self._safe_to_float(item.get("매입가")),
                        '현재가': self._safe_to_float(item.get("현재가")),
                        '평가금액': self._safe_to_float(item.get("평가금액")),
                        '매입금액': self._safe_to_float(item.get("매입금액")),
                        '평가손익': self._safe_to_float(item.get("평가손익")),
                        '수익률': self._safe_to_float(item.get("수익률", item.get("수익률(%)"))),
                    }
            self.account_state.portfolio = current_portfolio
            self.log(f"계좌 잔고(포트폴리오) 업데이트 (opw00018): {len(self.account_state.portfolio)} 종목", "INFO")
            # self.update_portfolio_and_log() # 포트폴리오 업데이트 후 로깅 - 해당 메서드 없음, 관련 로깅은 이미 수행됨
        self.portfolio_requested_time = None # 요청 완료 처리
