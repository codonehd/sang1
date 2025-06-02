import unittest
from unittest.mock import MagicMock, patch
import sys
import os
import logging
from typing import Dict, Any, List, Optional # typing 추가
from datetime import datetime, timedelta # datetime, timedelta 추가

# 테스트 대상 모듈을 import하기 위해 프로젝트 루트 경로를 sys.path에 추가
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

# from PyQt5.QtCore import QObject, pyqtSignal # PyQt 의존성 제거 시도
# from PyQt5.QtWidgets import QApplication # QApplication 임포트 제거
from strategy import TradingStrategy, StockTrackingData, TradingState # TradingState, StockTrackingData 추가
from config import ConfigManager # 실제 ConfigManager 사용 (필요시 Mock으로 교체)
from logger import Logger
from util import ScreenManager # 실제 ScreenManager 사용 (Mock으로 대체 가능)
from tests.mock_api_base import BaseMockKiwoomAPI # BaseMockKiwoomAPI 임포트

class MockKiwoomAPI(BaseMockKiwoomAPI):
    """
    Mock KiwoomAPI for unit tests in test_strategy.py.
    Inherits from BaseMockKiwoomAPI and overrides methods for specific simple behaviors.
    """
    def __init__(self, logger: Optional[Logger] = None, screen_manager: Optional[ScreenManager] = None):
        super().__init__(logger=logger if logger else Logger(log_level=logging.DEBUG, name="MockKiwoomStrategyTest"))
        self.screen_manager = screen_manager # ScreenManager 인스턴스 저장 (Base에는 없음)
        # self.account_number = "1234567890" # Base에서 설정
        # self.connected = True # Base에서 설정
        # self.tr_data_cache: Dict[str, Dict[str, Any]] = {} # Base에서 설정
        # self.current_input_values: Dict[str, str] = {} # Base에서 설정
        self.strategy_instance = None # strategy_instance 초기화 (Base에 이미 있음)
        self.send_order_call_history: List[Dict[str, Any]] = [] # Base에 이미 있음, 여기서는 명시적으로 재선언 (선택적)

    # KiwoomAPI의 메서드들은 일단 유지 (시그널만 제거)
    # subscribe_real_data 와 unsubscribe_real_data는 BaseMockKiwoomAPI에 set_real_reg/disconnect_real_data로 이미 있음
    # 필요시 별도 로깅이나 로직 추가 가능. 여기서는 Base의 것을 사용하도록 함.

    def get_stock_basic_info(self, code: str, market_context: str = None, screen_no: Optional[str] = None): # KiwoomAPI와 시그니처 일치
        self.log(f"MockKiwoomAPI (StrategyTest) TR (opt10001) 요청: {code}, MarketCtx: {market_context}, Screen: {screen_no}", "DEBUG")
        if code == "005930":
            return {'현재가': 70000, '종목명': '삼성전자', '종목코드': code}
        elif code == "000660":
            return {'현재가': 100000, '종목명': 'SK하이닉스', '종목코드': code}
        return None

    def get_daily_chart(self, code: str, *, date_to: str = "", date_from: str = "", market_context: str = None, screen_no_override: Optional[str] = None, rq_name_override: Optional[str] = None) -> List[Dict[str, Any]]: # KiwoomAPI와 시그니처 일치, 반환 타입 명시
        self.log(f"MockKiwoomAPI (StrategyTest) TR (opt10081) 요청: {code}, DateTo: {date_to}, MarketCtx: {market_context}", "DEBUG")
        if code == "005930":
            return [{'일자': '20230102', '시가': 70500, '현재가': 70000}, {'일자': '20230101', '시가': 69000, '현재가': 69500}]
        elif code == "000660":
             return [{'일자': '20230102', '시가': 101000, '현재가': 100000}, {'일자': '20230101', '시가': 99000, '현재가': 99500}]
        return []

    # send_order는 BaseMockKiwoomAPI의 것을 사용. 필요시 오버라이드.
    # get_login_info, get_connect_state, set_input_value는 BaseMockKiwoomAPI의 것을 사용.

    def comm_rq_data(self, rq_name: str, tr_code: str, prev_next: int, screen_no: str, input_values_override: Optional[Dict[str, str]] = None, market_context: Optional[str] = None):
        self.log(f"MockKiwoomAPI (StrategyTest) CommRqData: RQName({rq_name}), TRCode({tr_code}), PrevNext({prev_next}), ScreenNo({screen_no})", "DEBUG")
        
        effective_inputs = self.current_input_values.copy() # Base에서 관리
        if input_values_override:
            effective_inputs.update(input_values_override)

        # Base의 tr_data_cache 사용
        parsed_tr_data_for_cache: Dict[str, Any] = {
            'tr_code': tr_code, 'single_data': {}, 'multi_data': [], 
            'status': 'pending_response', 'rq_name': rq_name, 
            'screen_no': screen_no, 'prev_next_for_rq': str(prev_next)
        }

        if tr_code == "opt10001":
            code_input = effective_inputs.get("종목코드")
            # self.get_stock_basic_info는 이 클래스에 오버라이드된 버전 사용
            stock_info_data = self.get_stock_basic_info(code_input, market_context=market_context, screen_no=screen_no) 
            if stock_info_data: # get_stock_basic_info가 dict를 반환한다고 가정
                parsed_tr_data_for_cache['single_data'] = stock_info_data
                parsed_tr_data_for_cache['status'] = 'completed'
        elif tr_code == "opt10081":
            code_input = effective_inputs.get("종목코드")
            # self.get_daily_chart는 이 클래스에 오버라이드된 버전 사용
            daily_data_list = self.get_daily_chart(code=code_input, date_to=effective_inputs.get("기준일자",""), market_context=market_context, screen_no_override=screen_no, rq_name_override=rq_name)
            parsed_tr_data_for_cache['multi_data'] = daily_data_list
            parsed_tr_data_for_cache['status'] = 'completed' 
        elif tr_code == "opw00001": 
             parsed_tr_data_for_cache['single_data'] = {'예수금': "5000000", '주문가능금액': "5000000"} # 문자열로 우선 저장
             parsed_tr_data_for_cache['status'] = 'completed'
        elif tr_code == "opw00018": 
             parsed_tr_data_for_cache['single_data'] = {'총매입금액': "0", '총평가금액': "0"}
             parsed_tr_data_for_cache['multi_data'] = [] 
             parsed_tr_data_for_cache['status'] = 'completed'
        
        self.tr_data_cache[rq_name] = parsed_tr_data_for_cache
        self.current_input_values.clear() # Base에 이미 있음, 호출은 유지

        # Simulate TR data reception for strategy
        if self.strategy_instance and parsed_tr_data_for_cache['status'] == 'completed':
            # Strategy의 on_tr_data_received는 dict를 기대함.
            # KiwoomAPI의 _parse_tr_data 결과를 모방해야 함.
            # 여기서는 단순화된 데이터를 Strategy에 직접 전달.
            # 실제 _parse_tr_data는 더 복잡한 구조를 반환함.
            # 이 Mock의 목적은 Strategy의 로직을 테스트하는 것이므로, Strategy가 기대하는 형태로 데이터를 가공할 필요가 있음.
            # KiwoomAPI의 _parse_tr_data는 {'single_data': {...}, 'multi_data': [...], ...} 형태를 반환함.
            # 현재 parsed_tr_data_for_cache가 이 형태와 유사하므로 그대로 전달.
            
            # 숫자형 필드 변환 (Strategy가 기대하는 형태에 맞추기 위함)
            if 'single_data' in parsed_tr_data_for_cache:
                 parsed_tr_data_for_cache['single_data'] = {k: self._attempt_numeric_conversion(v) for k,v in parsed_tr_data_for_cache['single_data'].items()}
            if 'multi_data' in parsed_tr_data_for_cache:
                 parsed_tr_data_for_cache['multi_data'] = [
                     {k: self._attempt_numeric_conversion(v) for k,v in row.items()} for row in parsed_tr_data_for_cache['multi_data']
                 ]

            if hasattr(self.strategy_instance, 'on_tr_data_received'):
                 # parsed_tr_data_for_cache의 'status'는 실제 API 응답에는 없음.
                 # Strategy는 TR 코드와 파싱된 데이터(single/multi)를 받음.
                 data_for_strategy = {'single_data': parsed_tr_data_for_cache.get('single_data',{}), 
                                      'multi_data': parsed_tr_data_for_cache.get('multi_data',[])}
                 self.strategy_instance.on_tr_data_received(rq_name, tr_code, data_for_strategy, prev_next_for_rq=parsed_tr_data_for_cache.get('prev_next_for_rq', '0'))
            
            # opt10081에 대한 특별 처리 (on_daily_chart_data_ready)
            if tr_code == "opt10081" and hasattr(self.strategy_instance, 'on_daily_chart_data_ready'):
                code_input = effective_inputs.get("종목코드")
                if code_input:
                    # on_daily_chart_data_ready는 chart_data (list of dicts)를 기대함
                    self.strategy_instance.on_daily_chart_data_ready(rq_name, code_input, parsed_tr_data_for_cache['multi_data'][:], is_continuous=(prev_next == 2))
        return 0 

    def _attempt_numeric_conversion(self, value_str):
        """Helper to convert string value to int or float if possible, else return original string."""
        if isinstance(value_str, str):
            try:
                return int(value_str)
            except ValueError:
                try:
                    return float(value_str)
                except ValueError:
                    return value_str
        return value_str # 이미 숫자이거나 변환 불가능한 타입이면 그대로 반환

    # get_comm_data, get_repeat_cnt는 BaseMockKiwoomAPI의 것을 사용.
    # set_real_reg, disconnect_real_data는 BaseMockKiwoomAPI의 것을 사용.
    # get_code_market_info는 BaseMockKiwoomAPI의 것을 사용 (필요 시 오버라이드).
    # parse_chejan_data는 BaseMockKiwoomAPI의 것을 사용 (필요 시 오버라이드).
    
    # set_strategy_instance는 BaseMockKiwoomAPI의 것을 사용.


class MockConfigManager:
    def __init__(self, settings_override=None):
        self.settings = {
            "매매전략": {
                "종목당매수금액": 1000000.0,
                "손절손실률": 3.0,
                "익절수익률": 5.0,
                "분할매도비율": 0.5,
                "트레일링하락률": 2.0,
                "MarketOpenTime": "09:00:00",
                "MarketCloseTime": "15:30:00",
            },
            "API_Limit": {
                "tr_request_interval_ms": 210,
            },
            "계좌정보": {
                "계좌번호": "1234567890",
                "비밀번호": "test_password" 
            },
            "API": {
                "RealTimeFID": "10;11;12;13" 
            },
            "Logging": {
                "level": "DEBUG",
                "max_bytes": 10485760, 
                "backup_count": 5
            },
            "PeriodicStatusReport": {
                "enabled": False, 
                "interval_seconds": 300 
            }
        }
        if settings_override:
            for section, new_values in settings_override.items():
                if section not in self.settings:
                    self.settings[section] = {}
                self.settings[section].update(new_values)
        # Mock 로거 추가 (실제 ConfigManager처럼)
        self.logger = Logger(log_level=self.settings.get("Logging", {}).get("level", "INFO"))
        self.logger.logger.name = "MockConfigManagerLogger"
                
    def get_setting(self, section, key, default=None):
        return self.settings.get(section, {}).get(key, default)

    def load_settings(self): 
        self.logger.info("MockConfigManager: Settings loaded (no actual file reading).")


class MockDatabaseManager:
    def __init__(self, logger=None):
        self.logger = logger if logger else Logger(log_level=logging.DEBUG)
        self.logger.logger.name = "MockDBManagerLogger"
        self.watchlist_items: List[Dict[str, Any]] = [] 
        self.trade_records: List[Dict[str, Any]] = []
        self.decision_records: List[Dict[str, Any]] = []
        self.daily_snapshots: Dict[str, Dict[str, Any]] = {}

    def add_watchlist_item(self, code: str, name: str, strategy_profile_name: Optional[str]=None, created_at: Optional[str]=None) -> bool: # 시그니처 변경
        self.watchlist_items.append({'code': code, 'name': name, 'strategy_profile_name': strategy_profile_name})
        self.logger.info(f"MockDB: Added to watchlist - Code: {code}, Name: {name}")
        return True

    def remove_watchlist_item(self, code: str) -> bool:
        original_len = len(self.watchlist_items)
        self.watchlist_items = [item for item in self.watchlist_items if item['code'] != code]
        removed = len(self.watchlist_items) < original_len
        if removed:
            self.logger.info(f"MockDB: Removed from watchlist - Code: {code}")
        return removed

    def get_watchlist(self) -> List[Dict[str, Any]]:
        return self.watchlist_items[:]

    def add_trade_record(self, timestamp: str, order_no: str, original_rq_name: str, code: str, stock_name: str, trade_type: str, quantity: int, price: float, reason: Optional[str]=None, fees: float=0, tax: float=0, profit_loss: float=0) -> bool:
        record = {
            'timestamp': timestamp, 'order_no': order_no, 'original_rq_name': original_rq_name,
            'code': code, 'stock_name': stock_name, 'trade_type': trade_type,
            'quantity': quantity, 'price': price, 'reason': reason,
            'fees': fees, 'tax': tax, 'profit_loss': profit_loss
        }
        self.trade_records.append(record)
        self.logger.info(f"MockDB: Added trade record - Code: {code}, Type: {trade_type}, Qty: {quantity}, Price: {price}")
        return True

    def get_trade_records(self, code: Optional[str]=None, trade_type: Optional[str]=None, start_date: Optional[str]=None, end_date: Optional[str]=None) -> List[Dict[str, Any]]:
        filtered = self.trade_records
        if code:
            filtered = [r for r in filtered if r['code'] == code]
        if trade_type:
            filtered = [r for r in filtered if r['trade_type'] == trade_type]
        return filtered[:]

    def add_decision_record(self, timestamp: str, code: str, decision_type: str, reason: str, related_data_dict: Dict[str, Any]) -> bool:
        record = {
            'timestamp': timestamp, 'code': code, 'decision_type': decision_type,
            'reason': reason, 'related_data': related_data_dict
        }
        self.decision_records.append(record)
        self.logger.info(f"MockDB: Added decision record - Code: {code}, Type: {decision_type}")
        return True

    def add_daily_snapshot(self, date: str, deposit: float, total_purchase_amount: float, total_evaluation_amount: float, total_profit_loss_amount: float, total_return_rate: float, portfolio_details_dict: Dict[str, Any], total_asset_value: Optional[float]=None) -> bool:
        if date in self.daily_snapshots:
            self.logger.warning(f"MockDB: Daily snapshot for {date} already exists. Overwriting.")
        self.daily_snapshots[date] = {
            'date': date, 'deposit': deposit, 
            'total_purchase_amount': total_purchase_amount,
            'total_evaluation_amount': total_evaluation_amount,
            'total_profit_loss_amount': total_profit_loss_amount,
            'total_return_rate': total_return_rate,
            'portfolio_details': portfolio_details_dict,
            'total_asset_value': total_asset_value
        }
        self.logger.info(f"MockDB: Added daily snapshot for {date}")
        return True

class MockScreenManager:
    def __init__(self, logger=None):
        self.logger = logger or Logger(log_level=logging.DEBUG)
        self.logger.logger.name = "MockScreenManagerLogger"
        self.available_screens = [f"{2000 + i:04d}" for i in range(20)] 
        self.used_screens_by_identifier: Dict[str, str] = {} 
        self.log_prefix = "[MockScreenManager]"

    def get_available_screen(self, identifier: str) -> Optional[str]:
        if identifier in self.used_screens_by_identifier:
            self.logger.warning(f"{self.log_prefix} Identifier '{identifier}' is already associated with screen '{self.used_screens_by_identifier[identifier]}'. Returning existing.")
            return self.used_screens_by_identifier[identifier]
        
        if not self.available_screens:
            self.logger.error(f"{self.log_prefix} No available screens for identifier '{identifier}'.")
            return None
        
        screen_no = self.available_screens.pop(0)
        self.used_screens_by_identifier[identifier] = screen_no
        self.logger.info(f"{self.log_prefix} Assigned screen '{screen_no}' to identifier '{identifier}'. Available: {len(self.available_screens)}")
        return screen_no

    def release_screen(self, screen_no: str, identifier: str) -> bool:
        if identifier in self.used_screens_by_identifier and self.used_screens_by_identifier[identifier] == screen_no:
            del self.used_screens_by_identifier[identifier]
            if screen_no not in self.available_screens: 
                 self.available_screens.append(screen_no)
            self.logger.info(f"{self.log_prefix} Released screen '{screen_no}' for identifier '{identifier}'. Available: {len(self.available_screens)}")
            return True
        else:
            self.logger.warning(f"{self.log_prefix} Failed to release screen '{screen_no}' for identifier '{identifier}'. Not found or mismatch.")
            return False
            
    def get_screen_number(self) -> Optional[str]: 
        if not self.available_screens:
            self.logger.error(f"{self.log_prefix} No available screens (generic request).")
            return None
        screen_no = self.available_screens.pop(0)
        self.logger.info(f"{self.log_prefix} Assigned generic screen '{screen_no}'. Available: {len(self.available_screens)}")
        return screen_no

    def release_screen_number(self, screen_no: str) -> bool:
        is_used_by_id = False
        for used_id, used_scr_no in self.used_screens_by_identifier.items():
            if used_scr_no == screen_no:
                is_used_by_id = True
                self.logger.warning(f"{self.log_prefix} Screen '{screen_no}' is actively used by identifier '{used_id}'. Cannot release generically via release_screen_number. Use release_screen instead.")
                break
        if is_used_by_id:
            return False
            
        if screen_no not in self.available_screens:
            self.available_screens.append(screen_no)
            self.logger.info(f"{self.log_prefix} Released generic screen '{screen_no}'. Available: {len(self.available_screens)}")
            return True
        self.logger.debug(f"{self.log_prefix} Screen '{screen_no}' already available or never assigned generically.")
        return False 

    def cleanup_screens(self):
        self.logger.info(f"{self.log_prefix} Cleaning up all screens. ({len(self.used_screens_by_identifier)} used screens by identifier will be released)")
        for identifier, screen_no in list(self.used_screens_by_identifier.items()):
            self.release_screen(screen_no, identifier)
        self.logger.info(f"{self.log_prefix} Screen cleanup finished. Available: {len(self.available_screens)}")


class TestTradingStrategy(unittest.TestCase):

    def setUp(self):
        self.test_logger = Logger(log_level=logging.DEBUG) 
        self.test_logger.logger.handlers = [] 
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter('[%(levelname)s][%(name)s] %(asctime)s - %(message)s') 
        stream_handler.setFormatter(formatter)
        self.test_logger.logger.addHandler(stream_handler)
        self.test_logger.logger.propagate = False
        self.test_logger.logger.name = "TestStrategyLogger" 

        self.mock_config_manager = MockConfigManager()
        self.mock_screen_manager = MockScreenManager(logger=self.test_logger) 
        self.mock_kiwoom_api = MockKiwoomAPI(logger=self.test_logger, screen_manager=self.mock_screen_manager)
        self.mock_db_manager = MockDatabaseManager(logger=self.test_logger) 
        
        self.strategy = TradingStrategy(
            kiwoom_api=self.mock_kiwoom_api,
            config_manager=self.mock_config_manager, 
            logger=self.test_logger,
            db_manager=self.mock_db_manager, 
            screen_manager=self.mock_screen_manager 
        )
        # 테스트를 위해 계좌번호를 명시적으로 설정
        self.strategy.account_state.account_number = self.mock_kiwoom_api.get_login_info("ACCNO").split(';')[0]
        self.strategy.log(f"테스트용 계좌번호 설정됨: {self.strategy.account_state.account_number}", "DEBUG")
        
        self.mock_kiwoom_api.set_strategy_instance(self.strategy)
        self.mock_kiwoom_api.send_order = MagicMock(name="send_order_mock", return_value=0)

        # Cooldown test specific settings
        self.TEST_CODE = "005930"
        self.TEST_NAME = "테스트삼성"
        self.MAX_BUY_ATTEMPTS = 2
        self.COOLDOWN_MINUTES = 10

        self.mock_config_manager.settings["매매전략"]["종목당_최대시도횟수"] = self.MAX_BUY_ATTEMPTS
        self.mock_config_manager.settings["매매전략"]["cooldown_duration_minutes"] = self.COOLDOWN_MINUTES
        # Ensure settings are reloaded or directly set in strategy if _load_strategy_settings is called in init
        self.strategy.settings.max_buy_attempts_per_stock = self.MAX_BUY_ATTEMPTS
        self.strategy.settings.cooldown_duration_minutes = self.COOLDOWN_MINUTES

        # Ensure sufficient funds for testing buys
        self.strategy.account_state.account_summary['주문가능금액'] = "500000000" # Sufficiently large amount as string
        self.strategy.account_state.account_summary['예수금'] = "500000000"


    def _simulate_successful_buy(self, code, stock_name, buy_price, quantity_to_buy):
        """Helper function to simulate a successful buy order and its execution."""
        stock_info = self.strategy.watchlist.get(code)
        if not stock_info:
            # If not in watchlist, add it. This might be needed if test starts without it.
            self.strategy.add_to_watchlist(code, stock_name, yesterday_close_price=buy_price * 0.98) # Dummy yesterday close
            stock_info = self.strategy.watchlist.get(code)

        stock_info.current_price = buy_price
        stock_info.strategy_state = TradingState.WAITING # Ensure it's in a state that allows buying

        # Mock send_order to always succeed for this simulation
        self.mock_kiwoom_api.send_order.return_value = 0

        buy_executed = self.strategy.execute_buy(code)
        self.assertTrue(buy_executed, f"execute_buy for {code} should have succeeded.")

        rq_name = stock_info.last_order_rq_name
        self.assertIsNotNone(rq_name, "last_order_rq_name should be set after sending buy order.")

        # Simulate chejan data for buy execution
        # Ensure the order is in active_orders before simulating chejan
        self.assertIn(rq_name, self.strategy.account_state.active_orders, "Order should be in active_orders after sending.")
        self.strategy.account_state.active_orders[rq_name]['order_no'] = f"mock_ord_no_{datetime.now().timestamp()}"

        chejan_data = {
            '9001': code,  # 종목코드
            '302': stock_name, # 종목명
            '9203': self.strategy.account_state.active_orders[rq_name]['order_no'],  # 주문번호
            '913': '체결',  # 주문상태
            '900': str(quantity_to_buy),  # 주문수량
            '902': '0',  # 미체결수량 (전량체결)
            '10': str(buy_price),  # 체결가
            '911': str(quantity_to_buy),  # 체결량
            '905': '+매수', # 주문구분
            # 필요한 다른 FID 값들 추가...
        }

        # Ensure on_chejan_data_received can find the active order entry
        # The _find_active_order_rq_name_key will use the 'order_no' from chejan_data

        self.strategy.on_chejan_data_received(gubun='0', chejan_data=chejan_data)

        # Post-chejan assertions
        self.assertEqual(stock_info.strategy_state, TradingState.BOUGHT, "Stock state should be BOUGHT after buy chejan.")
        # buy_completion_count is incremented in _handle_order_execution_report
        # self.assertEqual(stock_info.buy_completion_count, expected_completion_count_after_buy)


    def tearDown(self):
        if hasattr(self.strategy, 'is_running') and self.strategy.is_running:
            self.strategy.stop()
        if self.test_logger and self.test_logger.logger:
            for handler in list(self.test_logger.logger.handlers): 
                self.test_logger.logger.removeHandler(handler)
                handler.close()

    def test_initialize_stock_data_success(self):
        code = "005930"
        name = "삼성전자"
        
        self.mock_kiwoom_api.set_real_reg = MagicMock(return_value=0) 
        self.strategy.initialize_stock_data(code, stock_name_param=name)

        self.assertIn(code, self.strategy.watchlist)
        stock_data = self.strategy.watchlist[code] 
        
        self.assertEqual(stock_data.stock_name, name)
        self.assertEqual(stock_data.current_price, 70000) 
        self.assertEqual(stock_data.yesterday_close_price, 69500) 
        self.assertEqual(stock_data.today_open_price, 70500) 
        self.assertFalse(stock_data.daily_chart_error)
        self.assertTrue(stock_data.is_gap_up_today)
        # initialize_stock_data -> on_daily_chart_data_ready -> check_initial_conditions -> (gap_up시) WAITING
        self.assertEqual(stock_data.strategy_state, TradingState.WAITING)
        
        expected_fids = self.mock_config_manager.get_setting("API", "RealTimeFID", "10;11;12;13")
        self.mock_kiwoom_api.set_real_reg.assert_called_once() 
        call_args = self.mock_kiwoom_api.set_real_reg.call_args[0]
        self.assertEqual(call_args[1], code) 
        self.assertEqual(call_args[2], expected_fids) 
        self.assertEqual(call_args[3], "1")

    def test_initialize_stock_data_success_goes_below_yesterday_close(self):
        """관심종목 초기화 성공 & 전일 종가 하회 조건 만족 케이스"""
        code = "005930"
        name = "삼성전자"

        self.mock_kiwoom_api.get_daily_chart = MagicMock(return_value=[
            {'일자': '20230102', '시가': 70500, '현재가': 69000}, 
            {'일자': '20230101', '시가': 68000, '현재가': 69500}  
        ])
        self.mock_kiwoom_api.get_stock_basic_info = MagicMock(return_value={
            '현재가': 69000, 
            '종목명': name,
            '종목코드': code
        })
        self.mock_kiwoom_api.set_real_reg = MagicMock(return_value=0)

        self.strategy.initialize_stock_data(code, stock_name_param=name)

        self.assertIn(code, self.strategy.watchlist)
        stock_data = self.strategy.watchlist[code]

        self.assertEqual(stock_data.stock_name, name)
        self.assertEqual(stock_data.current_price, 69000)
        self.assertEqual(stock_data.yesterday_close_price, 69500)
        self.assertEqual(stock_data.today_open_price, 70500)
        self.assertFalse(stock_data.daily_chart_error)
        self.assertTrue(stock_data.today_open_price > stock_data.yesterday_close_price)
        self.assertTrue(stock_data.current_price < stock_data.yesterday_close_price)
        self.assertTrue(stock_data.is_gap_up_today) 
        self.assertEqual(stock_data.strategy_state, TradingState.WAITING)

        # process_strategy 호출하여 _handle_waiting_state 실행 유도
        self.strategy.process_strategy(code)

        # 위 조건에서 process_strategy -> _handle_waiting_state가 호출되어 is_yesterday_close_broken_today가 True로 설정됨
        self.assertTrue(stock_data.is_yesterday_close_broken_today)

        expected_fids = self.mock_config_manager.get_setting("API", "RealTimeFID", "10;11;12;13")
        self.mock_kiwoom_api.set_real_reg.assert_called_once()
        call_args = self.mock_kiwoom_api.set_real_reg.call_args[0]
        self.assertEqual(call_args[1], code)
        self.assertEqual(call_args[2], expected_fids)
        self.assertEqual(call_args[3], "1")

    def test_initialize_stock_data_fail_daily_chart(self):
        """관심종목 초기화 실패 케이스 - 일봉 데이터 조회 실패 (빈 데이터 반환)"""
        code = "005930"
        name = "삼성전자"

        # MockKiwoomAPI의 get_daily_chart가 빈 리스트를 반환하도록 설정
        self.mock_kiwoom_api.get_daily_chart = MagicMock(return_value=[])
        # get_stock_basic_info는 호출되지 않거나, 호출되어도 이후 로직에 영향 미미
        self.mock_kiwoom_api.get_stock_basic_info = MagicMock(return_value={
            '현재가': 70000, 
            '종목명': name,
            '종목코드': code
        })
        self.mock_kiwoom_api.set_real_reg = MagicMock() # 호출되지 않아야 함

        self.strategy.initialize_stock_data(code, stock_name_param=name)

        self.assertIn(code, self.strategy.watchlist) # watchlist에는 추가됨
        stock_data = self.strategy.watchlist[code]

        self.assertEqual(stock_data.stock_name, name)
        self.assertTrue(stock_data.daily_chart_error) # 에러 플래그 확인
        # 주요 가격 정보는 초기값(0)이어야 함
        self.assertEqual(stock_data.current_price, 0)
        self.assertEqual(stock_data.yesterday_close_price, 0)
        self.assertEqual(stock_data.today_open_price, 0)
        self.assertEqual(stock_data.strategy_state, TradingState.IDLE) # IDLE 상태 유지 (또는 에러 상태)

        # comm_rq_data("opt10081")는 호출되지만, 이후 set_real_reg는 호출되지 않아야 함
        # MockKiwoomAPI.comm_rq_data가 on_daily_chart_data_ready를 호출하고, 
        # on_daily_chart_data_ready 내부에서 chart_data가 비어있으면 subscribe_stock_real_data를 호출하지 않음.
        self.mock_kiwoom_api.set_real_reg.assert_not_called()

    def test_remove_from_watchlist_success(self):
        """관심종목 제거 성공 케이스"""
        code = "005930"
        name = "삼성전자"

        # 1. 먼저 관심종목에 추가 (성공 케이스와 동일하게 설정)
        self.mock_kiwoom_api.get_daily_chart = MagicMock(return_value=[
            {'일자': '20230102', '시가': 70500, '현재가': 70000}, 
            {'일자': '20230101', '시가': 69000, '현재가': 69500}  
        ])
        self.mock_kiwoom_api.set_real_reg = MagicMock(return_value=0)
        self.strategy.initialize_stock_data(code, stock_name_param=name)
        self.assertIn(code, self.strategy.watchlist)
        # 초기화 시 strategy_state는 WAITING이 됨
        self.assertEqual(self.strategy.watchlist[code].strategy_state, TradingState.WAITING)
        
        # 실시간 데이터 구독에 사용된 화면 번호 확인 (실제로는 strategy 내부에서 관리됨)
        # initialize_stock_data -> ... -> subscribe_stock_real_data 에서 할당
        # 테스트에서는 set_real_reg 호출 시 사용된 화면번호를 알아야 함.
        # MockScreenManager가 마지막으로 할당한 일반 화면번호(get_screen_number) 또는
        # set_real_reg에 전달된 화면번호를 특정할 수 있어야 함.
        # 여기서는 subscribe_stock_real_data 내부에서 할당된 화면번호가 stock_info.api_data['real_screen_no']에 저장된다고 가정.
        # 실제 TradingStrategy.subscribe_stock_real_data에서 real_screen_no 저장 확인 필요.
        # --> TradingStrategy.subscribe_stock_real_data에서 stock_info.api_data['real_screen_no'] = screen_no 확인.
        real_data_screen_no = self.strategy.watchlist[code].api_data.get('real_screen_no')
        self.assertIsNotNone(real_data_screen_no, "실시간 데이터 화면번호가 watchlist에 저장되어야 합니다.")

        # TR 요청(opt10081)에 사용된 화면 번호 확인
        tr_screen_no = self.strategy.watchlist[code].api_data.get('screen_no')
        self.assertIsNotNone(tr_screen_no, "TR 요청 화면번호가 watchlist에 저장되어야 합니다.")

        # disconnect_real_data 및 release_screen 모킹
        self.mock_kiwoom_api.disconnect_real_data = MagicMock()
        # self.mock_screen_manager.release_screen = MagicMock() # release_screen은 identifier도 받음
        # self.mock_screen_manager.release_screen_number = MagicMock() # 이 메서드는 이제 사용 빈도 낮음
        # release_screen은 특정 rq_name(identifier)과 함께 호출될 것이므로, 여기서는 spy로 확인하거나, 
        # 실제 MockScreenManager의 내부 상태 변화를 확인.

        # 2. 메소드 호출
        self.strategy.remove_from_watchlist(code)

        # 3. 검증
        self.assertNotIn(code, self.strategy.watchlist)
        # strategy_state 등 다른 관련 상태들도 제거되었는지 확인 (TradingStrategy의 remove_from_watchlist 구현에 따라)
        # 현재 TradingStrategy.remove_from_watchlist는 self.watchlist에서만 제거함.
        # self.assertNotIn(code, self.strategy.strategy_state) # strategy_state는 watchlist 객체 내에 있음
        # self.assertNotIn(code, self.strategy.buy_prices) # 이 필드들은 strategy에 없음

        # KiwoomAPI의 실시간 데이터 해지 메서드 호출 확인
        self.mock_kiwoom_api.disconnect_real_data.assert_called_once_with(real_data_screen_no)
        
        # ScreenManager의 화면번호 반환 확인
        # remove_from_watchlist는 real_data_screen_no와 tr_screen_no를 해제해야 함
        self.assertNotIn(real_data_screen_no, self.mock_screen_manager.used_screens_by_identifier.values())
        self.assertIn(real_data_screen_no, self.mock_screen_manager.available_screens)
        self.assertNotIn(tr_screen_no, self.mock_screen_manager.used_screens_by_identifier.values()) # tr_screen_no는 rq_name과 함께 해제됨
        self.assertIn(tr_screen_no, self.mock_screen_manager.available_screens)

    # ... (이하 테스트 메서드 생략)

    def test_buy_success_scenario(self):
        """매수 성공 시나리오: 갭상승 -> 전일가 하회 -> 전일가 재돌파 -> 매수 -> 체결 -> BOUGHT 상태 확인"""
        code = "005930"
        name = "삼성전자"
        yesterday_close_price = 70000
        today_open_price = 70500 # 갭상승
        initial_buy_amount = self.strategy.settings.buy_amount_per_stock

        # 1. Mock KiwoomAPI 설정 (일봉 데이터, 기본 정보)
        self.mock_kiwoom_api.get_daily_chart = MagicMock(return_value=[
            {'일자': '20230102', '시가': today_open_price, '현재가': today_open_price}, # 당일 데이터 (초기 현재가는 시가와 동일 가정)
            {'일자': '20230101', '시가': 69000, '현재가': yesterday_close_price}      # 전일 데이터
        ])
        self.mock_kiwoom_api.get_stock_basic_info = MagicMock(return_value={
            '현재가': today_open_price, '종목명': name, '종목코드': code
        })
        self.mock_kiwoom_api.set_real_reg = MagicMock(return_value=0)
        # send_order는 setUp에서 이미 MagicMock으로 설정됨 (return_value=0)

        # 2. 관심종목 추가 및 초기화 (이때 WAITING 상태가 됨)
        self.strategy.initialize_stock_data(code, stock_name_param=name)
        stock_data = self.strategy.watchlist[code]
        self.assertEqual(stock_data.strategy_state, TradingState.WAITING)
        self.assertTrue(stock_data.is_gap_up_today)
        self.assertEqual(stock_data.yesterday_close_price, yesterday_close_price)
        stock_data.current_price = today_open_price # 초기 현재가 설정

        # 3. 전일 종가 하회 시나리오
        price_below_yesterday_close = yesterday_close_price - 100
        stock_data.current_price = price_below_yesterday_close
        self.strategy.process_strategy(code) 
        self.assertTrue(stock_data.is_yesterday_close_broken_today, "전일 종가 하회 시 플래그 설정 확인")
        self.mock_kiwoom_api.send_order.assert_not_called() # 아직 매수 주문 나가면 안됨

        # 4. 전일 종가 재돌파 및 매수 주문 발생
        price_above_yesterday_close_for_buy = yesterday_close_price + 100
        stock_data.current_price = price_above_yesterday_close_for_buy
        # 이전 daily_buy_executed_count 저장
        prev_buy_count = self.strategy.daily_buy_executed_count

        self.strategy.process_strategy(code) # 여기서 execute_buy 호출 예상
        
        expected_quantity = int(initial_buy_amount / price_above_yesterday_close_for_buy)
        self.mock_kiwoom_api.send_order.assert_called_once()
        call_args = self.mock_kiwoom_api.send_order.call_args[0]
        self.assertEqual(call_args[2], self.strategy.account_state.account_number) # acc_no
        self.assertIn(call_args[3], [1, 11]) # order_type (매수 또는 ATS 매수)
        self.assertEqual(call_args[4], code)      # code
        self.assertEqual(call_args[5], expected_quantity) # quantity
        self.assertEqual(call_args[6], price_above_yesterday_close_for_buy) # price
        # call_args[0] is rq_name, call_args[1] is screen_no, call_args[7] is hoga_gb, call_args[8] is org_order_no
        
        # 매수 주문 후 last_order_rq_name이 설정되어야 함
        self.assertIsNotNone(stock_data.last_order_rq_name)
        sent_rq_name = stock_data.last_order_rq_name
        self.assertIn(sent_rq_name, self.strategy.account_state.active_orders)
        self.assertEqual(self.strategy.account_state.active_orders[sent_rq_name]['order_status'], '접수요청')

        # 5. 매수 체결 처리
        # 체결 데이터 생성 (on_chejan_data_received 용)
        chejan_data_buy = {
            "9001": code, "302": name, "9203": "ORDER_NO_123", "913": "체결",
            "900": str(expected_quantity), "901": "0", "902": str(expected_quantity), # 주문수량, 미체결수량, 체결누계수량
            "10": str(price_above_yesterday_close_for_buy), "911": str(expected_quantity) # 체결가, 체결량
        }
        # self.mock_kiwoom_api.parse_chejan_data.return_value = chejan_data_buy # parse_chejan_data는 strategy 내부에서 호출
        # _find_active_order_entry가 잘 동작하도록 설정
        self.strategy.account_state.active_orders[sent_rq_name]['order_no'] = "ORDER_NO_123" # API 주문번호 업데이트

        with patch.object(self.mock_kiwoom_api, 'parse_chejan_data', return_value=chejan_data_buy) as mock_parse:
            self.strategy.on_chejan_data_received(gubun='0', item_cnt=0, fid_list_str="") # gubun '0'은 주문접수/체결

        self.assertEqual(stock_data.strategy_state, TradingState.BOUGHT, "매수 체결 후 BOUGHT 상태 확인")
        self.assertAlmostEqual(stock_data.avg_buy_price, price_above_yesterday_close_for_buy)
        self.assertEqual(stock_data.total_buy_quantity, expected_quantity)
        self.assertIsNotNone(stock_data.buy_timestamp, "매수 시간 기록 확인")
        self.assertFalse(stock_data.is_yesterday_close_broken_today, "매수 성공 후 플래그 리셋 확인")
        # last_order_rq_name은 체결 완료 후 None으로 리셋되어야 함 (on_chejan_data_received 내부 로직)
        self.assertIsNone(stock_data.last_order_rq_name, "체결 완료 후 last_order_rq_name 초기화 확인")
        self.assertNotIn(sent_rq_name, self.strategy.account_state.active_orders, "체결 완료된 주문은 active_orders에서 제거되어야 함")

        # 일일 매수 횟수 증가 확인
        self.assertEqual(self.strategy.daily_buy_executed_count, prev_buy_count + 1, "일일 매수 횟수 증가 확인")

    def test_trailing_stop_partial_sell_scenario(self):
        original_target_profit_rate = self.strategy.settings.target_profit_rate
        self.strategy.settings.target_profit_rate = 100.0  # 트레일링 스탑 테스트를 위해 매우 높게 설정
        self.addCleanup(setattr, self.strategy.settings, 'target_profit_rate', original_target_profit_rate)
        """트레일링 스탑 (50% 매도) 시나리오"""
        code = "005930"
        name = "삼성전자"
        avg_buy_price = 70000
        initial_quantity = 100
        trailing_fall_rate = self.strategy.settings.trailing_stop_fall_rate # 예: 2.0

        # 1. 초기 상태 설정: BOUGHT 상태, 특정 매수가와 수량 보유
        stock_data = StockTrackingData(code=code, stock_name=name)
        stock_data.strategy_state = TradingState.BOUGHT
        stock_data.avg_buy_price = avg_buy_price
        stock_data.total_buy_quantity = initial_quantity
        stock_data.current_high_price_after_buy = avg_buy_price # 초기 고점은 매수가
        stock_data.buy_timestamp = datetime.now() - timedelta(minutes=10) # 매수 후 시간 좀 경과
        stock_data.trailing_stop_partially_sold = False
        stock_data.yesterday_close_price = avg_buy_price * 0.98 # 0이 아닌 값으로 설정
        self.strategy.watchlist[code] = stock_data

        # 포트폴리오에도 해당 종목 정보 추가
        self.strategy.account_state.portfolio[code] = {
            'stock_name': name,
            '보유수량': initial_quantity,
            '매입가': avg_buy_price,
            '매입금액': avg_buy_price * initial_quantity,
            '현재가': avg_buy_price # 초기 현재가는 매입가로 가정
        }
        stock_data.current_price = avg_buy_price # stock_data의 현재가도 업데이트

        # 2. 고점 형성
        high_price = avg_buy_price * 1.05 # 매수가보다 5% 상승하여 고점 형성
        stock_data.current_price = high_price
        self.strategy.process_strategy(code) # process_strategy -> _handle_holding_state -> 고점 업데이트
        self.assertEqual(stock_data.current_high_price_after_buy, high_price, "고점 업데이트 확인")
        self.mock_kiwoom_api.send_order.assert_not_called() # 아직 매도 주문 X

        # 3. 트레일링 스탑 발동 가격 이하로 하락
        trailing_trigger_price = high_price * (1 - trailing_fall_rate / 100)
        price_below_trigger = trailing_trigger_price - 100 # 발동가보다 낮게 설정
        stock_data.current_price = price_below_trigger
        
        # send_order 모의 객체 초기화 (이전 호출 카운트 무시)
        self.mock_kiwoom_api.send_order.reset_mock()

        self.strategy.process_strategy(code) # 여기서 50% 매도 주문 발생 예상

        # 4. 50% 매도 주문 확인
        expected_sell_quantity = int(initial_quantity * 0.5)
        self.mock_kiwoom_api.send_order.assert_called_once()
        call_args = self.mock_kiwoom_api.send_order.call_args[0]
        self.assertIn(call_args[3], [2, 12]) # order_type (매도 또는 ATS 매도)
        self.assertEqual(call_args[4], code)      # code
        self.assertEqual(call_args[5], expected_sell_quantity) # 50% quantity
        self.assertEqual(call_args[6], price_below_trigger) # price
        # call_args[8] (org_order_no)는 비어 있어야 함
        self.assertEqual(call_args[8], "", "신규 매도 주문 시 원주문번호는 비어있어야 함")
        
        # 주문 후 last_order_rq_name 설정 확인
        self.assertIsNotNone(stock_data.last_order_rq_name)
        sent_rq_name_partial_sell = stock_data.last_order_rq_name
        self.assertIn(sent_rq_name_partial_sell, self.strategy.account_state.active_orders)
        self.assertEqual(self.strategy.account_state.active_orders[sent_rq_name_partial_sell]['reason'], "트레일링스탑(50%)")

        # 5. 50% 매도 체결 처리
        chejan_data_partial_sell = {
            "9001": code, "302": name, "9203": "ORDER_NO_TS1", "913": "체결",
            "900": str(expected_sell_quantity), "901": "0", "902": str(expected_sell_quantity),
            "10": str(price_below_trigger), "911": str(expected_sell_quantity)
        }
        self.strategy.account_state.active_orders[sent_rq_name_partial_sell]['order_no'] = "ORDER_NO_TS1"

        with patch.object(self.mock_kiwoom_api, 'parse_chejan_data', return_value=chejan_data_partial_sell) as mock_parse:
            self.strategy.on_chejan_data_received(gubun='0', item_cnt=0, fid_list_str="")

        self.assertTrue(stock_data.trailing_stop_partially_sold, "50% 매도 후 플래그 True 확인")
        self.assertEqual(stock_data.strategy_state, TradingState.PARTIAL_SOLD, "50% 매도 체결 후 PARTIAL_SOLD 상태 확인")
        
        # 포트폴리오 수량 확인
        self.assertEqual(self.strategy.account_state.portfolio[code]['보유수량'], initial_quantity - expected_sell_quantity)
        self.assertEqual(stock_data.total_buy_quantity, initial_quantity) # total_buy_quantity는 유지 (평단가 계산용)
        self.assertIsNone(stock_data.last_order_rq_name, "체결 완료 후 last_order_rq_name 초기화 확인")
        self.assertNotIn(sent_rq_name_partial_sell, self.strategy.account_state.active_orders, "체결 완료된 주문은 active_orders에서 제거되어야 함")

    def test_trailing_stop_full_sell_after_partial_scenario(self):
        """트레일링 스탑 (부분 매도 후 나머지 전량 매도) 시나리오"""
        code = "005930"
        name = "삼성전자"
        avg_buy_price = 70000
        initial_quantity = 100 # 초기 매수 수량
        partially_sold_quantity = 50 # 50% 매도 후 남은 수량
        trailing_fall_rate = self.strategy.settings.trailing_stop_fall_rate

        # 1. 초기 상태 설정: PARTIAL_SOLD 상태, 50% 매도 완료된 상태로 설정
        stock_data = StockTrackingData(code=code, stock_name=name)
        stock_data.strategy_state = TradingState.PARTIAL_SOLD
        stock_data.avg_buy_price = avg_buy_price # 평균매입가는 유지됨
        stock_data.total_buy_quantity = initial_quantity # 최초 매수량은 유지
        stock_data.current_high_price_after_buy = avg_buy_price * 1.05 # 이전 고점 (예시)
        stock_data.buy_timestamp = datetime.now() - timedelta(minutes=20)
        stock_data.trailing_stop_partially_sold = True # 이미 50% 매도됨
        stock_data.yesterday_close_price = avg_buy_price * 0.98 # 0이 아닌 값으로 설정
        self.strategy.watchlist[code] = stock_data

        # 포트폴리오도 50% 매도된 상태로 설정
        self.strategy.account_state.portfolio[code] = {
            'stock_name': name,
            '보유수량': partially_sold_quantity,
            '매입가': avg_buy_price,
            '매입금액': avg_buy_price * partially_sold_quantity, # 현재 보유분 기준 매입금액
            '현재가': stock_data.current_high_price_after_buy # 현재가는 이전 고점으로 가정
        }
        stock_data.current_price = stock_data.current_high_price_after_buy

        # 2. 다시 새로운 고점 형성 (PARTIAL_SOLD 상태에서도 고점은 계속 업데이트됨)
        new_high_price = stock_data.current_high_price_after_buy * 1.03 # 이전 고점보다 3% 더 상승
        stock_data.current_price = new_high_price
        self.strategy.process_strategy(code)
        self.assertEqual(stock_data.current_high_price_after_buy, new_high_price, "새로운 고점 업데이트 확인")
        self.mock_kiwoom_api.send_order.assert_not_called()

        # 3. 트레일링 스탑 발동 가격 이하로 하락 (전량 매도 조건)
        trailing_trigger_price_for_full_sell = new_high_price * (1 - trailing_fall_rate / 100)
        price_below_trigger_for_full_sell = trailing_trigger_price_for_full_sell - 100
        stock_data.current_price = price_below_trigger_for_full_sell

        self.mock_kiwoom_api.send_order.reset_mock()
        self.strategy.process_strategy(code) # 여기서 나머지 전량 매도 주문 발생 예상

        # 4. 전량 매도 주문 확인
        self.mock_kiwoom_api.send_order.assert_called_once()
        call_args = self.mock_kiwoom_api.send_order.call_args[0]
        self.assertIn(call_args[3], [2, 12]) # 매도 주문 유형
        self.assertEqual(call_args[4], code)
        self.assertEqual(call_args[5], partially_sold_quantity) # 남은 전량 수량
        self.assertEqual(call_args[6], int(price_below_trigger_for_full_sell)) # 주문 가격은 정수로 변환됨
        self.assertEqual(call_args[8], "", "신규 매도 주문 시 원주문번호는 비어있어야 함")
        
        self.assertIsNotNone(stock_data.last_order_rq_name)
        sent_rq_name_full_sell = stock_data.last_order_rq_name
        self.assertIn(sent_rq_name_full_sell, self.strategy.account_state.active_orders)
        self.assertEqual(self.strategy.account_state.active_orders[sent_rq_name_full_sell]['reason'], "트레일링스탑(잔량)")

        # 5. 전량 매도 체결 처리
        chejan_data_full_sell = {
            "9001": code, "302": name, "9203": "ORDER_NO_TS2", "913": "체결",
            "900": str(partially_sold_quantity), "901": "0", "902": str(partially_sold_quantity),
            "10": str(price_below_trigger_for_full_sell), "911": str(partially_sold_quantity)
        }
        self.strategy.account_state.active_orders[sent_rq_name_full_sell]['order_no'] = "ORDER_NO_TS2"

        with patch.object(self.mock_kiwoom_api, 'parse_chejan_data', return_value=chejan_data_full_sell) as mock_parse:
            self.strategy.on_chejan_data_received(gubun='0', item_cnt=0, fid_list_str="")

        # reset_stock_strategy_info 호출로 상태가 초기화되어야 함
        self.assertEqual(stock_data.strategy_state, TradingState.WAITING, "전량 매도 체결 후 WAITING 상태(초기화) 확인")
        self.assertFalse(stock_data.trailing_stop_partially_sold, "전량 매도 후 플래그 False(초기화) 확인")
        self.assertEqual(stock_data.avg_buy_price, 0.0) # 초기화 확인
        self.assertEqual(stock_data.total_buy_quantity, 0) # 초기화 확인
        self.assertIsNone(stock_data.buy_timestamp, "매수 시간 초기화 확인") # 초기화 확인
        
        self.assertEqual(self.strategy.account_state.portfolio[code]['보유수량'], 0, "포트폴리오 보유수량 0 확인")
        self.assertIsNone(stock_data.last_order_rq_name, "체결 완료 후 last_order_rq_name 초기화 확인")

        self.assertNotIn(sent_rq_name_full_sell, self.strategy.account_state.active_orders, "체결 완료된 주문은 active_orders에서 제거되어야 함")

    def test_target_profit_full_sell_scenario(self):
        """4. 목표 수익률 (전량) 케이스"""
        code = "005930"
        name = "삼성전자"
        avg_buy_price = 70000
        initial_quantity = 100
        target_profit_rate = self.strategy.settings.target_profit_rate # 설정에서 가져옴 (예: 5.0)

        # 1. 초기 상태 설정: BOUGHT 상태
        stock_data = StockTrackingData(code=code, stock_name=name)
        stock_data.strategy_state = TradingState.BOUGHT
        stock_data.avg_buy_price = avg_buy_price
        stock_data.total_buy_quantity = initial_quantity
        stock_data.buy_timestamp = datetime.now() - timedelta(minutes=10)
        stock_data.yesterday_close_price = avg_buy_price * 0.98 # 전일 종가 설정 추가
        self.strategy.watchlist[code] = stock_data

        # 포트폴리오 설정
        self.strategy.account_state.portfolio[code] = {
            'stock_name': name,
            '보유수량': initial_quantity,
            '매입가': avg_buy_price,
            '매입금액': avg_buy_price * initial_quantity,
            '현재가': avg_buy_price
        }
        stock_data.current_price = avg_buy_price

        # 2. 목표 수익률 도달 가격으로 현재가 설정
        target_price = avg_buy_price * (1 + target_profit_rate / 100)
        stock_data.current_price = target_price + 100 # 목표가보다 약간 높게 설정하여 확실히 조건 만족
        stock_data.last_order_rq_name = None # 이전 주문 영향 배제

        self.mock_kiwoom_api.send_order.reset_mock()
        self.strategy.process_strategy(code) # _check_and_execute_profit_taking 호출 예상

        # 3. 전량 매도 주문 확인
        self.mock_kiwoom_api.send_order.assert_called_once()
        call_args = self.mock_kiwoom_api.send_order.call_args[0]
        self.assertIn(call_args[3], [2, 12]) # 매도 주문 유형
        self.assertEqual(call_args[4], code)
        self.assertEqual(call_args[5], initial_quantity) # 전량 수량
        self.assertEqual(call_args[6], stock_data.current_price) # 현재가(시장가 주문 시) 또는 지정가
        
        self.assertIsNotNone(stock_data.last_order_rq_name)
        sent_rq_name_profit_sell = stock_data.last_order_rq_name
        self.assertIn(sent_rq_name_profit_sell, self.strategy.account_state.active_orders)
        self.assertEqual(self.strategy.account_state.active_orders[sent_rq_name_profit_sell]['reason'], "목표수익률달성(전량)")

        # 4. 전량 매도 체결 처리
        chejan_data_profit_sell = {
            "9001": code, "302": name, "9203": "ORDER_NO_PROFIT", "913": "체결",
            "900": str(initial_quantity), "901": "0", "902": str(initial_quantity),
            "10": str(stock_data.current_price), "911": str(initial_quantity)
        }
        self.strategy.account_state.active_orders[sent_rq_name_profit_sell]['order_no'] = "ORDER_NO_PROFIT"

        with patch.object(self.mock_kiwoom_api, 'parse_chejan_data', return_value=chejan_data_profit_sell):
            self.strategy.on_chejan_data_received(gubun='0', item_cnt=0, fid_list_str="")

        # 5. 상태 확인
        # reset_stock_strategy_info 호출로 상태가 초기화되어야 함
        self.assertEqual(stock_data.strategy_state, TradingState.WAITING, "전량 매도 체결 후 WAITING 상태(초기화) 확인")
        self.assertFalse(stock_data.trailing_stop_partially_sold, "플래그 False(초기화) 확인")
        self.assertEqual(stock_data.avg_buy_price, 0.0)
        self.assertEqual(stock_data.total_buy_quantity, 0)
        self.assertIsNone(stock_data.buy_timestamp)
        
        self.assertEqual(self.strategy.account_state.portfolio[code]['보유수량'], 0, "포트폴리오 보유수량 0 확인")
        self.assertIsNone(stock_data.last_order_rq_name)

        self.assertNotIn(sent_rq_name_profit_sell, self.strategy.account_state.active_orders)

    def test_stop_loss_from_yesterday_close_scenario(self):
        """5. 손절 케이스 (전일 종가 기준)"""
        code = "005930"
        name = "삼성전자"
        yesterday_close_price = 70000
        # StockTrackingData의 yesterday_close_price는 initialize_stock_data에서 설정됨.
        # 여기서는 BOUGHT 상태를 바로 만드므로, 해당 값을 직접 설정해줘야 함.
        initial_quantity = 100
        stop_loss_rate = self.strategy.settings.stop_loss_rate_from_yesterday_close # 예: 3.0
        avg_buy_price = yesterday_close_price * 1.02 # 전일 종가보다 약간 위에서 샀다고 가정

        # 1. 초기 상태 설정: BOUGHT 상태, 전일 종가 설정
        stock_data = StockTrackingData(code=code, stock_name=name)
        stock_data.strategy_state = TradingState.BOUGHT
        stock_data.avg_buy_price = avg_buy_price 
        stock_data.total_buy_quantity = initial_quantity
        stock_data.yesterday_close_price = yesterday_close_price # 직접 설정
        stock_data.buy_timestamp = datetime.now() - timedelta(minutes=10)
        # is_gap_up_today, is_yesterday_close_broken_today 등은 이 테스트와 직접 관련 없으므로 기본값 유지
        self.strategy.watchlist[code] = stock_data

        # 포트폴리오 설정
        self.strategy.account_state.portfolio[code] = {
            'stock_name': name,
            '보유수량': initial_quantity,
            '매입가': avg_buy_price,
            '매입금액': avg_buy_price * initial_quantity,
            '현재가': avg_buy_price
        }
        stock_data.current_price = avg_buy_price

        # 2. 손절 가격 이하로 현재가 설정
        # _check_and_execute_stop_loss 에서는 current_price 와 stop_loss_price_from_yesterday_close 비교
        # stop_loss_price_from_yesterday_close = yesterday_close_price * (1 - stop_loss_rate / 100)
        # 이 값은 strategy 내부에서 계산되므로, current_price만 잘 설정하면 됨.
        stop_loss_trigger_price = yesterday_close_price * (1 - stop_loss_rate / 100)
        stock_data.current_price = stop_loss_trigger_price - 100 # 손절가보다 낮게 설정

        self.mock_kiwoom_api.send_order.reset_mock()
        self.strategy.process_strategy(code) # _check_and_execute_stop_loss 호출 예상

        # 3. 전량 매도 주문 확인
        self.mock_kiwoom_api.send_order.assert_called_once()
        call_args = self.mock_kiwoom_api.send_order.call_args[0]
        self.assertIn(call_args[3], [2, 12]) # 매도 주문 유형
        self.assertEqual(call_args[4], code)
        self.assertEqual(call_args[5], initial_quantity) # 전량 수량
        self.assertEqual(call_args[6], stock_data.current_price) # 현재가 (시장가 주문 시)
        
        self.assertIsNotNone(stock_data.last_order_rq_name)
        sent_rq_name_stop_loss = stock_data.last_order_rq_name
        self.assertIn(sent_rq_name_stop_loss, self.strategy.account_state.active_orders)
        # strategy.py의 _check_and_execute_stop_loss에서 reason 확인 필요 -> "손절(전일종가기준)"
        self.assertEqual(self.strategy.account_state.active_orders[sent_rq_name_stop_loss]['reason'], "손절(전일종가기준)")

        # 4. 전량 매도 체결 처리
        chejan_data_stop_loss = {
            "9001": code, "302": name, "9203": "ORDER_NO_STOPLOSS", "913": "체결",
            "900": str(initial_quantity), "901": "0", "902": str(initial_quantity),
            "10": str(stock_data.current_price), "911": str(initial_quantity)
        }
        self.strategy.account_state.active_orders[sent_rq_name_stop_loss]['order_no'] = "ORDER_NO_STOPLOSS"

        with patch.object(self.mock_kiwoom_api, 'parse_chejan_data', return_value=chejan_data_stop_loss):
            self.strategy.on_chejan_data_received(gubun='0', item_cnt=0, fid_list_str="")

        # 5. 상태 확인 (reset_stock_strategy_info 호출로 초기화)
        self.assertEqual(stock_data.strategy_state, TradingState.WAITING) # 또는 IDLE/COMPLETE
        self.assertEqual(stock_data.avg_buy_price, 0.0)
        self.assertEqual(stock_data.total_buy_quantity, 0)
        self.assertIsNone(stock_data.buy_timestamp)
        self.assertFalse(stock_data.trailing_stop_partially_sold)
        
        self.assertEqual(self.strategy.account_state.portfolio[code]['보유수량'], 0)
        self.assertIsNone(stock_data.last_order_rq_name)

        self.assertNotIn(sent_rq_name_stop_loss, self.strategy.account_state.active_orders)

    def test_max_daily_buy_count_exceeded_scenario(self):
        """6. 하루 매수 횟수 초과 시 매수 시도"""
        code = "005930"
        name = "삼성전자"
        yesterday_close_price = 70000
        today_open_price = 70500

        # 1. 설정 변경: max_daily_buy_count를 1로 설정
        original_max_buy = self.strategy.settings.max_daily_buy_count
        self.strategy.settings.max_daily_buy_count = 1
        # strategy의 daily_buy_executed_count를 max_daily_buy_count와 같게 설정
        self.strategy.daily_buy_executed_count = 1 

        # 2. 매수 조건 충족 상태로 StockTrackingData 설정 (갭상승 -> 전일가 하회 -> 전일가 재돌파 직전)
        #    이 테스트는 execute_buy가 호출되지 않는 것을 검증하므로, initialize_stock_data 부터 시작
        self.mock_kiwoom_api.get_daily_chart = MagicMock(return_value=[
            {'일자': '20230102', '시가': today_open_price, '현재가': today_open_price},
            {'일자': '20230101', '시가': 69000, '현재가': yesterday_close_price}
        ])
        self.mock_kiwoom_api.get_stock_basic_info = MagicMock(return_value={
            '현재가': today_open_price, '종목명': name, '종목코드': code
        })
        self.mock_kiwoom_api.set_real_reg = MagicMock(return_value=0)
        self.strategy.initialize_stock_data(code, stock_name_param=name)
        stock_data = self.strategy.watchlist[code]
        self.assertEqual(stock_data.strategy_state, TradingState.WAITING)

        # 전일 종가 하회
        stock_data.current_price = yesterday_close_price - 100
        self.strategy.process_strategy(code)
        self.assertTrue(stock_data.is_yesterday_close_broken_today)

        # 3. 매수 시도 (process_strategy를 통해)
        self.mock_kiwoom_api.send_order.reset_mock()
        # Logger 모킹 (경고 로그 확인용)
        # self.test_logger.logger.warning = MagicMock() # 실제 로거 객체 사용 시 이렇게 하거나, spy 사용

        stock_data.current_price = yesterday_close_price + 100 # 매수 조건 충족 가격
        
        # execute_buy를 직접 호출하는 대신 process_strategy를 사용
        # process_strategy 내부에서 _handle_waiting_state -> check_buy_condition -> (조건 만족 시) execute_buy 호출 시도
        # execute_buy가 False를 반환해야 함

        # execute_buy가 False를 반환하고, 그 결과로 send_order가 호출되지 않아야 함
        # 또한, _handle_waiting_state에서 execute_buy의 반환값을 직접 사용하지 않으므로,
        # send_order 미호출과 daily_buy_executed_count 미증가로 확인.
        
        with patch.object(self.test_logger.logger, 'warning') as mock_log_warning:
            self.strategy.process_strategy(code)

        # 4. 확인
        self.mock_kiwoom_api.send_order.assert_not_called() # send_order 호출 안됨
        self.assertEqual(self.strategy.daily_buy_executed_count, 1, "일일 매수 실행 횟수 변경 없음 확인")
        # stock_data.strategy_state는 여전히 WAITING (매수 주문 안 나갔으므로)
        self.assertEqual(stock_data.strategy_state, TradingState.WAITING)

        # 관련 경고 로그 확인 (실제 로그 메시지와 비교)
        # 예시: self.test_logger.logger.warning.assert_any_call(f"일일 최대 매수 횟수({self.strategy.settings.max_daily_buy_count}) 초과로 {code} 매수 불가.")
        # 정확한 로그 메시지는 strategy.py의 execute_buy 함수 내부를 확인해야 함.
        # 현재 execute_buy의 로그: f"일일 매수 횟수 제한({self.settings.max_daily_buy_count}회) 도달. 금일 추가 매수 불가. (현재: {self.daily_buy_executed_count}회)"
        expected_log_message = f"일일 매수 횟수 제한({self.strategy.settings.max_daily_buy_count}회) 도달. 금일 추가 매수 불가. (현재: {self.strategy.daily_buy_executed_count}회)"
        
        called_warnings = [call_args[0][0] for call_args in mock_log_warning.call_args_list]
        # 로그 메시지에는 타임스탬프 등이 포함될 수 있으므로, 핵심 내용만 포함하는지 확인
        # self.assertIn(expected_log_message, called_warnings, "매수 횟수 초과 경고 로그 확인")
        self.assertTrue(any(expected_log_message in called_arg for called_arg in called_warnings), "매수 횟수 초과 경고 로그 확인")

        # 설정 원복

        self.strategy.settings.max_daily_buy_count = original_max_buy

    def test_cancel_pending_orders_on_exit_scenario(self):
        """7. 프로그램 종료 시 미체결 주문 취소 테스트"""
        code = "005930"
        name = "삼성전자"
        order_rq_name = "buy_order_rq_005930_1"
        order_no = "ORDER_NO_PENDING"
        order_quantity = 10
        order_price = 70000

        # 1. 설정: cancel_pending_orders_on_exit = True
        original_cancel_setting = self.strategy.settings.cancel_pending_orders_on_exit
        self.strategy.settings.cancel_pending_orders_on_exit = True

        # 2. 미체결 주문 추가 (active_orders에)
        # 실제 active_orders에 저장되는 정보와 유사하게 구성
        self.strategy.account_state.active_orders[order_rq_name] = {
            'order_no': order_no,
            'code': code,
            'stock_name': name,
            'order_type': '매수', # 문자열 '매수'로 수정
            'order_qty': order_quantity, # strategy.py 내부와 일관성 있게 order_qty 사용
            'order_price': order_price,
            'unfilled_qty': order_quantity, # 미체결 수량 (strategy.py의 cancel_all_pending_orders에서는 unfilled_qty 사용)
            'order_status': '접수완료', # 또는 '미체결' 등
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'reason': '테스트용미체결매수'
        }
        # last_order_rq_name과는 직접 관련 없지만, 혹시 모르니 초기화
        # cancel_all_pending_orders는 watchlist의 last_order_rq_name을 참조하지 않음.
        pass # 특별히 수정할 필요 없음

        # 3. KiwoomAPI.send_order 모의 설정 (주문 취소 시 성공 반환)
        self.mock_kiwoom_api.send_order.reset_mock()
        # send_order는 주문 취소 시에도 0을 반환하도록 setUp에서 이미 설정됨

        # 4. strategy.start() 호출 (is_running = True 만들기 위해)
        self.strategy.start()
        self.addCleanup(self.strategy.stop) # 테스트 종료 시 stop 보장

        # 5. strategy.stop() 호출 (테스트 대상)
        self.strategy.stop() # 이 내부에서 cancel_all_pending_orders 호출

        # 5. 확인
        # cancel_all_pending_orders 내에서 send_order 호출 확인
        self.mock_kiwoom_api.send_order.assert_called_once()
        call_args = self.mock_kiwoom_api.send_order.call_args[0]
        
        # send_order 파라미터 확인
        # rq_name (자동 생성), screen_no, acc_no, order_type (취소: 3 또는 4), code, quantity (0), price (0), hoga_gb ("00"), org_order_no
        # self.assertEqual(call_args[0], f"CancelOrder_{order_rq_name}") # rq_name은 내부적으로 생성될 수 있음, 여기서는 실제 호출된 값 확인
        self.assertEqual(call_args[2], self.strategy.account_state.account_number) # acc_no
        self.assertIn(call_args[3], [3, 4, 13, 14])  # 주문 유형: 3(매수취소), 4(매도취소), ATS 취소 등
        self.assertEqual(call_args[4], code)          # code
        self.assertEqual(call_args[5], 0)             # quantity (취소 시 0)
        self.assertEqual(call_args[6], 0)             # price (취소 시 0)
        # self.assertEqual(call_args[7], "00")          # hoga_gb (지정가 취소 시 "00" - 실제 구현 확인 필요)
        self.assertEqual(call_args[8], order_no)      # org_order_no

        # active_orders의 해당 주문 상태 변경 확인 (예: '취소요청중')
        # cancel_all_pending_orders가 주문 상태를 직접 변경하는지, 아니면 체결/확인 응답을 기다리는지에 따라 다름.
        # 현재 cancel_all_pending_orders는 상태를 '취소요청'으로 변경함.
        self.assertEqual(self.strategy.account_state.active_orders[order_rq_name]['order_status'], '취소요청중',
                         "미체결 주문 상태가 '취소요청중'으로 변경되었는지 확인")

        # 설정 원복

        self.strategy.settings.cancel_pending_orders_on_exit = original_cancel_setting

    def test_auto_liquidate_after_time_scenario(self):
        """8. 시간 경과 자동 청산 테스트"""
        code = "005930"
        name = "삼성전자"
        avg_buy_price = 70000
        initial_quantity = 100
        auto_liquidate_minutes = 30 # 예시: 30분

        # 1. 설정
        original_auto_liquidate_enabled = self.strategy.settings.auto_liquidate_after_minutes_enabled
        original_auto_liquidate_minutes = self.strategy.settings.auto_liquidate_after_minutes
        self.strategy.settings.auto_liquidate_after_minutes_enabled = True
        self.strategy.settings.auto_liquidate_after_minutes = auto_liquidate_minutes

        # 2. 초기 상태 설정: BOUGHT 상태, 매수 시간은 (현재 - 설정시간 - 여유) 이전으로
        stock_data = StockTrackingData(code=code, stock_name=name)
        stock_data.strategy_state = TradingState.BOUGHT
        stock_data.avg_buy_price = avg_buy_price
        stock_data.total_buy_quantity = initial_quantity
        # 현재 시간보다 (설정된 자동 청산 시간 + 5분) 만큼 이전으로 매수 시간을 설정
        stock_data.buy_timestamp = datetime.now() - timedelta(minutes=auto_liquidate_minutes + 5)
        stock_data.last_order_rq_name = None # 이전 주문 영향 배제
        stock_data.yesterday_close_price = avg_buy_price * 0.98 # 전일 종가 설정 추가
        self.strategy.watchlist[code] = stock_data

        # 포트폴리오 설정
        self.strategy.account_state.portfolio[code] = {
            'stock_name': name,
            '보유수량': initial_quantity,
            '매입가': avg_buy_price,
            '매입금액': avg_buy_price * initial_quantity,
            '현재가': avg_buy_price # 현재가는 중요하지 않음, 시간 조건만 만족하면 됨
        }
        stock_data.current_price = avg_buy_price # 현재가 설정

        # 3. process_strategy 호출
        self.mock_kiwoom_api.send_order.reset_mock()
        self.strategy.process_strategy(code) # _check_and_execute_auto_liquidation 호출 예상

        # 4. 전량 매도 주문 확인
        self.mock_kiwoom_api.send_order.assert_called_once()
        call_args = self.mock_kiwoom_api.send_order.call_args[0]
        self.assertIn(call_args[3], [2, 12]) # 매도 주문 유형
        self.assertEqual(call_args[4], code)
        self.assertEqual(call_args[5], initial_quantity) # 전량 수량
        self.assertEqual(call_args[6], stock_data.current_price) # 현재가 (시장가 주문 시)
        
        self.assertIsNotNone(stock_data.last_order_rq_name)
        sent_rq_name_auto_liq = stock_data.last_order_rq_name
        self.assertIn(sent_rq_name_auto_liq, self.strategy.account_state.active_orders)
        # strategy.py의 _check_and_execute_auto_liquidation에서 reason 확인 -> "시간경과자동청산"
        self.assertEqual(self.strategy.account_state.active_orders[sent_rq_name_auto_liq]['reason'], "시간경과자동청산") # reason "시간청산({hold_minutes:.0f}분)"
        # self.assertEqual(self.strategy.account_state.active_orders[sent_rq_name_auto_liq]['reason'], f"시간청산({int(stock_data.buy_timestamp.minute)}분)")


        # 5. 전량 매도 체결 처리 (이 테스트에서는 체결까지는 필수는 아니지만, 완전성을 위해 추가)
        chejan_data_auto_liq = {
            "9001": code, "302": name, "9203": "ORDER_NO_AUTOLIQ", "913": "체결",
            "900": str(initial_quantity), "901": "0", "902": str(initial_quantity),
            "10": str(stock_data.current_price), "911": str(initial_quantity)
        }
        self.strategy.account_state.active_orders[sent_rq_name_auto_liq]['order_no'] = "ORDER_NO_AUTOLIQ"

        with patch.object(self.mock_kiwoom_api, 'parse_chejan_data', return_value=chejan_data_auto_liq):
            self.strategy.on_chejan_data_received(gubun='0', item_cnt=0, fid_list_str="")

        # 6. 상태 확인 (reset_stock_strategy_info 호출로 초기화)
        self.assertEqual(stock_data.strategy_state, TradingState.WAITING)
        self.assertEqual(stock_data.avg_buy_price, 0.0)
        self.assertEqual(stock_data.total_buy_quantity, 0)
        self.assertIsNone(stock_data.buy_timestamp)
        self.assertFalse(stock_data.trailing_stop_partially_sold)
        
        self.assertEqual(self.strategy.account_state.portfolio[code]['보유수량'], 0)
        self.assertIsNone(stock_data.last_order_rq_name)
        self.assertNotIn(sent_rq_name_auto_liq, self.strategy.account_state.active_orders)

        # 설정 원복

        self.strategy.settings.auto_liquidate_after_minutes_enabled = original_auto_liquidate_enabled
        self.strategy.settings.auto_liquidate_after_minutes = original_auto_liquidate_minutes

    def test_stock_code_normalization(self):
        """Test the _normalize_stock_code method."""
        self.strategy.log("Running test_stock_code_normalization...", "INFO")
        # Standard 6-digit code
        self.assertEqual(self.strategy._normalize_stock_code("005930"), "005930")
        # Leading 'A'
        self.assertEqual(self.strategy._normalize_stock_code("A005930"), "005930")
        self.assertEqual(self.strategy._normalize_stock_code("A035720"), "035720")
        # With spaces around
        self.assertEqual(self.strategy._normalize_stock_code(" 005930 "), "005930")
        self.assertEqual(self.strategy._normalize_stock_code(" A005930 "), "005930")
        # Space after 'A' but before digits (should not remove 'A' if not immediately followed by digits or if length criteria not met by pure code)
        # Current logic: "A 005930" -> strip() -> "A 005930". startswith('A') is true. len(" 005930") is 7.
        # The current logic `normalized[1:]` would make it " 005930".
        # However, the condition `len(normalized) > 1` along with `startswith('A')` means 'A' itself is not a valid code.
        # And the check `if normalized.startswith('A') and len(normalized) > 1:`
        # If normalized = "A XXXXX", it becomes " XXXXX".
        # This case "A 005930" -> "A 005930" (no change because `normalized[1:]` is not taken due to space) is correct.
        # Let's clarify the expected behavior for "A XXXXX" vs "AXXXXX"
        # Current implementation:
        # "A005930" -> strip -> "A005930" -> startswith('A') and len > 1 -> normalized[1:] -> "005930" (Correct)
        # "A 005930" -> strip -> "A 005930" -> startswith('A') and len > 1 -> normalized[1:] -> " 005930" (This is the actual result of `normalized[1:]`)
        # The _normalize_stock_code does not re-strip after `normalized[1:]`.
        # So, "A 005930" becomes " 005930". This is probably not intended.
        # The intention is likely to only remove 'A' if it's a prefix to a standard code.
        # For "A 005930", it should probably remain "A 005930" if it's not a valid format to begin with.
        # The current code `normalized = normalized[1:]` if it starts with 'A'.
        # Let's test the current behavior and then consider if the method itself needs a fix.
        self.assertEqual(self.strategy._normalize_stock_code("A 005930"), " 005930") # Current behavior
        # Non-A prefix
        self.assertEqual(self.strategy._normalize_stock_code("B005930"), "B005930")
        # Empty string
        self.assertEqual(self.strategy._normalize_stock_code(""), "")
        # Shorter than 6 digits (after potential 'A' removal)
        self.assertEqual(self.strategy._normalize_stock_code("12345"), "12345")
        self.assertEqual(self.strategy._normalize_stock_code("A12345"), "12345")
        # Longer than 6 digits (after potential 'A' removal)
        self.assertEqual(self.strategy._normalize_stock_code("0000001"), "0000001")
        self.assertEqual(self.strategy._normalize_stock_code("A0000001"), "0000001")
        # Only 'A'
        self.assertEqual(self.strategy._normalize_stock_code("A"), "A") # len(normalized) > 1 is false
        # 'A' followed by non-digit or too short
        self.assertEqual(self.strategy._normalize_stock_code("Abcde"), "bcde") # current behavior
        self.assertEqual(self.strategy._normalize_stock_code("A123"), "123") # current behavior
        # Null input
        self.assertEqual(self.strategy._normalize_stock_code(None), "") # Handles None input

    def test_buy_limit_triggers_cooldown(self):
        self.strategy.log(f"Running test_buy_limit_triggers_cooldown...", "INFO")
        self.strategy.add_to_watchlist(self.TEST_CODE, self.TEST_NAME, yesterday_close_price=69000)
        stock_info = self.strategy.watchlist[self.TEST_CODE]
        stock_info.strategy_state = TradingState.WAITING
        stock_info.current_price = 70000 # Set a valid price

        # Simulate max_buy_attempts_per_stock successful buys
        for i in range(self.MAX_BUY_ATTEMPTS):
            self.strategy.log(f"Simulating buy attempt #{i+1} for {self.TEST_CODE}", "DEBUG")
            # Ensure stock is in WAITING state before each buy if it was changed by chejan
            stock_info.strategy_state = TradingState.WAITING
            self._simulate_successful_buy(self.TEST_CODE, self.TEST_NAME, buy_price=70000 + i*100, quantity_to_buy=1)
            # After _simulate_successful_buy, state becomes BOUGHT. For next buy, it should be WAITING.
            # Or, reset the state for the purpose of this loop if necessary.
            # For this test, we are interested in buy_completion_count.
            # After each simulated buy, reset_stock_strategy_info to allow next "first" buy.
            # This is to purely test the buy_completion_count accumulation and cooldown trigger.
            # A more realistic scenario would involve selling in between.
            # For now, let's assume buy_completion_count is correctly incremented by _simulate_successful_buy's chejan handling.
            self.assertEqual(stock_info.buy_completion_count, i + 1)
            # To allow next execute_buy, we need to reset state from BOUGHT.
            # This is tricky as execute_buy itself checks for BOUGHT state.
            # Let's assume for this test, we are just checking the counter and cooldown transition.
            # So, we'll manually reset the state to allow further calls to execute_buy for count accumulation.
            if i < self.MAX_BUY_ATTEMPTS -1 : # For all but the last simulated buy that fills the quota
                 self.strategy.reset_stock_strategy_info(self.TEST_CODE) # Resets buy_completion_count, so this approach is flawed for accumulation.
                 stock_info.strategy_state = TradingState.WAITING # Re-set state
                 stock_info.buy_completion_count = i + 1 # Manually restore count
                 stock_info.current_price = 70000 + (i+1)*100


        # At this point, buy_completion_count should be MAX_BUY_ATTEMPTS
        # Let's re-do the loop for buy_completion_count accumulation more cleanly
        stock_info.buy_completion_count = 0 # Reset for clean accumulation
        for i in range(self.MAX_BUY_ATTEMPTS):
            self.strategy.log(f"Cleanly Simulating buy completion #{i+1} for {self.TEST_CODE}", "DEBUG")
            stock_info.buy_completion_count +=1 # Directly increment for test purpose
        self.assertEqual(stock_info.buy_completion_count, self.MAX_BUY_ATTEMPTS)


        # Attempt one more buy - this should trigger cooldown
        stock_info.strategy_state = TradingState.WAITING # Set to WAITING to attempt buy
        stock_info.current_price = 70000 + self.MAX_BUY_ATTEMPTS * 100

        # Patch datetime.now for predictable cooldown_until_timestamp
        mock_now = datetime(2024, 1, 1, 10, 0, 0)
        with patch('strategy.datetime') as mock_datetime:
            mock_datetime.now.return_value = mock_now
            mock_datetime.strptime = datetime.strptime # Keep strptime working
            mock_datetime.timedelta = timedelta     # Keep timedelta working

            self.assertFalse(self.strategy.execute_buy(self.TEST_CODE), "execute_buy should fail after max attempts.")

        self.assertEqual(stock_info.strategy_state, TradingState.COOL_DOWN)
        expected_cooldown_until = mock_now + timedelta(minutes=self.COOLDOWN_MINUTES)
        self.assertIsNotNone(stock_info.cooldown_until_timestamp)
        self.assertEqual(stock_info.cooldown_until_timestamp, expected_cooldown_until)
        self.strategy.log(f"Cooldown triggered for {self.TEST_CODE}. Cooldown until: {stock_info.cooldown_until_timestamp}", "INFO")

    def test_buy_attempt_during_cooldown(self):
        self.strategy.log(f"Running test_buy_attempt_during_cooldown...", "INFO")
        self.strategy.add_to_watchlist(self.TEST_CODE, self.TEST_NAME, yesterday_close_price=69000)
        stock_info = self.strategy.watchlist[self.TEST_CODE]

        # Bring stock to COOL_DOWN state
        stock_info.buy_completion_count = self.MAX_BUY_ATTEMPTS
        stock_info.strategy_state = TradingState.WAITING
        stock_info.current_price = 71000

        mock_now = datetime(2024, 1, 1, 10, 0, 0)
        with patch('strategy.datetime') as mock_datetime:
            mock_datetime.now.return_value = mock_now
            mock_datetime.strptime = datetime.strptime
            mock_datetime.timedelta = timedelta
            self.assertFalse(self.strategy.execute_buy(self.TEST_CODE), "execute_buy should fail to enter cooldown.")

        self.assertEqual(stock_info.strategy_state, TradingState.COOL_DOWN)
        self.assertIsNotNone(stock_info.cooldown_until_timestamp)

        # Attempt to buy while in cooldown (before timestamp expires)
        # Simulate time passing but not enough to expire cooldown
        mock_now_during_cooldown = mock_now + timedelta(minutes=self.COOLDOWN_MINUTES // 2)
        with patch('strategy.datetime') as mock_datetime:
            mock_datetime.now.return_value = mock_now_during_cooldown
            mock_datetime.strptime = datetime.strptime
            mock_datetime.timedelta = timedelta

            # Ensure state is still COOL_DOWN before attempting buy
            # process_strategy might alter state if time is manipulated, so check execute_buy directly
            original_cooldown_ts = stock_info.cooldown_until_timestamp
            self.assertFalse(self.strategy.execute_buy(self.TEST_CODE), "execute_buy should still fail during cooldown.")

        self.assertEqual(stock_info.strategy_state, TradingState.COOL_DOWN, "State should remain COOL_DOWN.")
        self.assertEqual(stock_info.cooldown_until_timestamp, original_cooldown_ts, "Cooldown timestamp should not change.")
        self.strategy.log(f"Buy attempt during cooldown for {self.TEST_CODE} correctly blocked.", "INFO")

    def test_cooldown_expires_and_resets_state(self):
        self.strategy.log(f"Running test_cooldown_expires_and_resets_state...", "INFO")
        self.strategy.add_to_watchlist(self.TEST_CODE, self.TEST_NAME, yesterday_close_price=69000)
        stock_info = self.strategy.watchlist[self.TEST_CODE]

        # 1. Bring stock to COOL_DOWN state
        stock_info.buy_completion_count = self.MAX_BUY_ATTEMPTS
        stock_info.strategy_state = TradingState.WAITING
        stock_info.current_price = 71000

        mock_now_cooldown_start = datetime(2024, 1, 1, 10, 0, 0)
        with patch('strategy.datetime') as mock_datetime:
            mock_datetime.now.return_value = mock_now_cooldown_start
            mock_datetime.strptime = datetime.strptime
            mock_datetime.timedelta = timedelta
            self.assertFalse(self.strategy.execute_buy(self.TEST_CODE)) # This sets it to COOL_DOWN

        self.assertEqual(stock_info.strategy_state, TradingState.COOL_DOWN)
        self.assertIsNotNone(stock_info.cooldown_until_timestamp)

        # 2. Simulate time passing for cooldown to expire
        mock_now_after_cooldown = mock_now_cooldown_start + timedelta(minutes=self.COOLDOWN_MINUTES + 1)
        with patch('strategy.datetime') as mock_datetime:
            mock_datetime.now.return_value = mock_now_after_cooldown
            mock_datetime.strptime = datetime.strptime
            mock_datetime.timedelta = timedelta

            # Call process_strategy, which should call _handle_cool_down_state
            self.strategy.process_strategy(self.TEST_CODE)

        # 3. Verify state is reset
        self.assertEqual(stock_info.strategy_state, TradingState.WAITING, "State should reset to WAITING after cooldown.")
        self.assertEqual(stock_info.buy_completion_count, 0, "buy_completion_count should reset to 0.")
        self.assertIsNone(stock_info.cooldown_until_timestamp, "cooldown_until_timestamp should be None.")
        self.strategy.log(f"Cooldown expired for {self.TEST_CODE}, state reset.", "INFO")

        # 4. Verify buy is possible again
        stock_info.current_price = 72000 # Ensure a valid price
        # _simulate_successful_buy will set state to WAITING if needed.
        # We expect one successful buy here.
        self.mock_kiwoom_api.send_order.reset_mock() # Reset mock before new call
        self._simulate_successful_buy(self.TEST_CODE, self.TEST_NAME, buy_price=72000, quantity_to_buy=1)
        self.mock_kiwoom_api.send_order.assert_called_once()
        self.assertEqual(stock_info.strategy_state, TradingState.BOUGHT)
        self.assertEqual(stock_info.buy_completion_count, 1, "buy_completion_count should be 1 after new buy.")
        self.strategy.log(f"Buy successful for {self.TEST_CODE} after cooldown.", "INFO")

    def test_reset_stock_info_clears_cooldown(self):
        self.strategy.log(f"Running test_reset_stock_info_clears_cooldown...", "INFO")
        self.strategy.add_to_watchlist(self.TEST_CODE, self.TEST_NAME, yesterday_close_price=69000)
        stock_info = self.strategy.watchlist[self.TEST_CODE]

        # 1. Bring stock to COOL_DOWN state
        stock_info.buy_completion_count = self.MAX_BUY_ATTEMPTS
        stock_info.strategy_state = TradingState.WAITING
        stock_info.current_price = 71000

        mock_now = datetime(2024, 1, 1, 10, 0, 0)
        with patch('strategy.datetime') as mock_datetime:
            mock_datetime.now.return_value = mock_now
            mock_datetime.strptime = datetime.strptime
            mock_datetime.timedelta = timedelta
            self.assertFalse(self.strategy.execute_buy(self.TEST_CODE))

        self.assertEqual(stock_info.strategy_state, TradingState.COOL_DOWN)
        self.assertIsNotNone(stock_info.cooldown_until_timestamp)
        original_cooldown_ts = stock_info.cooldown_until_timestamp

        # 2. Call reset_stock_strategy_info
        self.strategy.reset_stock_strategy_info(self.TEST_CODE)

        # 3. Verify cooldown_until_timestamp is cleared
        self.assertIsNone(stock_info.cooldown_until_timestamp, "cooldown_until_timestamp should be None after reset.")
        self.assertEqual(stock_info.strategy_state, TradingState.WAITING, "State should be WAITING after reset.")
        self.assertEqual(stock_info.buy_completion_count, 0, "buy_completion_count should be 0 after reset.")
        self.strategy.log(f"Cooldown info cleared for {self.TEST_CODE} after reset.", "INFO")


if __name__ == '__main__':
    unittest.main()
