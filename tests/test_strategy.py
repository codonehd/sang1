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

# Mock KiwoomAPI 클래스 (QObject 상속 제거)
class MockKiwoomAPI: # (QObject) 제거
    # real_data_updated = pyqtSignal(str, str, dict) # 시그널 제거
    # chejan_data_received = pyqtSignal(str, dict) # 시그널 제거
    # tr_data_received = pyqtSignal(str, dict) # 시그널 제거

    def __init__(self, logger=None, screen_manager=None): # screen_manager 인자 추가
        super().__init__()
        self.logger = logger if logger else Logger(log_level=logging.DEBUG) # 기본 로거 레벨 변경
        self.screen_manager = screen_manager # ScreenManager 인스턴스 저장
        self.account_number = "1234567890"
        self.connected = True
        self.tr_data_cache: Dict[str, Dict[str, Any]] = {} # 타입 명시
        self.current_input_values: Dict[str, str] = {} # 타입 명시, set_input_value에서 사용
        self.strategy_instance = None # strategy_instance 초기화

    # KiwoomAPI의 메서드들은 일단 유지 (시그널만 제거)
    def subscribe_real_data(self, screen_no, code, real_type_name):
        self.logger.info(f"Mock Kiwoom Subscribe: Screen({screen_no}), Code({code}), Type({real_type_name})")

    def unsubscribe_real_data(self, screen_no, code=None):
        self.logger.info(f"Mock Kiwoom Unsubscribe: Screen({screen_no}), Code({code if code else 'ALL'})")
    
    def get_stock_basic_info(self, code: str, market_context: str = None): # KiwoomAPI와 시그니처 일치
        self.logger.info(f"Mock Kiwoom TR (opt10001) 요청: {code}, MarketCtx: {market_context}")
        if code == "005930":
            return {'현재가': 70000, '종목명': '삼성전자', '종목코드': code} # '종목코드' 추가
        elif code == "000660":
            return {'현재가': 100000, '종목명': 'SK하이닉스', '종목코드': code}
        return None

    def get_daily_chart(self, code: str, *, date_to: str = "", date_from: str = "", market_context: str = None) -> List[Dict[str, Any]]: # KiwoomAPI와 시그니처 일치, 반환 타입 명시
        self.logger.info(f"Mock Kiwoom TR (opt10081) 요청: {code}, DateTo: {date_to}, MarketCtx: {market_context}")
        if code == "005930":
            return [{'일자': '20230102', '시가': 70500, '현재가': 70000}, {'일자': '20230101', '시가': 69000, '현재가': 69500}]
        elif code == "000660":
             return [{'일자': '20230102', '시가': 101000, '현재가': 100000}, {'일자': '20230101', '시가': 99000, '현재가': 99500}]
        return []

    def send_order(self, rq_name, screen_no, acc_no, order_type, code, quantity, price, hoga_gb, org_order_no=""):
        self.logger.info(f"Mock Kiwoom 주문: {rq_name}, 유형({order_type}), 종목({code}), 수량({quantity}), 가격({price if price else '시장가'}), 화면({screen_no})")
        return 0 

    def get_login_info(self, tag):
        if tag == "ACCNO":
            return self.account_number + ";" 
        return "test_user"

    def get_connect_state(self):
        return 1 if self.connected else 0

    def set_input_value(self, item_name, value):
        self.logger.debug(f"SetInputValue: {item_name} = {value}")
        self.current_input_values[item_name] = str(value) 

    def comm_rq_data(self, rq_name: str, tr_code: str, prev_next: int, screen_no: str, input_values_override: Optional[Dict[str, str]] = None, market_context: Optional[str] = None): # KiwoomAPI와 시그니처 일치
        self.logger.debug(f"CommRqData: RQName({rq_name}), TRCode({tr_code}), PrevNext({prev_next}), ScreenNo({screen_no}), InputsOverride({input_values_override}), MarketCtx({market_context})")
        
        effective_inputs = self.current_input_values.copy()
        if input_values_override:
            effective_inputs.update(input_values_override)

        parsed_tr_data_for_cache: Dict[str, Any] = {'tr_code': tr_code, 'single_data': {}, 'multi_data': [], 'status': 'pending_response', 'rq_name': rq_name, 'screen_no': screen_no, 'prev_next_for_rq': str(prev_next)} # prev_next_for_rq 추가

        if tr_code == "opt10001":
            code_input = effective_inputs.get("종목코드")
            stock_info = self.get_stock_basic_info(code_input) 
            if stock_info:
                parsed_tr_data_for_cache['single_data'] = stock_info
                parsed_tr_data_for_cache['status'] = 'completed'
        elif tr_code == "opt10081":
            code_input = effective_inputs.get("종목코드")
            daily_data = self.get_daily_chart(code_input) 
            # daily_data가 빈 리스트일 수 있지만, 요청 자체는 완료된 것으로 간주
            parsed_tr_data_for_cache['multi_data'] = daily_data
            parsed_tr_data_for_cache['status'] = 'completed' 
        elif tr_code == "opw00001": 
             parsed_tr_data_for_cache['single_data'] = {'예수금': 5000000, '주문가능금액': 5000000}
             parsed_tr_data_for_cache['status'] = 'completed'
        elif tr_code == "opw00018": 
             parsed_tr_data_for_cache['single_data'] = {'총매입금액': 0, '총평가금액': 0}
             parsed_tr_data_for_cache['multi_data'] = [] 
             parsed_tr_data_for_cache['status'] = 'completed'
        
        self.tr_data_cache[rq_name] = parsed_tr_data_for_cache
        self.current_input_values.clear() 

        if self.strategy_instance and parsed_tr_data_for_cache['status'] == 'completed':
            if hasattr(self.strategy_instance, 'on_tr_data_received'):
                 self.strategy_instance.on_tr_data_received(rq_name, tr_code, parsed_tr_data_for_cache.copy())
            
            if tr_code == "opt10081" and hasattr(self.strategy_instance, 'on_daily_chart_data_ready'):
                code_input = effective_inputs.get("종목코드")
                if code_input: # None 체크
                    self.strategy_instance.on_daily_chart_data_ready(rq_name, code_input, parsed_tr_data_for_cache['multi_data'][:])
        return 0 

    def get_comm_data(self, tr_code, rq_name, index, item_name):
        cached_data = self.tr_data_cache.get(rq_name, {})
        data_source = None
        if 'multi_data' in cached_data and index < len(cached_data['multi_data']):
            data_source = cached_data['multi_data'][index]
        elif 'single_data' in cached_data and index == 0:
            data_source = cached_data['single_data']
        return str(data_source.get(item_name, "")) if data_source else ""

    def get_repeat_cnt(self, tr_code, rq_name):
        cached_data = self.tr_data_cache.get(rq_name, {})
        return len(cached_data.get('multi_data', []))

    def set_real_reg(self, screen_no: str, code_list_str: str, fid_list_str: str, opt_type: str): # KiwoomAPI와 시그니처 일치
        self.logger.info(f"SetRealReg: Screen({screen_no}), Codes({code_list_str}), FIDs({fid_list_str}), Type({opt_type})")
        return 0 

    def disconnect_real_data(self, screen_no: str): # KiwoomAPI와 시그니처 일치
        self.logger.info(f"DisconnectRealData: Screen({screen_no})")

    def get_code_market_info(self, full_code_str: str): 
        if full_code_str.endswith('_NX'):
            return full_code_str[:-3], 'NXT'
        return full_code_str, 'KRX' 

    def parse_chejan_data(self, fid_list_str: str) -> dict: 
        parsed = {}
        if fid_list_str:
            fids = fid_list_str.split(';')
            for i, fid_str in enumerate(fids):
                 if fid_str: # 빈 FID 문자열 방지
                    parsed[fid_str] = f"value_for_fid_{fid_str}" 
        return parsed
    
    def set_strategy_instance(self, strategy_instance):
        self.strategy_instance = strategy_instance


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
        self.assertEqual(self.strategy.account_state.active_orders[sent_rq_name_auto_liq]['reason'], "시간경과자동청산")

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

if __name__ == '__main__':
    unittest.main()
