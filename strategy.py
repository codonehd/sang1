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
    SOLD = auto() # 매도 완료 상태 추가

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
    dry_run_mode: bool = False # 드라이런 모드

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
    daily_chart_error: bool = False # 일봉 데이터 로드 오류 플래그
    last_error_message: Optional[str] = None # 마지막 오류 메시지
    temp_order_quantity: int = 0 # 임시 주문 수량 (매도 주문 시 사용)


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

        if normalized_code in self.account_state.portfolio and normalized_code not in self.watchlist:
            portfolio_item = self.account_state.portfolio[normalized_code]
            stock_name = portfolio_item.get('stock_name', normalized_code)
            
            self.add_to_watchlist(normalized_code, stock_name, yesterday_close_price=0.0)
            
            stock_info = self.watchlist.get(normalized_code) 
            if not stock_info: 
                self.log(f"[RECOVER_FAIL] _recover_missing_stock_from_portfolio: Failed to retrieve {normalized_code} from watchlist after adding.", "ERROR")
                return None
                
            stock_info.strategy_state = TradingState.BOUGHT
            stock_info.avg_buy_price = _safe_to_float(portfolio_item.get('매입가'))
            stock_info.total_buy_quantity = _safe_to_int(portfolio_item.get('보유수량'))
            stock_info.buy_timestamp = datetime.now() 
            
            self.account_state.trading_status[normalized_code] = {
                'status': TradingState.BOUGHT,
                'bought_price': stock_info.avg_buy_price,
                'bought_quantity': stock_info.total_buy_quantity,
                'bought_time': stock_info.buy_timestamp
            }
            
            self.log(f"[AUTO_RECOVERY] {normalized_code} ({stock_name}) watchlist 자동 복구 완료 (원본 입력: {original_code_param})", "WARNING")
            return stock_info
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
        self.pending_daily_data_stocks = set() 
        self.is_initialized_successfully = False 
        self.initialization_status = {
            "account_info_loaded": False, "deposit_info_loaded": False, 
            "portfolio_loaded": False, "settings_loaded": False,
            "market_hours_initialized": False
        }
        self.current_status_message = "초기화 중..."
        self.start_time = time.time()
        self.start_time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        self.account_state = AccountState()
        self.settings = StrategySettings()
        self._load_strategy_settings() 
        
        db_path = self.modules.config_manager.get_setting("Database", "path", "logs/trading_data.db")
        db_dir = os.path.dirname(db_path)
        if not db_dir: db_dir = os.path.dirname(os.path.abspath(__file__))
        self.state_file_path = os.path.join(db_dir, "trading_state.json")
        self.log(f"상태 파일 경로: {self.state_file_path}", "INFO")
        
        old_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trading_state.json")
        if os.path.exists(old_path) and old_path != self.state_file_path:
            try:
                if not os.path.exists(db_dir): os.makedirs(db_dir, exist_ok=True)
                if os.path.exists(self.state_file_path):
                    old_mtime = os.path.getmtime(old_path)
                    new_mtime = os.path.getmtime(self.state_file_path)
                    if old_mtime > new_mtime:
                        backup_path = f"{self.state_file_path}.bak"
                        if os.path.exists(backup_path): os.remove(backup_path)
                        os.rename(self.state_file_path, backup_path)
                        self.log(f"기존 상태 파일을 {backup_path}로 백업했습니다.", "INFO")
                        os.rename(old_path, self.state_file_path)
                        self.log(f"이전 위치의 상태 파일을 새 경로로 이동했습니다: {old_path} -> {self.state_file_path}", "INFO")
                    else:
                        os.remove(old_path)
                        self.log(f"더 오래된 이전 위치의 상태 파일을 삭제했습니다: {old_path}", "INFO")
                else:
                    os.rename(old_path, self.state_file_path)
                    self.log(f"이전 위치의 상태 파일을 새 경로로 이동했습니다: {old_path} -> {self.state_file_path}", "INFO")
            except Exception as e:
                self.log(f"상태 파일 이동 중 오류 발생: {e}", "ERROR")
        
        self.account_state.trading_records = {
            '매수건수': 0, '매수금액': 0, '매도건수': 0, '매도금액': 0,
            '총손익금': 0, '이익건수': 0, '이익금액': 0, '손실건수': 0, '손실금액': 0
        }
        if self.initialization_status["settings_loaded"]: 
             self.log("전략 설정 로드 완료.", "INFO")
        else:
            self.log("전략 설정 로드 실패. 기본값으로 진행될 수 있습니다.", "WARNING")


        self.watchlist: Dict[str, StockTrackingData] = {}
        self.current_async_calls = set()
        self.is_running = False
        self.check_timer = QTimer()
        self.check_timer.setInterval(2000)
        self.check_timer.timeout.connect(self.check_conditions)
        self.status_report_timer = QTimer()
        self.status_report_timer.timeout.connect(self.report_periodic_status)
        self.daily_snapshot_timer = QTimer()
        self.daily_snapshot_timer.timeout.connect(self.record_daily_snapshot_if_needed)
        self.daily_snapshot_timer.setInterval(3600 * 1000) 
        self.last_snapshot_date = None
        self.today_date_for_buy_limit: Optional[str] = None 
        self.daily_buy_executed_count: int = 0 

        try:
            self.market_open_time = datetime.strptime(self.settings.market_open_time_str, "%H:%M:%S").time()
            self.market_close_time = datetime.strptime(self.settings.market_close_time_str, "%H:%M:%S").time()
            self.log(f"장운영시간 초기화: {self.settings.market_open_time_str} - {self.settings.market_close_time_str}", "INFO")
            self.initialization_status["market_hours_initialized"] = True
        except ValueError as e:
            self.log(f"설정에서 장운영시간 파싱 오류: {e}. 기본값 09:00-15:30 사용.", "ERROR")
            self.market_open_time = datetime.strptime("09:00:00", "%H:%M:%S").time()
            self.market_close_time = datetime.strptime("15:30:00", "%H:%M:%S").time()
            self.initialization_status["market_hours_initialized"] = True 
        
        self.current_real_data_count = 0 
        self.log("TradingStrategy 객체 생성 완료. 추가 초기화가 필요합니다.", "INFO")
        self.watchlist_data_requested = False 
        self.current_status_message = "TradingStrategy 객체 생성됨. API 연결 및 데이터 로딩 대기 중."

        if self.modules.config_manager:
            all_fee_tax_rates = self.modules.config_manager.get_setting("fee_tax_rates", default_val={})
            self.account_type = self.modules.config_manager.get_setting("계좌정보", "account_type", "실거래") 
            self.current_fee_tax_rates = all_fee_tax_rates.get(
                self.account_type,  
                { "buy_fee_rate": 0.0, "sell_fee_rate": 0.0, "sell_tax_rate": 0.0 }
            )
            self.log(f"현재 계좌 유형({self.account_type})에 따른 수수료/세금율 로드: {self.current_fee_tax_rates}", "INFO")
        else:
            self.log("ConfigManager가 없어 수수료/세금율을 로드할 수 없습니다. 기본값(0)을 사용합니다.", "WARNING")
            self.account_type = "실거래" # 기본값
            self.current_fee_tax_rates = {
                "buy_fee_rate": 0.0, "sell_fee_rate": 0.0, "sell_tax_rate": 0.0
            }

    def _load_strategy_settings(self):
        if not self.modules.config_manager:
            self.log("설정 관리자가 설정되지 않아 기본값을 사용합니다.", "WARNING")
            self.initialization_status["settings_loaded"] = False # 명시적 실패 처리
            return
        
        try:
            self.settings.buy_amount_per_stock = self.modules.config_manager.get_setting("매수금액", 1000000.0)
            self.settings.stop_loss_rate_from_yesterday_close = self.modules.config_manager.get_setting("매매전략", "손절손실률_전일종가기준", 2.0)
            self.settings.partial_take_profit_rate = self.modules.config_manager.get_setting("매매전략", "익절_수익률", 5.0)
            self.settings.partial_sell_ratio = self.modules.config_manager.get_setting("매매전략", "익절_매도비율", 50.0) / 100.0
            self.settings.full_take_profit_target_rate = self.modules.config_manager.get_setting("매매전략", "최종_익절_수익률", 9.0)
            self.settings.trailing_stop_activation_profit_rate = self.modules.config_manager.get_setting("매매전략", "트레일링_활성화_수익률", 2.0)
            self.settings.trailing_stop_fall_rate = self.modules.config_manager.get_setting("매매전략", "트레일링_하락률", 1.5)
            self.settings.market_open_time_str = self.modules.config_manager.get_setting("매매전략", "MarketOpenTime", "09:00:00")
            self.settings.market_close_time_str = self.modules.config_manager.get_setting("매매전략", "MarketCloseTime", "15:30:00")
            self.settings.dry_run_mode = self.modules.config_manager.get_setting("매매전략", "dry_run_mode", False)
            self.settings.max_buy_attempts_per_stock = self.modules.config_manager.get_setting("매매전략", "종목당_최대시도횟수", 3)
            
            self.settings.periodic_report_enabled = self.modules.config_manager.get_setting("PeriodicStatusReport", "enabled", True)
            self.settings.periodic_report_interval_seconds = self.modules.config_manager.get_setting("PeriodicStatusReport", "interval_seconds", 60)
            
            self.account_type = self.modules.config_manager.get_setting("계좌정보", "account_type", "실거래")
            self.log(f"계좌 유형 설정 로드: {self.account_type}", "INFO")
            self.initialization_status["settings_loaded"] = True
        except Exception as e:
            self.log(f"전략 설정 로드 중 오류 발생: {e}. 기본값으로 진행합니다.", "ERROR")
            self.initialization_status["settings_loaded"] = False


    def log(self, message, level="INFO"):
        timestamp = get_current_time_str()
        
        if hasattr(self, 'modules') and self.modules and hasattr(self.modules, 'logger') and self.modules.logger:
            log_func = getattr(self.modules.logger, level.lower(), self.modules.logger.info)
            log_func(f"[Strategy][{timestamp}] {message}")
        else:
            pass 

    # ... (다른 메서드들) ...

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
            return False # 실패 시 False 반환 추가
        
        # 상태 초기화
        old_state_name = stock_info.strategy_state.name if stock_info.strategy_state else 'N/A'
        
        stock_info.strategy_state = TradingState.WAITING # WAITING으로 설정
        stock_info.avg_buy_price = 0.0
        stock_info.total_buy_quantity = 0
        stock_info.current_high_price_after_buy = 0.0
        stock_info.is_trailing_stop_active = False
        stock_info.trailing_stop_partially_sold = False
        stock_info.partial_take_profit_executed = False
        stock_info.buy_timestamp = None
        stock_info.buy_completion_count = 0
        stock_info.last_order_rq_name = None # last_order_rq_name 초기화 추가
        stock_info.is_yesterday_close_broken_today = False # 추가된 필드 초기화
        # is_gap_up_today는 보통 add_to_watchlist 시점에 결정되거나 일봉 데이터 수신 시 업데이트되므로,
        # 여기서 반드시 초기화할 필요는 없을 수 있지만, 필요하다면 False로 설정합니다.
        # stock_info.is_gap_up_today = False 
        
        # 임시 주문 수량 초기화
        if hasattr(stock_info, 'temp_order_quantity'): # 안전하게 속성 존재 여부 확인
            old_temp_qty = getattr(stock_info, 'temp_order_quantity', 0)
            if old_temp_qty != 0 : # 0이 아닐 때만 로깅
                self.log(f"[{code}] 상태 초기화 중 임시 주문 수량도 초기화: {old_temp_qty} -> 0", "DEBUG")
            stock_info.temp_order_quantity = 0
        
        # trading_status에서도 제거
        if code in self.account_state.trading_status:
            del self.account_state.trading_status[code]
            self.log(f"[{code}] trading_status에서 항목 제거됨.", "DEBUG")
        
        self.log(f"[{code}] 종목 상태 초기화 완료: {old_state_name} -> {stock_info.strategy_state.name}", "INFO")
        return True # 성공 시 True 반환

    def check_conditions(self):
        """전략 조건 검사 및 매매 실행"""
        # 일일 매수 횟수 제한을 위한 날짜 확인 및 카운트 초기화
        current_date = datetime.now().strftime('%Y-%m-%d')
        if self.today_date_for_buy_limit != current_date:
            self.log(f"날짜 변경 감지: {self.today_date_for_buy_limit} -> {current_date}. 일일 매수 카운트 초기화", "INFO")
            # 일일 매수 횟수 초기화
            self.daily_buy_executed_count = 0
            # 모든 종목의 매수 시도 횟수 초기화 (buy_completion_count)
            for code_to_reset, stock_data_to_reset in self.watchlist.items():
                if stock_data_to_reset.buy_completion_count > 0:
                    self.log(f"[{code_to_reset}] 매수 체결 완료 횟수 초기화 (날짜 변경): {stock_data_to_reset.buy_completion_count} -> 0", "DEBUG")
                    stock_data_to_reset.buy_completion_count = 0
            self.today_date_for_buy_limit = current_date
        
        # 시장 시간이 아니면 종료
        if not self.is_market_hours():
            # self.log("장 운영 시간이 아니므로 조건 검사를 건너<0xEB><0x9B><0x81>니다.", "DEBUG") # 너무 빈번한 로그 방지
            return

        for code in list(self.watchlist.keys()): # dict 변경 중 순회 오류 방지를 위해 list로 복사
            stock_info = self.watchlist.get(code) 
            if not stock_info: 
                self.log(f"[INCONSISTENCY_CHECK_SKIP] {code}: StockTrackingData를 찾을 수 없어 일관성 검사 건너뜀.", "ERROR")
                continue 

            # 일관성 검사 시작
            inconsistent_state_detected = False
            if stock_info.strategy_state == TradingState.PARTIAL_SOLD and stock_info.total_buy_quantity <= 0:
                self.log(f"[INCONSISTENCY_DETECTED] {code}: PARTIAL_SOLD 상태이나 보유수량 0 이하 ({stock_info.total_buy_quantity}). 정보 초기화 예정.", "WARNING")
                inconsistent_state_detected = True

            # BOUGHT 또는 PARTIAL_SOLD 상태인데 avg_buy_price가 0 이하인 경우 (단, total_buy_quantity가 0보다 클 때만 해당)
            if stock_info.strategy_state in [TradingState.BOUGHT, TradingState.PARTIAL_SOLD] and \
               stock_info.total_buy_quantity > 0 and stock_info.avg_buy_price <= 0:
                self.log(f"[INCONSISTENCY_DETECTED] {code}: 보유 상태({stock_info.strategy_state.name}) 및 보유수량({stock_info.total_buy_quantity}) 존재하나 평균매입가 0 이하 ({stock_info.avg_buy_price:.2f}). 정보 초기화 예정.", "WARNING")
                inconsistent_state_detected = True
            
            if stock_info.is_trailing_stop_active and stock_info.avg_buy_price > 0 and \
               stock_info.current_high_price_after_buy <= stock_info.avg_buy_price :
                self.log(f"[INCONSISTENCY_DETECTED] {code}: 트레일링 스탑 활성 상태이나, 기준고점({stock_info.current_high_price_after_buy:.2f})이 평균매입가({stock_info.avg_buy_price:.2f}) 이하. 트레일링 스탑 비활성화 및 고점 재설정 시도.", "WARNING")
                stock_info.is_trailing_stop_active = False
                stock_info.current_high_price_after_buy = stock_info.current_price if stock_info.current_price > stock_info.avg_buy_price else stock_info.avg_buy_price * 1.001 # 현재가가 낮으면 매입가보다 약간 높게 설정
                # 이 조건만으로는 전체 초기화는 하지 않음

            if inconsistent_state_detected:
                # --- 요청된 디버깅 로그 추가 시작 ---
                stock_info_before_reset = self.watchlist.get(code) # 상태 변경 전 객체 (참조 동일)
                if stock_info_before_reset: # 혹시 모를 None 체크
                    self.log(f"[DEBUG_RESET] Before reset_stock_strategy_info for {code}: state = {stock_info_before_reset.strategy_state.name}", "DEBUG")
                
                reset_success = self.reset_stock_strategy_info(code) # 반환 값 활용
                
                stock_info_after_reset = self.watchlist.get(code) # 상태 변경 후 객체 (참조 동일)
                if stock_info_after_reset:
                    self.log(f"[DEBUG_RESET] After reset_stock_strategy_info for {code}: success={reset_success}, new_state = {stock_info_after_reset.strategy_state.name}", "DEBUG")
                    
                    # 만약 reset_success는 True인데, 실제 상태가 WAITING이 아니라면 추가 로그
                    if reset_success and stock_info_after_reset.strategy_state != TradingState.WAITING:
                        self.log(f"[DEBUG_RESET_WARN] {code}: reset_stock_strategy_info reported success, but state is {stock_info_after_reset.strategy_state.name} instead of WAITING.", "WARNING")
                # --- 요청된 디버깅 로그 추가 끝 ---

                # 기존 로그 (초기화 성공/실패)는 reset_stock_strategy_info 내부 또는 여기서 조건부로 남길 수 있음
                if reset_success:
                    self.log(f"[{code}] 일관성 없는 상태 감지 및 정보 초기화 완료. 다음 로직 건너뜀.", "INFO")
                else:
                    self.log(f"[{code}] 일관성 없는 상태 감지, 정보 초기화 실패. 다음 로직 건너뜀.", "ERROR")
                
                continue # for code in list(self.watchlist.keys()): 루프의 다음 아이템으로 넘어감

            # self.watchlist.get(code)를 다시 호출할 필요는 없음. stock_info는 참조이므로 reset_stock_strategy_info에서 변경된 사항이 반영됨.
            if code in self.watchlist: 
                self.process_strategy(code)
            else: # 혹시 모를 경우 (reset_stock_strategy_info가 watchlist에서 제거하는 로직이 추가된다면)
                self.log(f"[{code}] reset_stock_strategy_info 호출 후 watchlist에 존재하지 않아 process_strategy 건너뜀.", "WARNING")

    # ... (파일의 나머지 부분) ...
```

**주요 변경점 요약:**

*   `check_conditions` 함수 내 `if inconsistent_state_detected:` 블록에 요청하신 디버깅 로그를 추가했습니다.
    *   `reset_stock_strategy_info` 호출 전후의 `strategy_state`를 로깅합니다.
    *   `reset_stock_strategy_info`의 성공 여부와 실제 상태 변경 결과를 비교하여 불일치 시 경고 로그를 남깁니다.
*   `reset_stock_strategy_info` 함수에는 `last_order_rq_name` 및 `is_yesterday_close_broken_today` 필드 초기화 로직을 추가하고, 로그 메시지를 개선했습니다.

이 수정으로 `test_scenario_inconsistent_state_partial_sold_zero_qty` 테스트 케이스 실패 원인을 분석하는 데 필요한 상세 로그를 확보할 수 있을 것입니다.
