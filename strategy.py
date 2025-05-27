#!/usr/bin/env python
# -*- coding: utf-8 -*-

import time
from datetime import datetime, timedelta # timedelta 추가
from PyQt5.QtCore import QTimer, QObject
from logger import Logger
import copy
import re
from util import ScreenManager, get_current_time_str, _safe_to_int, _safe_to_float
from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
import os
import json
import ats_utils

# --- 로그 색상 막 정의 ---
class TradeColors:
    # 전략 신호
    BUY_SIGNAL = '\033[92m'     # 밝은 녹색 - 매수 신호
    SELL_SIGNAL = '\033[91m'    # 밝은 빨간색 - 매도 신호
    STOP_LOSS = '\033[95m'      # 보라색 - 손절 신호
    TAKE_PROFIT = '\033[96m'    # 청록색 - 익절 신호
    TRAILING = '\033[93m'       # 노란색 - 트레일링 신호
    
    # 주문 상태
    ORDER_SENT = '\033[93m'     # 노란색 - 주문 전송
    ORDER_RECEIVED = '\033[94m' # 파란색 - 주문 접수
    FILLED = '\033[92m'         # 녹색 - 체결
    PARTIAL_FILLED = '\033[96m' # 청록색 - 부분 체결
    ORDER_FAILED = '\033[91m'   # 빨간색 - 주문 실패
    
    # 포트폴리오
    PORTFOLIO = '\033[94m'      # 파란색 - 포트폴리오 업데이트
    BALANCE = '\033[97m'        # 흰색 - 잠고 업데이트
    PROFIT = '\033[92m'         # 녹색 - 수익
    LOSS = '\033[91m'           # 빨간색 - 손실
    
    # 일반
    INFO = '\033[97m'           # 흰색 - 일반 정보
    WARNING = '\033[93m'        # 노란색 - 경고
    ERROR = '\033[91m'          # 빨간색 - 오류
    
    # 리셋
    RESET = '\033[0m'           # 색상 리셋

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
    trading_status: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    trading_records: Dict[str, Any] = field(default_factory=dict)

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
    max_buy_attempts_per_stock: int = 3  # 종목당 최대 매수 시도 횟수
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
    buy_completion_count: int = 0  # 매수 체결 완료 횟수 (종목당 최대 3회 제한용)
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
    def _normalize_stock_code(self, code):
        """종목코드를 일관된 형태로 정규화"""
        if not code:
            return ""
        normalized = str(code).strip()
        if normalized.startswith('A') and len(normalized) > 1:
            normalized = normalized[1:]
        return normalized
    
    def _recover_missing_stock_from_portfolio(self, code):
        """포트폴리오에 있지만 watchlist에 없는 종목을 자동 복구"""
        original_code_param = code # 로깅용
        normalized_code = self._normalize_stock_code(code)
        if original_code_param != normalized_code:
            self.log(f"[RECOVER_NORMALIZE] _recover_missing_stock_from_portfolio: Input code '{original_code_param}' normalized to '{normalized_code}'", "DEBUG")

        # 이제 normalized_code를 사용하여 포트폴리오와 watchlist를 확인합니다.
        # 원본 코드로도 확인하는 로직은 제거하고 정규화된 코드로 일관되게 처리합니다.
        if normalized_code in self.account_state.portfolio and normalized_code not in self.watchlist:
            portfolio_item = self.account_state.portfolio[normalized_code]
            stock_name = portfolio_item.get('stock_name', normalized_code)
            
            # watchlist에 다시 추가 (add_to_watchlist는 내부적으로 정규화하므로 normalized_code 전달)
            self.add_to_watchlist(normalized_code, stock_name, yesterday_close_price=0.0)
            
            # 보유 상태로 복구 (watchlist의 키는 add_to_watchlist에 의해 정규화됨)
            stock_info = self.watchlist.get(normalized_code) # 정규화된 코드로 조회
            if not stock_info: # 혹시 모를 경우 방어
                self.log(f"[RECOVER_FAIL] _recover_missing_stock_from_portfolio: Failed to retrieve {normalized_code} from watchlist after adding.", "ERROR")
                return None
                
            stock_info.strategy_state = TradingState.BOUGHT
            stock_info.avg_buy_price = _safe_to_float(portfolio_item.get('매입가'))
            stock_info.total_buy_quantity = _safe_to_int(portfolio_item.get('보유수량'))
            stock_info.buy_timestamp = datetime.now()  # 정확한 시간은 알 수 없으므로 현재 시간으로 설정
            
            # trading_status에도 상태 저장 (정규화된 코드로)
            self.account_state.trading_status[normalized_code] = {
                'status': TradingState.BOUGHT,
                'bought_price': stock_info.avg_buy_price,
                'bought_quantity': stock_info.total_buy_quantity,
                'bought_time': stock_info.buy_timestamp
            }
            
            self.log(f"[AUTO_RECOVERY] {normalized_code} ({stock_name}) watchlist 자동 복구 완료 (원본 입력: {original_code_param})", "WARNING")
            return stock_info
        elif normalized_code in self.account_state.portfolio and normalized_code in self.watchlist:
            # 포트폴리오에도 있고, watchlist에도 이미 있는 경우 (정상)
            pass
        elif normalized_code not in self.account_state.portfolio:
            # 포트폴리오에 없는 경우 (복구 대상 아님)
            pass
            
        return None

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
        # 시작 시간 초기화
        self.start_time = time.time()
        self.start_time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        self.account_state = AccountState()
        self.settings = StrategySettings()
        self._load_strategy_settings() # 설정 로드는 여기서 먼저 수행
        
        # 상태 저장 및 복원 관련 파일 경로 설정
        # settings.json에 지정된 DB 경로와 동일한 디렉토리에 trading_state.json 파일 저장
        db_path = self.modules.config_manager.get_setting("Database", "path", "logs/trading_data.db")
        db_dir = os.path.dirname(db_path)
        if not db_dir:
            db_dir = os.path.dirname(os.path.abspath(__file__))
        self.state_file_path = os.path.join(db_dir, "trading_state.json")
        self.log(f"상태 파일 경로: {self.state_file_path}", "INFO")
        
        # 이전 위치에 있는 trading_state.json 파일을 새 경로로 이동
        old_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trading_state.json")
        if os.path.exists(old_path) and old_path != self.state_file_path:
            try:
                # 대상 디렉토리가 존재하는지 확인하고 없으면 생성
                if not os.path.exists(db_dir):
                    os.makedirs(db_dir, exist_ok=True)
                
                # 새 경로에 이미 파일이 존재하면 병합 또는 백업 결정
                if os.path.exists(self.state_file_path):
                    # 두 파일의 수정 시간 비교
                    old_mtime = os.path.getmtime(old_path)
                    new_mtime = os.path.getmtime(self.state_file_path)
                    
                    if old_mtime > new_mtime:
                        # 이전 파일이 더 최신이면 백업 후 이동
                        backup_path = f"{self.state_file_path}.bak"
                        if os.path.exists(backup_path):
                            os.remove(backup_path)
                        os.rename(self.state_file_path, backup_path)
                        self.log(f"기존 상태 파일을 {backup_path}로 백업했습니다.", "INFO")
                        os.rename(old_path, self.state_file_path)
                        self.log(f"이전 위치의 상태 파일을 새 경로로 이동했습니다: {old_path} -> {self.state_file_path}", "INFO")
                    else:
                        # 새 파일이 더 최신이면 이전 파일 삭제
                        os.remove(old_path)
                        self.log(f"더 오래된 이전 위치의 상태 파일을 삭제했습니다: {old_path}", "INFO")
                else:
                    # 새 경로에 파일이 없으면 바로 이동
                    os.rename(old_path, self.state_file_path)
                    self.log(f"이전 위치의 상태 파일을 새 경로로 이동했습니다: {old_path} -> {self.state_file_path}", "INFO")
            except Exception as e:
                self.log(f"상태 파일 이동 중 오류 발생: {e}", "ERROR")
        
        # trading_records 초기화
        self.account_state.trading_records = {
            '매수건수': 0,
            '매수금액': 0,
            '매도건수': 0,
            '매도금액': 0,
            '총손익금': 0,
            '이익건수': 0,
            '이익금액': 0,
            '손실건수': 0,
            '손실금액': 0
        }
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
        """매매 전략 설정을 로드합니다."""
        if not self.modules.config_manager:
            self.log("설정 관리자가 설정되지 않아 기본값을 사용합니다.", "WARNING")
            return
        
        self.settings.buy_amount_per_stock = self.modules.config_manager.get_setting("매수금액", 1000000.0)
        
        # 매매 전략 관련 설정
        self.settings.stop_loss_rate_from_yesterday_close = self.modules.config_manager.get_setting("매매전략", "손절손실률_전일종가기준", 2.0)
        self.settings.partial_take_profit_rate = self.modules.config_manager.get_setting("매매전략", "익절_수익률", 5.0)
        self.settings.partial_sell_ratio = self.modules.config_manager.get_setting("매매전략", "익절_매도비율", 50.0) / 100.0  # 퍼센트 -> 비율 변환
        self.settings.full_take_profit_target_rate = self.modules.config_manager.get_setting("매매전략", "최종_익절_수익률", 9.0)
        self.settings.trailing_stop_activation_profit_rate = self.modules.config_manager.get_setting("매매전략", "트레일링_활성화_수익률", 2.0)
        self.settings.trailing_stop_fall_rate = self.modules.config_manager.get_setting("매매전략", "트레일링_하락률", 1.5)
        self.settings.market_open_time_str = self.modules.config_manager.get_setting("매매전략", "MarketOpenTime", "09:00:00")
        self.settings.market_close_time_str = self.modules.config_manager.get_setting("매매전략", "MarketCloseTime", "15:30:00")
        self.settings.dry_run_mode = self.modules.config_manager.get_setting("매매전략", "dry_run_mode", False)
        self.settings.max_buy_attempts_per_stock = self.modules.config_manager.get_setting("매매전략", "종목당_최대시도횟수", 3)
        
        # 주기적 상태 보고 관련 설정
        self.settings.periodic_report_enabled = self.modules.config_manager.get_setting("PeriodicStatusReport", "enabled", True)
        self.settings.periodic_report_interval_seconds = self.modules.config_manager.get_setting("PeriodicStatusReport", "interval_seconds", 60)
        
        self.account_type = self.modules.config_manager.get_setting("계좌정보", "account_type", "실거래") # 기본값을 config.py와 일치
        self.log(f"계좌 유형 설정 로드: {self.account_type}", "INFO")

    def log(self, message, level="INFO"):
        """색상 지원 로그 메서드 - Logger 모듈을 통해 파일 및 콘솔에 기록"""
        timestamp = get_current_time_str()
        
        if hasattr(self, 'modules') and self.modules and hasattr(self.modules, 'logger') and self.modules.logger:
            log_func = getattr(self.modules.logger, level.lower(), self.modules.logger.info)
            # 로그 메시지 포맷은 Logger 클래스에서 처리하므로, 여기서는 순수 메시지만 전달하거나,
            # Strategy 모듈명을 명시적으로 포함하여 전달할 수 있습니다.
            # 여기서는 기존처럼 [Strategy] 접두사를 포함하여 전달합니다.
            log_func(f"[Strategy][{timestamp}] {message}")
        else:
            # Logger 모듈이 없는 경우에 대한 fallback 로깅 (예: 표준 print 또는 logging 사용)
            # 이 부분은 원래 print를 사용했으므로, 만약 logger가 없는 극단적인 상황을 대비해 유지하거나,
            # 혹은 logger가 항상 존재한다고 가정하고 이 else 블록을 제거할 수 있습니다.
            # 현재 요구사항은 print 제거이므로, 이 fallback도 제거하거나 logger를 사용하는 방식으로 변경해야 합니다.
            # 여기서는 logger가 항상 존재한다고 가정하고 else 블록 내용을 주석 처리하거나 삭제합니다.
            # print(f"[{level.upper()}][Strategy_FALLBACK_NO_LOGGER][{timestamp}] {message}") # 이 부분도 제거
            pass # Logger가 없다면 아무 동작도 하지 않음 (또는 기본 logging 모듈 사용 고려)

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
            
            # 저장된 상태 로드 시도
            self.load_saved_state()
            
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
        
        original_code_param = code # 로깅용
        normalized_code = self._normalize_stock_code(code)
        if original_code_param != normalized_code:
            self.log(f"[REAL_DATA_NORMALIZE] on_actual_real_data_received: Input code '{original_code_param}' normalized to '{normalized_code}'", "DEBUG")

        stock_info = self.watchlist.get(normalized_code) # 정규화된 코드로 조회
        if not stock_info:
            if self.current_real_data_count % 500 == 0: # 500건마다 로깅하는 것은 유지
                self.log(f"수신된 실시간 데이터({original_code_param} -> {normalized_code})가 관심종목에 없어 무시합니다.", "DEBUG")
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
        new_current_price = _safe_to_float(stock_info.api_data.get('현재가', stock_info.current_price))
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
            if self.current_real_data_count % 100 == 0: # 100건마다 로깅하는 것은 유지
                 self.log(f"실시간 데이터 업데이트 ({normalized_code}): 현재가({stock_info.current_price}), API데이터({stock_info.api_data.get('현재가', 'N/A')})", "DEBUG")

        if update_occurred and stock_info.strategy_state != TradingState.IDLE :
            self.process_strategy(normalized_code) # 정규화된 코드로 process_strategy 호출

    def start(self):
        self.log("TradingStrategy 시작 요청 접수...", "INFO")
        self.log(f"[STRATEGY_DEBUG] ENTERING start() method. is_running={self.is_running}, init_status={self.initialization_status}, watchlist_items={len(self.watchlist)}", "DEBUG")
        self.current_status_message = "전략 시작 중..."
        if self.is_running:
            self.log(f"{TradeColors.WARNING}⚠️ [WARNING] Trading strategy is already running.{TradeColors.RESET}", "WARNING")
            self.current_status_message = "전략 이미 실행 중."
            return

        # 모든 초기화 단계 확인
        if not self.initialization_status["account_info_loaded"]:
            self.log(f"{TradeColors.ERROR}❌ [ERROR] 시작 실패: 계좌번호가 로드되지 않았습니다.{TradeColors.RESET}", "ERROR")
            self.current_status_message = "오류: 계좌번호 미로드. 전략 시작 불가."
            self.is_running = False
            return
        
        if not (self.initialization_status["deposit_info_loaded"] and self.initialization_status["portfolio_loaded"]):
            self.log(f"{TradeColors.WARNING}⚠️ [WARNING] 시작 보류: 예수금 또는 포트폴리오 정보가 아직 로드되지 않았습니다.{TradeColors.RESET}", "WARNING")
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
            self.log(f"{TradeColors.WARNING}⚠️ [WARNING] 시작 보류: 관심종목이 없습니다. 최소 하나 이상의 관심종목을 추가해주세요.{TradeColors.RESET}", "WARNING")
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
        
        # 상태 저장
        self.save_current_state()
        self.log("현재 상태를 파일에 저장했습니다.", "INFO")
        
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
        original_code_param = code # 로깅용
        normalized_code = self._normalize_stock_code(code)
        if original_code_param != normalized_code:
            self.log(f"[WATCHLIST_NORMALIZE] add_to_watchlist: Input code '{original_code_param}' normalized to '{normalized_code}'", "DEBUG")
        
        # 이제 code 변수에는 항상 정규화된 코드가 들어감
        code = normalized_code 
        
        self.log(f"[WATCHLIST_ADD_START] 관심종목 추가/업데이트 시작: 코드({code}), 이름({stock_name}), 설정된 전일종가({yesterday_close_price})", "DEBUG")
        
        safe_yesterday_cp = _safe_to_float(yesterday_close_price)

        if code not in self.watchlist: # 정규화된 코드로 확인
            self.watchlist[code] = StockTrackingData( # 정규화된 코드를 키로 사용
                code=code, # StockTrackingData 내부의 code 필드도 정규화된 코드로 저장
                stock_name=stock_name,
                yesterday_close_price=safe_yesterday_cp
            )
            self.log(f"관심종목 신규 추가: {stock_name}({code}), 전일종가: {safe_yesterday_cp}, 초기상태: {self.watchlist[code].strategy_state.name}", "INFO")
        else: # 이미 있다면 업데이트 (키는 이미 정규화된 코드)
            self.watchlist[code].stock_name = stock_name
            self.watchlist[code].yesterday_close_price = safe_yesterday_cp
            # code 필드는 이미 정규화되어 있으므로 업데이트 불필요: self.watchlist[code].code = code
            self.log(f"관심종목 정보 업데이트: {stock_name}({code}), 전일종가: {safe_yesterday_cp}, 현재상태: {self.watchlist[code].strategy_state.name}", "INFO")
        
        if safe_yesterday_cp == 0:
            self.log(f"주의: 관심종목 {stock_name}({code})의 전일종가가 0으로 설정되었습니다. 매매 전략에 영향을 줄 수 있습니다.", "WARNING")

        self.log(f"[WATCHLIST_ADD_END] 관심종목 추가/업데이트 완료: 코드({code}) - 현재 self.watchlist에 {len(self.watchlist)}개 항목", "DEBUG")

    def remove_from_watchlist(self, code, screen_no=None, unsubscribe_real=True):
        original_code_param = code # 로깅용
        normalized_code = self._normalize_stock_code(code)
        if original_code_param != normalized_code:
            self.log(f"[WATCHLIST_NORMALIZE] remove_from_watchlist: Input code '{original_code_param}' normalized to '{normalized_code}'", "DEBUG")
        
        code = normalized_code # 이후 모든 로직에서 정규화된 코드 사용

        self.log(f"Removing {code} from watchlist... Unsubscribe real data: {unsubscribe_real}", "INFO")
        stock_info = self.watchlist.get(code) # 정규화된 코드로 조회

        if stock_info and unsubscribe_real:
            # 실시간 데이터 구독 해지 (종목코드도 정규화된 것 사용)
            real_data_screen_no = stock_info.api_data.get('real_screen_no')
            if real_data_screen_no:
                self.modules.kiwoom_api.disconnect_real_data(real_data_screen_no) # API 호출
                self.modules.screen_manager.release_screen(real_data_screen_no, f"real_{code}") # ScreenManager에도 알림
                self.log(f"Unsubscribed real data for {code} using screen_no: {real_data_screen_no}", "DEBUG")
            else:
                self.log(f"Real data screen number for {code} not found. Cannot unsubscribe specific real data.", "WARNING")
        
        tr_screen_no_key = f"chart_{code}" # get_available_screen에서 사용한 identifier와 일치시킴
        tr_screen_no_val = self.modules.screen_manager.get_screen_for_identifier(tr_screen_no_key)
        if tr_screen_no_val:
            self.modules.screen_manager.release_screen(tr_screen_no_val, tr_screen_no_key)
            self.log(f"Released TR screen_no: {tr_screen_no_val} for {code} (Key: {tr_screen_no_key}).", "DEBUG")
        
        if screen_no: # 인자로 직접 받은 screen_no가 있다면 그것도 해제 시도 (Identifier를 모를 경우 대비)
             released_by_direct_screen_no = self.modules.screen_manager.release_screen(screen_no) # Identifier 없이 해제 시도
             if released_by_direct_screen_no:
                self.log(f"Released screen_no (from arg): {screen_no} for {code}. Identifier was unknown or already cleared.", "DEBUG")

        if code in self.watchlist: # 정규화된 코드로 삭제
            del self.watchlist[code]
            self.log(f"{code} removed from watchlist.", "INFO")
        else:
            self.log(f"{code} not found in watchlist for removal (already removed or never added).", "WARNING")


    def subscribe_stock_real_data(self, code):
        original_code_param = code # 로깅용
        normalized_code = self._normalize_stock_code(code)
        if original_code_param != normalized_code:
            self.log(f"[REAL_SUB_NORMALIZE] subscribe_stock_real_data: Input code '{original_code_param}' normalized to '{normalized_code}'", "DEBUG")
        
        code = normalized_code # 이후 모든 로직에서 정규화된 코드 사용

        stock_info = self.watchlist.get(code) # 정규화된 코드로 조회
        if not stock_info:
            self.log(f"Cannot subscribe real data for {code}: not in watchlist.", "ERROR")
            return

        if stock_info.api_data.get('real_subscribed', False):
            self.log(f"Real data for {code} is already subscribed.", "DEBUG")
            return

        screen_identifier = f"real_{code}" # ScreenManager에 사용할 identifier
        screen_no = self.modules.screen_manager.get_available_screen(screen_identifier)
        if not screen_no:
            self.log(f"Failed to get a screen number for real data subscription of {code} (Identifier: {screen_identifier}).", "ERROR")
            return
        
        fids_to_subscribe = self.modules.config_manager.get_setting("API", "RealTimeFID", "10;11;12;13") # 설정에서 FID 목록 가져오기
        
        # KiwoomAPI의 set_real_reg는 종목코드를 ; 구분자로 여러 개 받을 수 있음. 여기서는 단일 종목.
        ret = self.modules.kiwoom_api.set_real_reg(screen_no, code, fids_to_subscribe, "1") # "1"은 최초 등록

        # SetRealReg의 반환값은 API 호출 성공 여부이지, 실제 구독 성공 여부는 아님.
        # 키움 API에서는 이벤트(OnReceiveRealData)로 구독 성공/실패를 알리지 않고, 요청 후 바로 데이터가 오기 시작함.
        # 따라서 요청이 성공적으로 보내졌다면 구독된 것으로 간주.
        if ret == 0: # 일반적으로 API 호출 자체의 성공을 의미 (키움 API 문서 참조)
            self.log(f"실시간 데이터 구독 요청 전송 (화면: {screen_no}, 종목: {code}, FID: {fids_to_subscribe}). 실제 구독은 데이터 수신으로 확인.", "INFO")
            stock_info.api_data['real_screen_no'] = screen_no # 실시간 데이터용 화면번호 저장
            stock_info.api_data['real_subscribed'] = True
            # self.modules.kiwoom_api.subscribed_real_data[code] = {"screen_no": screen_no, "fids": fids_to_subscribe.split(';')} # API 모듈에서 관리
        else:
            self.log(f"실시간 데이터 구독 요청 전송 실패 (화면: {screen_no}, 종목: {code}). SetRealReg 반환값: {ret}", "ERROR")
            self.modules.screen_manager.release_screen(screen_no, screen_identifier) # 실패 시 화면번호 반환

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
        """전략 조건 검사 및 매매 실행"""
        # 일일 매수 횟수 제한을 위한 날짜 확인 및 카운트 초기화
        current_date = datetime.now().strftime('%Y-%m-%d')
        if self.today_date_for_buy_limit != current_date:
            self.log(f"날짜 변경 감지: {self.today_date_for_buy_limit} -> {current_date}. 일일 매수 카운트 초기화", "INFO")
            # 일일 매수 횟수 초기화
            self.daily_buy_executed_count = 0
            # 모든 종목의 매수 시도 횟수 초기화
            for code, stock_info in self.watchlist.items():
                if stock_info.buy_completion_count > 0:
                    self.log(f"[{code}] 매수 시도 횟수 초기화: {stock_info.buy_completion_count} -> 0", "DEBUG")
                    stock_info.buy_completion_count = 0
            self.today_date_for_buy_limit = current_date
        
        # 시장 시간이 아니면 종료
        if not self.is_market_hours():
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
            self.log(f"{TradeColors.STOP_LOSS}📉 [STOP_LOSS] 손절 조건 충족: {code} ({stock_info.stock_name}), 현재가({current_price:.2f}) <= 손절가({stop_loss_price:.2f}){TradeColors.RESET}", "INFO")
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
            self.log(f"{TradeColors.TAKE_PROFIT}🎯 [TAKE_PROFIT] 최종 익절 조건 충족: {code} ({stock_info.stock_name}), 현재가({current_price:.2f}) >= 최종목표가({target_price:.2f}){TradeColors.RESET}", "INFO")
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
            sell_qty = int(holding_quantity * self.settings.partial_sell_ratio)
            if sell_qty <= 0 and holding_quantity > 0:
                sell_qty = holding_quantity
                self.log(f"[{code}] 부분 익절: 계산된 매도 수량 0이나 보유량 있어 전량({sell_qty}) 매도 시도.", "WARNING")
            elif sell_qty <= 0:
                 self.log(f"[{code}] 부분 익절: 계산된 매도 수량 0. 진행 안함.", "DEBUG")
                 return False

            self.log(f"{TradeColors.TAKE_PROFIT}💰 [PARTIAL_PROFIT] 부분 익절 조건 충족: {code} ({stock_info.stock_name}), 현재가({current_price:.2f}) >= 부분익절가({target_price:.2f}), 매도수량({sell_qty}){TradeColors.RESET}", "INFO")
            
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

                self.log(f"{TradeColors.TRAILING}🔽 [TRAILING_STOP] 트레일링 스탑 발동(50%): {code} ({stock_info.stock_name}), 현재가({current_price:.2f}) <= 발동가({trailing_stop_trigger_price:.2f}), 매도수량({sell_qty}){TradeColors.RESET}", "INFO")
                if self.execute_sell(code, reason="트레일링스탑(50%)", quantity_type="수량", quantity_val=sell_qty):
                    stock_info.trailing_stop_partially_sold = True
                    self.log(f"[{code}] 트레일링 스탑 (50%) 매도 주문 접수. trailing_stop_partially_sold 플래그 True 설정.", "INFO")
                    return True
                else:
                    self.log(f"[{code}] 트레일링 스탑 (50%) 매도 주문 실패.", "ERROR")
            else: # 이미 부분 매도된 상태 (두 번째 트레일링 스탑 발동)
                self.log(f"{TradeColors.TRAILING}🔽 [TRAILING_STOP] 트레일링 스탑 발동(잔량): {code} ({stock_info.stock_name}), 현재가({current_price:.2f}) <= 발동가({trailing_stop_trigger_price:.2f}){TradeColors.RESET}", "INFO")
                if self.execute_sell(code, reason="트레일링스탑(잔량)", quantity_type="전량"):
                    return True
                else:
                    self.log(f"[{code}] 트레일링 스탑 (잔량 전량) 매도 주문 실패.", "ERROR")
        return False

    def _handle_waiting_state(self, code, stock_info: StockTrackingData, current_price):
        """
        종목이 WAITING 상태일 때 현재가가 매수 조건을 충족하는지 확인하고, 충족하면 매수 주문을 실행합니다.
        """
        # 이미 보유중인지 확인 (watchlist 상태와 실제 portfolio 모두 확인)
        if code in self.account_state.portfolio:
            holding_quantity = _safe_to_int(self.account_state.portfolio[code].get('보유수량', 0))
            if holding_quantity > 0:
                # 이미 종목을 보유 중인데 상태가 잘못되어 있는 경우 상태 교정
                if stock_info.strategy_state != TradingState.BOUGHT:
                    self.log(f"[{code}] 상태 교정: 실제로 {holding_quantity}주 보유 중이지만 상태가 {stock_info.strategy_state.name}입니다. BOUGHT로 변경", "WARNING")
                    stock_info.strategy_state = TradingState.BOUGHT
                    stock_info.avg_buy_price = _safe_to_float(self.account_state.portfolio[code].get('매입가', 0))
                    stock_info.total_buy_quantity = holding_quantity
                    stock_info.current_high_price_after_buy = max(stock_info.current_high_price_after_buy, current_price)
                    stock_info.buy_timestamp = datetime.now()  # 정확한 시간은 알 수 없으므로 현재 시간으로 설정
                    
                    # trading_status에도 상태 저장
                    self.account_state.trading_status[code] = {
                        'status': TradingState.BOUGHT,
                        'bought_price': stock_info.avg_buy_price,
                        'bought_quantity': stock_info.total_buy_quantity,
                        'bought_time': stock_info.buy_timestamp
                    }
                return False  # 이미 보유 중이므로 추가 매수 없음
        
        # 관련 주문이 처리 중인지 확인
        if stock_info.last_order_rq_name is not None:
            self.log(f"[{code}] 매수 조건 검사 건너뜀. 이전 주문({stock_info.last_order_rq_name})이 아직 처리 중입니다.", "DEBUG")
            return False

        # 매수 실행 가능 시간인지 확인
        if not self.is_market_hours():
            self.log(f"{TradeColors.WARNING}⏰ [MARKET_CLOSED] [{code}] 매수 조건 충족하지만 장 시간이 아니므로 매수 보류.{TradeColors.RESET}", "DEBUG")
            return False

        # 현재가와 전일 종가 비교 로직
        if stock_info.is_yesterday_close_broken_today:
            # 전일 종가를 하회했던 이력이 있는 경우, 다시 전일 종가 이상으로 회복했는지 확인
            if current_price >= stock_info.yesterday_close_price:
                self.log(f"{TradeColors.BUY_SIGNAL}📈 [BUY_SIGNAL] 전일 종가 재돌파 매수 조건 충족: {code} (전일종가: {stock_info.yesterday_close_price}, 현재가: {current_price}){TradeColors.RESET}", "INFO")
                if self.execute_buy(code): # 매수 실행
                    # 매수 주문 성공 시 플래그 리셋
                    stock_info.is_yesterday_close_broken_today = False
                    self.log(f"[{code}] 매수 주문 접수 성공 후 'is_yesterday_close_broken_today' 플래그 리셋.", "DEBUG")
                    return True
            else:
                # 전일 종가 아래이지만 이미 기록된 상태이므로 별도 로깅 없음
                pass
        else:
            # 처음으로 전일 종가 아래로 내려간 상황 기록
            if current_price < stock_info.yesterday_close_price:
                stock_info.is_yesterday_close_broken_today = True
                self.log(f"[{code}] 전일 종가 하회 기록 (전일종가: {stock_info.yesterday_close_price}, 현재가: {current_price})", "INFO")
            # 전일 종가보다 같거나 큰 경우는 아무 동작 없음 (기본 상태)

        return False

    def _handle_holding_state(self, code, stock_info: StockTrackingData, current_price):
        """보유 중인 종목에 대한 전략 처리"""
        
        # 포트폴리오에서 보유 정보 확인
        portfolio_item = self.account_state.portfolio.get(code, {})
        avg_buy_price = _safe_to_float(portfolio_item.get('매입가', stock_info.avg_buy_price))
        holding_quantity = _safe_to_int(portfolio_item.get('보유수량', 0))
        
        # 로그 추가: 포트폴리오와 종목 상태 비교 (디버깅용)
        self.log(f"[HOLDING_STATE_DEBUG] {code}: 현재가({current_price}), 매입가({avg_buy_price}), 보유량({holding_quantity}), StockInfo 상태({stock_info.strategy_state.name})", "DEBUG")
        
        # 보유량이 0이거나 없으면 reset 처리
        if holding_quantity <= 0:
            self.log(f"{code} 포트폴리오 보유량이 0이거나 없음. 전략 정보 초기화.", "INFO")
            self.reset_stock_strategy_info(code)
            return
        
        # 매도 주문이 이미 진행 중인지 확인 (활성 주문 검색)
        active_orders_for_code = []
        for key, order in self.account_state.active_orders.items():
            if order.get('code') == code and order.get('order_type') == '매도':
                active_orders_for_code.append(order)
        
        if active_orders_for_code:
            total_unfilled = sum(_safe_to_int(order.get('unfilled_qty', 0)) for order in active_orders_for_code)
            self.log(f"{code} 매도 주문 진행 중: {len(active_orders_for_code)}개 주문, 미체결 총량: {total_unfilled}. 추가 전략 처리 건너뜀.", "INFO")
            return

        # 주문 임시 수량 가져오기
        temp_order_quantity = getattr(stock_info, 'temp_order_quantity', 0)
        portfolio_temp_order_quantity = portfolio_item.get('임시_주문수량', 0)
        
        # 실제 사용 가능한 수량 계산 (보유량 - 임시 주문 수량)
        available_quantity = holding_quantity - max(temp_order_quantity, portfolio_temp_order_quantity)
        
        # 실제 가용 수량이 0 이하면 건너뜀
        if available_quantity <= 0:
            self.log(f"{code} 가용 수량이 0 이하입니다. 보유량: {holding_quantity}, 임시주문량: {max(temp_order_quantity, portfolio_temp_order_quantity)}. 전략 처리 건너뜀.", "INFO")
            return

        # 트레일링 스탑 활성화 조건 검사 (다른 매도 조건보다 먼저 실행될 수 있도록 배치)
        if holding_quantity > 0 and not stock_info.is_trailing_stop_active:
            activation_price = avg_buy_price * (1 + self.settings.trailing_stop_activation_profit_rate / 100.0)
            if current_price >= activation_price:
                stock_info.is_trailing_stop_active = True
                # 활성화 시점의 현재가를 매수 후 최고가로 설정하여 즉시 트레일링 스탑 감시 시작
                stock_info.current_high_price_after_buy = current_price 
                self.log(f"{TradeColors.TRAILING}📈 [{code}] 트레일링 스탑 활성화됨. 현재가({current_price:.2f}) >= 활성화가({activation_price:.2f}). 활성화 후 기준 고점: {stock_info.current_high_price_after_buy:.2f}{TradeColors.RESET}", "INFO")
            
        # 손절 조건 검사 (priority 1) - 실제 가용 수량 전달
        if self._check_and_execute_stop_loss(code, stock_info, current_price, avg_buy_price, available_quantity):
            self.log(f"{code} 손절 실행완료, 다음 조건검사 건너뜀.", "INFO")
            return

        # 현재가가 매수 후 최고가보다 높으면 업데이트 (향후 트레일링 스탑에 사용)
        if current_price > stock_info.current_high_price_after_buy:
            old_high = stock_info.current_high_price_after_buy
            stock_info.current_high_price_after_buy = current_price
            self.log(f"{code} 매수 후 최고가 갱신: {old_high} -> {current_price}", "DEBUG")

        # 최종 익절 조건 검사 (priority 2)
        if self._check_and_execute_full_take_profit(code, stock_info, current_price, avg_buy_price, holding_quantity):
            self.log(f"{code} 최종 익절(전량매도) 실행완료, 다음 조건검사 건너뜀.", "INFO")
            return

        # 부분 익절 조건 검사 (1회만) (priority 3)
        if not stock_info.partial_take_profit_executed:
            if self._check_and_execute_partial_take_profit(code, stock_info, current_price, avg_buy_price, holding_quantity):
                self.log(f"{code} 부분 익절 실행완료, 추가 조건검사 계속.", "INFO")
                # 부분 익절 후에도 계속 다른 조건 검사 (트레일링 스탑 등)

        # 트레일링 스탑 조건 검사 (priority 4)
        # 이미 익절이 된 경우에도 남은 물량에 대해 트레일링 스탑 적용
        if self._check_and_execute_trailing_stop(code, stock_info, current_price, avg_buy_price, holding_quantity):
            self.log(f"{code} 트레일링 스탑 실행완료.", "INFO")
            return
        
        # 보유 시간 기반 자동 청산 조건 (필요 시)
        if self.settings.auto_liquidate_after_minutes_enabled and stock_info.buy_timestamp:
            hold_minutes = (datetime.now() - stock_info.buy_timestamp).total_seconds() / 60
            if hold_minutes >= self.settings.auto_liquidate_after_minutes:
                self.log(f"{code} 보유시간({hold_minutes:.1f}분) 기준 자동 청산 조건 충족. 설정: {self.settings.auto_liquidate_after_minutes}분", "IMPORTANT")
                self.execute_sell(code, reason=f"시간청산({hold_minutes:.0f}분)", quantity_type="전량")
                return

    def process_strategy(self, code):
        """코드 전략을 실행합니다."""
        original_code_param = code # 로깅용
        normalized_code = self._normalize_stock_code(code)
        if original_code_param != normalized_code:
            self.log(f"[PROCESS_STRATEGY_NORMALIZE] process_strategy: Input code '{original_code_param}' normalized to '{normalized_code}'", "DEBUG")
        
        code = normalized_code # 이후 모든 로직에서 정규화된 코드 사용

        stock_info = self.watchlist.get(code) # 정규화된 코드로 조회
        
        if not stock_info:
            # watchlist 자동 복구 시도 (내부에서 code 정규화 사용)
            recovered_stock_info = self._recover_missing_stock_from_portfolio(original_code_param) # 원본 파라미터로 복구 시도
            if recovered_stock_info:
                stock_info = recovered_stock_info
                code = stock_info.code # 복구된 StockTrackingData의 code 사용 (이미 정규화됨)
                self.log(f"[PROCESS_STRATEGY] {code} 자동 복구 성공하여 계속 진행.", "INFO")
            else:
                # 복구 실패 시 포트폴리오 직접 확인 (중복 매수 방지)
                # _recover_missing_stock_from_portfolio가 이미 original_code_param과 normalized_code 모두 확인하므로,
                # 여기서 추가적인 포트폴리오 확인은 중복될 수 있음.
                # 다만, _recover_missing_stock_from_portfolio가 None을 반환했다면,
                # 포트폴리오에 없거나, 있더라도 watchlist에 이미 있거나, 복구에 실패한 경우임.
                # 여기서는 최종적으로 stock_info가 여전히 None이면 무시.
                self.log(f"[ProcessStrategy] 관심종목 목록에 없는 종목({original_code_param} -> {code})의 전략 실행 요청 무시됨 (복구 시도 후).", "DEBUG")
                return

        # 현재가 확인
        current_price = stock_info.current_price
        if current_price <= 0:
            # 현재가가 0 이하인 경우 처리하지 않음
            self.log(f"[ProcessStrategy] 종목({code})의 현재가({current_price})가 0 이하이므로 전략 실행 불가", "WARNING")
            return

        # 주문 처리 타임아웃 확인 (주문 접수 후 5분 이상 경과한 경우)
        if stock_info.last_order_rq_name and stock_info.buy_timestamp:
            current_time = datetime.now()
            order_elapsed_minutes = (current_time - stock_info.buy_timestamp).total_seconds() / 60
            
            # 최소 5분이 경과한 주문은 타임아웃으로 간주
            if order_elapsed_minutes > 5:
                self.log(f"[{code}] 미처리 주문({stock_info.last_order_rq_name}) 감지 - {order_elapsed_minutes:.1f}분 경과. 주문 상태 초기화", "WARNING")
                stock_info.last_order_rq_name = None
                
                # 포트폴리오에 종목이 있는지 확인하여 상태 조정
                if code in self.account_state.portfolio and _safe_to_int(self.account_state.portfolio[code].get('보유수량', 0)) > 0:
                    self.log(f"[{code}] 포트폴리오에 종목이 존재함 - 상태를 BOUGHT로 변경", "WARNING")
                    stock_info.strategy_state = TradingState.BOUGHT
                    stock_info.avg_buy_price = _safe_to_float(self.account_state.portfolio[code].get('매입가', 0))
                    stock_info.total_buy_quantity = _safe_to_int(self.account_state.portfolio[code].get('보유수량', 0))
                    
                    # trading_status에도 상태 저장
                    self.account_state.trading_status[code] = {
                        'status': TradingState.BOUGHT,
                        'bought_price': stock_info.avg_buy_price,
                        'bought_quantity': stock_info.total_buy_quantity,
                        'bought_time': stock_info.buy_timestamp or datetime.now()
                    }
        
        # 현재 상태 로깅
        self.log(f"[ProcessStrategy] 종목: {code}, 현재상태: {stock_info.strategy_state.name}, 현재가: {current_price}, 전일종가: {stock_info.yesterday_close_price}", "DEBUG")
        
        # 상태별 핸들러 매핑
        state_handler_map = {
            TradingState.IDLE: self._handle_idle_state,
            TradingState.WAITING: self._handle_waiting_state,
            TradingState.BOUGHT: self._handle_bought_state, # Renamed from _handle_holding_state
            TradingState.PARTIAL_SOLD: self._handle_partial_sold_state,
            TradingState.COMPLETE: self._handle_complete_state,
            # TradingState.READY 는 현재 WAITING에서 바로 매수 시도로 이어지므로 별도 핸들러 불필요할 수 있음
        }

        handler = state_handler_map.get(stock_info.strategy_state)
        if handler:
            handler(code, stock_info, current_price)
        else:
            self.log(f"[{code}] 정의되지 않은 상태({stock_info.strategy_state.name})에 대한 핸들러가 없습니다.", "WARNING")


    def _handle_idle_state(self, code, stock_info: StockTrackingData, current_price):
        """IDLE 상태의 종목을 처리합니다."""
        # self.log(f"[{code}] IDLE 상태입니다. 현재가: {current_price}. (특별한 동작 없음)", "DEBUG")
        # 필요시 초기 진입 조건 검사 또는 특정 로직 추가 가능
        # 예를 들어, 특정 조건 만족 시 WAITING 또는 READY로 변경하는 로직
        # if stock_info.is_gap_up_today and current_price > stock_info.today_open_price:
        #     stock_info.strategy_state = TradingState.WAITING
        #     self.log(f"[{code}] IDLE에서 WAITING으로 변경 (갭상승 및 시가 이상 조건 충족)")
        pass # 현재는 특별한 동작 없음

    def _handle_bought_state(self, code, stock_info: StockTrackingData, current_price):
        """BOUGHT 상태 (보유 중)인 종목에 대한 전략을 처리합니다."""
        portfolio_item = self.account_state.portfolio.get(code, {})
        avg_buy_price = _safe_to_float(portfolio_item.get('매입가', stock_info.avg_buy_price))
        holding_quantity = _safe_to_int(portfolio_item.get('보유수량', 0))

        if holding_quantity <= 0:
            self.log(f"[{code}] BOUGHT 상태이지만 포트폴리오 보유량 0. 전략 정보 초기화.", "WARNING")
            self.reset_stock_strategy_info(code)
            return

        active_sell_orders = [
            order for order in self.account_state.active_orders.values()
            if order.get('code') == code and order.get('order_type') == '매도' and order.get('unfilled_qty', 0) > 0
        ]
        if active_sell_orders:
            self.log(f"[{code}] BOUGHT 상태이나, 활성 매도 주문({len(active_sell_orders)}건) 존재. 추가 매도 조건 검사 건너뜀.", "INFO")
            return

        # 손절 조건 검사
        if self._check_and_execute_stop_loss(code, stock_info, current_price, avg_buy_price, holding_quantity):
            return # 주문 실행됨

        # 매수 후 최고가 갱신
        if current_price > stock_info.current_high_price_after_buy:
            old_high = stock_info.current_high_price_after_buy
            stock_info.current_high_price_after_buy = current_price
            self.log(f"[{code}] BOUGHT 상태 매수 후 최고가 갱신: {old_high} -> {current_price}", "DEBUG")
        
        # 트레일링 스탑 활성화 조건 검사 (다른 매도 조건보다 먼저 실행될 수 있도록 배치)
        if not stock_info.is_trailing_stop_active:
            activation_price = avg_buy_price * (1 + self.settings.trailing_stop_activation_profit_rate / 100.0)
            if current_price >= activation_price:
                stock_info.is_trailing_stop_active = True
                stock_info.current_high_price_after_buy = current_price # 활성화 시점 고점 재설정
                self.log(f"{TradeColors.TRAILING}📈 [{code}] 트레일링 스탑 활성화됨 (BOUGHT). 현재가({current_price:.2f}) >= 활성화가({activation_price:.2f}). 기준 고점: {stock_info.current_high_price_after_buy:.2f}{TradeColors.RESET}", "INFO")

        # 최종 익절 조건 검사
        if self._check_and_execute_full_take_profit(code, stock_info, current_price, avg_buy_price, holding_quantity):
            return # 주문 실행됨

        # 부분 익절 조건 검사 (1회만)
        if not stock_info.partial_take_profit_executed:
            if self._check_and_execute_partial_take_profit(code, stock_info, current_price, avg_buy_price, holding_quantity):
                # 부분 익절 후에는 상태가 PARTIAL_SOLD로 변경되어야 함 (on_chejan_data_received에서 처리 예상)
                # 여기서는 주문 실행 후 추가 로직을 진행하지 않도록 return 할 수 있으나,
                # 다른 조건 (예: 트레일링 스탑)도 바로 체크하는 것이 유리할 수 있음.
                # 현재는 부분 익절 주문이 나가면 일단 현재 사이클에서는 추가 동작 안함.
                return 

        # 트레일링 스탑 조건 검사
        if self._check_and_execute_trailing_stop(code, stock_info, current_price, avg_buy_price, holding_quantity):
            return # 주문 실행됨
        
        # 보유 시간 기반 자동 청산 조건
        if self.settings.auto_liquidate_after_minutes_enabled and stock_info.buy_timestamp:
            hold_minutes = (datetime.now() - stock_info.buy_timestamp).total_seconds() / 60
            if hold_minutes >= self.settings.auto_liquidate_after_minutes:
                self.log(f"[{code}] BOUGHT 상태 보유시간({hold_minutes:.1f}분) 기준 자동 청산 조건 충족. 설정: {self.settings.auto_liquidate_after_minutes}분", "IMPORTANT")
                self.execute_sell(code, reason=f"시간청산({hold_minutes:.0f}분)", quantity_type="전량")
                return

    def _handle_partial_sold_state(self, code, stock_info: StockTrackingData, current_price):
        """PARTIAL_SOLD 상태 (일부 매도 후 보유 중)인 종목에 대한 전략을 처리합니다."""
        portfolio_item = self.account_state.portfolio.get(code, {})
        avg_buy_price = _safe_to_float(portfolio_item.get('매입가', stock_info.avg_buy_price)) # 부분매도 후 매입가는 유지될 수도, 업데이트될 수도 있음. DB/포폴 기준.
        holding_quantity = _safe_to_int(portfolio_item.get('보유수량', 0))

        if holding_quantity <= 0:
            self.log(f"[{code}] PARTIAL_SOLD 상태이지만 포트폴리오 보유량 0. 전략 정보 초기화.", "WARNING")
            self.reset_stock_strategy_info(code)
            return

        active_sell_orders = [
            order for order in self.account_state.active_orders.values()
            if order.get('code') == code and order.get('order_type') == '매도' and order.get('unfilled_qty', 0) > 0
        ]
        if active_sell_orders:
            self.log(f"[{code}] PARTIAL_SOLD 상태이나, 활성 매도 주문({len(active_sell_orders)}건) 존재. 추가 매도 조건 검사 건너뜀.", "INFO")
            return
            
        # 손절 조건 검사 (여전히 유효)
        if self._check_and_execute_stop_loss(code, stock_info, current_price, avg_buy_price, holding_quantity):
            return

        # 매수 후 최고가 갱신 (부분 매도 후에도 계속해서 고점 추적)
        if current_price > stock_info.current_high_price_after_buy:
            old_high = stock_info.current_high_price_after_buy
            stock_info.current_high_price_after_buy = current_price
            self.log(f"[{code}] PARTIAL_SOLD 상태 매수 후 최고가 갱신: {old_high} -> {current_price}", "DEBUG")

        # 트레일링 스탑 활성화 (이미 BOUGHT 상태에서 활성화되었을 가능성 높음, 여기서도 체크)
        if not stock_info.is_trailing_stop_active:
            activation_price = avg_buy_price * (1 + self.settings.trailing_stop_activation_profit_rate / 100.0)
            if current_price >= activation_price:
                stock_info.is_trailing_stop_active = True
                stock_info.current_high_price_after_buy = current_price # 활성화 시점 고점 재설정
                self.log(f"{TradeColors.TRAILING}📈 [{code}] 트레일링 스탑 활성화됨 (PARTIAL_SOLD). 현재가({current_price:.2f}) >= 활성화가({activation_price:.2f}). 기준 고점: {stock_info.current_high_price_after_buy:.2f}{TradeColors.RESET}", "INFO")

        # 최종 익절 조건 검사 (남은 물량에 대해)
        if self._check_and_execute_full_take_profit(code, stock_info, current_price, avg_buy_price, holding_quantity):
            return

        # 부분 익절은 이미 실행되었으므로 여기서는 호출하지 않음 (_check_and_execute_partial_take_profit 호출 안함)

        # 트레일링 스탑 조건 검사 (남은 물량에 대해)
        if self._check_and_execute_trailing_stop(code, stock_info, current_price, avg_buy_price, holding_quantity):
            return
            
        # 보유 시간 기반 자동 청산 조건 (남은 물량에 대해)
        if self.settings.auto_liquidate_after_minutes_enabled and stock_info.buy_timestamp: # buy_timestamp는 최초 매수 시점
            hold_minutes = (datetime.now() - stock_info.buy_timestamp).total_seconds() / 60
            if hold_minutes >= self.settings.auto_liquidate_after_minutes:
                self.log(f"[{code}] PARTIAL_SOLD 상태 보유시간({hold_minutes:.1f}분) 기준 자동 청산 조건 충족. 설정: {self.settings.auto_liquidate_after_minutes}분", "IMPORTANT")
                self.execute_sell(code, reason=f"시간청산(잔량,{hold_minutes:.0f}분)", quantity_type="전량")
                return

    def _handle_complete_state(self, code, stock_info: StockTrackingData, current_price):
        """COMPLETE 상태의 종목을 처리합니다. (예: 최대 매수 시도 도달)"""
        self.log(f"[{code}] COMPLETE 상태입니다. 현재가: {current_price}. (추가 거래 작업 없음)", "DEBUG")
        # 필요시, 이 상태의 종목을 주기적으로 재검토하거나 하는 로직 추가 가능
        # 예를 들어, 일정 시간 후 다시 WAITING으로 변경하여 재시도할 수 있게 하거나,
        # 수동 개입 전까지 이 상태를 유지하도록 할 수 있음.
        # 현재는 아무 동작도 하지 않음.
        pass

    def execute_buy(self, code):
        # 일일 매수 횟수 제한 확인 - 제거됨 (종목별 시도 횟수로 대체)
        original_code_param = code # 로깅용
        normalized_code = self._normalize_stock_code(code)
        if original_code_param != normalized_code:
            self.log(f"[EXECUTE_BUY_NORMALIZE] execute_buy: Input code '{original_code_param}' normalized to '{normalized_code}'", "DEBUG")
        
        code = normalized_code # 이후 모든 로직에서 정규화된 코드 사용

        current_date = datetime.now().strftime("%Y-%m-%d")
        if self.today_date_for_buy_limit != current_date:
            self.daily_buy_executed_count = 0
            self.today_date_for_buy_limit = current_date
            self.log(f"일일 매수 제한 카운터를 초기화했습니다. 새 날짜: {current_date}", "INFO")
        
        stock_info = self.watchlist.get(code) # 정규화된 코드로 조회
        if not stock_info:
            self.log(f"매수 실행 불가: {code}는 관심종목 목록에 없습니다.", "ERROR")
            return False
        
        # 종목별 최대 체결 횟수 확인
        if stock_info.buy_completion_count >= self.settings.max_buy_attempts_per_stock:
            self.log(f"[{code}] 매수 실행 불가: 이미 최대 체결 횟수({self.settings.max_buy_attempts_per_stock}회)에 도달했습니다. 현재 체결 횟수: {stock_info.buy_completion_count}", "WARNING")
            stock_info.strategy_state = TradingState.COMPLETE  # 더 이상 매수 시도하지 않도록 상태 변경
            return False
        
        # 매수 시도 횟수 증가 부분 제거 - 체결 시에만 증가하도록 변경
        
        # 매매가 진행 중이거나 거래가 완료된 경우 체크
        if stock_info.strategy_state in [TradingState.BOUGHT, TradingState.PARTIAL_SOLD, TradingState.COMPLETE]:
            self.log(f"[{code}] 매수 실행 불가: 이미 해당 종목은 {stock_info.strategy_state} 상태입니다.", "WARNING")
            return False
        
        # 이후 코드는 그대로 유지
        # ... 기존 코드 ...
        # 주문가능금액 확인
        account_number = self.account_state.account_number
        if not account_number:
            self.log(f"{TradeColors.ERROR}❌ [ERROR] 매수 주문 실패: 계좌번호가 설정되지 않았습니다.{TradeColors.RESET}", "ERROR")
            return False
        
        # 수정된 부분: account_summary에서 직접 주문가능금액을 찾도록 수정
        orderable_cash = _safe_to_int(self.account_state.account_summary.get("주문가능금액", 0))
        
        if orderable_cash < self.settings.buy_amount_per_stock:
            self.log(f"{TradeColors.WARNING}⚠️ [WARNING] 매수 주문 불가: 주문가능금액({orderable_cash:,}원)이 설정된 매수금액({self.settings.buy_amount_per_stock:,}원)보다 적습니다.{TradeColors.RESET}", "WARNING")
            return False
        
        # 현재가 확인 (0 또는 음수면 주문 불가)
        current_price = stock_info.current_price
        if current_price <= 0:
            self.log(f"{TradeColors.WARNING}⚠️ [WARNING] [{code}] 매수 주문 불가: 현재가({current_price})가 유효하지 않습니다.{TradeColors.RESET}", "WARNING") 
            return False
        
        # 주문 수량 계산
        order_quantity = int(self.settings.buy_amount_per_stock / current_price)
        if order_quantity < 1:
            self.log(f"{TradeColors.WARNING}⚠️ [WARNING] [{code}] 매수 주문 불가: 계산된 주문 수량({order_quantity})이 1주 미만입니다.{TradeColors.RESET}", "WARNING")
            return False
        
        # 실제 소요 금액 (현재가 기준)
        expected_total_price = int(current_price * order_quantity)
        
        # 매매 타입 (시장가, 지정가 등) 결정 및 주문가격 설정
        order_type = 1  # 시장가 매수 (default)
        order_price = 0  # 시장가 주문에서는 가격을 0으로 설정
        hoga_gb = "03"  # 시장가 주문에 맞는 호가구분 설정
        
        # 지정가 주문을 원한다면 아래 코드 활성화 및 수정
        # order_type = 2  # 지정가 매수
        # order_price = current_price  # 현재가로 주문 (원하는 가격으로 수정 가능)
        # hoga_gb = "00"  # 지정가 주문에 맞는 호가구분 설정
        
        # 주문 요청 식별자 생성 (RQ_NAME: 주문 응답을 구분하기 위한 식별자)
        rq_name = f"BUY_REQ_{code}_{int(time.time())}"
        
        # 매매 주문 로깅
        self.log(f"{TradeColors.ORDER_SENT}⚡ [ORDER_SENT] 매수 주문 실행: {code} {stock_info.stock_name}, 수량: {order_quantity}주, 현재가: {current_price:,}원, 예상금액: {expected_total_price:,}원{TradeColors.RESET}", "INFO")
        
        # 주문 실행 전에 상태를 WAITING으로 설정 (READY 상태에서만 매수 주문 실행하므로 현재는 큰 영향 없음)
        stock_info.strategy_state = TradingState.WAITING
        
        # 주문 정보 저장 (주문 체결 데이터에서 참조할 정보)
        stock_info.last_order_rq_name = rq_name
        
        # 주문 요청
        if self.modules.kiwoom_api:
            # Dry Run 모드인 경우
            if self.settings.dry_run_mode:
                self.log(f"[DRY RUN] {code} ({stock_info.stock_name}) 매수 주문 요청: 수량={order_quantity}, 가격={current_price:,}원", "INFO")
                # 실제 주문 대신 시뮬레이션 진행
                # 실제 환경에서는 아래 on_chejan_data_received가 호출되지만, dry run에서는 직접 시뮬레이션
                self._simulate_buy_order_execution(code, stock_info, order_quantity, current_price)
                return True
            else:
                # 실제 주문 실행
                result = self.modules.kiwoom_api.send_order(
                    rq_name=rq_name,
                    screen_no="0101",  # 주문용 화면번호
                    acc_no=self.account_state.account_number,  # 계좌번호 추가
                    order_type=order_type,  # 1: 신규매수
                    code=code,
                    quantity=order_quantity,
                    price=order_price,
                    hoga_gb=hoga_gb,  # 시장가 주문(03) 또는 지정가 주문(00)
                    org_order_no=""  # 원주문번호 (취소/정정 시 필요)
                )
                
                # 주문 요청 결과 처리
                if result == 0:
                    self.log(f"{TradeColors.ORDER_RECEIVED}📄 [ORDER_RECEIVED] 매수 주문 접수 성공: {code} {stock_info.stock_name}, 수량: {order_quantity}주{TradeColors.RESET}", "INFO")
                    
                    # 주문 정보 저장 (실제 체결 정보는 OnReceiveChejanData 이벤트에서 처리)
                    order_time = datetime.now()
                    self.account_state.active_orders[rq_name] = {
                        "order_type": "매수",
                        "code": code, # 정규화된 코드 사용
                        "stock_name": stock_info.stock_name,
                        "order_qty": order_quantity,
                        "quantity": order_quantity, # For compatibility if other parts use 'quantity'
                        "price": current_price,  # 주문 시점의 현재가 (참고용)
                        "expected_price": current_price, # <--- 이 줄 추가
                        "order_price": order_price,  # 실제 주문 가격 (지정가 주문 시 사용)
                        "order_time": order_time,
                        "status": "접수",
                        "filled_quantity": 0, # This might be redundant if using last_known_unfilled_qty logic fully
                        "remaining_quantity": order_quantity, # This will be updated by chejan
                        "last_known_unfilled_qty": order_quantity, # Initialize here
                        "filled_price": 0,
                        "order_no": "",  # 접수 후 체결 데이터에서 업데이트
                        "api_order_type": order_type,
                        "api_quote_type": "00"
                    }
                    
                    # 일일 매수 실행 횟수 증가 (전체 매수 실행 횟수 통계용으로만 유지)
                    self.daily_buy_executed_count += 1
                    
                    return True
                else:
                    self.log(f"{TradeColors.ORDER_FAILED}❌ [ORDER_FAILED] 매수 주문 요청 실패: {code} {stock_info.stock_name}, 오류 코드: {result}{TradeColors.RESET}", "ERROR")
                    return False
        else:
            self.log(f"매수 주문 실패: KiwoomAPI 인스턴스가 설정되지 않았습니다.", "ERROR")
            return False


    def execute_sell(self, code, reason="", quantity_type="전량", quantity_val=0):
        original_code_param = code # 로깅용
        normalized_code = self._normalize_stock_code(code)
        if original_code_param != normalized_code:
            self.log(f"[EXECUTE_SELL_NORMALIZE] execute_sell: Input code '{original_code_param}' normalized to '{normalized_code}'", "DEBUG")
        
        code = normalized_code # 이후 모든 로직에서 정규화된 코드 사용

        stock_info = self.watchlist.get(code) # 정규화된 코드로 조회
        if not stock_info:
            self.log(f"매도 주문 실패: {code} StockTrackingData 정보를 찾을 수 없습니다.", "ERROR")
            return False

        self.log(f"[Strategy_EXECUTE_SELL_DEBUG] execute_sell 호출. 계좌번호: '{self.account_state.account_number}'", "DEBUG")
        
        # get_code_market_info는 내부적으로 정규화된 코드를 반환하므로, 여기서는 code (이미 정규화됨) 사용
        pure_code, market_ctx = ats_utils.get_code_market_info(code, logger_instance=self.modules.logger if hasattr(self.modules, 'logger') else None)


        if stock_info.last_order_rq_name:
            self.log(f"매도 주문 건너뜀: {pure_code}(정규화:{code})에 대해 이미 주문({stock_info.last_order_rq_name})이 전송되었거나 처리 중입니다.", "INFO")
            return False

        order_type_to_send = 2 # 기본 KRX 매도
        if market_ctx == 'NXT':
            order_type_to_send = 12 # Nextrade 신규매도
            self.log(f"ATS 주문 감지 ({code}): 시장 NXT, order_type을 {order_type_to_send}로 설정합니다.", "INFO")
        # ... (기타 시장 컨텍스트 처리) ...

        if not self.account_state.account_number:
            self.log(f"{TradeColors.ERROR}❌ [ERROR] 매도 주문 실패: 계좌번호가 설정되지 않았습니다.{TradeColors.RESET}", "ERROR")
            return False

        portfolio_item = self.account_state.portfolio.get(pure_code)
        if not portfolio_item: 
            self.log(f"{TradeColors.ERROR}❌ [ERROR] 매도 주문 실패: {pure_code}(원본:{code}) 포트폴리오에 없음.{TradeColors.RESET}", "ERROR")
            return False
            
        current_price = stock_info.current_price # StockTrackingData 에서 현재가 사용
        if current_price == 0:
            self.log(f"{TradeColors.ERROR}❌ [ERROR] 매도 주문 실패 ({pure_code}, 원본:{code}): 현재가 정보 없음.{TradeColors.RESET}", "ERROR")
            return False

        available_quantity = _safe_to_int(portfolio_item.get('보유수량')) 

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
                "full_take_profit_target_rate": self.settings.full_take_profit_target_rate, # 수정됨
                "partial_take_profit_rate": self.settings.partial_take_profit_rate, 
                "partial_sell_ratio": self.settings.partial_sell_ratio,
                "trailing_stop_fall_rate": self.settings.trailing_stop_fall_rate,
                "high_price_for_trailing": stock_info.current_high_price_after_buy
            }
        }
        self.modules.db_manager.add_decision_record(get_current_time_str(), pure_code, "매도", decision_reason_full, related_data_for_decision)

        if available_quantity == 0:
            self.log(f"{TradeColors.WARNING}⚠️ [WARNING] 매도 주문 실패 ({pure_code}, 원본:{code}): 매도 가능 수량 0.{TradeColors.RESET}", "WARNING")
            return False

        sell_quantity = 0
        if quantity_type == "전량":
            sell_quantity = available_quantity
        elif quantity_type == "비율": 
            sell_quantity = int(available_quantity * (_safe_to_float(quantity_val) / 100.0))
        elif quantity_type == "수량":
            sell_quantity = min(_safe_to_int(quantity_val), available_quantity)
        
        if sell_quantity <= 0: 
            self.log(f"매도 주문 실패 ({pure_code}, 원본:{code}): 계산된 매도 수량 {sell_quantity} (타입: {quantity_type}, 값: {quantity_val}, 보유량: {available_quantity})", "WARNING")
            return False

        price_to_order = current_price 
        rq_name = f"매도_{pure_code}_{get_current_time_str(format='%H%M%S%f')}_{reason}" 
        screen_no = self.modules.screen_manager.get_available_screen(rq_name) 

        self.log(f"{TradeColors.ORDER_SENT}⚡ [ORDER_SENT] 매도 주문 시도 ({reason}): {code} {stock_info.stock_name}, 수량: {sell_quantity}, 가격: {price_to_order}{TradeColors.RESET}", "INFO")
        
        order_ret = self.modules.kiwoom_api.send_order(rq_name, screen_no, self.account_state.account_number, order_type_to_send, pure_code, sell_quantity, int(price_to_order), "03", "") 

        if order_ret == 0:
            self.log(f"{TradeColors.ORDER_RECEIVED}📄 [ORDER_RECEIVED] 매도 주문 접수 성공: {pure_code} ({reason}), RQName: {rq_name}{TradeColors.RESET}", "INFO")
            stock_info.last_order_rq_name = rq_name # StockTrackingData에 RQName 저장
            self.account_state.active_orders[rq_name] = {
                'order_no': None, 
                'code': pure_code, # 순수 코드 (API 전달용)
                'stock_name': stock_info.stock_name,
                'order_type': '매도',
                'order_qty': sell_quantity, # Original total quantity for this order
                'unfilled_qty': sell_quantity, # Initial unfilled quantity
                'last_known_unfilled_qty': sell_quantity, # Initialize here
                'order_price': price_to_order,
                'expected_price': price_to_order, # <--- 이 줄 추가
                'order_status': '접수요청', 
                'timestamp': get_current_time_str(),
                'reason': reason
            }
            
            # 주문 접수 성공 시 포트폴리오와 StockTrackingData의 보유량을 임시로 감소
            # 이렇게 하면 중복 주문 발생을 방지할 수 있음
            old_portfolio_quantity = portfolio_item.get('보유수량', 0)
            portfolio_item['임시_주문수량'] = portfolio_item.get('임시_주문수량', 0) + sell_quantity
            
            # StockTrackingData에 임시 주문 수량 기록
            old_tracking_quantity = stock_info.total_buy_quantity
            stock_info.temp_order_quantity = getattr(stock_info, 'temp_order_quantity', 0) + sell_quantity
            
            self.log(f"매도 주문 접수 후 임시 수량 처리: {pure_code} (원본:{code}), 주문량: {sell_quantity}, "
                     f"포트폴리오 임시주문량: {portfolio_item['임시_주문수량']}, "
                     f"StockTracking 임시주문량: {stock_info.temp_order_quantity}", "INFO")
            
            self.log(f"active_orders에 매도 주문 추가: {rq_name}, 상세: {self.account_state.active_orders[rq_name]}", "DEBUG")
            return True
        else:
            self.log(f"{TradeColors.ORDER_FAILED}❌ [ORDER_FAILED] 매도 주문 접수 실패: {pure_code} ({reason}), 반환값: {order_ret}{TradeColors.RESET}", "ERROR")
            if screen_no: self.modules.screen_manager.release_screen(screen_no, rq_name) 
            return False

    def reset_stock_strategy_info(self, code):
        """종목의 전략 상태와 관련 정보를 초기화합니다."""
        original_code_param = code # 로깅용
        normalized_code = self._normalize_stock_code(code)
        if original_code_param != normalized_code:
            self.log(f"[RESET_STOCK_NORMALIZE] reset_stock_strategy_info: Input code '{original_code_param}' normalized to '{normalized_code}'", "DEBUG")
        
        code = normalized_code # 이후 모든 로직에서 정규화된 코드 사용

        stock_info = self.watchlist.get(code) # 정규화된 코드로 조회
        if not stock_info:
            self.log(f"[{code}] reset_stock_strategy_info 실패: 관심종목 목록에 없음", "ERROR")
            return False
        
        # 상태 초기화
        old_state = stock_info.strategy_state
        stock_info.strategy_state = TradingState.WAITING
        stock_info.avg_buy_price = 0.0
        stock_info.total_buy_quantity = 0
        stock_info.current_high_price_after_buy = 0.0
        stock_info.is_trailing_stop_active = False
        stock_info.trailing_stop_partially_sold = False
        stock_info.partial_take_profit_executed = False
        stock_info.buy_timestamp = None
        stock_info.buy_completion_count = 0  # 매수 체결 완료 횟수 초기화
        
        # 임시 주문 수량 초기화
        if hasattr(stock_info, 'temp_order_quantity'):
            old_temp_qty = getattr(stock_info, 'temp_order_quantity', 0)
            stock_info.temp_order_quantity = 0
            self.log(f"[{code}] 상태 초기화 중 임시 주문 수량도 초기화: {old_temp_qty} -> 0", "DEBUG")
        
        # trading_status에서도 제거
        if code in self.account_state.trading_status:
            del self.account_state.trading_status[code]
        
        self.log(f"[{code}] 종목 상태 초기화: {old_state} -> {stock_info.strategy_state}", "INFO")
        return True

        # 임시 주문 수량 초기화
        if hasattr(stock_info, 'temp_order_quantity'):
            stock_info.temp_order_quantity = 0
        
        # trading_status에서도 제거
        if code in self.account_state.trading_status:
            del self.account_state.trading_status[code]
        
        self.log(f"[{code}] 종목 상태 초기화: {old_state} -> {stock_info.strategy_state}", "INFO")
        return True

    def update_portfolio_on_execution(self, code, stock_name, trade_price, quantity, trade_type):
        """
        주문 체결 시 포트폴리오 정보를 업데이트합니다.
        trade_type: '매수', '매도'
        """
        original_code_param = code # 로깅용
        normalized_code = self._normalize_stock_code(code)
        if original_code_param != normalized_code:
            self.log(f"[PORTFOLIO_UPDATE_NORMALIZE] update_portfolio_on_execution: Input code '{original_code_param}' normalized to '{normalized_code}'", "DEBUG")
        
        code = normalized_code # 이후 모든 로직에서 정규화된 코드 사용

        trade_price = _safe_to_float(trade_price)
        quantity = _safe_to_int(quantity)
        portfolio = self.account_state.portfolio
        
        stock_data = self.watchlist.get(code) # 정규화된 코드로 조회

        if trade_type == '매수':
            if code not in portfolio: # 정규화된 코드로 확인 및 추가
                portfolio[code] = {
                    'stock_name': stock_name, # stock_name은 파라미터로 받은 것 사용
                    '보유수량': 0,
                    '매입가': 0, 
                    '매입금액': 0, 
                    '평가금액': 0,
                    '평가손익': 0,
                    '수익률': 0.0
                }
            
            current_quantity = _safe_to_int(portfolio[code].get('보유수량',0))
            current_total_buy_amount = _safe_to_float(portfolio[code].get('매입금액',0))
            
            new_total_quantity = current_quantity + quantity
            new_total_buy_amount = current_total_buy_amount + (trade_price * quantity)
            
            portfolio[code]['보유수량'] = new_total_quantity
            portfolio[code]['매입금액'] = new_total_buy_amount
            if new_total_quantity > 0 :
                portfolio[code]['매입가'] = new_total_buy_amount / new_total_quantity
            else:
                 portfolio[code]['매입가'] = 0
            
            # StockTrackingData 업데이트
            if stock_data:
                # 이전 보유 수량 기록 (로깅용)
                prev_total_buy_quantity = stock_data.total_buy_quantity
                
                # 매수 체결 시 - 포트폴리오 보유수량으로 StockTrackingData 업데이트
                stock_data.total_buy_quantity = new_total_quantity
                stock_data.avg_buy_price = portfolio[code]['매입가']
                
                # 매수 시 항상 상태를 BOUGHT로 설정 (부분체결 시에도)
                if stock_data.strategy_state != TradingState.BOUGHT:
                    stock_data.strategy_state = TradingState.BOUGHT
                    stock_data.buy_timestamp = datetime.now()
                    self.log(f"[{code}] 매수 체결로 상태 변경: {stock_data.strategy_state.name}, 보유량 업데이트: {prev_total_buy_quantity} -> {stock_data.total_buy_quantity}", "INFO")
                else:
                    self.log(f"[{code}] 추가 매수 체결: 보유량 업데이트: {prev_total_buy_quantity} -> {stock_data.total_buy_quantity}", "INFO")
            
            # 매수 시 trading_status에 항목 추가
            self.account_state.trading_status[code] = {
                'status': TradingState.BOUGHT,
                'bought_price': portfolio[code]['매입가'],
                'bought_quantity': new_total_quantity,
                'bought_time': datetime.now()
            }
            self.log(f"[상태 업데이트] {code} ({stock_name}) 트레이딩 상태를 BOUGHT로 설정. 매수가: {portfolio[code]['매입가']}", "INFO")

        elif trade_type == '매도':
            if code in portfolio:
                old_quantity = portfolio[code]['보유수량']
                portfolio[code]['보유수량'] -= quantity
                
                # StockTrackingData 업데이트 (매도 체결 시 total_buy_quantity 동기화)
                if stock_data:
                    old_tracking_quantity = stock_data.total_buy_quantity
                    stock_data.total_buy_quantity = portfolio[code]['보유수량']
                    self.log(f"[{code}] 매도 체결 후 StockTrackingData 업데이트: 보유량 {old_tracking_quantity} -> {stock_data.total_buy_quantity} (포트폴리오: {old_quantity} -> {portfolio[code]['보유수량']})", "INFO")
                
                if portfolio[code]['보유수량'] <= 0:
                    self.log(f"{stock_name}({code}) 전량 매도 완료. 포트폴리오 항목 유지 (수량 0).", "INFO")
                    portfolio[code]['보유수량'] = 0 
                    portfolio[code]['매입가'] = 0 
                    portfolio[code]['매입금액'] = 0
                    
                    # StockTrackingData 수량도 0으로 설정하고 상태 초기화
                    if stock_data:
                        stock_data.total_buy_quantity = 0
                        # 전량 매도 시 상태 초기화
                        self.reset_stock_strategy_info(code)
                    
                    # 매도 완료 시 trading_status에서 SOLD로 상태 변경
                    if code in self.account_state.trading_status:
                        self.account_state.trading_status[code]['status'] = TradingState.SOLD
                        self.log(f"[상태 업데이트] {code} ({stock_name}) 트레이딩 상태를 SOLD로 변경", "INFO")
                else:
                    # 부분 매도 시 상태를 PARTIAL_SOLD로 변경
                    if stock_data and stock_data.strategy_state == TradingState.BOUGHT:
                        stock_data.strategy_state = TradingState.PARTIAL_SOLD
                        self.log(f"[{code}] 부분 매도로 상태 변경: {stock_data.strategy_state.name}, 잔여 수량: {stock_data.total_buy_quantity}", "INFO")
            else:
                self.log(f"매도 체결 처리 오류: {code}가 포트폴리오에 없음.", "WARNING")
                return 

        if stock_data and code in portfolio and portfolio[code]['보유수량'] > 0:
            current_price = stock_data.current_price # watchlist의 StockTrackingData에서 현재가 사용
            avg_buy_price = _safe_to_float(portfolio[code]['매입가'])
            held_quantity = _safe_to_int(portfolio[code]['보유수량'])

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

        self.log(f"{TradeColors.PORTFOLIO}📊 [PORTFOLIO] 포트폴리오 업데이트 ({trade_type}): {code}, 보유수량: {portfolio.get(code, {}).get('보유수량')}, 매입가: {portfolio.get(code, {}).get('매입가', 0):.2f}{TradeColors.RESET}", "INFO")

    def get_account_summary(self):
        """계좌 요약 정보를 반환합니다."""
        summary = {
            "총매입금액": _safe_to_float(self.account_state.account_summary.get('총매입금액')),
            "총평가금액": _safe_to_float(self.account_state.account_summary.get('총평가금액')),
            "총평가손익금액": _safe_to_float(self.account_state.account_summary.get('총평가손익금액')),
            "총수익률": _safe_to_float(self.account_state.account_summary.get('총수익률(%)')),
            "추정예탁자산": _safe_to_float(self.account_state.account_summary.get('추정예탁자산')),
            "예수금": _safe_to_float(self.account_state.account_summary.get('예수금', self.account_state.account_summary.get('d+2추정예수금')))
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
        self.log("===========================================", "INFO")
        
        # 런타임 문자열 생성
        runtime = time.time() - self.start_time
        hours, rem = divmod(runtime, 3600)
        minutes, seconds = divmod(rem, 60)
        runtime_str = f"{int(hours)}시간 {int(minutes)}분 {int(seconds)}초"
        
        self.log(f"운영 시간: {runtime_str} (시작: {self.start_time_str})", "INFO")
        self.log(f"초기화 완료된 전략 실행 중. 자세한 상태는 주기적 보고에서 확인하세요.", "INFO")
        self.log("===========================================", "INFO")
        
        # 일일 매수 제한 정보는 통계용으로만 표시
        self.log(f"일일 매수 실행 횟수: {self.daily_buy_executed_count} (통계용)", "INFO")

        # 종목별 매수 시도 횟수 표시 (매수 시도가 있는 모든 종목)
        attempt_stocks = [(code, info.stock_name, info.buy_completion_count, info.strategy_state.name) 
                         for code, info in self.watchlist.items() 
                         if info.buy_completion_count > 0]
        
        if attempt_stocks:
            self.log(f"종목별 매수 시도 현황 (최대 {self.settings.max_buy_attempts_per_stock}회):", "INFO")
            # 매수 시도 횟수 기준 내림차순 정렬
            attempt_stocks.sort(key=lambda x: x[2], reverse=True)
            for code, name, count, state in attempt_stocks:
                max_reached = " (최대치)" if count >= self.settings.max_buy_attempts_per_stock else ""
                self.log(f"  - [{code}] {name}: {count}/{self.settings.max_buy_attempts_per_stock}회{max_reached}, 상태: {state}", "INFO")
        
        self.log("===========================================", "INFO")

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
                parsed_data[fid_str] = _safe_to_int(value_str)
            elif fid_str in float_fids:
                parsed_data[fid_str] = _safe_to_float(value_str)
            else:
                parsed_data[fid_str] = str(value_str).strip() if value_str is not None else ''
        return parsed_data

    def _find_active_order_rq_name_key(self, code_from_chejan, api_order_no_from_chejan, chejan_data_dict): # chejan_data_dict는 로깅용으로만 사용될 수 있음
        # 종목코드 정규화 ('A'로 시작하는 경우 제거)
        normalized_code = code_from_chejan
        if normalized_code and normalized_code.startswith('A') and len(normalized_code) > 1:
            normalized_code = normalized_code[1:]
        
        self.log(f"_find_active_order_rq_name_key: 종목코드({code_from_chejan} -> {normalized_code}), API주문번호({api_order_no_from_chejan if api_order_no_from_chejan else 'N/A'}) 탐색 시작.", "DEBUG")

        if not self.account_state or not self.account_state.active_orders:
            self.log(f"_find_active_order_rq_name_key: self.account_state.active_orders가 비어있거나 없습니다.", "WARNING")
            return None

        # 1. API 주문번호가 있고, active_orders의 'order_no'와 일치하는 경우
        if api_order_no_from_chejan:
            for rq_name_key, order_entry in self.account_state.active_orders.items():
                order_no_from_entry = order_entry.get('order_no')
                if order_no_from_entry and order_no_from_entry == api_order_no_from_chejan:
                    self.log(f"_find_active_order_rq_name_key: API주문번호({api_order_no_from_chejan})로 active_orders에서 일치하는 항목 찾음: {rq_name_key}", "DEBUG")
                    return rq_name_key

        # 2. 종목코드로 매칭 (마지막으로 해당 종목에 대해 요청된 주문)
        if normalized_code:
            matching_entries = []
            for rq_name_key, order_entry in self.account_state.active_orders.items():
                code_from_entry = order_entry.get('code')
                # 종목코드도 정규화하여 비교
                normalized_code_from_entry = code_from_entry
                if normalized_code_from_entry and normalized_code_from_entry.startswith('A') and len(normalized_code_from_entry) > 1:
                    normalized_code_from_entry = normalized_code_from_entry[1:]
                
                if normalized_code_from_entry and normalized_code_from_entry == normalized_code:
                    matching_entries.append((rq_name_key, order_entry))
            
            # 가장 최근 주문 선택 (마지막에 추가된 항목이 최근 주문이라고 가정)
            if matching_entries:
                # timestamp가 있으면 timestamp로 정렬, 없으면 마지막 항목 선택
                if all('timestamp' in entry[1] for entry in matching_entries):
                    # 타임스탬프 기준 내림차순 정렬
                    matching_entries.sort(key=lambda x: x[1].get('timestamp', 0), reverse=True)
                
                latest_rq_name_key, latest_entry = matching_entries[0]
                self.log(f"_find_active_order_rq_name_key: 종목코드({normalized_code})로 active_orders에서 일치하는 항목 찾음: {latest_rq_name_key}", "DEBUG")
                return latest_rq_name_key

        # 3. BUY_REQ, SELL_REQ로 시작하는 RQName에서 코드 추출 시도
        if normalized_code:
            buy_req_prefix = f"BUY_REQ_{normalized_code}_"
            sell_req_prefix = f"SELL_REQ_{normalized_code}_"
            
            for rq_name_key in self.account_state.active_orders.keys():
                if (rq_name_key.startswith(buy_req_prefix) or 
                    rq_name_key.startswith(sell_req_prefix)):
                    self.log(f"_find_active_order_rq_name_key: RQName 패턴({buy_req_prefix} 또는 {sell_req_prefix})으로 active_orders에서 일치하는 항목 찾음: {rq_name_key}", "DEBUG")
                    return rq_name_key

        self.log(f"_find_active_order_rq_name_key: 종목코드({normalized_code}), API주문번호({api_order_no_from_chejan if api_order_no_from_chejan else 'N/A'})로 일치하는 활성 주문을 찾지 못했습니다.", "WARNING")
        return None

    def on_chejan_data_received(self, gubun, chejan_data):  # item_cnt, fid_list_str 제거, chejan_data는 dict
        self.log(f"체결/잔고 데이터 수신 - 구분: {gubun}", "DEBUG")  # item_cnt 관련 로그 제거
        self.current_status_message = f"체결/잔고 수신 (구분: {gubun})"
        
        # fid_list_str을 이용한 파싱 로직은 KiwoomAPI에서 처리하고 결과를 chejan_data로 전달받으므로 여기서는 불필요.
        if not chejan_data or not isinstance(chejan_data, dict):
            self.log(f"수신된 체결 데이터(chejan_data)가 없거나 딕셔너리 형태가 아닙니다. 타입: {type(chejan_data)}", "WARNING")
            return

        self.log(f"체결/잔고 FID 상세: {chejan_data}", "DEBUG") # FID 전체 로깅

        code_raw = chejan_data.get('9001', '')  # 종목코드 FID (예: A005930)
        api_order_no = chejan_data.get('9203', '') # 주문번호 FID
        stock_name_fid = chejan_data.get('302', '') # 종목명 FID (KOA Studio 기준)
        order_status = chejan_data.get('913', '')  # 주문상태 (접수, 체결 등)
        filled_qty = chejan_data.get('911', '')    # 체결량
        filled_price = chejan_data.get('10', '')   # 체결가
        order_type_fid = chejan_data.get('905', '') # 주문구분 (매도/매수)
        
        # 처리 전 중요 필드 로깅
        self.log(f"체결 처리 시작 - 종목코드: {code_raw}, 주문번호: {api_order_no}, 상태: {order_status}, 체결량: {filled_qty}, 체결가: {filled_price}, 주문구분: {order_type_fid}", "INFO")
        
        # 🔧 핵심 수정: 모든 곳에서 동일한 정규화 로직 사용
        code = self._normalize_stock_code(code_raw)
        if not code: # 종목코드가 비어있는 경우
            self.log(f"체결 데이터에서 종목코드(FID 9001)를 얻지 못했습니다. 원본: '{code_raw}', 정규화: '{code}', Gubun: {gubun}", "ERROR")
            # 다른 로직에서 이 code를 사용할 경우 문제가 될 수 있으므로, 여기서 처리를 중단하거나 기본값 설정 필요.
            # 여기서는 일단 진행하되, _find_active_order_rq_name_key 등에서 code가 비어있으면 실패할 것임.
            pass # code는 빈 문자열로 유지

        stock_info = self.watchlist.get(code) if code else None
        
        # 🔧 추가: StockTrackingData 검색 실패 시 상세 로깅
        if not stock_info and code:
            self.log(f"[STOCKDATA_SEARCH_FAIL] 체결 데이터 처리 중 StockTrackingData 검색 실패", "WARNING")
            self.log(f"  - 원본 코드: '{code_raw}', 정규화된 코드: '{code}'", "WARNING") 
            self.log(f"  - 현재 watchlist 종목들: {list(self.watchlist.keys())}", "WARNING")
            
            # 백업 검색: 원본 코드로도 시도
            if code_raw != code:
                stock_info = self.watchlist.get(code_raw)
                if stock_info:
                    self.log(f"  - 원본 코드('{code_raw}')로 StockTrackingData 발견! 정규화 불일치 문제 확인됨", "CRITICAL")
                    code = code_raw  # 발견된 코드로 업데이트 # code가 비어있으면 stock_info도 None
        
        # 종목명 우선순위: 1. watchlist의 stock_name, 2. FID 302의 종목명, 3. 그냥 code (비어있을수도)
        stock_name = stock_info.stock_name if stock_info and stock_info.stock_name else \
                     (stock_name_fid if stock_name_fid else (code if code else "종목코드없음"))
        
        # 🔧 StockTrackingData 발견 여부 로깅
        if stock_info:
            self.log(f"[STOCKDATA_FOUND] '{stock_name}'({code}) StockTrackingData 정상 접근 (상태: {stock_info.strategy_state.name})", "DEBUG")
        else:
            self.log(f"[STOCKDATA_NOT_FOUND] '{stock_name}'({code}) StockTrackingData 접근 실패 - 백업 처리 또는 무시", "WARNING")

        # _find_active_order_entry 대신 _find_active_order_rq_name_key 사용
        # 이 함수는 self.account_state.active_orders의 '키' (즉, rq_name)를 반환함.
        original_rq_name_key = self._find_active_order_rq_name_key(code_raw, api_order_no, chejan_data)
        
        active_order_entry_ref = None # 실제 active_orders 딕셔너리 내의 주문 객체에 대한 참조
        if original_rq_name_key and original_rq_name_key in self.account_state.active_orders:
            active_order_entry_ref = self.account_state.active_orders[original_rq_name_key]
            self.log(f"체결 데이터({code}, API주문번호 {api_order_no if api_order_no else 'N/A'})에 대한 활성 주문 참조 획득 성공 (RQName Key: {original_rq_name_key})", "DEBUG")
        else:
            self.log(f"체결 데이터({code}, API주문번호 {api_order_no if api_order_no else 'N/A'})에 대한 활성 주문 참조 획득 실패. original_rq_name_key: {original_rq_name_key}", "DEBUG")
            
            # 활성 주문 참조를 찾지 못했지만 체결 데이터가 존재하는 경우 백업 처리
            if gubun == '0' and stock_info and code and order_status == '체결' and filled_qty:
                self.log(f"[백업 처리] {code} ({stock_name}) 주문 참조 없이 체결 데이터 수신. 포트폴리오 정보로 상태 업데이트 시도", "WARNING")
                
                # 체결량과 체결가 가져오기
                filled_qty_int = _safe_to_int(filled_qty)
                filled_price_float = _safe_to_float(filled_price)
                
                # 매수/매도 구분 확인
                is_buy_order = order_type_fid and ('매수' in order_type_fid)
                is_sell_order = order_type_fid and ('매도' in order_type_fid)
                
                # 매수 체결인 경우
                if is_buy_order and filled_qty_int > 0:
                    # 이미 stock_info.last_order_rq_name이 있는 경우 초기화
                    if stock_info.last_order_rq_name:
                        self.log(f"[백업 처리] {code} ({stock_name}) last_order_rq_name 초기화: {stock_info.last_order_rq_name} -> None", "WARNING")
                        stock_info.last_order_rq_name = None
                    
                    # 매수 체결 횟수 증가
                    stock_info.buy_completion_count += 1
                    self.log(f"[백업 처리] [{code}] 매수 체결 완료 #{stock_info.buy_completion_count}/{self.settings.max_buy_attempts_per_stock}", "WARNING")
                    
                    # 상태 업데이트
                    stock_info.strategy_state = TradingState.BOUGHT
                    self.log(f"[백업 처리] [매수 체결 완료] {code} ({stock_name}) 상태 변경: {stock_info.strategy_state.name}", "IMPORTANT")
                    
                    # 포트폴리오 정보 업데이트
                    portfolio_item = self.account_state.portfolio.get(code)
                    if portfolio_item:
                        stock_info.avg_buy_price = _safe_to_float(portfolio_item.get('매입가'))
                        stock_info.total_buy_quantity = _safe_to_int(portfolio_item.get('보유수량'))
                        stock_info.current_high_price_after_buy = stock_info.avg_buy_price
                        stock_info.buy_timestamp = datetime.now()
                        
                        # trading_status에도 상태 저장
                        self.account_state.trading_status[code] = {
                            'status': TradingState.BOUGHT,
                            'bought_price': stock_info.avg_buy_price,
                            'bought_quantity': stock_info.total_buy_quantity,
                            'bought_time': stock_info.buy_timestamp
                        }
                        
                        self.log(f"[백업 처리] [매수 정보 기록] {code}: 매수가({stock_info.avg_buy_price}), 수량({stock_info.total_buy_quantity}), 매수시간({stock_info.buy_timestamp.strftime('%Y-%m-%d %H:%M:%S') if stock_info.buy_timestamp else 'N/A'})", "WARNING")
                        
                        # 즉시 process_strategy 호출하여 매도 조건 확인
                        self.log(f"[백업 처리] [즉시 매도 조건 확인] {code} 매수 체결 후 즉시 매도 조건 확인 시작", "WARNING")
                        self.process_strategy(code)
                    else:
                        self.log(f"[백업 처리] 매수 완료 후 포트폴리오 항목을 찾을 수 없어 StockTrackingData 일부 업데이트 실패 ({code})", "ERROR")
                
                # 매도 체결인 경우
                elif is_sell_order and filled_qty_int > 0:
                    self.log(f"[백업 처리] {code} ({stock_name}) 매도 체결 처리 - 상태 변경 필요 여부 확인", "WARNING")
                    
                    # 포트폴리오 확인하여 보유 수량이 0이면 초기화
                    portfolio_item = self.account_state.portfolio.get(code)
                    if portfolio_item and _safe_to_int(portfolio_item.get('보유수량', 0)) == 0:
                        self.log(f"[백업 처리] {code} ({stock_name}) 전량 매도 완료. 관련 전략 정보 초기화.", "WARNING")
                        self.reset_stock_strategy_info(code)

        if gubun == '0':  # 주문체결통보
            log_msg_prefix = f"주문 체결 통보 - 종목: {stock_name}({code if code else '코드없음'})"
            log_msg_suffix = f"API 주문번호: {api_order_no if api_order_no else 'N/A'}, 연결된 RQName Key: {original_rq_name_key if original_rq_name_key else 'N/A'}"
            self.log(f"{log_msg_prefix}, {log_msg_suffix}", "INFO")
            # active_order_entry_ref가 있는 경우만 정상 처리
            if active_order_entry_ref:
                # active_order_entry_ref (참조)와 original_rq_name_key (키)를 전달
                self._handle_order_execution_report(chejan_data, active_order_entry_ref, original_rq_name_key, code, stock_name, stock_info)
        elif gubun == '1':  # 국내주식 잔고통보
            self.log(f"계좌 잔고 변경 통보 - 종목: {stock_name}({code if code else '코드없음'}), API 주문번호: {api_order_no if api_order_no else 'N/A'}", "INFO")
            # active_order_entry_ref (참조)와 original_rq_name_key (키)를 전달
            self._handle_balance_update_report(chejan_data, active_order_entry_ref, original_rq_name_key, code, stock_name, stock_info)
        else:
            self.log(f"알 수 없는 체결 구분 값: {gubun}", "WARNING")
        
        self.current_status_message = f"체결/잔고 처리 완료 (구분: {gubun}, 종목: {code if code else '코드없음'})"

    def _handle_order_execution_report(self, chejan_data, active_order_entry_ref, original_rq_name_key, code, stock_name, stock_info: Optional[StockTrackingData]):
        """주문 체결 보고를 처리합니다. 매수 체결 완료 시 buy_completion_count를 증가시킵니다."""
        # active_order_entry_ref가 None이면 더 이상 진행할 수 없음
        if active_order_entry_ref is None:
            log_api_order_no = chejan_data.get("9203", "N/A")
            self.log(f"주문 접수/확인 처리 중단 ({stock_name}, {code}): 연관된 활성 주문 참조(active_order_entry_ref)를 찾을 수 없습니다. API주문번호: {log_api_order_no}. ChejanData: {chejan_data}", "WARNING")
            return

        # API 주문번호(9203)가 체결 데이터에 있고, active_order_entry_ref의 order_no가 아직 None이면 업데이트 (원본 객체 직접 수정)
        api_order_no_from_chejan = chejan_data.get("9203")
        if api_order_no_from_chejan and active_order_entry_ref.get('order_no') is None:
            active_order_entry_ref['order_no'] = api_order_no_from_chejan
            self.log(f"활성 주문에 API 주문번호 업데이트 (원본 수정): {active_order_entry_ref['order_no']} (RQName Key: {original_rq_name_key}, Code: {code})", "INFO")

        order_status = chejan_data.get("913")  # 주문상태 (예: 접수, 확인, 체결)
        original_order_qty = _safe_to_int(chejan_data.get("900"))  # 주문수량 FID
        unfilled_qty = _safe_to_int(chejan_data.get("902"))        # 미체결수량 FID (키움 API에서 직접 제공)
        total_filled_qty = original_order_qty - unfilled_qty           # 체결누계수량 (계산)
        
        # active_order_entry_ref는 원본이므로, 여기서의 변경사항은 self.account_state.active_orders에 반영됨
        # 키움 API에서 직접 제공하는 미체결수량을 사용하여 정확성 향상
        initial_order_qty_from_ref = active_order_entry_ref.get('order_qty', 0)
        
        active_order_entry_ref['unfilled_qty'] = unfilled_qty  # 키움 API에서 제공한 미체결량 사용
        active_order_entry_ref['order_status'] = order_status

        log_order_no_ref = active_order_entry_ref.get('order_no', 'N/A') # 참조에서 주문번호 가져오기
        self.log(f"주문 접수/확인 ({code}, {stock_name}): RQNameKey({original_rq_name_key}), API주문번호({log_order_no_ref}), 상태({order_status}), 원주문수량({original_order_qty}), 총체결({total_filled_qty}), 미체결({unfilled_qty})", "INFO")

        if total_filled_qty > 0: # 누적 체결량이 0보다 크면 (부분 또는 전체 체결)
            last_filled_price = _safe_to_float(chejan_data.get("10")) # 체결가 FID
            
            # 🔧 핵심 수정: last_filled_qty 계산 로직 변경
            current_unfilled_qty_from_chejan = _safe_to_int(chejan_data.get("902")) # FID 902
            
            # Get the original order quantity for fallback if 'last_known_unfilled_qty' is somehow missing
            original_order_qty_from_ref = active_order_entry_ref.get('order_qty', 0) 
            
            previous_unfilled_qty_for_calc = active_order_entry_ref.get('last_known_unfilled_qty', original_order_qty_from_ref)
            
            last_filled_qty = previous_unfilled_qty_for_calc - current_unfilled_qty_from_chejan
            
            # Update last_known_unfilled_qty for the next event
            active_order_entry_ref['last_known_unfilled_qty'] = current_unfilled_qty_from_chejan
            
            # The line active_order_entry_ref['unfilled_qty'] = unfilled_qty can remain for general info
            # active_order_entry_ref['unfilled_qty'] = current_unfilled_qty_from_chejan # This is fine, already done a few lines above: active_order_entry_ref['unfilled_qty'] = unfilled_qty

            if last_filled_qty > 0: # 이번 체결 이벤트에서 실제 체결된 수량이 있을 경우
                trade_type = active_order_entry_ref['order_type'] # '매수' 또는 '매도'
                self.log(f"{TradeColors.FILLED}✅ [FILLED] 체결 발생: {code} ({stock_name}), 유형({trade_type}), 체결가({last_filled_price}), 체결량({last_filled_qty}){TradeColors.RESET}", "INFO")
                
                # 부분 체결 시 임시 주문 수량 비례 감소 (매도 주문인 경우)
                if trade_type == '매도' and stock_info:
                    portfolio_item = self.account_state.portfolio.get(code)
                    if portfolio_item and portfolio_item.get('임시_주문수량', 0) > 0:
                        old_portfolio_temp_qty = portfolio_item.get('임시_주문수량', 0)
                        # 체결된 수량만큼 임시 주문 수량 감소
                        new_portfolio_temp_qty = max(0, old_portfolio_temp_qty - last_filled_qty)
                        portfolio_item['임시_주문수량'] = new_portfolio_temp_qty
                        self.log(f"[{code}] 부분 체결로 포트폴리오 임시 주문 수량 감소: {old_portfolio_temp_qty} -> {new_portfolio_temp_qty} (체결량: {last_filled_qty})", "INFO")
                    
                    if hasattr(stock_info, 'temp_order_quantity') and stock_info.temp_order_quantity > 0:
                        old_stock_temp_qty = stock_info.temp_order_quantity
                        # 체결된 수량만큼 임시 주문 수량 감소
                        new_stock_temp_qty = max(0, old_stock_temp_qty - last_filled_qty)
                        stock_info.temp_order_quantity = new_stock_temp_qty
                        self.log(f"[{code}] 부분 체결로 StockTrackingData 임시 주문 수량 감소: {old_stock_temp_qty} -> {new_stock_temp_qty} (체결량: {last_filled_qty})", "INFO")
                
                
                slippage = 0  # 기본값
                expected_price = active_order_entry_ref.get('expected_price')
                if expected_price is not None and expected_price > 0 and last_filled_price > 0 : # last_filled_price는 이번 체결 가격
                    if active_order_entry_ref['order_type'] == '매수':
                        slippage = last_filled_price - expected_price
                    elif active_order_entry_ref['order_type'] == '매도':
                        slippage = expected_price - last_filled_price
                    self.log(f"[{code}] 슬리피지 계산: {slippage:.2f} (예상가: {expected_price:.2f}, 체결가: {last_filled_price:.2f}, 유형: {active_order_entry_ref['order_type']})")
                else:
                    self.log(f"[{code}] 슬리피지 계산 불가: expected_price({expected_price}) 또는 last_filled_price({last_filled_price}) 정보 부족", "WARNING")
                
                self.update_portfolio_on_execution(code, stock_name, last_filled_price, last_filled_qty, trade_type)

                # 매수 체결인 경우 추가 처리 (부분 체결 시에도 체결 정보와 상태 업데이트)
                if trade_type == '매수' and stock_info:
                    # 매수 체결 시 임시 주문 수량 감소 처리 (매도와 동일한 로직)
                    portfolio_item = self.account_state.portfolio.get(code)
                    if portfolio_item and portfolio_item.get('임시_주문수량', 0) > 0:
                        old_portfolio_temp_qty = portfolio_item.get('임시_주문수량', 0)
                        # 체결된 수량만큼 임시 주문 수량 감소
                        new_portfolio_temp_qty = max(0, old_portfolio_temp_qty - last_filled_qty)
                        portfolio_item['임시_주문수량'] = new_portfolio_temp_qty
                        self.log(f"[{code}] 매수 부분 체결로 포트폴리오 임시 주문 수량 감소: {old_portfolio_temp_qty} -> {new_portfolio_temp_qty} (체결량: {last_filled_qty})", "INFO")
                    
                    if hasattr(stock_info, 'temp_order_quantity') and stock_info.temp_order_quantity > 0:
                        old_stock_temp_qty = stock_info.temp_order_quantity
                        # 체결된 수량만큼 임시 주문 수량 감소
                        new_stock_temp_qty = max(0, old_stock_temp_qty - last_filled_qty)
                        stock_info.temp_order_quantity = new_stock_temp_qty
                        self.log(f"[{code}] 매수 부분 체결로 StockTrackingData 임시 주문 수량 감소: {old_stock_temp_qty} -> {new_stock_temp_qty} (체결량: {last_filled_qty})", "INFO")
                    
                    # 첫 번째 매수 체결인 경우 상태를 BOUGHT로 변경하고, buy_timestamp 설정 (buy_completion_count는 완전 체결 시 증가)
                    if stock_info.strategy_state != TradingState.BOUGHT:
                        # stock_info.buy_completion_count += 1 # 제거됨: 완전 체결 시로 이동
                        # self.log(f"[{code}] 첫 매수 체결 시 buy_completion_count 증가: {stock_info.buy_completion_count}", "INFO") # 제거됨
                        stock_info.strategy_state = TradingState.BOUGHT
                        stock_info.buy_timestamp = datetime.now()
                        self.log(f"[{code}] 첫 매수 체결로 상태 변경: {stock_info.strategy_state.name}", "IMPORTANT")
                        
                        # trading_status에도 상태 저장
                        self.account_state.trading_status[code] = {
                            'status': TradingState.BOUGHT,
                            'bought_price': stock_info.avg_buy_price if stock_info.avg_buy_price > 0 else last_filled_price,
                            'bought_quantity': stock_info.total_buy_quantity if stock_info.total_buy_quantity > 0 else last_filled_qty,
                            'bought_time': stock_info.buy_timestamp
                        }
                    
                    # 매수 체결 시 현재가를 기준으로 고점 초기화
                    if stock_info.current_high_price_after_buy < stock_info.current_price:
                        stock_info.current_high_price_after_buy = stock_info.current_price
                        self.log(f"[{code}] 매수 체결 후 고점 업데이트: {stock_info.current_high_price_after_buy}", "DEBUG")
                
                # 체결 데이터에서 수수료 및 세금 정보 가져오기 시도
                fees_from_chejan = _safe_to_float(chejan_data.get("938", 0)) # 수수료 FID
                tax_from_chejan = _safe_to_float(chejan_data.get("939", 0))   # 세금 FID

                # 계좌 유형별 수수료/세금 처리 기반
                calculated_fees = fees_from_chejan
                calculated_tax = tax_from_chejan

                if self.account_type == "모의투자":
                    self.log(f"[{code}] 모의투자 계좌 유형에 따른 수수료/세금 적용 예정 (현재는 API 값 사용).", "DEBUG")
                    # TODO: 모의투자용 수수료/세금 계산 로직 (키움증권 공식 규정 확인 필요)
                    # 예시: calculated_fees = (last_filled_price * last_filled_qty) * 0.0035 # 모의투자 수수료율 0.35% 가정
                    #      calculated_tax = 0 # 모의투자는 세금 면제라고 가정 (실제 확인 필요)
                    pass # 실제 로직은 다음 단계에서 구현
                elif self.account_type == "실거래":
                    self.log(f"[{code}] 실거래 계좌 유형에 따른 수수료/세금 적용 예정 (현재는 API 값 사용).", "DEBUG")
                    # TODO: 실거래용 수수료/세금 계산 로직 (키움증권 공식 규정 확인 필요)
                    # 예시: calculated_fees = fees_from_chejan # API 값을 그대로 사용하거나, 필요시 재계산
                    #      calculated_tax = tax_from_chejan  # API 값을 그대로 사용하거나, 필요시 재계산 (매도 시 세금 등)
                    pass # 실제 로직은 다음 단계에서 구현
                else:
                    self.log(f"[{code}] 알 수 없는 계좌 유형({self.account_type}). 기본 API 수수료/세금 값 사용.", "WARNING")
                
                net_profit_for_db = 0
                if active_order_entry_ref['order_type'] == '매도' and stock_info: # stock_info가 있어야 bought_price 접근 가능
                    # profit_amount 계산은 전량 매도 시에만 수행되었으므로, 여기서 bought_price를 다시 가져와야 할 수 있음
                    bought_price_for_net_profit = 0
                    if code in self.account_state.trading_status:
                        ts_status = self.account_state.trading_status[code]
                        if isinstance(ts_status, dict):
                             bought_price_for_net_profit = ts_status.get('bought_price', 0)
                    if bought_price_for_net_profit == 0 and stock_info.avg_buy_price > 0 : # trading_status에 없다면 stock_info에서 가져오기
                        bought_price_for_net_profit = stock_info.avg_buy_price
                    
                    if bought_price_for_net_profit > 0 :
                        매도체결금액 = last_filled_price * last_filled_qty
                        매수원금_이번체결분 = bought_price_for_net_profit * last_filled_qty
                        # 순수익금 계산 시 calculated_fees, calculated_tax 사용하도록 수정
                        net_profit_amount_이번체결분 = 매도체결금액 - 매수원금_이번체결분 - calculated_fees - calculated_tax # 수정됨
                        net_profit_for_db = net_profit_amount_이번체결분
                        
                        self.log(f"[{code}] 순수익금(이번 체결분) 계산: {net_profit_amount_이번체결분:.0f}원 (매도금액: {매도체결금액:.0f}, 매수원금({bought_price_for_net_profit:.0f}*{last_filled_qty}): {매수원금_이번체결분:.0f}, 적용된수수료: {calculated_fees:.0f}, 적용된세금: {calculated_tax:.0f})")
                        
                        if '총순손익금' not in self.account_state.trading_records:
                            self.account_state.trading_records['총순손익금'] = 0
                        self.account_state.trading_records['총순손익금'] += net_profit_amount_이번체결분
                    else:
                        self.log(f"[{code}] 매도 순수익금 계산 불가: 매수가 정보 부족 (bought_price_for_net_profit: {bought_price_for_net_profit})", "WARNING")


                self.modules.db_manager.add_trade( 
                    order_no=log_order_no_ref, 
                    code=code,
                    name=stock_name, 
                    trade_type=trade_type,
                    quantity=last_filled_qty,
                    price=last_filled_price,
                    trade_reason=active_order_entry_ref.get('reason', ''),
                    fees=calculated_fees,   # 수정됨
                    tax=calculated_tax,     # 수정됨
                    net_profit=net_profit_for_db, 
                    slippage=slippage             
                )
                self.log(f"DB에 체결 기록 저장 완료: {code}, {trade_type}, {last_filled_qty}주 @ {last_filled_price}원 (적용된수수료: {calculated_fees}, 적용된세금: {calculated_tax}, 순손익: {net_profit_for_db}, 슬리피지: {slippage})", "DEBUG")

        # 전량 체결 완료 시 처리 (미체결 0 그리고 상태 '체결')
        if unfilled_qty == 0 and order_status == '체결':
            self.log(f"{TradeColors.FILLED}✅ [ORDER_COMPLETED] 주문 전량 체결 완료: {code} ({stock_name}), RQNameKey({original_rq_name_key}){TradeColors.RESET}", "INFO")
            
            if stock_info is None:
                self.log(f"전량 체결 완료 처리 중단 ({code}): stock_info가 None입니다. Watchlist에 없는 종목일 수 있습니다.", "ERROR")
                # active_orders에서 제거는 아래에서 수행
            else: # stock_info가 있는 경우에만 상태 업데이트
                if active_order_entry_ref['order_type'] == '매수':
                    # 매수 주문 완전 체결 시 buy_completion_count 증가
                    stock_info.buy_completion_count += 1
                    self.log(f"[{code}] 매수 주문 완전 체결 - buy_completion_count 증가: {stock_info.buy_completion_count}/{self.settings.max_buy_attempts_per_stock}", "INFO")
                    
                    # 이 로그가 사용자님이 찾으시는 로그!
                    self.log(f"{TradeColors.FILLED}💰 [BUY_COMPLETED] 매수 체결 완료: {code} ({stock_name}), 상태: {stock_info.strategy_state.name}{TradeColors.RESET}", "IMPORTANT") 
                    
                    portfolio_item = self.account_state.portfolio.get(code)
                    if portfolio_item:
                        # 부분 체결 처리 개선: 포트폴리오 보유량으로 다시 동기화
                        stock_info.avg_buy_price = _safe_to_float(portfolio_item.get('매입가'))
                        stock_info.total_buy_quantity = _safe_to_int(portfolio_item.get('보유수량'))
                        
                        self.log(f"[매수 정보 기록] {code}: 매수가({stock_info.avg_buy_price}), 수량({stock_info.total_buy_quantity}), 매수시간({stock_info.buy_timestamp.strftime('%Y-%m-%d %H:%M:%S') if stock_info.buy_timestamp else 'N/A'})", "INFO")
                        
                        # 즉시 process_strategy 호출하여 매도 조건 확인
                        self.log(f"[즉시 매도 조건 확인] {code} 매수 체결 후 즉시 매도 조건 확인 시작", "INFO")
                        self.process_strategy(code)
                    else:
                        self.log(f"매수 완료 후 포트폴리오 항목을 찾을 수 없어 StockTrackingData 일부 업데이트 실패 ({code})", "ERROR")
                
                elif active_order_entry_ref['order_type'] == '매도':
                    # 손익 계산 및 로깅
                    if code in self.account_state.trading_status:
                        ts = self.account_state.trading_status[code]
                        if isinstance(ts, dict): # ts가 딕셔너리인지 확인
                            bought_price = ts.get('bought_price', 0)
                            executed_price = _safe_to_float(chejan_data.get("10")) # 체결가 추가
                            # 🔧 수정: 전량 체결이므로 원 주문 수량 사용 (FID 911 사용 중단)
                            executed_qty = original_order_qty  # 전량 체결 시 전체 주문 수량
                            bought_price = ts.get('bought_price', 0) # 이 bought_price는 평균 매수가
                            executed_price = _safe_to_float(chejan_data.get("10")) # 체결가
                            executed_qty = original_order_qty  # 전량 체결 시 전체 주문 수량
                            
                            # 총 손익금 (Gross Profit)
                            profit_amount_gross = (executed_price - bought_price) * executed_qty
                            profit_rate_gross = round((executed_price / bought_price - 1) * 100, 2) if bought_price > 0 else 0
                            
                            # 수익/손실에 따른 색상 구분 (총 손익금 기준)
                            profit_color = TradeColors.PROFIT if profit_amount_gross > 0 else TradeColors.LOSS
                            profit_emoji = "💰" if profit_amount_gross > 0 else "📉"
                            self.log(f"{profit_color}{profit_emoji} [매도 상세(총)] 매도가: {executed_price}, 평균매수가: {bought_price}, 총수익금: {profit_amount_gross}원, 총수익률: {profit_rate_gross}%{TradeColors.RESET}")
                            
                            # 통계 업데이트 (총손익금 - Gross)
                            self.account_state.trading_records['매도건수'] += 1
                            self.account_state.trading_records['매도금액'] += executed_qty * executed_price # 총 매도금액
                            self.account_state.trading_records['총손익금'] += profit_amount_gross # Gross Profit
                            
                            if profit_amount_gross > 0:
                                self.account_state.trading_records['이익건수'] += 1
                                self.account_state.trading_records['이익금액'] += profit_amount_gross
                            else:
                                self.account_state.trading_records['손실건수'] += 1
                                self.account_state.trading_records['손실금액'] += abs(profit_amount_gross)
                            
                            # 순손익금 (Net Profit) - 이미 위에서 `net_profit_amount_이번체결분`으로 계산되어 `총순손익금`에 누적됨.
                            # 여기서는 전량 체결 시의 최종 순손익을 한번 더 로깅할 수 있음.
                            # 다만, 부분 체결이 여러번 있었다면, `net_profit_amount_이번체결분`은 마지막 체결 건에 대한 순손익임.
                            # 전체 주문에 대한 총 순손익을 보려면, active_order_entry_ref에 누적된 fees, tax를 사용하거나,
                            # DB에서 해당 주문번호의 모든 거래를 합산해야 함.
                            # 현재는 `net_profit_amount_이번체결분`이 `총순손익금`에 계속 누적되므로,
                            # `self.account_state.trading_records['총순손익금']`이 해당 주문의 최종 누적 순손익을 반영.
                            # 여기서는 로깅 목적으로만 간단히 표시.
                            final_net_profit_for_this_order = self.account_state.trading_records.get('총순손익금', 0) # 이 값은 전체 누적임.
                                                                                                        # 이번 주문만의 순손익은 아님.
                                                                                                        # net_profit_for_db가 마지막 체결분에 대한 순손익.
                            self.log(f"[{code}] 해당 주문의 마지막 체결분 순손익: {net_profit_for_db:.0f}원 (참고: 총누적순손익: {final_net_profit_for_this_order:.0f}원)", "DEBUG")
                            
                            # 매도된 종목의 상태를 COMPLETE로 변경 (Enum의 이름(문자열)을 사용)
                            # ts['status'] = TradingState.COMPLETE.name # 이 줄은 아래의 새 로직으로 대체됨
                            # self.log(f"[상태 업데이트] {code} ({stock_name}) 트레이딩 상태를 {TradingState.COMPLETE.name}으로 변경", "INFO")
                        # else:
                            # self.log(f"[{code}] trading_status의 항목이 예상된 딕셔너리 형태가 아닙니다. 타입: {type(ts)}", "ERROR")
                    # else:
                        # self.log(f"[{code}] trading_status에 해당 종목 정보가 없어 상태를 COMPLETE로 변경할 수 없습니다.", "WARNING")
                    
                    # 포트폴리오 임시 주문 수량 초기화
                    portfolio_item = self.account_state.portfolio.get(code) # 이미 위에서 한번 호출했지만, 명확성을 위해 다시 가져올 수 있음 (또는 기존 변수 사용)
                    if portfolio_item and portfolio_item.get('임시_주문수량', 0) > 0:
                        old_temp_qty = portfolio_item.get('임시_주문수량', 0)
                        portfolio_item['임시_주문수량'] = 0
                        self.log(f"[{code}] 매도 체결 완료 후 포트폴리오 임시 주문 수량 초기화: {old_temp_qty} -> 0", "INFO")
                    
                    # StockTrackingData 임시 주문 수량 초기화
                    if stock_info and hasattr(stock_info, 'temp_order_quantity') and stock_info.temp_order_quantity > 0:
                        old_temp_qty = stock_info.temp_order_quantity
                        stock_info.temp_order_quantity = 0
                        self.log(f"[{code}] 매도 체결 완료 후 StockTrackingData 임시 주문 수량 초기화: {old_temp_qty} -> 0", "INFO")
                    
                    # <<< 여기가 핵심 수정 지점 >>>
                    if portfolio_item:
                        remaining_qty = _safe_to_int(portfolio_item.get('보유수량', 0))
                        if remaining_qty == 0:
                            # 실제 종목 전량 매도 완료
                            self.log(f"{TradeColors.FILLED}🏁 [SELL_COMPLETED] {code} ({stock_name}) 포트폴리오 상 전량 매도 완료. 관련 전략 정보 초기화.{TradeColors.RESET}", "INFO")
                            self.reset_stock_strategy_info(code) # WAITING 등으로 상태 변경
                            
                            if code in self.account_state.trading_status:
                                ts_entry = self.account_state.trading_status[code]
                                if isinstance(ts_entry, dict):
                                    ts_entry['status'] = TradingState.COMPLETE.name # COMPLETE 상태로 변경
                                    self.log(f"[상태 업데이트] {code} ({stock_name}) 트레이딩 상태를 {TradingState.COMPLETE.name}으로 변경 (전량 매도 완료)", "INFO")
                                else:
                                    self.log(f"경고: {code}의 trading_status 항목이 dict가 아님. COMPLETE 상태 변경 불가.", "WARNING")
                            else:
                                self.log(f"경고: {code}가 trading_status에 없어 COMPLETE로 상태 변경 못함", "WARNING")

                        elif remaining_qty > 0:
                            # 부분 매도 완료 (잔량 존재)
                            stock_info.strategy_state = TradingState.PARTIAL_SOLD
                            self.log(f"{code} ({stock_name}) 주문은 전량 체결되었으나, 포트폴리오에 잔량({remaining_qty}) 존재. StockTrackingData 상태를 PARTIAL_SOLD로 설정/유지.", "INFO")
                            
                            if code in self.account_state.trading_status:
                                ts_entry = self.account_state.trading_status[code]
                                if isinstance(ts_entry, dict):
                                    ts_entry['status'] = TradingState.PARTIAL_SOLD.name # PARTIAL_SOLD 상태로 변경
                                    self.log(f"[상태 업데이트] {code} ({stock_name}) 트레이딩 상태를 {TradingState.PARTIAL_SOLD.name}으로 변경 (부분 매도 주문 완료 후 잔량 존재)", "INFO")
                                else:
                                    self.log(f"경고: {code}의 trading_status 항목이 dict가 아님. PARTIAL_SOLD 상태 변경 불가.", "WARNING")
                            else:
                               self.log(f"경고: {code}가 trading_status에 없어 PARTIAL_SOLD로 상태 변경 못함", "WARNING")
                        # else: remaining_qty < 0 인 경우는 비정상적이므로 로깅만 (위에서 _safe_to_int로 처리되어 음수가 나오긴 어려움)
                        #    self.log(f"경고: {code} ({stock_name}) 포트폴리오 보유수량 음수({remaining_qty}). 상태 변경 로직 재검토 필요.", "ERROR")
                            
                    else: # portfolio_item이 없는 경우 (매우 예외적 상황)
                        self.log(f"경고: {code} ({stock_name}) 주문 전량 체결되었으나, 포트폴리오 정보를 찾을 수 없음. 상태 변경 보류.", "ERROR")
                        # 이 경우 reset_stock_strategy_info를 호출하여 최소한의 안전 상태로 만들거나,
                        # 또는 아무것도 하지 않고 다음 로직/주기적 점검에서 처리되도록 할 수 있음.
                        # 여기서는 일단 로그만 남기고 넘어감.

                # stock_info의 last_order_rq_name 초기화 조건: 현재 완료된 주문의 original_rq_name_key와 일치할 때
                if stock_info and stock_info.last_order_rq_name == original_rq_name_key: # stock_info None 체크 추가
                    stock_info.last_order_rq_name = None
                    self.log(f"{code}의 last_order_rq_name을 None으로 설정 (체결 완료). 이전 RQNameKey: {original_rq_name_key}", "INFO")
                elif stock_info.last_order_rq_name and stock_info.last_order_rq_name != original_rq_name_key:
                    self.log(f"{code}의 last_order_rq_name ({stock_info.last_order_rq_name})이 현재 완료된 주문의 RQNameKey ({original_rq_name_key})와 다릅니다. 변경 안함.", "DEBUG")
                elif not stock_info.last_order_rq_name:
                     self.log(f"{code}의 last_order_rq_name이 이미 None입니다. 추가 변경 없음.", "DEBUG")

            # 주문이 '체결' 상태로 전량 완료되었으므로 active_orders에서 제거
            if original_rq_name_key and original_rq_name_key in self.account_state.active_orders:
                self.log(f"active_orders에서 {original_rq_name_key} 제거 시도 (사유: 주문 전량 체결)", "DEBUG")
                del self.account_state.active_orders[original_rq_name_key]
                self.log(f"active_orders에서 {original_rq_name_key} 제거 완료.", "INFO")
            elif original_rq_name_key:
                self.log(f"active_orders에서 {original_rq_name_key}를 찾을 수 없어 제거 못함. active_orders: {list(self.account_state.active_orders.keys())}", "WARNING")
        
        # 주문 상태가 '체결'이 아니지만, API에서 '미체결없음'(예: 취소확인, 거부 등)을 의미하는 경우도 처리 필요
        # 예를 들어 order_status가 '취소', '거부' 등이고 unfilled_qty == 0 이면 active_orders에서 제거 및 last_order_rq_name 초기화
        elif unfilled_qty == 0 and order_status not in ['접수', '확인']: # '체결'이 아니면서 미체결 0 (예: 취소, 거부 등)
            self.log(f"주문({original_rq_name_key})이 '{order_status}' 상태로 미체결 없이 종료됨. ({code}, {stock_name})", "INFO")
            if stock_info and stock_info.last_order_rq_name == original_rq_name_key:
                stock_info.last_order_rq_name = None
                self.log(f"{code}의 last_order_rq_name을 None으로 설정 (사유: {order_status}로 종료). 이전 RQNameKey: {original_rq_name_key}", "INFO")
            
            if original_rq_name_key and original_rq_name_key in self.account_state.active_orders:
                self.log(f"active_orders에서 {original_rq_name_key} 제거 시도 (사유: {order_status}로 종료)", "DEBUG")
                del self.account_state.active_orders[original_rq_name_key]
                self.log(f"active_orders에서 {original_rq_name_key} 제거 완료.", "INFO")

    def _handle_balance_update_report(self, chejan_data, active_order_entry_ref, original_rq_name_key, code, stock_name, stock_info: Optional[StockTrackingData]):
        # active_order_entry_ref가 None일 수 있음을 명시적으로 처리
        log_api_order_no = chejan_data.get("9203", "N/A") 
        
        if active_order_entry_ref is None:
            self.log(f"잔고 변경 보고 처리 중 ({stock_name}, {code}): 연관된 활성 주문 참조(active_order_entry_ref)를 찾을 수 없습니다. API주문번호: {log_api_order_no}. 실현손익/수수료/세금만 로깅 시도.", "WARNING")
        
        realized_pnl = _safe_to_float(chejan_data.get("950")) # 실현손익 FID
        commission = _safe_to_float(chejan_data.get("938")) # 수수료 FID
        tax = _safe_to_float(chejan_data.get("939")) # 세금 FID
        
        # active_order_entry_ref가 None일 경우를 대비하여 .get 사용 및 기본값 설정
        log_order_no_for_balance = active_order_entry_ref.get('order_no', log_api_order_no) if active_order_entry_ref else log_api_order_no
        log_rq_name_for_balance = original_rq_name_key if original_rq_name_key else "N/A"

        self.log(f"잔고 변경 보고 ({code}, {stock_name}): 연결된RQNameKey({log_rq_name_for_balance}), API주문번호({log_order_no_for_balance}), 실현손익({realized_pnl}), 수수료({commission}), 세금({tax})", "INFO")

        if realized_pnl != 0 or commission != 0 or tax != 0 :
            self.log(f"DB Trade Record에 실현손익/수수료/세금 정보 업데이트 필요 (미구현 상세 로직): {code}, 주문({log_order_no_for_balance})", "DEBUG")

        # 잔고통보(gubun='1')는 주문의 최종 완료 상태를 직접 변경하기보다는,
        # 주문 체결(gubun='0')에 따른 계좌 상태 변화를 알리는 부수적인 정보로 활용.
        # 따라서 여기서 active_orders 정리 로직은 보통 불필요.

    def report_periodic_status(self):
        """주기적인 상태 보고"""
        if not self.is_running or not self.settings.periodic_report_enabled:
            return
            
        # 미처리 주문 확인 및 정리
        self._check_and_cleanup_stale_orders()
        
        # 현재 시간을 포함한 타이틀 추가
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.log(f"{TradeColors.INFO}📊 ===== 주기적 상태 보고 ({current_time}) ====={TradeColors.RESET}", "INFO")
        
        # 전략 실행 상태 정보
        runtime = time.time() - self.start_time if self.start_time else 0
        hours, rem = divmod(runtime, 3600)
        minutes, seconds = divmod(rem, 60)
        runtime_str = f"{int(hours)}시간 {int(minutes)}분 {int(seconds)}초"
        
        self.log(f"전략 실행 상태: {'실행 중' if self.is_running else '중지됨'}, 최종 초기화 성공: {self.is_initialized_successfully}", "INFO")
        self.log(f"현재 상태 메시지: {self.status_message if hasattr(self, 'status_message') and self.status_message else '정상 실행 중'}", "INFO")
        self.log(f"계좌번호: {self.account_state.account_number}", "INFO")
        
        # 계좌 정보 요약
        # 예수금 값을 직접 account_summary에서 가져오도록 수정
        deposit = _safe_to_int(self.account_state.account_summary.get("예수금", 0))
        # d+2추정예수금도 체크하여 예수금이 0일 경우 대체값으로 사용
        if deposit == 0:
            deposit = _safe_to_int(self.account_state.account_summary.get("d+2추정예수금", 0))
        self.log(f"예수금: {deposit:,}", "INFO")
        
        # 포트폴리오 요약
        if self.account_state.portfolio:
            self.log(f"{TradeColors.PORTFOLIO}💼 보유 종목 ({len(self.account_state.portfolio)}개):{TradeColors.RESET}", "INFO")
            for code, stock_data in self.account_state.portfolio.items():
                stock_name = stock_data.get("stock_name", "")
                quantity = _safe_to_int(stock_data.get("보유수량", 0))
                eval_amount = _safe_to_float(stock_data.get("평가금액", 0))
                pl_rate = _safe_to_float(stock_data.get("수익률", 0))
                self.log(f"  - {stock_name}({code}): {quantity}주, 평가액 {eval_amount:,.0f} (수익률 {pl_rate:.2f}%)", "INFO")
        else:
            self.log(f"{TradeColors.INFO}ℹ️ 보유 종목 없음{TradeColors.RESET}", "INFO")
        
        # 미체결 주문 요약
        pending_orders = self.get_pending_orders()
        if pending_orders:
            self.log(f"{TradeColors.WARNING}⏳ 미체결 주문 ({len(pending_orders)}건):{TradeColors.RESET}", "INFO")
            for order in pending_orders:
                code = order.get("code", "")
                stock_name = order.get("stock_name", "")
                order_type = order.get("order_type", "")
                quantity = _safe_to_int(order.get("remaining_quantity", 0))
                price = _safe_to_float(order.get("price", 0))
                order_status = order.get("order_status", "")
                rq_name = order.get("rq_name", "")
                self.log(f"  - RQ:{rq_name}, {stock_name}({code}), {order_type} {quantity}@{price:.1f}, 미체결:{quantity}, 상태:{order_status}", "INFO")
        else:
            self.log(f"{TradeColors.INFO}✓ 미체결 주문 없음{TradeColors.RESET}", "INFO")
        
        # 관심 종목 모니터링 현황 추가
        if self.watchlist:
            self.log(f"{TradeColors.INFO}🔍 관심 종목 ({len(self.watchlist)}개):{TradeColors.RESET}", "INFO")
            for code, stock_info in self.watchlist.items():
                state_name = stock_info.strategy_state.name if hasattr(stock_info, 'strategy_state') and stock_info.strategy_state else 'N/A'
                current_price = stock_info.current_price if hasattr(stock_info, 'current_price') else 0
                buy_completion_count = stock_info.buy_completion_count if hasattr(stock_info, 'buy_completion_count') else 0
                self.log(f"  - {stock_info.stock_name}({code}): 현재가 {current_price:.1f}, 상태: {state_name}, 매수시도: {buy_completion_count}/{self.settings.max_buy_attempts_per_stock}회", "INFO")
        else:
            self.log(f"{TradeColors.WARNING}⚠️ 관심 종목 없음{TradeColors.RESET}", "INFO")
        
        # 일일 매수 실행 횟수 정보
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

    def _handle_opw00001_response(self, rq_name, data):
        """ opw00001 (예수금 상세현황) 응답 처리 """
        if 'single_data' in data:
            deposit_info = self._ensure_numeric_fields(data['single_data'])
            self.account_state.account_summary.update(deposit_info)
            
            # 주문가능금액 로그 추가
            orderable_cash = _safe_to_int(deposit_info.get("주문가능금액", 0))
            self.log(f"{TradeColors.BALANCE}💳 [BALANCE] 예수금 정보 업데이트: 주문가능금액={orderable_cash:,}원{TradeColors.RESET}", "INFO")
        else:
            self.log("예수금 정보 없음 (opw00001 응답에 single_data 없음)", "WARNING")
            
        self.initialization_status["deposit_info_loaded"] = True # 핸들러 호출 시 로드된 것으로 간주
        self.log(f"opw00001 핸들러 완료. deposit_info_loaded: {self.initialization_status['deposit_info_loaded']}", "DEBUG")
        self._check_all_data_loaded_and_start_strategy()


    def _handle_opw00018_response(self, rq_name, data):
        """ opw00018 (계좌평가잔고내역) 응답 처리 """
        if 'single_data' in data:
            summary_info = self._ensure_numeric_fields(data['single_data'])
            # 필요한 키만 선택적으로 업데이트 하거나, 전체를 업데이트 할 수 있습니다.
            # 예: self.account_state.account_summary['총매입금액'] = summary_info.get('총매입금액')
            self.account_state.account_summary.update(summary_info)
            self.log(f"{TradeColors.PORTFOLIO}📊 [PORTFOLIO] 계좌 평가 요약 정보 업데이트{TradeColors.RESET}", "INFO")

        if 'multi_data' in data:
            current_portfolio = {}
            for item_raw in data['multi_data']:
                item = self._ensure_numeric_fields(item_raw)
                code = item.get("종목번호")
                if code:
                    code = code.replace('A', '').strip() # 종목코드 클리닝 (A 제거)
                    # API 응답 필드명에 맞춰 '수익률(%)' -> '수익률' 변환 및 숫자형 변환
                    if '수익률(%)' in item:
                        item['수익률'] = _safe_to_float(item['수익률(%)'])
                    elif '수익률' in item: # 이미 '수익률' 필드가 있다면 숫자형 변환만 시도
                        item['수익률'] = _safe_to_float(item['수익률'])
                    
                    current_portfolio[code] = {
                        'stock_name': item.get("종목명"),
                        '보유수량': _safe_to_int(item.get("보유수량")),
                        '매입가': _safe_to_float(item.get("매입단가", item.get("매입가"))), # '매입단가' 또는 '매입가' 사용
                        '현재가': _safe_to_float(item.get("현재가")),
                        '평가금액': _safe_to_float(item.get("평가금액")),
                        '매입금액': _safe_to_float(item.get("매입금액")),
                        '평가손익': _safe_to_float(item.get("평가손익")),
                        '수익률': item.get('수익률', 0.0), # 이미 위에서 처리되었거나, 없다면 0.0
                        # 추가적으로 필요한 필드들 (예: '대출일', '만기일' 등)이 있다면 여기서 포함
                    }
            self.account_state.portfolio = current_portfolio
            self.log(f"{TradeColors.PORTFOLIO}📊 [PORTFOLIO] 계좌 잔고 업데이트: {len(self.account_state.portfolio)} 종목{TradeColors.RESET}", "INFO")
            for code, detail in self.account_state.portfolio.items():
                self.log(f"  - {detail.get('stock_name', code)}({code}): {detail.get('보유수량')}주 @ {detail.get('매입가')} (현:{detail.get('현재가')})", "DEBUG")

        # KiwoomAPI에서 연속조회 여부(prev_next)를 보고 '2'가 아니면 is_continuous=False로 설정
        # 여기서는 is_continuous 플래그를 직접 받지 않으므로, 모든 opw00018 응답 시 로드 완료로 간주
        # (kiwoom_api.py의 _emulate_tr_receive_for_dry_run에서 연속조회는 시뮬레이션하지 않음)
        self.initialization_status["portfolio_loaded"] = True
        self.log(f"opw00018 핸들러 완료. portfolio_loaded: {self.initialization_status['portfolio_loaded']}", "DEBUG")
        
        # 포트폴리오 로드 완료 후 DB와 저장된 상태에서 매매 상태 복원
        if self.initialization_status["portfolio_loaded"] and self.initialization_status["deposit_info_loaded"]:
            self.log("포트폴리오 및 예수금 로드 완료. DB 및 저장된 상태에서 매매 상태 복원 시도...", "INFO")
            self.restore_trading_state_from_db()
        
        self._check_all_data_loaded_and_start_strategy()

    def run_dry_run_test_scenario(self, scenario_name: str, test_params: dict):
        self.log(f"=== 드라이런 테스트 시나리오 시작: {scenario_name} ===", "IMPORTANT")
        
        # 0. 드라이런 모드 확인 (필수)
        is_dry_run = self.modules.config_manager.get_setting("매매전략", "dry_run_mode", False)
        if not is_dry_run:
            self.log("오류: 드라이런 테스트는 settings.json에서 'dry_run_mode': true 로 설정해야 합니다.", "ERROR")
            return

        # 드라이런 모드를 위한 강제 초기화 상태 설정
        self.log("드라이런 모드를 위한 강제 초기화 상태 설정...", "INFO")
        self.initialization_status = {
            "account_info_loaded": True,
            "deposit_info_loaded": True,
            "portfolio_loaded": True,
            "settings_loaded": True, 
            "market_hours_initialized": True 
        }
        if not self.account_state.account_number:
            self.account_state.account_number = "DRYRUN_ACCOUNT"
            self.log(f"드라이런용 임시 계좌번호 설정: {self.account_state.account_number}", "INFO")
        
        if self.modules.kiwoom_api and not self.modules.kiwoom_api.account_number:
             self.modules.kiwoom_api.account_number = self.account_state.account_number
             self.log(f"KiwoomAPI에도 드라이런용 계좌번호 전달: {self.modules.kiwoom_api.account_number}", "INFO")

        self.is_initialized_successfully = True 
        # self.start() # 타이머 시작 등은 실제 시나리오에서는 불필요할 수 있음

        code = test_params.get("code")
        stock_name = test_params.get("stock_name", code)
        
        yesterday_cp = test_params.get("yesterday_close_price", 0)
        self.add_to_watchlist(code, stock_name, yesterday_close_price=yesterday_cp)
        
        stock_info = self.watchlist.get(code)
        if not stock_info:
            self.log(f"테스트 실패: {code}를 watchlist에 추가할 수 없습니다.", "ERROR")
            return

        initial_portfolio = test_params.get("initial_portfolio")
        if initial_portfolio:
            self.account_state.portfolio[code] = copy.deepcopy(initial_portfolio)
            stock_info.strategy_state = TradingState.BOUGHT
            stock_info.avg_buy_price = _safe_to_float(initial_portfolio.get('매입가'))
            stock_info.total_buy_quantity = _safe_to_int(initial_portfolio.get('보유수량'))
            stock_info.current_high_price_after_buy = stock_info.avg_buy_price 
            
            st_data_override = test_params.get("stock_tracking_data_override", {})
            for key, value in st_data_override.items():
                if hasattr(stock_info, key):
                    # TradingState enum 값 변환 처리
                    if key == "strategy_state" and isinstance(value, str):
                        try:
                            setattr(stock_info, key, TradingState[value.upper()])
                        except KeyError:
                            self.log(f"경고: 유효하지 않은 TradingState 문자열 값({value})입니다. 기본 상태 유지.", "WARNING")
                    else:
                        setattr(stock_info, key, value)
                else:
                    self.log(f"경고: StockTrackingData에 없는 필드({key}) 설정 시도.", "WARNING")
            
            if 'buy_timestamp_str' in st_data_override:
                ts_str = st_data_override['buy_timestamp_str']
                try:
                    if ts_str.startswith("now-"):
                        if 'm' in ts_str:
                            minutes_ago = int(ts_str.split('-')[1].replace('m', ''))
                            stock_info.buy_timestamp = datetime.now() - timedelta(minutes=minutes_ago)
                        elif 'h' in ts_str:
                            hours_ago = int(ts_str.split('-')[1].replace('h', ''))
                            stock_info.buy_timestamp = datetime.now() - timedelta(hours=hours_ago)
                        else: # "now-"만 있는 경우 또는 잘못된 형식
                            self.log(f"buy_timestamp_str 형식 오류 ('now-'): {ts_str}. 현재 시간으로 설정.", "ERROR")
                        stock_info.buy_timestamp = datetime.now()
                    else:
                         stock_info.buy_timestamp = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                except Exception as e:
                    self.log(f"buy_timestamp_str 파싱 오류: {e} (입력값: {ts_str}). 현재 시간으로 설정.", "ERROR")
                    stock_info.buy_timestamp = datetime.now()
            elif not stock_info.buy_timestamp: 
                 stock_info.buy_timestamp = datetime.now()

            self.log(f"가상 포트폴리오 설정 ({code}): {self.account_state.portfolio[code]}", "INFO")
            self.log(f"StockTrackingData 설정 ({code}): 상태({stock_info.strategy_state.name if stock_info.strategy_state else 'N/A'}), 매수가({stock_info.avg_buy_price}), 수량({stock_info.total_buy_quantity}), 고점({stock_info.current_high_price_after_buy}), 부분익절({stock_info.partial_take_profit_executed}), 트레일링활성({stock_info.is_trailing_stop_active}), 트레일링부분매도({stock_info.trailing_stop_partially_sold}), 매수시간({stock_info.buy_timestamp.strftime('%Y-%m-%d %H:%M:%S') if stock_info.buy_timestamp else 'N/A'})", "INFO")

        test_current_price = test_params.get("test_current_price")
        if test_current_price is not None:
            stock_info.current_price = _safe_to_float(test_current_price)
            self.log(f"테스트 현재가 설정 ({code}): {stock_info.current_price}", "INFO")
        else:
            self.log(f"경고: 테스트 현재가가 제공되지 않았습니다 ({code}).", "WARNING")

        self.log(f"process_strategy({code}) 호출 중...", "INFO")
        # 장운영시간 체크를 드라이런 시에는 우회하거나, 테스트 파라미터로 제어할 수 있게 하는 것이 좋음.
        # 여기서는 is_market_hours()가 True를 반환한다고 가정하거나, check_conditions 대신 process_strategy를 직접 호출하므로 영향이 적을 수 있음.
        # 만약 is_market_hours()가 False면 process_strategy 내부 로직이 실행 안 될 수 있으니 주의.
        # 임시로 is_market_hours를 오버라이드하거나, check_conditions 대신 process_strategy를 사용.
        # 현재 process_strategy는 is_market_hours와 직접적 연관은 없음. check_conditions가 is_market_hours 사용.
        self.process_strategy(code) 

        self.log(f"--- 테스트 시나리오 '{scenario_name}' 실행 후 상태 ({code}) ---", "INFO")
        self.log(f"StockTrackingData: 상태({stock_info.strategy_state.name if stock_info.strategy_state else 'N/A'}), 매수가({stock_info.avg_buy_price}), 수량({stock_info.total_buy_quantity}), 부분익절({stock_info.partial_take_profit_executed}), 트레일링활성({stock_info.is_trailing_stop_active}), 트레일링부분매도({stock_info.trailing_stop_partially_sold})", "INFO")
        portfolio_after = self.account_state.portfolio.get(code)
        if portfolio_after:
            self.log(f"포트폴리오: 보유수량({portfolio_after.get('보유수량')}), 매입가({portfolio_after.get('매입가')})", "INFO")
        else:
            self.log(f"포트폴리오에 {code} 정보 없음 (전량 매도된 경우 정상)", "INFO")
        
        self.log(f"=== 드라이런 테스트 시나리오 종료: {scenario_name} ===\\n", "IMPORTANT") # 로그 구분을 위해 개행 추가

    def save_current_state(self):
        """현재 상태를 JSON 파일에 저장합니다."""
        import json
        
        try:
            # 디렉토리가 존재하는지 확인하고 없으면 생성
            state_dir = os.path.dirname(self.state_file_path)
            if state_dir and not os.path.exists(state_dir):
                os.makedirs(state_dir, exist_ok=True)
                self.log(f"상태 파일 디렉토리를 생성했습니다: {state_dir}", "INFO")
            
            trading_status_serializable = {}
            for code, status in self.account_state.trading_status.items():
                # datetime 객체는 직접 JSON 직렬화가 안 되므로 문자열로 변환
                status_copy = status.copy()
                if 'bought_time' in status_copy and isinstance(status_copy['bought_time'], datetime):
                    status_copy['bought_time'] = status_copy['bought_time'].strftime('%Y-%m-%d %H:%M:%S')
                
                # TradingState Enum은 직접 직렬화가 안 되므로 이름으로 변환
                if 'status' in status_copy and isinstance(status_copy['status'], TradingState):
                    status_copy['status'] = status_copy['status'].name
                
                trading_status_serializable[code] = status_copy
            
            # 각 종목의 전략 상태 정보 수집
            watchlist_serializable = {}
            for code, stock_info in self.watchlist.items():
                stock_info_dict = {
                    'code': stock_info.code,
                    'stock_name': stock_info.stock_name,
                    'current_price': stock_info.current_price,
                    'yesterday_close_price': stock_info.yesterday_close_price,
                    'strategy_state': stock_info.strategy_state.name,  # Enum -> 문자열
                    'avg_buy_price': stock_info.avg_buy_price,
                    'total_buy_quantity': stock_info.total_buy_quantity,
                    'current_high_price_after_buy': stock_info.current_high_price_after_buy,
                    'is_trailing_stop_active': stock_info.is_trailing_stop_active,
                    'trailing_stop_partially_sold': stock_info.trailing_stop_partially_sold,
                    'partial_take_profit_executed': stock_info.partial_take_profit_executed,
                    'buy_completion_count': stock_info.buy_completion_count  # 매수 체결 완료 횟수 추가
                }
                
                # datetime 객체 변환
                if stock_info.buy_timestamp:
                    stock_info_dict['buy_timestamp'] = stock_info.buy_timestamp.strftime('%Y-%m-%d %H:%M:%S')
                
                watchlist_serializable[code] = stock_info_dict
            
            # 저장할 상태 데이터
            state_data = {
                'daily_buy_executed_count': self.daily_buy_executed_count,
                'today_date_for_buy_limit': self.today_date_for_buy_limit,
                'trading_status': trading_status_serializable,
                'watchlist': watchlist_serializable,
                'trading_records': self.account_state.trading_records,
                'last_snapshot_date': self.last_snapshot_date,
                'saved_datetime': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
            with open(self.state_file_path, 'w', encoding='utf-8') as f:
                json.dump(state_data, f, ensure_ascii=False, indent=2)
            
            self.log(f"현재 상태를 '{self.state_file_path}'에 저장했습니다.", "INFO")
            return True
        except Exception as e:
            self.log(f"상태 저장 중 오류 발생: {e}", "ERROR")
            return False
    
    def load_saved_state(self):
        """저장된 상태를 JSON 파일에서 로드합니다."""
        import json
        import os
        
        if not os.path.exists(self.state_file_path):
            # 기존 경로도 확인
            old_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trading_state.json")
            if os.path.exists(old_path) and old_path != self.state_file_path:
                self.log(f"저장된 상태 파일이 이전 경로({old_path})에 존재합니다. 다음 실행 시 자동으로 이동됩니다.", "WARNING")
            else:
                self.log(f"저장된 상태 파일({self.state_file_path})이 없습니다. 새로 시작합니다.", "WARNING")
            return False
        
        try:
            with open(self.state_file_path, 'r', encoding='utf-8') as f:
                state_data = json.load(f)
            
            # 기본 상태 정보 복원
            self.daily_buy_executed_count = state_data.get('daily_buy_executed_count', 0)
            self.today_date_for_buy_limit = state_data.get('today_date_for_buy_limit')
            self.last_snapshot_date = state_data.get('last_snapshot_date')
            
            # 오늘 날짜와 저장된 날짜가 다르면 일일 매수 카운트 초기화
            current_date = datetime.now().strftime('%Y-%m-%d')
            if self.today_date_for_buy_limit != current_date:
                self.log(f"저장된 날짜({self.today_date_for_buy_limit})와 현재 날짜({current_date})가 다릅니다. 일일 매수 카운트를 0으로 초기화합니다.", "INFO")
                self.daily_buy_executed_count = 0
                self.today_date_for_buy_limit = current_date
            
            # trading_records 복원
            if 'trading_records' in state_data:
                self.account_state.trading_records = state_data['trading_records']
            
            # watchlist 정보는 나중에 복원 (포트폴리오 로드 후)
            self.saved_watchlist_data = state_data.get('watchlist', {})
            self.saved_trading_status = state_data.get('trading_status', {})
            
            saved_datetime = state_data.get('saved_datetime', '알 수 없음')
            self.log(f"'{self.state_file_path}'에서 상태 정보를 로드했습니다. 저장 시간: {saved_datetime}", "INFO")
            return True
        except Exception as e:
            self.log(f"상태 로드 중 오류 발생: {e}", "ERROR")
            return False
    
    def restore_trading_state_from_db(self):
        """DB에서 매매 이력을 로드하여 거래 상태를 복원합니다."""
        self.log("DB에서 거래 이력을 로드하여 거래 상태 복원 시작...", "INFO")
        
        try:
            # 계좌 포트폴리오 검증 (이미 로드되어 있어야 함)
            if not self.account_state.portfolio:
                self.log("포트폴리오가 아직 로드되지 않았습니다. 상태 복원을 위해 포트폴리오 로드가 필요합니다.", "WARNING")
                return False
            
            # 오늘의 매매 기록 로드 (정보 제공용 - 더이상 일일 매수 카운트에 사용하지 않음)
            today_date = datetime.now().strftime('%Y-%m-%d')
            today_trades = self.modules.db_manager.get_trades_by_date(today_date)
            
            if today_trades:
                buy_trades = [trade for trade in today_trades if trade.get('trade_type') == '매수']
                trade_count = len(buy_trades)
                self.log(f"DB에서 오늘({today_date})의 매수 거래 {trade_count}건을 확인했습니다. (통계용)", "INFO")
            
            # 저장된 JSON 파일 상태 정보로 추가 복원
            self.restore_additional_state_from_saved_data()
            
            return True
        except Exception as e:
            self.log(f"DB에서 거래 상태 복원 중 오류 발생: {e}", "ERROR")
            return False
    
    def restore_additional_state_from_saved_data(self):
        """JSON 파일에서 로드한 추가 상태 정보를 복원합니다."""
        if not hasattr(self, 'saved_watchlist_data') or not hasattr(self, 'saved_trading_status'):
            self.log("저장된 추가 상태 정보가 없습니다.", "DEBUG")
            return
        
        try:
            # 이미 로드된 watchlist와 trading_status에 추가 정보 적용
            for code, saved_info in self.saved_watchlist_data.items():
                if code in self.watchlist:
                    stock_info = self.watchlist[code]
                    
                    # 부분 매도, 트레일링 스탑 등의 상태 복원
                    if 'partial_take_profit_executed' in saved_info:
                        stock_info.partial_take_profit_executed = saved_info['partial_take_profit_executed']
                    if 'is_trailing_stop_active' in saved_info:
                        stock_info.is_trailing_stop_active = saved_info['is_trailing_stop_active']
                    if 'trailing_stop_partially_sold' in saved_info:
                        stock_info.trailing_stop_partially_sold = saved_info['trailing_stop_partially_sold']
                    if 'buy_completion_count' in saved_info:
                        stock_info.buy_completion_count = saved_info['buy_completion_count']
                    
                    # 현재 상태가 BOUGHT가 아니라면, 저장된 상태로 변경
                    if stock_info.strategy_state != TradingState.BOUGHT and 'strategy_state' in saved_info:
                        try:
                            stock_info.strategy_state = TradingState[saved_info['strategy_state']]
                            self.log(f"[{code}] 상태를 저장된 값({saved_info['strategy_state']})으로 복원했습니다.", "INFO")
                        except (KeyError, ValueError):
                            pass
            
            # trading_status 복원 (상태 문자열을 Enum으로 변환)
            if hasattr(self, 'saved_trading_status') and self.saved_trading_status:
                for code, saved_status_dict in self.saved_trading_status.items():
                    if code in self.account_state.trading_status: # 이미 항목이 있다면 업데이트
                        current_status_entry = self.account_state.trading_status[code]
                    else: # 없다면 새로 생성
                        current_status_entry = {}
                        self.account_state.trading_status[code] = current_status_entry
                    
                    # 모든 키-값 쌍 복사
                    for key, value in saved_status_dict.items():
                        if key == 'status' and isinstance(value, str):
                            try:
                                current_status_entry[key] = TradingState[value]
                                self.log(f"[{code}] trading_status의 'status'를 Enum으로 복원: {value} -> {current_status_entry[key]}", "DEBUG")
                            except KeyError:
                                self.log(f"[{code}] trading_status 복원 중 알 수 없는 상태 값({value})입니다. 문자열로 유지합니다.", "WARNING")
                                current_status_entry[key] = value # 변환 실패 시 원본 문자열 유지
                        elif key == 'bought_time' and isinstance(value, str):
                            try:
                                current_status_entry[key] = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
                            except ValueError:
                                self.log(f"[{code}] trading_status의 'bought_time'({value}) 복원 중 날짜 형식 오류. 문자열로 유지.", "WARNING")
                                current_status_entry[key] = value
                        else:
                            current_status_entry[key] = value
                    self.log(f"[{code}] trading_status 항목 복원/업데이트 완료: {current_status_entry}", "DEBUG")

            self.log("저장된 추가 상태 정보를 성공적으로 복원했습니다.", "INFO")
        except Exception as e:
            self.log(f"추가 상태 정보 복원 중 오류 발생: {e}", "ERROR")
            
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
            
            # 저장된 상태 로드 시도
            self.load_saved_state()
            
            self.request_account_info() # 예수금 정보 요청
            self.request_portfolio_info() # 포트폴리오 정보 요청
        else:
            self.log("계좌번호가 최종적으로 설정되지 않아 계좌 관련 작업을 진행할 수 없습니다.", "CRITICAL")
            self.initialization_status["account_info_loaded"] = False
            self.current_status_message = "오류: 계좌번호 설정 실패. 프로그램 기능 제한됨."
            # 이 경우 is_initialized_successfully는 False로 유지됨

    def stop_strategy(self):
        """매매 전략 중지"""
        self.log("매매 전략 중지 시작...", "INFO")
        self.is_running = False
        self.check_timer.stop()
        self.status_report_timer.stop()
        self.daily_snapshot_timer.stop()
        
        # 상태 저장
        self.save_current_state()
        
        self.log("매매 전략 중지 완료.", "INFO")
        # stop_strategy 자체에는 이벤트 시그널 핸들러 제거나 리소스 해제는 포함되어 있지 않음
        # 메인 프로그램에서 이를 수행

    def _check_and_cleanup_stale_orders(self):
        """오래된 미처리 주문을 확인하고 정리합니다."""
        current_time = datetime.now()
        
        # 모든 관심종목에 대해 확인
        for code, stock_info in list(self.watchlist.items()):
            # last_order_rq_name이 있고 buy_timestamp가 설정된 경우만 확인
            if stock_info.last_order_rq_name and stock_info.buy_timestamp:
                elapsed_minutes = (current_time - stock_info.buy_timestamp).total_seconds() / 60
                
                # 5분 이상 경과한 주문은 타임아웃으로 간주
                if elapsed_minutes > 5:
                    self.log(f"[자동 정리] [{code}] 미처리 주문({stock_info.last_order_rq_name}) 감지 - {elapsed_minutes:.1f}분 경과", "WARNING")
                    
                    # 포트폴리오에 종목이 있는지 확인
                    if code in self.account_state.portfolio and _safe_to_int(self.account_state.portfolio[code].get('보유수량', 0)) > 0:
                        # 보유 중이지만 상태가 BOUGHT가 아니면 상태 교정
                        if stock_info.strategy_state != TradingState.BOUGHT:
                            self.log(f"[자동 정리] [{code}] 포트폴리오에 존재하지만 상태가 {stock_info.strategy_state.name}입니다. BOUGHT로 변경합니다.", "WARNING")
                            stock_info.strategy_state = TradingState.BOUGHT
                            stock_info.avg_buy_price = _safe_to_float(self.account_state.portfolio[code].get('매입가', 0))
                            stock_info.total_buy_quantity = _safe_to_int(self.account_state.portfolio[code].get('보유수량', 0))
                        
                        # trading_status에도 상태 저장
                        self.account_state.trading_status[code] = {
                            'status': TradingState.BOUGHT,
                                'bought_price': stock_info.avg_buy_price,
                                'bought_quantity': stock_info.total_buy_quantity,
                                'bought_time': stock_info.buy_timestamp or current_time
                            }
                    else:
                        # 포트폴리오에 없고 상태가 WAITING이 아니면 상태 초기화
                        if stock_info.strategy_state != TradingState.WAITING:
                            self.log(f"[자동 정리] [{code}] 포트폴리오에 존재하지 않고 상태가 {stock_info.strategy_state.name}입니다. WAITING으로 초기화합니다.", "WARNING")
                            # 주문 타임아웃 및 조건 불일치로 상태 초기화 시 buy_completion_count 리셋 경고 로그
                            if stock_info.buy_completion_count > 0:
                                self.log(f"[{code}] 주문 타임아웃 및 조건 불일치로 상태 초기화 예정. 현재 buy_completion_count({stock_info.buy_completion_count})가 0으로 리셋됩니다.", "WARNING")
                            # WARNING: 이 로직은 타임아웃된 주문 처리 시 StockTrackingData를 초기화하며, 이 과정에서 buy_completion_count도 0으로 리셋됩니다.
                            # 이는 이전에 성공했던 완전 체결 매수 횟수 기록을 지우고, 종목당 최대 매수 시도 횟수 제한을 약화시킬 수 있습니다.
                            # 추후 이 부분에 대한 정교한 상태 관리 또는 buy_completion_count 보존 로직 검토가 필요할 수 있습니다.
                            self.reset_stock_strategy_info(code)
                    
                    # last_order_rq_name 초기화
                    stock_info.last_order_rq_name = None
                    self.log(f"[자동 정리] [{code}] last_order_rq_name을 초기화했습니다.", "INFO")
        
        # 활성 주문 중에서 5분 이상 경과한 주문이 있는지 확인
        active_orders_to_remove = []
        for rq_name_key, order_entry in self.account_state.active_orders.items():
            # timestamp가 있는 경우만 확인
            if 'timestamp' in order_entry:
                order_time = order_entry['timestamp']
                if isinstance(order_time, (int, float)):
                    # timestamp가 유닉스 타임스탬프인 경우
                    order_time = datetime.fromtimestamp(order_time)
                
                if isinstance(order_time, datetime):
                    elapsed_minutes = (current_time - order_time).total_seconds() / 60
                    
                    # 5분 이상 경과한 주문은 타임아웃으로 간주
                    if elapsed_minutes > 5:
                        active_orders_to_remove.append(rq_name_key)
                        self.log(f"[자동 정리] 활성 주문({rq_name_key}) 타임아웃 감지 - {elapsed_minutes:.1f}분 경과", "WARNING")
        
        # 타임아웃된 활성 주문 제거
        for rq_name_key in active_orders_to_remove:
            if rq_name_key in self.account_state.active_orders:
                order_entry = self.account_state.active_orders[rq_name_key]
                code = order_entry.get('code')
                order_type = order_entry.get('order_type')
                self.log(f"[자동 정리] 활성 주문 제거: {rq_name_key}, 종목: {code}, 유형: {order_type}", "INFO")
                del self.account_state.active_orders[rq_name_key]

    def _find_active_order(self, api_order_no, code):
        """
        코드나 주문번호를 통해 활성 주문을 찾아 반환합니다.
        _find_active_order_rq_name_key 메서드를 사용하여 RQName을 찾은 후 해당 키로 active_orders에서 주문 항목을 반환합니다.
        
        Args:
            api_order_no: API 주문번호 (없으면 None)
            code: 종목코드
        
        Returns:
            찾은 주문 항목 (딕셔너리) 또는 None
        """
        rq_name_key = self._find_active_order_rq_name_key(code, api_order_no, None)
        if rq_name_key and rq_name_key in self.account_state.active_orders:
            return self.account_state.active_orders[rq_name_key]
        return None

    def _find_active_order_rq_name_key(self, code_from_chejan, api_order_no_from_chejan, chejan_data_dict): # chejan_data_dict는 로깅용으로만 사용될 수 있음
        # 종목코드 정규화 ('A'로 시작하는 경우 제거)
        normalized_code = code_from_chejan
        if normalized_code and normalized_code.startswith('A') and len(normalized_code) > 1:
            normalized_code = normalized_code[1:]
        
        self.log(f"_find_active_order_rq_name_key: 종목코드({code_from_chejan} -> {normalized_code}), API주문번호({api_order_no_from_chejan if api_order_no_from_chejan else 'N/A'}) 탐색 시작.", "DEBUG")

        if not self.account_state or not self.account_state.active_orders:
            self.log(f"_find_active_order_rq_name_key: self.account_state.active_orders가 비어있거나 없습니다.", "WARNING")
            return None

        # 1. API 주문번호가 있고, active_orders의 'order_no'와 일치하는 경우
        if api_order_no_from_chejan:
            for rq_name_key, order_entry in self.account_state.active_orders.items():
                order_no_from_entry = order_entry.get('order_no')
                if order_no_from_entry and order_no_from_entry == api_order_no_from_chejan:
                    self.log(f"_find_active_order_rq_name_key: API주문번호({api_order_no_from_chejan})로 active_orders에서 일치하는 항목 찾음: {rq_name_key}", "DEBUG")
                    return rq_name_key

        # 2. 종목코드로 매칭 (마지막으로 해당 종목에 대해 요청된 주문)
        if normalized_code:
            matching_entries = []
            for rq_name_key, order_entry in self.account_state.active_orders.items():
                code_from_entry = order_entry.get('code')
                # 종목코드도 정규화하여 비교
                normalized_code_from_entry = code_from_entry
                if normalized_code_from_entry and normalized_code_from_entry.startswith('A') and len(normalized_code_from_entry) > 1:
                    normalized_code_from_entry = normalized_code_from_entry[1:]
                
                if normalized_code_from_entry and normalized_code_from_entry == normalized_code:
                    matching_entries.append((rq_name_key, order_entry))
            
            # 가장 최근 주문 선택 (마지막에 추가된 항목이 최근 주문이라고 가정)
            if matching_entries:
                # timestamp가 있으면 timestamp로 정렬, 없으면 마지막 항목 선택
                if all('timestamp' in entry[1] for entry in matching_entries):
                    # 타임스탬프 기준 내림차순 정렬
                    matching_entries.sort(key=lambda x: x[1].get('timestamp', 0), reverse=True)
                
                latest_rq_name_key, latest_entry = matching_entries[0]
                self.log(f"_find_active_order_rq_name_key: 종목코드({normalized_code})로 active_orders에서 일치하는 항목 찾음: {latest_rq_name_key}", "DEBUG")
                return latest_rq_name_key

        # 3. BUY_REQ, SELL_REQ로 시작하는 RQName에서 코드 추출 시도
        if normalized_code:
            buy_req_prefix = f"BUY_REQ_{normalized_code}_"
            sell_req_prefix = f"SELL_REQ_{normalized_code}_"
            
            for rq_name_key in self.account_state.active_orders.keys():
                if (rq_name_key.startswith(buy_req_prefix) or 
                    rq_name_key.startswith(sell_req_prefix)):
                    self.log(f"_find_active_order_rq_name_key: RQName 패턴({buy_req_prefix} 또는 {sell_req_prefix})으로 active_orders에서 일치하는 항목 찾음: {rq_name_key}", "DEBUG")
                    return rq_name_key

        self.log(f"_find_active_order_rq_name_key: 종목코드({normalized_code}), API주문번호({api_order_no_from_chejan if api_order_no_from_chejan else 'N/A'})로 일치하는 활성 주문을 찾지 못했습니다.", "WARNING")
        return None
