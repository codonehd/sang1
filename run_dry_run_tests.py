import os
import unittest
from unittest.mock import MagicMock, ANY, call # ANY, call 추가
import logging
from datetime import datetime, timedelta

# 테스트 대상 모듈 임포트 (실제 경로에 맞게 수정 필요)
# sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))) # 필요시 경로 추가
from strategy import TradingStrategy, TradingState # TradingState 추가
from kiwoom_api import KiwoomAPI # 실제 KiwoomAPI 클래스 (모킹 대상)
from config import ConfigManager # 실제 ConfigManager 클래스 (모킹 대상)
from logger import Logger
from database import Database
from util import ScreenManager # ScreenManager 임포트

# 환경 변수 설정 (QAxWidget 문제 회피)
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['DISABLE_QT_FOR_TESTING'] = 'True'

class TestManualInterventionScenarios(unittest.TestCase):

    def setUp(self):
        # 로거 초기화
        self.logger = Logger(log_file="logs/test_app_manual.log", log_level=logging.DEBUG) # console_level 제거, 로그 파일명 변경

        # 테스트용 설정 데이터 (ConfigManager 모킹용)
        self.test_settings_data = {
            "계좌정보": {"계좌번호": "TESTACCT", "account_type": "모의투자"},
            "매수금액": 100000.0, # float으로 명시
            "매매전략": {
                "익절_수익률": 5.0, "익절_매도비율": 50.0,
                "최종_익절_수익률": 10.0, 
                "트레일링_활성화_수익률": 2.0, "트레일링_하락률": 1.5,
                "손절손실률_전일종가기준": 3.0,
                "dry_run_mode": True, # 중요!
                "종목당_최대시도횟수": 3,
                "MarketOpenTime": "09:00:00", 
                "MarketCloseTime": "15:30:00" 
            },
            "watchlist": [],
            "Database": {"path": "logs/test_trading_data.db"}, 
            "Logging": {"level": "DEBUG"},
            "API_Limit": {"tr_request_interval_ms": 210}, 
            "fee_tax_rates": { 
                "모의투자": {"buy_fee_rate": 0.0035, "sell_fee_rate": 0.0035, "sell_tax_rate": 0.0000} 
            },
            "AutoTrading": {"start_automatically": False}, 
            "PeriodicStatusReport": {"enabled": False, "interval_seconds": 60},
            "API": {"RealTimeFID":"10;11;12;13"} # 추가된 설정
        }

        # ConfigManager 모킹
        self.config_manager = MagicMock(spec=ConfigManager)
        def mock_get_setting(section_or_key, key_or_default=None, default_val=None):
            # self.logger.debug(f"MockConfigManager.get_setting 호출: section_or_key='{section_or_key}', key_or_default='{key_or_default}', default_val='{default_val}'")
            if isinstance(section_or_key, str) and isinstance(key_or_default, str): # 섹션, 키 모두 제공
                return self.test_settings_data.get(section_or_key, {}).get(key_or_default, default_val)
            elif isinstance(section_or_key, str): # 섹션 또는 최상위 키만 제공
                # 최상위 키인지, 아니면 섹션 전체를 요청하는 것인지 구분 필요
                # 여기서는 key_or_default가 default_val의 역할을 한다고 가정 (ConfigManager의 실제 동작 따라야 함)
                # 만약 get_setting("매수금액") 처럼 호출되면, key_or_default가 default_val이 됨
                # 만약 get_setting("fee_tax_rates") 처럼 호출되면, key_or_default가 default_val이 됨
                return self.test_settings_data.get(section_or_key, key_or_default if key_or_default is not None else default_val)
            # self.logger.warning(f"MockConfigManager: 처리되지 않은 get_setting 호출 - section_or_key: {section_or_key}, key_or_default: {key_or_default}")
            return default_val
        
        self.config_manager.get_setting.side_effect = mock_get_setting
        self.config_manager.config_file = "mock_settings.json" 

        # Database 초기화 (테스트용 인메모리 DB 또는 임시 파일 사용 권장)
        self.db_manager = Database(db_file=self.test_settings_data["Database"]["path"], logger=self.logger) 
        # self.db_manager.create_tables() # Database 클래스의 initialize_db가 자동으로 테이블 생성

        # KiwoomAPI 모킹
        self.mock_kiwoom_api = MagicMock(spec=KiwoomAPI)
        self.mock_kiwoom_api.get_server_gubun = MagicMock(return_value="1") 
        self.mock_kiwoom_api.send_order = MagicMock(return_value=0) 
        self.mock_kiwoom_api.account_number = self.test_settings_data["계좌정보"]["계좌번호"]

        # ScreenManager 초기화
        self.screen_manager = ScreenManager(logger=self.logger)

        # TradingStrategy 인스턴스 생성
        self.strategy = TradingStrategy(
            kiwoom_api=self.mock_kiwoom_api,
            config_manager=self.config_manager,
            logger=self.logger,
            db_manager=self.db_manager,
            screen_manager=self.screen_manager
        )
        
        self.strategy._load_strategy_settings() 
        
        # TradingStrategy 초기화 완료 상태로 설정
        self.strategy.initialization_status = {
            "account_info_loaded": True, "deposit_info_loaded": True,
            "portfolio_loaded": True, "settings_loaded": True,
            "market_hours_initialized": True
        }
        self.strategy.is_initialized_successfully = True
        self.strategy.account_state.account_number = self.mock_kiwoom_api.account_number
        
        # 수수료/세율은 _load_strategy_settings에서 account_type을 읽은 후 설정됨
        # self.strategy.account_type은 _load_strategy_settings에서 설정되어야 함
        self.logger.info(f"Strategy account_type after load: {self.strategy.account_type}")
        self.logger.info(f"Strategy current_fee_tax_rates after load: {self.strategy.current_fee_tax_rates}")


        self.strategy.is_running = True 
        self.strategy.log = MagicMock() 
        
        self.strategy.watchlist.clear()
        self.strategy.account_state.portfolio.clear()
        self.strategy.account_state.active_orders.clear()
        self.strategy.account_state.trading_status.clear()
        
        self.logger.info("Test setUp 완료")


    def tearDown(self):
        self.logger.info("Test tearDown 시작")
        # 핸들러 닫기 (파일 삭제 전)
        handlers = self.logger.logger.handlers[:]
        for handler in handlers:
            handler.close()
            self.logger.logger.removeHandler(handler)

        # 테스트 중 생성된 파일 삭제
        db_path = self.test_settings_data["Database"]["path"]
        log_path = self.logger.log_file # Logger에 log_file 속성이 있다고 가정

        if os.path.exists(db_path):
            try:
                self.db_manager.close() # DB 연결 먼저 닫기
                os.remove(db_path)
                # self.logger.info(f"테스트 DB 파일 삭제: {db_path}") # 로거가 이미 닫혔을 수 있음
                print(f"테스트 DB 파일 삭제: {db_path}")
            except Exception as e:
                print(f"테스트 DB 파일 삭제 실패: {e}")

        if os.path.exists(log_path):
            try:
                os.remove(log_path)
                print(f"테스트 로그 파일 삭제: {log_path}")
            except Exception as e:
                print(f"테스트 로그 파일 삭제 실패: {e}")
        
        logs_dir = "logs"
        if os.path.exists(logs_dir) and not os.listdir(logs_dir): 
            try:
                os.rmdir(logs_dir)
                print(f"logs 디렉토리 삭제 성공.")
            except Exception as e:
                print(f"logs 디렉토리 삭제 실패: {e}")
        print("Test tearDown 완료")


    def test_scenario_manual_full_sell(self):
        self.logger.info("시나리오 1: 수동 전체 매도 - 테스트 시작")
        code = "000001"
        stock_name = "테스트종목_수동매도"
        self.strategy.add_to_watchlist(code, stock_name, yesterday_close_price=10000)
        stock_info = self.strategy.watchlist.get(code)

        # 초기 매수 상태 설정
        stock_info.strategy_state = TradingState.BOUGHT
        stock_info.avg_buy_price = 10000.0
        stock_info.total_buy_quantity = 10
        stock_info.current_high_price_after_buy = 10000.0
        stock_info.buy_timestamp = datetime.now() - timedelta(hours=1)
        stock_info.buy_completion_count = 1 

        self.strategy.account_state.portfolio[code] = {
            'stock_name': stock_name, '보유수량': 10, '매입가': 10000.0, '현재가': 10000.0,
            '평가금액': 100000, '매입금액': 100000, '평가손익': 0, '수익률': 0.0
        }
        self.strategy.account_state.trading_status[code] = {
            'status': TradingState.BOUGHT, 'bought_price': 10000.0,
            'bought_quantity': 10, 'bought_time': stock_info.buy_timestamp
        }

        # 수동 매도 시뮬레이션: opw00018 응답에서 해당 종목 제외
        mock_opw00018_data_after_manual_sell = {
            'single_data': {'총매입금액': '0', '총평가금액': '0', '총평가손익금액': '0', '총수익률(%)': '0.00', '추정예탁자산': '10000000'},
            'multi_data': [] 
        }
        self.strategy._handle_opw00018_response(rq_name="test_opw00018_full_sell", data=mock_opw00018_data_after_manual_sell)

        # 결과 검증
        updated_stock_info = self.strategy.watchlist.get(code) 
        self.assertEqual(updated_stock_info.strategy_state, TradingState.WAITING)
        self.assertEqual(updated_stock_info.total_buy_quantity, 0)
        self.assertEqual(updated_stock_info.avg_buy_price, 0.0)
        self.assertIsNone(updated_stock_info.buy_timestamp)
        self.assertEqual(updated_stock_info.buy_completion_count, 0) 
        self.assertNotIn(code, self.strategy.account_state.trading_status)

        # 로그 검증
        log_calls_info = [args[0] for args, kwargs in self.strategy.log.call_args_list if kwargs.get('level', 'INFO').upper() == 'INFO']
        self.assertTrue(any(f"[SYNC_PORTFOLIO] 수동 전량 매도 감지: {code}" in log_msg for log_msg in log_calls_info))
        self.assertTrue(any(f"[{code}] 종목 상태 초기화: BOUGHT -> WAITING" in log_msg for log_msg in log_calls_info))
        self.logger.info("시나리오 1: 수동 전체 매도 - 테스트 완료")


    def test_scenario_manual_additional_buy(self):
        self.logger.info("시나리오 2: 수동 추가 매수 - 테스트 시작")
        code = "000002"
        stock_name = "테스트종목_수동추가매수"
        self.strategy.add_to_watchlist(code, stock_name, yesterday_close_price=5000)
        stock_info = self.strategy.watchlist.get(code)

        # 초기 매수 상태 설정
        stock_info.strategy_state = TradingState.BOUGHT
        stock_info.avg_buy_price = 5000.0
        stock_info.total_buy_quantity = 50
        stock_info.current_high_price_after_buy = 5000.0
        stock_info.buy_timestamp = datetime.now() - timedelta(hours=2)

        self.strategy.account_state.portfolio[code] = {
            'stock_name': stock_name, '보유수량': 50, '매입가': 5000.0, '현재가': 5000.0
        }
        self.strategy.account_state.trading_status[code] = {
            'status': TradingState.BOUGHT, 'bought_price': 5000.0,
            'bought_quantity': 50, 'bought_time': stock_info.buy_timestamp
        }

        # 수동 추가 매수 시뮬레이션
        mock_opw00018_data_after_manual_buy = {
            'single_data': {'총매입금액': '510000', '총평가금액': '520000', '현재가': '5200'}, 
            'multi_data': [{
                '종목번호': 'A'+code, '종목명': stock_name, '보유수량': '100', # 'A' 접두사 추가
                '매입단가': '5100', '현재가': '5200', '평가금액': '520000', '매입금액': '510000', '매입가': '5100'
            }]
        }
        self.strategy._handle_opw00018_response(rq_name="test_opw00018_add_buy", data=mock_opw00018_data_after_manual_buy)

        # 결과 검증
        updated_stock_info = self.strategy.watchlist.get(code)
        self.assertEqual(updated_stock_info.strategy_state, TradingState.BOUGHT)
        self.assertEqual(updated_stock_info.total_buy_quantity, 100)
        self.assertAlmostEqual(updated_stock_info.avg_buy_price, 5100.0, places=2)
        
        log_calls_info = [args[0] for args, kwargs in self.strategy.log.call_args_list if kwargs.get('level', 'INFO').upper() == 'INFO']
        self.assertTrue(any(f"[SYNC_PORTFOLIO] 수량 불일치 감지 ({code}): 추적(50) vs 실제(100)" in msg for msg in log_calls_info))
        self.assertTrue(any(f"[SYNC_PORTFOLIO] 평균 매입가 불일치 감지 ({code}): 추적(5000.00) vs 실제(5100.00)" in msg for msg in log_calls_info))
        self.logger.info("시나리오 2: 수동 추가 매수 - 테스트 완료")


    def test_scenario_on_chejan_manual_buy(self):
        self.logger.info("시나리오 3: on_chejan 수동 매수 - 테스트 시작")
        code = "000003"
        stock_name = "테스트종목_체결수동매수"
        self.strategy.add_to_watchlist(code, stock_name, yesterday_close_price=20000)
        stock_info_before = self.strategy.watchlist.get(code)

        self.assertEqual(stock_info_before.strategy_state, TradingState.WAITING)
        self.assertEqual(stock_info_before.total_buy_quantity, 0)
        self.strategy.account_state.active_orders.clear()

        # 수동 매수 체결 시뮬레이션
        manual_chejan_data = {
            '9001': 'A'+code, '302': stock_name, '9203': 'MANUALORDER123',
            '913': '체결', '905': '+매수', '911': '10', '10': '20500',
            '900': '10', '902': '0', '938': '100', '939': '0'
        }
        self.strategy.on_chejan_data_received(gubun='0', chejan_data=manual_chejan_data)

        # 결과 검증
        stock_info_after = self.strategy.watchlist.get(code)
        self.assertEqual(stock_info_after.strategy_state, TradingState.BOUGHT)
        self.assertEqual(stock_info_after.total_buy_quantity, 10) 
        self.assertAlmostEqual(stock_info_after.avg_buy_price, 20500.0, places=2)
        self.assertIsNotNone(stock_info_after.buy_timestamp)
        self.assertEqual(stock_info_after.buy_completion_count, 0) 

        log_calls_warning = [args[0] for args, kwargs in self.strategy.log.call_args_list if kwargs.get('level', 'INFO').upper() == 'WARNING'] # MANUAL_TRADE_DETECTED는 WARNING 레벨
        log_calls_info = [args[0] for args, kwargs in self.strategy.log.call_args_list if kwargs.get('level', 'INFO').upper() == 'INFO']
        
        self.assertTrue(any(f"[MANUAL_TRADE_DETECTED] 시스템 주문과 매칭되지 않는 체결 데이터 수신 (수동 거래 추정): {code}" in msg for msg in log_calls_warning))
        self.assertTrue(any(f"[MANUAL_TRADE] 수동 매수 체결 감지: {code}" in msg for msg in log_calls_info))

        trades = self.db_manager.get_trades_by_code(code)
        self.assertTrue(any(t['trade_reason'] == '수동체결' and t['quantity'] == 10 and t['price'] == 20500 for t in trades)) # trade_reason 수정
        self.logger.info("시나리오 3: on_chejan 수동 매수 - 테스트 완료")


    def test_scenario_inconsistent_state_partial_sold_zero_qty(self):
        self.logger.info("시나리오 4: 일관성 없는 상태 (PARTIAL_SOLD, 수량0) - 테스트 시작")
        code = "000004"
        stock_name = "테스트종목_상태오류"
        self.strategy.add_to_watchlist(code, stock_name, yesterday_close_price=30000)
        stock_info = self.strategy.watchlist.get(code)

        # 일관성 없는 상태 설정
        stock_info.strategy_state = TradingState.PARTIAL_SOLD
        stock_info.total_buy_quantity = 0
        stock_info.avg_buy_price = 30000.0
        stock_info.current_price = 30000.0 
        stock_info.partial_take_profit_executed = True 
        stock_info.buy_timestamp = datetime.now() - timedelta(days=1)

        if code in self.strategy.account_state.portfolio: 
            self.strategy.account_state.portfolio[code]['보유수량'] = 0
        
        self.strategy.check_conditions()

        # 결과 검증
        updated_stock_info = self.strategy.watchlist.get(code)
        self.assertEqual(updated_stock_info.strategy_state, TradingState.WAITING)
        self.assertEqual(updated_stock_info.total_buy_quantity, 0)
        self.assertEqual(updated_stock_info.avg_buy_price, 0.0)
        self.assertFalse(updated_stock_info.partial_take_profit_executed)

        log_calls_warning = [args[0] for args, kwargs in self.strategy.log.call_args_list if kwargs.get('level', 'INFO').upper() == 'WARNING']
        log_calls_info = [args[0] for args, kwargs in self.strategy.log.call_args_list if kwargs.get('level', 'INFO').upper() == 'INFO']
        self.assertTrue(any(f"[INCONSISTENCY_DETECTED] {code}: PARTIAL_SOLD 상태이나 보유수량 0 이하 (0)" in msg for msg in log_calls_warning))
        self.assertTrue(any(f"[{code}] 종목 상태 초기화: PARTIAL_SOLD -> WAITING" in msg for msg in log_calls_info))
        self.logger.info("시나리오 4: 일관성 없는 상태 (PARTIAL_SOLD, 수량0) - 테스트 완료")


if __name__ == '__main__':
    unittest.main()
