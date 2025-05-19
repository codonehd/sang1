import unittest
from unittest.mock import MagicMock, patch
import sys
import os
import logging

# 테스트 대상 모듈을 import하기 위해 프로젝트 루트 경로를 sys.path에 추가
# 이 경로는 실제 프로젝트 구조에 맞게 조정해야 할 수 있습니다.
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtWidgets import QApplication # QApplication 임포트 추가
from strategy import TradingStrategy
from config import ConfigManager
from logger import Logger # 실제 Logger 또는 MockLogger 사용 고려
# from database import Database # 실제 Database 또는 MockDatabase 사용 고려

# Mock KiwoomAPI 클래스 (strategy.py의 테스트 코드에서 가져옴)
class MockKiwoomAPI(QObject):
    real_data_updated = pyqtSignal(str, str, dict)
    chejan_data_received = pyqtSignal(str, dict)
    tr_data_received = pyqtSignal(str, dict)

    def __init__(self, logger=None):
        super().__init__()
        self.logger = logger if logger else Logger(log_file="mock_kiwoom_test_log.txt")
        self.account_number = "1234567890"
        self.connected = True # 테스트를 위해 기본적으로 연결된 상태로 설정
        self.tr_data_cache = {}

    def subscribe_real_data(self, screen_no, code, real_type_name):
        self.logger.info(f"Mock Kiwoom Subscribe: Screen({screen_no}), Code({code}), Type({real_type_name})")

    def unsubscribe_real_data(self, screen_no, code=None):
        self.logger.info(f"Mock Kiwoom Unsubscribe: Screen({screen_no}), Code({code if code else 'ALL'})")
    
    def get_stock_basic_info(self, code):
        self.logger.info(f"Mock Kiwoom TR (opt10001) 요청: {code}")
        # 테스트 케이스에 따라 반환값 변경 가능
        if code == "005930":
            return {'현재가': 70000, '종목명': '삼성전자'}
        elif code == "000660":
            return {'현재가': 100000, '종목명': 'SK하이닉스'}
        return None

    def get_daily_chart(self, code, date_to="", date_from="", prev_next='0', screen_no="0101"):
        self.logger.info(f"Mock Kiwoom TR (opt10081) 요청: {code}")
        # 테스트 케이스에 따라 반환값 변경 가능
        if code == "005930":
            return ([{'일자': '20230102', '시가': 70500, '종가': 70000}, {'일자': '20230101', '시가': 69000, '종가': 69500}], False)
        elif code == "000660":
             return ([{'일자': '20230102', '시가': 101000, '종가': 100000}, {'일자': '20230101', '시가': 99000, '종가': 99500}], False)
        return [], False

    def send_order(self, rq_name, screen_no, acc_no, order_type, code, quantity, price, hoga_gb, org_order_no=""):
        self.logger.info(f"Mock Kiwoom 주문: {rq_name}, 유형({order_type}), 종목({code}), 수량({quantity}), 가격({price if price else '시장가'})")
        return 0 # 성공으로 가정

    def get_login_info(self, tag):
        if tag == "ACCNO":
            return self.account_number + ";" # 실제 API처럼 세미콜론 포함
        return "test_user"

    def get_connect_state(self):
        return 1 if self.connected else 0

    def set_input_value(self, item_name, value):
        self.logger.debug(f"SetInputValue: {item_name} = {value}")

    def comm_rq_data(self, rq_name, tr_code, prev_next, screen_no):
        self.logger.debug(f"CommRqData: {rq_name}, {tr_code}, {prev_next}, {screen_no}")
        mock_response_data = {}
        if hasattr(self, 'current_input_values'):
            if tr_code == "opt10001":
                code_input = self.current_input_values.get("종목코드")
                stock_info = self.get_stock_basic_info(code_input)
                if stock_info:
                    mock_response_data = {'tr_code': tr_code, 'single_data': stock_info, 'multi_data': []}
            elif tr_code == "opt10081":
                code_input = self.current_input_values.get("종목코드")
                daily_data, _ = self.get_daily_chart(code_input)
                if daily_data:
                    mock_response_data = {'tr_code': tr_code, 'single_data': {}, 'multi_data': daily_data}
        
        self.tr_data_cache[rq_name] = mock_response_data
        
        if hasattr(self, 'tr_event_loop') and self.tr_event_loop is not None:
            if self.tr_event_loop.isRunning():
                 self.tr_event_loop.exit()
        return 0

    def get_comm_data(self, tr_code, rq_name, index, item_name):
        cached_data = self.tr_data_cache.get(rq_name, {})
        if 'multi_data' in cached_data and index < len(cached_data['multi_data']):
            return str(cached_data['multi_data'][index].get(item_name, ""))
        elif 'single_data' in cached_data and index == 0:
            return str(cached_data['single_data'].get(item_name, ""))
        return ""

    def get_repeat_cnt(self, tr_code, rq_name):
        cached_data = self.tr_data_cache.get(rq_name, {})
        if 'multi_data' in cached_data:
            return len(cached_data['multi_data'])
        return 0

class MockConfigManager:
    def __init__(self):
        self.settings = {
            "매수금액": 1000000,
            "익절_수익률": 5.0,
            "익절_매도비율": 50,
            "트레일링_하락률": 2.0,
            "손절_손실률": 3.0,
            "실시간화면번호_관심": "2001",
            "주문화면번호": "1001",
            "화면번호_예수금조회": "0301",
            "화면번호_잔고조회": "0302",
        }
    def get(self, key, default=None):
        return self.settings.get(key, default)

class MockDB:
    def __init__(self):
        self.watchlist = []
        self.trades = []

    def add_watchlist_item(self, code, name):
        self.watchlist.append({'code': code, 'name': name})
        return True

    def remove_watchlist_item(self, code):
        self.watchlist = [item for item in self.watchlist if item['code'] != code]
        return True

    def get_watchlist(self):
        return self.watchlist

    def add_trade(self, code, name, trade_type, quantity, price, trade_reason=None):
        self.trades.append({
            'code': code, 'name': name, 'trade_type': trade_type,
            'quantity': quantity, 'price': price, 'trade_reason': trade_reason
        })
        return True

    def get_trades(self, code=None, trade_type=None, start_date=None, end_date=None):
        return self.trades

class TestTradingStrategy(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """테스트 클래스 시작 시 한 번 호출됩니다."""
        cls.app = QApplication.instance() or QApplication(sys.argv)
        # 테스트 중 실제 파일에 로그가 기록되지 않도록 핸들러를 비우거나 NullHandler 사용
        # 또는 테스트용 Logger를 별도로 구성할 수 있습니다.
        # 여기서는 Logger 인스턴스 생성 시 파일명을 지정하여 테스트 로그 파일을 사용하고,
        # 테스트 완료 후 해당 파일은 삭제하거나 .gitignore에 추가하는 것을 권장합니다.
        cls.test_logger = Logger(log_file="logs/test_strategy_unittest_log.txt", log_level=logging.DEBUG) # DEBUG 레벨로 설정

    @classmethod
    def tearDownClass(cls):
        """테스트 클래스 종료 시 한 번 호출됩니다."""
        # cls.app.quit() # 필요에 따라 이벤트 루프 종료
        pass

    def setUp(self):
        """각 테스트 메소드 실행 전에 호출됩니다."""
        self.mock_kiwoom_api = MockKiwoomAPI()
        self.mock_config = MockConfigManager()
        self.test_logger.logger.handlers = [] # 핸들러 초기화 (중복 로깅 방지)
        stream_handler = logging.StreamHandler(sys.stdout) # 콘솔 출력용 핸들러
        stream_handler.setLevel(logging.DEBUG) # 콘솔 핸들러도 DEBUG 레벨
        formatter = logging.Formatter('[%(levelname)s] %(asctime)s - %(message)s')
        stream_handler.setFormatter(formatter)
        self.test_logger.logger.addHandler(stream_handler)
        self.test_logger.logger.propagate = False # 상위 로거로 전파 방지
        self.mock_db = MockDB()
        
        self.strategy = TradingStrategy(
            kiwoom_api=self.mock_kiwoom_api,
            config=self.mock_config,
            logger=self.test_logger,
            db=self.mock_db
        )
        self.strategy.start() # 전략 실행 상태로 변경

        # send_order mock은 각 테스트 메소드에서 구체적으로 설정
        self.mock_kiwoom_api.send_order = MagicMock(name="send_order_mock")

        def side_effect_set_input_value(item_name, value):
            if not hasattr(self.mock_kiwoom_api, 'current_input_values'):
                self.mock_kiwoom_api.current_input_values = {}
            self.mock_kiwoom_api.current_input_values[item_name] = value

        self.mock_kiwoom_api.set_input_value = MagicMock(side_effect=side_effect_set_input_value)

    def test_initialize_stock_data_success(self):
        """관심종목 데이터 초기화 성공 케이스"""
        code = "005930"
        name = "삼성전자"
        
        self.mock_kiwoom_api.get_stock_basic_info = MagicMock(return_value={
            '현재가': 70000, 
            '종목명': name
        })
        self.mock_kiwoom_api.get_daily_chart = MagicMock(return_value=(
            [
                {'일자': '20230102', '시가': 70500, '종가': 70000}, 
                {'일자': '20230101', '시가': 69000, '종가': 69500}  
            ], 
            False
        ))
        self.mock_kiwoom_api.subscribe_real_data = MagicMock()

        result = self.strategy.initialize_stock_data(code, name)

        self.assertTrue(result)
        self.assertIn(code, self.strategy.watchlist)
        
        stock_data = self.strategy.watchlist[code]
        self.assertEqual(stock_data['name'], name)
        self.assertEqual(stock_data['current_price'], 70000)
        self.assertEqual(stock_data['yesterday_close'], 69500)
        self.assertEqual(stock_data['today_open'], 70500)
        self.assertFalse(stock_data['crossed_yesterday_close'])
        self.assertFalse(stock_data['금일매수완료'])
        
        # check_initial_conditions에 의해 below_yesterday_close 상태가 결정됨
        # 이 예제 데이터에서는 today_open(70500) > yesterday_close(69500) 이고
        # current_price(70000) > yesterday_close(69500) 이므로 below_yesterday_close는 False여야 함.
        # 만약 current_price < yesterday_close 시나리오를 테스트하려면 mock_kiwoom_api.get_stock_basic_info 반환값 조정 필요.
        # 여기서는 현재 가격(70000)이 전일 종가(69500)보다 크므로 below_yesterday_close는 False가 되어야 함.
        self.assertFalse(stock_data['below_yesterday_close']) 

        self.assertEqual(self.strategy.strategy_state[code], TradingStrategy.WAITING)
        
        self.mock_kiwoom_api.get_stock_basic_info.assert_called_once_with(code)
        self.mock_kiwoom_api.get_daily_chart.assert_called_once_with(code)
        self.mock_kiwoom_api.subscribe_real_data.assert_called_once_with(
            self.mock_config.get("실시간화면번호_관심"),
            code, 
            "주식시세"
        )

    def test_initialize_stock_data_success_goes_below_yesterday_close(self):
        """관심종목 초기화 성공 & 전일 종가 하회 조건 만족 케이스"""
        code = "005930"
        name = "삼성전자"
        
        # 현재가가 전일 종가보다 낮은 상황을 모킹
        self.mock_kiwoom_api.get_stock_basic_info = MagicMock(return_value={
            '현재가': 69000, # 전일 종가보다 낮음
            '종목명': name
        })
        self.mock_kiwoom_api.get_daily_chart = MagicMock(return_value=(
            [
                {'일자': '20230102', '시가': 70500, '종가': 70000}, # 당일 데이터 (시가, 현재가와 무관하게 설정)
                {'일자': '20230101', '시가': 68000, '종가': 69500}  # 전일 데이터 (종가: 69500)
            ], 
            False
        ))
        self.mock_kiwoom_api.subscribe_real_data = MagicMock()

        result = self.strategy.initialize_stock_data(code, name)
        self.assertTrue(result)
        self.assertIn(code, self.strategy.watchlist)
        stock_data = self.strategy.watchlist[code]

        # 조건: 당일 시가(70500) > 전일 종가(69500) AND 현재가(69000) < 전일 종가(69500)
        self.assertTrue(stock_data['today_open'] > stock_data['yesterday_close'])
        self.assertTrue(stock_data['current_price'] < stock_data['yesterday_close'])
        self.assertTrue(stock_data['below_yesterday_close'])

    def test_initialize_stock_data_fail_basic_info(self):
        """관심종목 초기화 실패 케이스 - 기본 정보 조회 실패"""
        code = "999999"
        name = "테스트실패종목"

        self.mock_kiwoom_api.get_stock_basic_info = MagicMock(return_value=None)
        self.mock_kiwoom_api.get_daily_chart = MagicMock()
        self.mock_kiwoom_api.subscribe_real_data = MagicMock()

        result = self.strategy.initialize_stock_data(code, name)

        self.assertFalse(result)
        self.assertNotIn(code, self.strategy.watchlist)
        self.mock_kiwoom_api.get_stock_basic_info.assert_called_once_with(code)
        self.mock_kiwoom_api.get_daily_chart.assert_not_called()
        self.mock_kiwoom_api.subscribe_real_data.assert_not_called()

    def test_initialize_stock_data_fail_daily_chart(self):
        """관심종목 초기화 실패 케이스 - 일봉 데이터 조회 실패"""
        code = "005930"
        name = "삼성전자"

        self.mock_kiwoom_api.get_stock_basic_info = MagicMock(return_value={
            '현재가': 70000, 
            '종목명': name
        })
        self.mock_kiwoom_api.get_daily_chart = MagicMock(return_value=([], False))
        self.mock_kiwoom_api.subscribe_real_data = MagicMock()
        
        result = self.strategy.initialize_stock_data(code, name)

        self.assertFalse(result)
        self.assertNotIn(code, self.strategy.watchlist)
        self.mock_kiwoom_api.get_stock_basic_info.assert_called_once_with(code)
        self.mock_kiwoom_api.get_daily_chart.assert_called_once_with(code)
        self.mock_kiwoom_api.subscribe_real_data.assert_not_called()

    @patch.object(TradingStrategy, 'stock_data_updated')
    def test_remove_from_watchlist_success(self, mock_stock_data_updated_signal):
        """관심종목 제거 성공 케이스"""
        code = "005930"
        name = "삼성전자"

        # 먼저 관심종목에 추가
        self.mock_kiwoom_api.get_stock_basic_info = MagicMock(return_value={
            '현재가': 70000, 
            '종목명': name
        })
        self.mock_kiwoom_api.get_daily_chart = MagicMock(return_value=(
            [
                {'일자': '20230102', '시가': 70500, '종가': 70000}, 
                {'일자': '20230101', '시가': 69000, '종가': 69500}  
            ], 
            False
        ))
        self.strategy.initialize_stock_data(code, name)
        self.assertIn(code, self.strategy.watchlist)
        self.assertIn(code, self.strategy.strategy_state)

        # mock_stock_data_updated_signal의 호출 기록을 초기화합니다.
        # initialize_stock_data에서 발생한 emit 호출은 이 테스트의 검증 대상이 아니기 때문입니다.
        mock_stock_data_updated_signal.reset_mock()

        # 실시간 데이터 구독 해제 mock 설정
        self.mock_kiwoom_api.unsubscribe_real_data = MagicMock()
        # UI 업데이트 시그널 mock 설정 -> patch.object 데코레이터로 대체
        # self.strategy.stock_data_updated.emit = MagicMock() 

        # 메소드 호출
        self.strategy.remove_from_watchlist(code)

        # 검증
        self.assertNotIn(code, self.strategy.watchlist)
        self.assertNotIn(code, self.strategy.strategy_state)
        self.assertNotIn(code, self.strategy.buy_prices)
        self.assertNotIn(code, self.strategy.buy_quantities)
        self.assertNotIn(code, self.strategy.high_prices)

        self.mock_kiwoom_api.unsubscribe_real_data.assert_called_once_with(
            self.mock_config.get("실시간화면번호_관심"),
            code
        )
        # mock_stock_data_updated_signal을 사용하여 호출 검증
        mock_stock_data_updated_signal.emit.assert_called_once_with(code, {'제거': True, 'name': name})

    @patch.object(TradingStrategy, 'stock_data_updated')
    def test_remove_from_watchlist_not_exist(self, mock_stock_data_updated_signal):
        """존재하지 않는 관심종목 제거 시도 케이스"""
        code = "000000" # 존재하지 않는 코드
        self.mock_kiwoom_api.unsubscribe_real_data = MagicMock()
        # UI 업데이트 시그널 mock 설정 -> patch.object 데코레이터로 대체
        # self.strategy.stock_data_updated.emit = MagicMock()

        # 메소드 호출 (특별한 에러 없이 조용히 실패해야 함)
        self.strategy.remove_from_watchlist(code)

        # 검증 (아무것도 호출되지 않아야 함)
        self.mock_kiwoom_api.unsubscribe_real_data.assert_not_called()
        # mock_stock_data_updated_signal을 사용하여 호출 검증
        mock_stock_data_updated_signal.emit.assert_not_called()
        # 로그에는 "관심종목에 없는 종목입니다" 경고가 찍혀야 함 (Logger Mock 사용 시 확인 가능)
        # self.test_logger.warning.assert_called_with(f"[Strategy] 관심종목에 없는 종목입니다: {code}")

    @patch.object(TradingStrategy, 'stock_data_updated')
    def test_on_real_data_received_buy_condition_met(self, mock_stock_data_updated_signal):
        """실시간 데이터 수신 시 매수 조건 충족 케이스"""
        code = "005930"
        name = "삼성전자"

        # 1. 초기 관심종목 설정 (매수 조건 충족 직전 상태로)
        # (당일 시가 > 전일 종가) 이고 (현재가 < 전일 종가) 상태
        self.mock_kiwoom_api.get_stock_basic_info = MagicMock(return_value={
            '현재가': 69000, # 전일 종가(69500)보다 낮은 상태
            '종목명': name
        })
        self.mock_kiwoom_api.get_daily_chart = MagicMock(return_value=(
            [
                {'일자': '20230102', '시가': 70500, '종가': 70000}, # 당일 시가: 70500
                {'일자': '20230101', '시가': 68000, '종가': 69500}  # 전일 종가: 69500
            ], 
            False
        ))
        self.strategy.initialize_stock_data(code, name)
        self.assertEqual(self.strategy.watchlist[code]['today_open'], 70500)
        self.assertEqual(self.strategy.watchlist[code]['yesterday_close'], 69500)
        self.assertEqual(self.strategy.watchlist[code]['current_price'], 69000)
        self.assertTrue(self.strategy.watchlist[code]['below_yesterday_close']) # 전일 종가 하회 상태
        self.assertFalse(self.strategy.watchlist[code]['crossed_yesterday_close'])
        self.assertEqual(self.strategy.strategy_state[code], TradingStrategy.WAITING)
        
        # initialize_stock_data에서 발생한 emit은 초기화
        mock_stock_data_updated_signal.reset_mock()

        # 2. 실시간 데이터 수신 (전일 종가를 돌파하는 상황)
        real_time_data = {'현재가': 69600} # 전일 종가(69500) 돌파
        self.strategy.on_real_data_received(code, "주식시세", real_time_data)

        # 3. 검증
        # watchlist 데이터 업데이트 확인
        self.assertEqual(self.strategy.watchlist[code]['current_price'], 69600)
        self.assertTrue(self.strategy.watchlist[code]['crossed_yesterday_close'])
        
        # 전략 상태 변경 확인 (READY)
        # 조건: 당일시가(70500) > 전일종가(69500) AND 금일매수완료 False AND 주문전송플래그 없음
        self.assertEqual(self.strategy.strategy_state[code], TradingStrategy.READY)
        
        # stock_data_updated 시그널 호출 확인
        # on_real_data_received는 내부적으로 stock_data_updated.emit을 호출
        mock_stock_data_updated_signal.emit.assert_called_with(code, self.strategy.watchlist[code])
        self.assertGreaterEqual(mock_stock_data_updated_signal.emit.call_count, 1)

    @patch.object(TradingStrategy, 'stock_data_updated')
    def test_on_real_data_received_update_high_price(self, mock_stock_data_updated_signal):
        """실시간 데이터 수신 시 고점 갱신 케이스 (매수 상태에서)"""
        code = "005930"
        name = "삼성전자"

        # 1. 초기 관심종목 설정 및 매수 상태로 변경 (BOUGHT)
        self.strategy.initialize_stock_data(code, name) # 내부적으로 get_stock_basic_info 등 호출
        self.strategy.strategy_state[code] = TradingStrategy.BOUGHT
        self.strategy.buy_prices[code] = 69000
        self.strategy.high_prices[code] = 69500 # 초기 고점 설정
        self.strategy.watchlist[code]['current_price'] = 69500 # 현재가를 고점과 동일하게

        mock_stock_data_updated_signal.reset_mock() # 이전 emit 호출 초기화

        # 2. 실시간 데이터 수신 (고점 갱신)
        new_high_price = 70000
        real_time_data = {'현재가': new_high_price}
        self.strategy.on_real_data_received(code, "주식시세", real_time_data)

        # 3. 검증
        self.assertEqual(self.strategy.high_prices[code], new_high_price)
        self.assertEqual(self.strategy.watchlist[code]['current_price'], new_high_price)
        mock_stock_data_updated_signal.emit.assert_called_with(code, self.strategy.watchlist[code])
        self.assertGreaterEqual(mock_stock_data_updated_signal.emit.call_count, 1)

    @patch.object(TradingStrategy, 'stock_data_updated')
    def test_on_real_data_received_not_in_watchlist(self, mock_stock_data_updated_signal):
        """실시간 데이터 수신 시 관심종목에 없는 경우"""
        code = "000001" # 관심종목에 없는 코드
        real_time_data = {'현재가': 10000}

        self.strategy.on_real_data_received(code, "주식시세", real_time_data)

        # watchlist에 없으므로 아무런 변화도 없어야 함
        self.assertNotIn(code, self.strategy.watchlist)
        mock_stock_data_updated_signal.emit.assert_not_called()

    @patch.object(TradingStrategy, 'on_real_data_received')
    @patch.object(TradingStrategy, 'error_occurred')
    @patch.object(TradingStrategy, 'order_feedback')
    def test_on_chejan_data_received_buy_order_failed(self, mock_order_feedback, mock_error_occurred_signal, mock_on_real_data_received):
        """체결 데이터 수신: 매수 주문 실패/거부 처리 케이스"""
        # 테스트용 플래그 설정
        original_suppress_flag = self.strategy.suppress_signals_for_test
        self.strategy.suppress_signals_for_test = True

        try:
            self.strategy.stop() # <--- 타이머 중지
            code = "005930"
            name = "삼성전자"
            rq_name_buy_fail = f"매수_{code}_fail_77777"
            error_message_from_api = "계좌 비밀번호 불일치"

            # 1. 초기 상태 설정 (매수 주문 전송된 상태)
            self.strategy.initialize_stock_data(code, name) # watchlist에 추가
            self.strategy.order_sent_flags[code] = {'rq_name': rq_name_buy_fail, 'reason': '자동매수_테스트실패'}

            chejan_data_buy_failed = {
                '9201': rq_name_buy_fail,
                '302': name,
                '9001': f"A{code}",
                '913': '실패',
                '907': '+매수',
                '919': error_message_from_api,
                '9203': 'ORD_FAIL_001'
            }

            self.strategy.strategy_state[code] = TradingStrategy.READY
            self.test_logger.info(f"BUY_FAIL_TEST - Before on_chejan_data_received (forced READY), strategy_state[{code}]: {self.strategy.strategy_state.get(code)}")
            
            def mock_on_real_data_side_effect(code_arg, real_type_arg, real_data_arg):
                self.test_logger.info(f"MOCK on_real_data_received called with: code({code_arg}), type({real_type_arg}), data({real_data_arg})")
                pass
            mock_on_real_data_received.side_effect = mock_on_real_data_side_effect
            
            self.strategy.on_chejan_data_received('0', chejan_data_buy_failed)

            # 이벤트 큐를 소진시키기 위해 processEvents() 호출 -> 일단 주석 처리하여 직접적인 영향 확인
            # self.test_logger.info("Calling QApplication.processEvents() multiple times...")
            # for _ in range(5):
            #     self.app.processEvents()

            # 검증
            self.test_logger.info(f"BUY_FAIL_TEST - After on_chejan_data_received, strategy_state[{code}]: {self.strategy.strategy_state.get(code)}") # 로그 메시지 수정
            self.test_logger.info(f"BUY_FAIL_TEST - mock_on_real_data_received call count: {mock_on_real_data_received.call_count}")
            if mock_on_real_data_received.call_count > 0:
                self.test_logger.info(f"BUY_FAIL_TEST - mock_on_real_data_received calls: {mock_on_real_data_received.mock_calls}")
                
            self.assertEqual(self.strategy.strategy_state.get(code), TradingStrategy.WAITING)
            self.assertNotIn(code, self.strategy.order_sent_flags)
            mock_error_occurred_signal.emit.assert_called_once_with(f"{name}({code}) 주문 실패: {error_message_from_api}")
            mock_order_feedback.emit.assert_called_once()

        finally:
            # 테스트용 플래그 복원
            self.strategy.suppress_signals_for_test = original_suppress_flag

    @patch.object(TradingStrategy, 'on_real_data_received')
    @patch.object(TradingStrategy, 'error_occurred')
    @patch.object(TradingStrategy, 'order_feedback')
    def test_on_chejan_data_received_buy_order_failed_with_event_processing(self, mock_order_feedback, mock_error_occurred_signal, mock_on_real_data_received):
        """체결 데이터 수신: 매수 주문 실패/거부 처리 후 이벤트 처리 시 상태 유지 검증"""
        self.strategy.stop()
        code = "005930"
        name = "삼성전자"
        rq_name_buy_fail = f"매수_{code}_fail_event_proc"
        error_message_from_api = "계좌 비밀번호 불일치 (이벤트 처리 테스트)"

        self.strategy.initialize_stock_data(code, name)
        self.strategy.order_sent_flags[code] = {'rq_name': rq_name_buy_fail, 'reason': '자동매수_이벤트테스트실패'}
        self.strategy.strategy_state[code] = TradingStrategy.READY

        chejan_data_buy_failed = {
            '9201': rq_name_buy_fail, '302': name, '9001': f"A{code}",
            '913': '실패', '907': '+매수', '919': error_message_from_api, '9203': 'ORD_FAIL_EVENT_001'
        }

        def mock_on_real_data_side_effect(code_arg, real_type_arg, real_data_arg):
            self.test_logger.info(f"EVENT_PROC_TEST - MOCK on_real_data_received called with: code({code_arg}), type({real_type_arg}), data({real_data_arg})")
            if code_arg == code and code_arg in self.strategy.watchlist:
                if '현재가' in real_data_arg:
                    self.strategy.watchlist[code_arg]['current_price'] = real_data_arg['현재가']
            pass
        mock_on_real_data_received.side_effect = mock_on_real_data_side_effect

        self.test_logger.info(f"EVENT_PROC_TEST - Before on_chejan_data_received, strategy_state[{code}]: {self.strategy.strategy_state.get(code)}")
        self.strategy.on_chejan_data_received('0', chejan_data_buy_failed)
        self.test_logger.info(f"EVENT_PROC_TEST - After on_chejan_data_received, strategy_state[{code}]: {self.strategy.strategy_state.get(code)}")

        self.assertEqual(self.strategy.strategy_state.get(code), TradingStrategy.WAITING, "State should be WAITING immediately after on_chejan_data_received")

        self.test_logger.info("EVENT_PROC_TEST - Calling QApplication.processEvents() multiple times...")
        for _ in range(5):
            self.app.processEvents()

        self.test_logger.info(f"EVENT_PROC_TEST - After processEvents, strategy_state[{code}]: {self.strategy.strategy_state.get(code)}")
        self.test_logger.info(f"EVENT_PROC_TEST - mock_on_real_data_received call count: {mock_on_real_data_received.call_count}")
        
        self.assertEqual(self.strategy.strategy_state.get(code), TradingStrategy.WAITING, "State should remain WAITING even after processEvents")
        self.assertNotIn(code, self.strategy.order_sent_flags)
        mock_error_occurred_signal.emit.assert_called_once_with(f"{name}({code}) 주문 실패: {error_message_from_api}")

if __name__ == '__main__':
    unittest.main() 