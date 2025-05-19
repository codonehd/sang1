print("TestIntegration: Starting execution...")
import sys
print(f"TestIntegration: Python version: {sys.version}")
print(f"TestIntegration: Python executable: {sys.executable}")

import unittest
from unittest.mock import MagicMock, patch
import os
import logging
import traceback
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QTimer
from datetime import datetime, timedelta
import time
from PyQt5.QtTest import QTest
import random
import re

# 프로젝트 루트 경로를 sys.path에 추가
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

print("TestIntegration: About to import KiwoomAPI...")
from kiwoom_api import KiwoomAPI
print("TestIntegration: Successfully imported KiwoomAPI.")

print("TestIntegration: About to import TradingStrategy...")
from strategy import TradingStrategy
print("TestIntegration: Successfully imported TradingStrategy.")

print("TestIntegration: About to import ConfigManager...")
from config import ConfigManager
print("TestIntegration: Successfully imported ConfigManager.")

print("TestIntegration: About to import Logger...")
from logger import Logger, QTextEditLogHandler
print("TestIntegration: Successfully imported Logger.")

print("TestIntegration: About to import Database...")
from database import Database # DatabaseManager 대신 Database를 import
print("TestIntegration: Successfully imported Database.")

print("TestIntegration: About to import MainWindow...")
try:
    from ui import MainWindow
    print("TestIntegration: Successfully imported MainWindow.")
except BaseException as be:
    print(f"TestIntegration: EXCEPTION during MainWindow import: {type(be).__name__} - {be}")
    traceback.print_exc()
    sys.exit(1)

class MockKiwoomAPIForIntegration(KiwoomAPI):
    def __init__(self, logger=None, test_case_instance=None):
        super().__init__(logger=logger)
        self.send_order_call_history = []
        self.subscribed_real_data_mock = {}  # {screen_no: {codes: [], fids: [], type: ""}}
        self._mock_real_data_active_screens = {} # 화면번호별 실시간 데이터 구독 정보 (실제 API 구독과 유사하게 관리)
        self._mock_real_data_timer = None
        self.mock_tr_data_handler = None # 각 테스트에서 필요에 따라 설정 가능
        self.current_tr_data = None # comm_rq_data 호출 시 TR 데이터 저장용
        self.test_case_instance = test_case_instance # 현재 실행 중인 테스트 케이스 인스턴스
        self.current_test_id = None # 현재 실행 중인 테스트의 ID (예: self.id())
        if self.test_case_instance:
            self.current_test_id = self.test_case_instance.id()
        self.logger.info(f"[MockKiwoomInit] MockKiwoomAPIForIntegration initialized for test: {self.current_test_id}")

    def _get_mock_basic_info(self, code):
        self.logger.debug(f"[_get_mock_basic_info] Called for {code}. Current test ID: {self.current_test_id}")
        default_yesterday_close = 9500
        default_market_open_price = 9500
        default_current_price = 9500 # TR 시점 현재가
        default_high_price = 10500
        default_low_price = 9300
        default_volume = 100

        data_source_name = None
        data_source = None

        if self.test_case_instance and self.current_test_id:
            if "test_concurrent_buy_orders_and_logging" in self.current_test_id:
                data_source_name = 'initial_stock_data_concurrent'
                data_source = getattr(self.test_case_instance, data_source_name, None)
            elif "test_buy_order_api_error_handling" in self.current_test_id:
                data_source_name = 'initial_stock_data_buy_error'
                data_source = getattr(self.test_case_instance, data_source_name, None)
            elif "test_full_trading_cycle_with_realtime_data" in self.current_test_id:
                data_source_name = 'initial_stock_data_full_cycle'
                data_source = getattr(self.test_case_instance, data_source_name, None)
            elif "test_realtime_data_format_error_handling" in self.current_test_id:
                data_source_name = 'initial_stock_data_realtime_error'
                data_source = getattr(self.test_case_instance, data_source_name, None)
            elif "test_tr_data_request_error_handling" in self.current_test_id: # 추가
                data_source_name = 'initial_stock_data_tr_error'
                data_source = getattr(self.test_case_instance, data_source_name, None)
            # 다른 테스트 케이스에 대한 분기도 필요시 추가

        stock_data_from_source = None
        if data_source and code in data_source:
            stock_data_from_source = data_source[code]
            self.logger.debug(f"[_get_mock_basic_info] For {code} in {self.current_test_id}, found data in {data_source_name}: {stock_data_from_source}")
        else:
            self.logger.warning(f"[_get_mock_basic_info] For {code} in {self.current_test_id}, no data_source or code not found in {data_source_name}. Using default values.")

        name_val = stock_data_from_source.get("name", f"모의종목_{code}") if stock_data_from_source else f"모의종목_{code}"
        yesterday_close_val = stock_data_from_source.get("yesterday_close", default_yesterday_close) if stock_data_from_source else default_yesterday_close
        market_open_price_val = stock_data_from_source.get("market_open_price", default_market_open_price) if stock_data_from_source else default_market_open_price
        current_price_val = stock_data_from_source.get("current_price", default_current_price) if stock_data_from_source else default_current_price # TR 시점 현재가
        high_price_val = stock_data_from_source.get("high_price", default_high_price) if stock_data_from_source else default_high_price # 일중 고가
        low_price_val = stock_data_from_source.get("low_price", default_low_price) if stock_data_from_source else default_low_price   # 일중 저가
        volume_val = stock_data_from_source.get("volume", default_volume) if stock_data_from_source else default_volume         # 거래량

        self.logger.debug(f"[_get_mock_basic_info] For {code}, using values: yc={yesterday_close_val}, mop={market_open_price_val}, cp={current_price_val}, hp={high_price_val}, lp={low_price_val}, vol={volume_val}")

        return {
            "종목코드": code, "종목명": name_val, "현재가": str(current_price_val),
            "전일종가": str(yesterday_close_val), "시가": str(market_open_price_val),
            "고가": str(high_price_val), "저가": str(low_price_val),
            "거래량": str(volume_val), "상한가": str(int(yesterday_close_val * 1.3)),
            "하한가": str(int(yesterday_close_val * 0.7)), "기준가": str(yesterday_close_val),
            "등락률": f"{((current_price_val / yesterday_close_val - 1) * 100):.2f}" if yesterday_close_val else "0.00",
            "PER": "10.00", "PBR": "1.00", "EPS": "1000", "BPS": "10000",
            # 필요에 따라 더 많은 필드 추가
        }

    def _get_mock_daily_chart_data(self, code, date_str=None): # KiwoomAPI.get_daily_chart는 date_to를 사용
        self.logger.debug(f"[_get_mock_daily_chart_data] Called for {code}. Current test ID: {self.current_test_id}")
        # 기본값 설정
        default_yesterday_close = 9500
        default_today_open = 9500
        default_today_high = 10500
        default_today_low = 9300
        default_today_close = 9500 # 일봉 데이터의 '오늘 종가'는 TR 요청 시점의 현재가와 다를 수 있음
        default_today_volume = 100

        data_source_name = None
        data_source = None

        if self.test_case_instance and self.current_test_id:
            if "test_concurrent_buy_orders_and_logging" in self.current_test_id:
                data_source_name = 'initial_stock_data_concurrent'
                data_source = getattr(self.test_case_instance, data_source_name, None)
            elif "test_buy_order_api_error_handling" in self.current_test_id:
                data_source_name = 'initial_stock_data_buy_error'
                data_source = getattr(self.test_case_instance, data_source_name, None)
            elif "test_full_trading_cycle_with_realtime_data" in self.current_test_id:
                data_source_name = 'initial_stock_data_full_cycle'
                data_source = getattr(self.test_case_instance, data_source_name, None)
            elif "test_realtime_data_format_error_handling" in self.current_test_id:
                data_source_name = 'initial_stock_data_realtime_error'
                data_source = getattr(self.test_case_instance, data_source_name, None)
            elif "test_tr_data_request_error_handling" in self.current_test_id:
                data_source_name = 'initial_stock_data_tr_error'
                data_source = getattr(self.test_case_instance, data_source_name, None)

        stock_data_from_source = None
        if data_source and code in data_source:
            stock_data_from_source = data_source[code]
            self.logger.debug(f"[_get_mock_daily_chart_data] For {code} in {self.current_test_id}, found data in {data_source_name} for daily: {stock_data_from_source}")
        else:
            self.logger.warning(f"[_get_mock_daily_chart_data] For {code} in {self.current_test_id}, no data_source or code not found in {data_source_name} for daily. Using default daily values.")

        yesterday_close_val = stock_data_from_source.get("yesterday_close", default_yesterday_close) if stock_data_from_source else default_yesterday_close
        today_open_val = stock_data_from_source.get("market_open_price", default_today_open) if stock_data_from_source else default_today_open # 시가는 market_open_price 사용
        # 일봉의 고가/저가/종가는 TR요청시점의 현재가(current_price)나, 일중 최고/최저와는 다를 수 있음.
        # 테스트 데이터에 "daily_high", "daily_low", "daily_close" 등을 명시적으로 넣거나, current_price를 활용.
        today_high_val = stock_data_from_source.get("high_price", default_today_high) if stock_data_from_source else default_today_high # 예시로 TR용 high_price 사용
        today_low_val = stock_data_from_source.get("low_price", default_today_low) if stock_data_from_source else default_today_low     # 예시로 TR용 low_price 사용
        today_close_val = stock_data_from_source.get("current_price", default_today_close) if stock_data_from_source else default_today_close # 예시로 TR용 current_price를 일봉 종가로 사용
        today_volume_val = stock_data_from_source.get("volume", default_today_volume) if stock_data_from_source else default_today_volume

        self.logger.debug(f"[_get_mock_daily_chart_data] For {code}, using daily values: yc={yesterday_close_val}, open={today_open_val}, high={today_high_val}, low={today_low_val}, close={today_close_val}, vol={today_volume_val}")

        # (일자, 시가, 고가, 저가, 현재가(종가), 거래량)
        mock_data_list = [
            {
                "일자": datetime.now().strftime("%Y%m%d") if not date_str else date_str, # 오늘 또는 요청된 날짜
                "시가": str(today_open_val), "고가": str(today_high_val),
                "저가": str(today_low_val), "종가": str(today_close_val), "거래량": str(today_volume_val)
            }, # 오늘 데이터 (가장 최근)
            {
                "일자": (datetime.now() - timedelta(days=1)).strftime("%Y%m%d"), # 어제 날짜
                "시가": str(yesterday_close_val), "고가": str(yesterday_close_val), # 어제 종가를 시/고/저/종가로 사용
                "저가": str(yesterday_close_val), "종가": str(yesterday_close_val), "거래량": "0" # 단순화를 위해 거래량 0
            }  # 어제 데이터
        ]
        return mock_data_list


    def get_stock_basic_info(self, code, screen_no="0102"):
        self.logger.info(f"[MockKiwoom] get_stock_basic_info called for {code}, screen_no: {screen_no}, test_id: {self.current_test_id}")
        if self.mock_tr_data_handler:
            handled_data = self.mock_tr_data_handler(rq_name=f"mock_opt10001_req_{code}", tr_code="opt10001", screen_no=screen_no, code=code)
            # 핸들러가 명시적으로 False를 반환하지 않으면 그 결과를 사용
            # 핸들러가 None을 반환하는 경우 (TR 오류 시뮬레이션 등)도 여기서 처리
            if handled_data is not False:
                self.logger.debug(f"[MockKiwoom] get_stock_basic_info for {code} handled by mock_tr_data_handler. Data: {handled_data}")
                return handled_data # 핸들러가 None을 반환하면 None이 그대로 반환됨

        self.logger.debug(f"[MockKiwoom] get_stock_basic_info for {code} using _get_mock_basic_info (handler did not process or returned False).")
        return self._get_mock_basic_info(code)

    def get_daily_chart(self, code, *, date_to=None, prev_next=None, screen_no="0101"): # KiwoomAPI 시그니처와 일치
        self.logger.info(f"[MockKiwoom] get_daily_chart called for {code}, date_to: {date_to}, screen_no: {screen_no}, test_id: {self.current_test_id}")
        # 특정 TR 요청에 대한 응답을 mock_tr_data_handler를 통해 제어할 수 있도록 수정
        # date_to는 KiwoomAPI에서는 사용되지만, 여기서는 단순화를 위해 현재 날짜 기준으로 생성
        # prev_next 또한 실제 API에서는 중요하지만, 여기서는 기본적으로 최근 2일치 데이터 제공
        if self.mock_tr_data_handler:
            handled_data = self.mock_tr_data_handler(rq_name=f"mock_opt10081_req_{code}", tr_code="opt10081", screen_no=screen_no, code=code, date_to=date_to, prev_next=prev_next)
            if handled_data is not False and handled_data is not None:
                self.logger.debug(f"[MockKiwoom] get_daily_chart for {code} handled by mock_tr_data_handler. Data: {handled_data}")
                # 핸들러가 직접 (data_list, is_next) 튜플을 반환하도록 기대
                if isinstance(handled_data, tuple) and len(handled_data) == 2:
                    return handled_data
                else: # 아니면 기본 형식으로 감싸서 반환 (data_list만 반환된 경우)
                    return (handled_data, False)


        # mock_tr_data_handler가 없거나 처리하지 않은 경우, 내부 _get_mock_daily_chart_data 사용
        self.logger.debug(f"[MockKiwoom] get_daily_chart for {code} using _get_mock_daily_chart_data.")
        chart_data_list = self._get_mock_daily_chart_data(code, date_to)
        return (chart_data_list, False) # (데이터 리스트, 연속조회여부=False)

    def subscribe_real_data(self, screen_no, code_list_str, real_type_str):
        # 부모 클래스의 메서드 호출 (실제 API 호출 부분은 실행되지 않도록 주의)
        # KiwoomAPI의 subscribe_real_data는 실제 OCX 호출을 포함하므로,
        # 여기서는 모의 동작만 수행하도록 재정의하거나,
        # 부모 메서드가 모의 환경에서 안전하게 동작하도록 만들어야 함.
        # 지금은 단순히 성공했다고 가정하고 로깅 및 내부 상태만 업데이트
        self.logger.info(f"[MockKiwoom] Subscribing to real data: Screen({screen_no}), Codes('{code_list_str}'), Type('{real_type_str}')")
        codes = code_list_str.split(';')
        # fid_list = self._parse_fids(fid_list_str) # KiwoomAPI의 _parse_fids 사용
        
        # KiwoomAPI의 subscribe_real_data는 내부적으로 self.subscribed_real_data를 업데이트.
        # Mock에서는 해당 변수를 직접 사용하지 않고, _mock_real_data_active_screens를 사용.
        # 하지만 호환성을 위해 부모 클래스의 동작을 일부 모방하거나, 필요한 부분만 가져올 수 있음.

        # 여기서는 KiwoomAPI의 원래 로직을 그대로 호출하지 않고,
        # MockKiwoomAPIForIntegration의 내부 상태(_mock_real_data_active_screens)만 관리.
        if screen_no not in self._mock_real_data_active_screens:
            self._mock_real_data_active_screens[screen_no] = {'codes': [], 'fids': [], 'type': real_type_str} # fid는 단순화

        for code in codes:
            if code not in self._mock_real_data_active_screens[screen_no]['codes']:
                self._mock_real_data_active_screens[screen_no]['codes'].append(code)
        
        self.logger.info(f"[MockKiwoom] _mock_real_data_active_screens updated: {self._mock_real_data_active_screens}")
        return 0 # 성공 리턴

    def _parse_fids(self, fid_list_str): # KiwoomAPI에도 동일 메서드 존재, 여기서는 mock용으로 단순화 가능
        if not fid_list_str: # 빈 문자열이면 빈 리스트 반환 (실제 API와 동작 맞춤)
             self.logger.debug(f"[MockKiwoom] _parse_fids called with: '{fid_list_str}', returning empty list for mock.")
             return []
        return [fid.strip() for fid in fid_list_str.split(';') if fid.strip()]

    def unsubscribe_real_data(self, screen_no, code_list_str=""):
        self.logger.info(f"[MockKiwoom] Unsubscribe called: Screen({screen_no}), Codes('{code_list_str}'). Current active screens: {self._mock_real_data_active_screens}")
        if not code_list_str: # 종목코드 리스트가 비어있으면 해당 화면의 모든 구독 해제
            if screen_no in self._mock_real_data_active_screens:
                del self._mock_real_data_active_screens[screen_no]
                self.logger.info(f"[MockKiwoom] Unsubscribed all real data for screen {screen_no}.")
        else:
            codes_to_remove = code_list_str.split(';')
            if screen_no in self._mock_real_data_active_screens:
                for code in codes_to_remove:
                    if code in self._mock_real_data_active_screens[screen_no]['codes']:
                        self._mock_real_data_active_screens[screen_no]['codes'].remove(code)
                if not self._mock_real_data_active_screens[screen_no]['codes']: # 해당 화면에 더이상 구독 종목 없으면 화면 자체 제거
                    del self._mock_real_data_active_screens[screen_no]
                self.logger.info(f"[MockKiwoom] Unsubscribed {codes_to_remove} from screen {screen_no}. Updated screens: {self._mock_real_data_active_screens}")
            else:
                self.logger.warning(f"[MockKiwoom] Screen {screen_no} not found in _mock_real_data_active_screens during unsubscribe.")
        return 0


    def start_emitting_mock_real_data(self, duration_seconds=10, interval_ms=100):
        if not self._mock_real_data_timer:
            self._mock_real_data_timer = QTimer()
            self._mock_real_data_timer.timeout.connect(self._emit_one_mock_real_data_batch)
        
        if not self._mock_real_data_timer.isActive():
            self._mock_real_data_timer.start(interval_ms)
            self.logger.info(f"[MockKiwoom] Started emitting mock real data every {interval_ms}ms for {duration_seconds}s.")
            # 일정 시간 후 자동 중지 (테스트 환경에서 유용)
            if duration_seconds > 0:
                QTimer.singleShot(duration_seconds * 1000, self.stop_emitting_mock_real_data)
        else:
            self.logger.info("[MockKiwoom] Mock real data emission timer is already active.")

    def _emit_one_mock_real_data_batch(self):
        if not self._mock_real_data_active_screens:
            # self.logger.debug("[MockKiwoom] No active screens to emit mock real data.")
            return

        for screen_no, sub_info in list(self._mock_real_data_active_screens.items()): # dict 변경 중 순회 오류 방지
            codes = sub_info.get('codes', [])
            real_type = sub_info.get('type', "주식체결") # 기본값 또는 설정된 타입 사용
            
            for code in codes:
                # 테스트 케이스별 초기 데이터 가져오기
                data_source = None
                if self.test_case_instance and self.current_test_id:
                    if "test_concurrent_buy_orders_and_logging" in self.current_test_id:
                        data_source = getattr(self.test_case_instance, 'initial_stock_data_concurrent', None)
                    # ... 다른 테스트 케이스에 대한 initial_stock_data 참조 ...

                base_price = 10000 # 기본 기준가
                if data_source and code in data_source:
                    base_price = data_source[code].get('current_price', # 실시간 데이터의 기준이 될 가격 (TR 요청시 current_price)
                                                      data_source[code].get('market_open_price',
                                                                          data_source[code].get('yesterday_close', 10000)))

                # 간단한 변동성 추가
                price_change = random.randint(-50, 50)
                current_mock_price = base_price + price_change
                volume_change = random.randint(10, 100)

                real_data_packet = {
                    # FID: 값 형태로 실제 데이터 모의 (주요 FID 위주)
                    '10': str(current_mock_price),  # 현재가
                    '11': str(price_change),       # 전일대비
                    '12': f"{((current_mock_price / base_price - 1) * 100) if base_price else 0:.2f}",  # 등락률
                    '13': str(volume_change),      # 누적거래량 (여기서는 단순 변동량)
                    '15': str(current_mock_price + 100), # 시가 (예시)
                    '16': str(current_mock_price + 200), # 고가 (예시)
                    '17': str(current_mock_price - 100), # 저가 (예시)
                    # 필요시 더 많은 FID 추가
                }
                # self.logger.debug(f"[MockKiwoomEmit] Emitting mock real data for {code} on screen {screen_no}: {real_data_packet}")
                self.real_data_received.emit(code, real_type, real_data_packet) # 시그널 발생
        QApplication.processEvents() # Emit 후 이벤트 처리 강제 (옵션)


    def stop_emitting_mock_real_data(self):
        if self._mock_real_data_timer and self._mock_real_data_timer.isActive():
            self._mock_real_data_timer.stop()
            self.logger.info("[MockKiwoom] Stopped emitting mock real data.")

    def send_order(self, rq_name, screen_no, acc_no, order_type, code, quantity, price, hoga_gb, org_order_no=""):
        self.logger.info(f"[MockIntegrationKiwoom] ENTERING send_order. Current Test ID: {getattr(self, 'current_test_id', 'N/A')}, Test Case Instance: {self.test_case_instance is not None}") # 로그 추가
        self.logger.info(f"[MockIntegrationKiwoom] send_order called. RQName: {rq_name}, Code: {code}, Quantity: {quantity}, Price: {price}, Hoga: {hoga_gb}, OrderType: {order_type}")
        
        call_detail = {
            "rq_name": rq_name, "screen_no": screen_no, "acc_no": acc_no,
            "order_type": order_type, "code": code, "quantity": quantity,
            "price": price, "hoga_gb": hoga_gb, "org_order_no": org_order_no,
            "timestamp": time.time()
        }
        # self.send_order_call_history.append(call_detail) # 여기가 중복될 수 있으므로 아래로 이동
        # self.logger.debug(f"[MockIntegrationKiwoom] Appended to send_order_call_history: {call_detail}, Current history length: {len(self.send_order_call_history)}")
        
        # current_test_id가 초기화되지 않았을 수 있으므로 getattr로 안전하게 접근
        current_test_id = getattr(self, 'current_test_id', None)
        mock_order_no_for_chejan = f"mock_ord_{int(time.time())}_{random.randint(100,999)}" # 체결 데이터에서 사용할 모의 주문번호
        call_detail['generated_order_no'] = mock_order_no_for_chejan # 생성된 주문번호를 call_detail에 저장

        # 테스트 케이스별 send_order 반환 값 제어
        if current_test_id: # current_test_id가 None이 아닌지 확인
            if "test_buy_order_api_error_handling" in current_test_id:
                self.logger.info(f"[MockIntegrationKiwoom] send_order for test_buy_order_api_error_handling. Returning 0 (success). Chejan will carry error. OrderNo for chejan: {mock_order_no_for_chejan}")
                self.send_order_call_history.append(call_detail)
                # self.logger.debug(f"[MockIntegrationKiwoom] API Error Test - Appended to send_order_call_history. Length: {len(self.send_order_call_history)}")
                return 0 # SendOrder 자체는 성공(0)했다고 가정. 체결 데이터에서 오류 발생.
            elif "test_another_scenario_expecting_specific_order_no" in current_test_id: # 예시
                 # 특정 주문번호 반환 시에도 호출 내역 기록
                self.send_order_call_history.append(call_detail)
                # self.logger.debug(f"[MockIntegrationKiwoom] Specific OrderNo Test - Appended to send_order_call_history. Length: {len(self.send_order_call_history)}")
                # 이 경우에도 SendOrder 자체는 성공(0)을 반환하고, 생성된 주문번호는 call_detail['generated_order_no']에 있음
                return 0 # 성공 반환
        
        # 기본적으로 성공(0) 모의
        self.send_order_call_history.append(call_detail) # 모든 경우에 호출 내역 기록
        self.logger.debug(f"[MockIntegrationKiwoom] Default Case - Appended to send_order_call_history. OrderNo for chejan: {mock_order_no_for_chejan}. Length: {len(self.send_order_call_history)}")
        # mock_order_no = f"mock_ord_{int(time.time())}_{random.randint(100,999)}" # 주문번호 중복 방지 강화 -> 위로 이동
        self.logger.info(f"[MockIntegrationKiwoom] send_order default mock. Returning 0 (success). OrderNo for chejan: {mock_order_no_for_chejan}")
        return 0 # 성공(0) 또는 API 에러코드 반환

    def comm_rq_data(self, rq_name, tr_code, prev_next, screen_no):
        self.logger.info(f"[MockIntegrationKiwoom] comm_rq_data: RQName({rq_name}), TRCode({tr_code}), PrevNext({prev_next}), ScreenNo({screen_no})")
        # TR 요청 시 mock_tr_data_handler가 설정되어 있으면 해당 핸들러 호출
        if self.mock_tr_data_handler:
            # 핸들러에 모든 관련 정보 전달 (kwargs 활용 가능)
            # 예: comm_rq_data(self, rq_name, tr_code, prev_next, screen_no, **self.tr_input_values)
            # 여기서는 간단히 필요한 정보만 전달
            code_match = re.search(r"_([0-9A-Z]+)$", rq_name) # rq_name에서 종목코드 추출 (예: "TR_REQ_opt10001_005930")
            code_for_handler = code_match.group(1) if code_match else None
            
            handler_result = self.mock_tr_data_handler(
                rq_name=rq_name, 
                tr_code=tr_code, 
                prev_next=prev_next, 
                screen_no=screen_no,
                code=code_for_handler # rq_name에서 추출한 code 전달
            )
            # 핸들러가 False를 명시적으로 반환하지 않으면, 핸들러가 TR을 처리한 것으로 간주
            if handler_result is not False: 
                self.logger.info(f"[MockIntegrationKiwoom] TR request {rq_name} ({tr_code}) handled by mock_tr_data_handler. Result: {handler_result is not None}")
                # 핸들러가 데이터를 반환하면, 그것이 실제 TR 데이터인 것처럼 TR 시그널을 발생시키거나 current_tr_data에 저장
                # (현재는 mock_tr_data_handler 내부에서 emit 하거나, TestIntegrationScenarios.setUp의 핸들러처럼 동작)
                # 여기서는 핸들러가 직접 emit한다고 가정하고, 성공(0)만 반환
                return 0 # 성공 리턴

        # mock_tr_data_handler가 없거나 False를 반환한 경우, TR 코드에 따라 기본 모의 데이터 생성
        self.logger.info(f"[MockIntegrationKiwoom] TR request {rq_name} ({tr_code}) using default mock generation.")
        data_to_emit = {}
        code_match = re.search(r"_([0-9A-Z]+)$", rq_name) # rq_name에서 종목코드 추출 (예: "TR_REQ_opt10001_005930")
        code = code_match.group(1) if code_match else None

        if tr_code == "opt10001": # 종목기본정보요청
            if code:
                data_to_emit = self._get_mock_basic_info(code)
            else: # 코드 없이 요청된 경우 (예: 전체 시장 정보 등, 여기선 간단히 빈 데이터)
                data_to_emit = {"종목명": "N/A_UNKNOWN_CODE_FOR_OPT10001"}
        elif tr_code == "opt10081": # 주식일봉차트조회
            if code:
                chart_data, _ = self._get_mock_daily_chart_data(code) # is_next는 무시
                # opt10081은 멀티데이터를 포함할 수 있으므로, 실제 API 응답 형식에 맞춰야 함.
                # 여기서는 단순화를 위해 list of dicts를 'multi_data' 키 아래에 넣고,
                # 단일 데이터 필드도 몇 개 추가 (예: '종목코드')
                data_to_emit = {
                    '종목코드': code,
                    'multi_data': chart_data, # TradingStrategy.on_tr_data_received에서 이 부분을 처리해야 함
                    'repeat_cnt': len(chart_data)
                }
            else:
                data_to_emit = {"종목코드": "N/A_UNKNOWN_CODE_FOR_OPT10081", 'multi_data': [], 'repeat_cnt':0}
        elif tr_code == "opw00001": # 예수금상세현황요청
            data_to_emit = {"예수금": "10000000", "총매입금액": "500000"} # 예시 데이터
        elif tr_code == "opw00018": # 계좌평가잔고내역요청
             data_to_emit = {
                "총매입금액": "0", "총평가금액": "0", "총손익금액": "0", "총수익률(%)": "0.00",
                "추정예탁자산": "10000000", "repeat_cnt": 0, "multi_data": []
            }
            # 보유 종목이 있다면 multi_data에 추가하는 로직 필요
            # 예: self.portfolio (실제 KiwoomAPI 클래스에는 없음, 모의용)
            # if hasattr(self, 'portfolio_for_mock_opw00018'): 
            #     multi_data = []
            #     for stock_code, details in self.portfolio_for_mock_opw00018.items():
            #         multi_data.append({
            #             "종목번호": f"A{stock_code}", # 'A' 접두사 포함
            #             "종목명": details.get("종목명", f"모의종목_{stock_code}"),
            #             "보유수량": str(details.get("보유수량", 0)),
            #             "매입가": str(details.get("매입단가", 0)),
            #             "현재가": str(details.get("현재가", 0)),
            #             "평가손익": str(details.get("평가손익", 0)),
            #             "수익률(%)": str(details.get("수익률(%)", "0.00"))
            #         })
            #     data_to_emit["multi_data"] = multi_data
            #     data_to_emit["repeat_cnt"] = len(multi_data)

        else:
            self.logger.warning(f"[MockIntegrationKiwoom] Unhandled TR Code {tr_code} in comm_rq_data mock. Returning empty data.")
            data_to_emit = {"error": f"Unhandled TR: {tr_code}"}

        self.current_tr_data = data_to_emit # 외부에서 조회 가능하도록 설정
        # QTimer.singleShot(10, lambda: self.tr_data_received.emit(rq_name, tr_code, data_to_emit)) # 비동기적으로 TR 응답 시그널 발생
        self.tr_data_received.emit(rq_name, tr_code, data_to_emit) # 동기적으로 발생 (테스트 용이)
        self.logger.info(f"[MockIntegrationKiwoom] Emitted tr_data_received for {rq_name} ({tr_code}). Data: {data_to_emit}")
        return 0 # 성공 리턴

    # --- 추가적인 Mock 메소드 (필요에 따라) ---
    def emit_mock_real_data(self, code, real_type, data):
        """테스트 코드에서 직접 실시간 데이터를 주입하기 위한 메서드"""
        self.logger.info(f"[MockKiwoomInject] Injecting real data: Code({code}), Type({real_type}), Data({data})")
        self.real_data_received.emit(code, real_type, data)
        QApplication.processEvents() # 즉시 처리되도록

    def emit_mock_chejan_data(self, gubun, chejan_data):
        """테스트 코드에서 직접 체결 데이터를 주입하기 위한 메서드"""
        self.logger.info(f"[MockKiwoomInject] Injecting chejan data: Gubun({gubun}), Data({chejan_data})")
        self.chejan_data_received.emit(gubun, chejan_data)
        QApplication.processEvents()

    def simulate_real_data(self, codes, num_packets=1, interval_ms=10):
        """특정 종목들에 대해 지정된 횟수만큼 실시간 데이터를 짧은 간격으로 발생시키는 유틸리티"""
        self.logger.info(f"[MockSimulate] Starting to simulate {num_packets} real data packets for codes {codes} with interval {interval_ms}ms.")
        
        for i in range(num_packets):
            for code in codes:
                # 테스트 케이스별 초기 데이터 가져오기 (여기서도 current_test_id 기반으로 data_source 가져오기)
                data_source = None
                current_test_id = getattr(self, 'current_test_id', None)
                if self.test_case_instance and current_test_id:
                    if "test_concurrent_buy_orders_and_logging" in current_test_id:
                        data_source = getattr(self.test_case_instance, 'initial_stock_data_concurrent', None)
                    # ... (다른 테스트 케이스에 대한 data_source 로드 로직) ...
                
                base_price = 10000 # 기본 기준가
                yesterday_close_for_real = base_price # 실시간 데이터의 기준이 될 전일종가
                
                if data_source and code in data_source:
                    # TR 요청시 current_price 또는 market_open_price 또는 yesterday_close를 실시간 데이터의 기준점으로 사용
                    base_price = data_source[code].get('current_price',
                                            data_source[code].get('market_open_price',
                                                                data_source[code].get('yesterday_close', 10000)))
                    yesterday_close_for_real = data_source[code].get('yesterday_close', base_price)


                price_change = random.randint(-50, 50) + (i * 10) # 시간에 따라 약간 변하도록
                current_mock_price = base_price + price_change
                volume_change = random.randint(10, 100) + (i * 5)
                real_type = "주식체결" # 기본값

                real_data_packet = {
                    '10': str(current_mock_price),
                    '11': str(current_mock_price - yesterday_close_for_real), # 전일대비는 실제 전일종가 기준
                    '12': f"{((current_mock_price / yesterday_close_for_real - 1) * 100) if yesterday_close_for_real else 0:.2f}",
                    '13': str(volume_change),
                    '15': str(base_price + 50), # 시가 (TR 요청시 market_open_price 사용)
                    '16': str(base_price + 100 + (int(code) % 50)), # 고가
                    '17': str(base_price - 100 - (int(code) % 50)), # 저가
                }
                self.logger.info(f"[MockSimulate] Emitting real_data_received for {code}: {real_data_packet}")
                self.real_data_received.emit(code, real_type, real_data_packet)
            
            if interval_ms > 0 : # 마지막 패킷 후에는 대기하지 않음
                 if i < num_packets -1 : # 마지막 루프 제외
                    QTest.qWait(interval_ms) # 여기서 QTest.qWait 사용
                    QApplication.processEvents() # 이벤트 처리

        self.logger.info(f"[MockSimulate] Finished simulating real data for codes {codes}.")


class TestIntegrationScenarios(unittest.TestCase):
    app = None
    # 클래스 변수로 test_logger 초기화
    test_logger = Logger(log_file="logs/test_integration_log.txt", log_level=logging.DEBUG)
    event_timer = None

    @classmethod
    def setUpClass(cls):
        cls.test_logger.info("TestIntegration: Starting setUpClass...")
        if QApplication.instance() is None:
            cls.app = QApplication(sys.argv)
            cls.test_logger.info("TestIntegration: QApplication instance created.")
        else:
            cls.app = QApplication.instance()
            cls.test_logger.info("TestIntegration: QApplication instance already exists.")
        
        # QTimer를 사용하여 주기적으로 processEvents 호출
        cls.event_timer = QTimer()
        cls.event_timer.setInterval(50) # 50ms 마다
        cls.event_timer.timeout.connect(lambda: QApplication.processEvents())
        cls.event_timer.start()
        cls.test_logger.info("TestIntegration: QApplication.processEvents() timer started.")


    @classmethod
    def tearDownClass(cls):
        cls.test_logger.info("TestIntegration: Starting tearDownClass...")
        if hasattr(cls, 'event_timer') and cls.event_timer.isActive():
            cls.event_timer.stop()
            cls.test_logger.info("TestIntegration: QApplication.processEvents() timer stopped.")
        
        app_instance = QApplication.instance()
        if app_instance:
            app_instance.quit()
            cls.test_logger.info("TestIntegration: QApplication.instance().quit() called.")

        # QApplication.quit() # 테스트 전체 종료 시 필요할 수 있으나, 개별 테스트에선 문제될 수 있음
        # cls.app = None
        cls.test_logger.info("TestIntegration: Finished tearDownClass.")

    def setUp(self):
        current_test_id = self.id()
        self.test_logger.info(f"--- Starting test: {current_test_id} ---")
        # 각 테스트에 대한 로거 설정 (기존 로거 사용 또는 테스트별 로거 생성)
        self.logger = TestIntegrationScenarios.test_logger 
        self.logger.info(f"setUp for {current_test_id} completed. Logger assigned to self.logger.")

        # QApplication 인스턴스 생성 또는 가져오기
        self.app = QApplication.instance() if QApplication.instance() else QApplication(sys.argv)
        
        # 설정 로드
        self.config = ConfigManager(config_file='settings_test.json')
        self.config.load_settings()

        # 모의 Kiwoom API 생성 및 test_case_instance 전달
        self.mock_kiwoom = MockKiwoomAPIForIntegration(test_case_instance=self, logger=self.logger)
        self.mock_kiwoom.connected = True # <--- 이 줄 추가
        self.mock_kiwoom.account_number = self.config.get_setting('계좌정보', '계좌번호') # 계좌번호도 여기서 명시적 설정
        
        self.db_path = self.config.get_setting('Database', 'path', 'logs/trading_data.test.db')
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

        self.database = Database(self.db_path) # Database 인스턴스 생성 (로거 인자 제거)
        # self.database.connect() # __init__에서 initialize_db 호출 (내부에서 connect)
        # self.database.create_tables() # __init__에서 initialize_db 호출 (내부에서 테이블 생성)

        # TradingStrategy 인스턴스를 먼저 생성
        self.strategy = TradingStrategy(kiwoom_api=self.mock_kiwoom, config_manager=self.config, logger=self.logger, db_manager=self.database, main_window_instance=None) 
        # TradingStrategy 객체 생성 직후 market_open/close_time 강제 설정
        self.strategy.market_open_time = datetime.strptime("00:00:00", "%H:%M:%S").time()
        self.strategy.market_close_time = datetime.strptime("23:59:59", "%H:%M:%S").time()
        self.logger.info(f"[TEST_SETUP_OVERRIDE_AFTER_STRATEGY_INIT] Market open/close times FORCED after strategy init: {self.strategy.market_open_time} - {self.strategy.market_close_time}")
        # main_window_instance는 나중에 main_window 객체로 설정될 수 있음 (순환 참조 방지)

        # MainWindow 생성 시 strategy도 내부적으로 생성됨
        self.main_window = MainWindow(kiwoom_api=self.mock_kiwoom, config_manager=self.config, strategy=self.strategy, logger=self.logger, db=self.database)
        # MainWindow 내부에서 self.strategy를 사용하므로, MainWindow 생성 전에 self.strategy가 먼저 존재해야 함.
        # 하지만 현재 MainWindow가 strategy를 내부적으로 생성하고, self.strategy = self.main_window.strategy로 가져오는 방식임.
        # MainWindow 생성자에 strategy를 전달하는 것은 원래 설계와 다를 수 있음. MainWindow가 strategy를 직접 생성하도록 두는 것이 맞다면,
        # self.strategy 인스턴스를 MainWindow 생성 전에 만들 필요는 없음. 지금은 일단 전달하는 방식으로 수정.
        # --> 이전 코드 self.strategy = self.main_window.strategy 이므로, MainWindow가 strategy를 생성하고 이를 가져오는 것이 맞음.
        # 따라서 MainWindow 생성자에서 strategy 인자를 제거하고, 이전처럼 main_window.strategy를 사용해야 함.
        # MainWindow.__init__ 시그니처에 strategy가 있으므로, 일단 전달하는 것으로 유지. 다만, 순환 참조나 이중 생성 가능성 검토 필요.

        # 이전 방식 복원:
        # self.main_window = MainWindow(kiwoom_api=self.mock_kiwoom, config_manager=self.config, logger=self.logger, db=self.database)
        # self.strategy = self.main_window.strategy 
        # --> MainWindow가 strategy를 받도록 되어 있으므로, 위 코드가 아닌 현재 수정된 코드가 맞음.

        # self.strategy = self.main_window.strategy # MainWindow가 생성한 strategy를 가져옴 (이 줄은 이제 불필요)
        self.strategy.main_window = self.main_window # TradingStrategy에 MainWindow 인스턴스 연결
        self.logger.info(f"[TEST_SETUP_STRATEGY_ID] Strategy instance ID in setUp: {id(self.strategy)}")

        # 테스트를 위해 장운영 시간을 항상 열려 있도록 설정 (위에서 strategy 생성 직후 수행함)
        # # 이 시점에서 self.strategy는 MainWindow 내부의 strategy와 동일한 인스턴스여야 함
        # self.strategy.market_start_time = datetime.strptime("00:00:00", "%H:%M:%S").time()
        # self.strategy.market_end_time = datetime.strptime("23:59:59", "%H:%M:%S").time()
        # self.logger.info(f"[TEST_SETUP_OVERRIDE] Market open/close times overridden for test: {self.strategy.market_start_time} - {self.strategy.market_end_time}")

        # TR 데이터 처리를 위한 mock 핸들러 설정은 각 테스트 메서드에서 수행하도록 변경
        # # self.mock_kiwoom.mock_tr_data_handler = self.default_mock_tr_data_handler
        # # self.logger.info("TestIntegration.setUp: Default mock_tr_data_handler assigned.")
        # # self.mock_kiwoom.mock_tr_data_handler = self.mock_tr_handler_setup
        # # self.logger.info("TestIntegration.setUp: mock_tr_data_handler assigned in setUp.")

        # 기본 TR 데이터 핸들러 정의
        def default_mock_tr_data_handler(rq_name, tr_code, prev_next=None, screen_no=None, **kwargs):
            self.logger.info(f"[DefaultMockTRHandler] Received TR request: {rq_name}, {tr_code}")
            if tr_code == "opw00001": # 예수금상세현황요청
                account_no_from_config = self.config.get_setting('계좌정보', '계좌번호')
                # 실제 계좌번호가 설정 파일에 있는지 확인 (없으면 Strategy의 account_number가 None이 됨)
                if not account_no_from_config:
                    self.logger.warning(f"[DefaultMockTRHandler] Account number not found in config.ini.test. 예수금 TR 응답에 계좌번호 포함되지 않음.")

                data_to_emit = {
                    "예수금": "10000000", 
                    "총매입금액": "0",
                    "총평가금액": "0",
                    "D+2추정예수금": "10000000",
                    # KiwoomAPI.get_account_info()에서 사용하는 다른 필드들도 필요시 추가
                }
                # emit을 여기서 직접 할 수도 있고, comm_rq_data의 기본 로직을 탈 수도 있음.
                # 여기서는 comm_rq_data의 기본 로직을 타도록 데이터를 반환 (또는 comm_rq_data가 직접 emit 하도록 수정)
                # KiwoomAPI.get_account_info -> comm_rq_data -> (handler or _get_mock_xxx)
                # comm_rq_data에서 self.tr_data_received.emit을 하므로, 여기서는 True만 반환해도 될 수 있음.
                # 또는, get_account_info가 반환값을 기대한다면 여기서 data_to_emit을 반환해야 함.
                # 현재 MockKiwoomAPIForIntegration.comm_rq_data는 핸들러가 False가 아니면 0을 반환하고, 핸들러 내부에서 emit 하도록 기대.
                # 따라서, 여기서 emit을 하거나, comm_rq_data의 기본 동작을 수정해야 함.
                # 가장 간단한 방법은 comm_rq_data의 기본 동작이 opw00001을 처리하도록 두거나, 여기서 emit하는 것.

                # comm_rq_data에서 emit을 하도록 유도 (핸들러는 데이터만 준비)
                # self.mock_kiwoom.current_tr_data = data_to_emit # comm_rq_data가 이걸 사용하도록 할 수도 있음
                # 또는 핸들러가 직접 emit
                self.mock_kiwoom.tr_data_received.emit(rq_name, tr_code, data_to_emit)
                self.logger.info(f"[DefaultMockTRHandler] Emitted mock data for opw00001: {data_to_emit}")
                return True # 핸들러가 처리했음을 알림 (comm_rq_data는 추가 작업 안 함)
            
            elif tr_code == "opw00018": # 계좌평가잔고내역요청 (기본 빈 상태)
                data_to_emit = {
                    "총매입금액": "0", "총평가금액": "0", "총손익금액": "0", "총수익률(%)": "0.00",
                    "추정예탁자산": self.strategy.account_info.get('예수금', "10000000"), # 예수금 정보가 이미 있다면 사용
                    "repeat_cnt": 0, "multi_data": []
                }
                self.mock_kiwoom.tr_data_received.emit(rq_name, tr_code, data_to_emit)
                self.logger.info(f"[DefaultMockTRHandler] Emitted mock data for opw00018: {data_to_emit}")
                return True

            # 기본적으로 처리 안 함을 명시 (다른 핸들러나 MockKiwoomAPI의 기본 TR 처리 로직이 있다면 그쪽으로 넘어감)
            self.logger.warning(f"[DefaultMockTRHandler] Unhandled TR Code: {tr_code} by default handler.")
            return False

        self.mock_kiwoom.mock_tr_data_handler = default_mock_tr_data_handler
        self.logger.info("TestIntegration.setUp: Default mock_tr_data_handler assigned.")

        # 테스트별 초기 데이터 설정
        # test_concurrent_buy_orders_and_logging
        self.initial_stock_data_concurrent = {
            "000020": {"yesterday_close": 10000, "market_open_price": 10100, "current_price": 10050, "name": "테스트종목_000020"}, # 조건1충족, 조건2 미충족 -> READY 대기
            "000040": {"yesterday_close": 20000, "market_open_price": 20100, "current_price": 19900, "name": "테스트종목_000040"}, # 조건1충족, 조건2 미충족 -> READY 대기
            "000060": {"yesterday_close": 30000, "market_open_price": 30100, "current_price": 28900, "name": "테스트종목_000060"}  # 조건1충족 (시가>종가) -> IDLE (초기화시, 실시간 데이터로 READY 변경 기대)
        }
        # test_buy_order_api_error_handling
        self.initial_stock_data_buy_error = {
            "000070": {"yesterday_close": 11000, "market_open_price": 11100, "current_price": 10900, "name": "테스트_API오류종목"} # 조건1충족, 조건2 미충족 -> READY 대기
        }
        # test_realtime_data_format_error_handling
        # 기본값으로 TR/실시간 데이터가 생성되도록 여기서는 특별히 설정 안 함.
        # 또는, 특정 초기값을 설정하여 해당 종목이 필터링되거나 기본 처리되도록 유도할 수 있음
        self.initial_stock_data_realtime_error = {
            "000100": {"yesterday_close": 5000, "market_open_price": 5000, "current_price": 5000, "name": "정상종목"}, # 조건 미충족
            "000200": {"yesterday_close": 5000, "market_open_price": 5000, "current_price": 5000, "name": "형식오류종목"},# 조건 미충족
            "000300": {"yesterday_close": 5000, "market_open_price": 5000, "current_price": 5000, "name": "누락종목"}  # 조건 미충족
        }
        # test_tr_data_request_error_handling
        self.initial_stock_data_tr_error = {
            "005930": {"name": "테스트_TR오류종목"} # TR 요청시 오류 발생 예상
        }
        # test_full_trading_cycle_with_realtime_data
        self.initial_stock_data_full_cycle = {
            "000660": { # SK하이닉스
                "name": "SK하이닉스",
                "yesterday_close": 142000,  # 전일 종가 (매수 조건2 기준)
                "market_open_price": 150000, # 당일 시가 (매수 조건1 기준)
                "current_price": 150000,   # TR 요청 시점 현재가 (초기값)
                "high_price": 155000,      # TR 데이터용 고가 (일봉 데이터용)
                "low_price": 148000,       # TR 데이터용 저가 (일봉 데이터용)
                "volume": 100000           # TR 데이터용 거래량 (일봉 데이터용)
            }
        }

        # 기본 TR 데이터 핸들러 (계좌 정보 등 공통 처리)
        # self.mock_kiwoom.mock_tr_data_handler = lambda rq_name, tr_code, prev_next, screen_no, **kwargs: \\
        #     self.default_mock_tr_data_handler(rq_name, tr_code, prev_next, screen_no, **kwargs)
        
        # setUp에서 공통적으로 mock_tr_data_handler를 설정합니다.
        # 각 테스트 메소드 내에서 이 핸들러를 필요에 따라 오버라이드 할 수 있습니다.


        # 로그인 완료 시그널 발생시켜 계좌정보 로드 유도
        self.logger.info(f"TestIntegration.setUp: Emitting login_completed signal with account_number: {self.config.get_setting('계좌정보', '계좌번호')}")
        self.mock_kiwoom.login_completed.emit(self.config.get_setting('계좌정보', '계좌번호'))
        QApplication.processEvents() # 시그널 처리 대기
        QTest.qWait(100) # 추가 대기 시간
        self.logger.info("TestIntegration.setUp: Events processed after login_completed. Account info should be loaded if mock_tr_handler worked.")

        self.main_window.load_initial_data() # 초기 데이터 로드 (관심종목, 거래내역 등) - DB 의존
        
        # 전략 타이머 시작 (주기적인 check_conditions 호출)
        # self.main_window.start_strategy_timer() # 실제 타이머 대신 테스트에서 직접 check_conditions 호출
                                                # 또는 모의 타이머 사용 고려
        self.strategy.start() # TradingStrategy의 자동매매 로직 및 이벤트 루프(타이머) 시작
        
        self.logger.info(f"TestIntegration: Finished setUp. Deposit: {self.strategy.account_info.get('예수금')}")

    def tearDown(self):
        self.test_logger.info("TestIntegration: Starting tearDown...")
        # 모든 QTimer 중지 시도 (MockKiwoomAPI 내부 타이머 포함)
        if hasattr(self.mock_kiwoom, '_mock_real_data_timer') and self.mock_kiwoom._mock_real_data_timer:
            self.mock_kiwoom._mock_real_data_timer.stop()
            
        if hasattr(self.strategy, 'check_timer') and self.strategy.check_timer:
            self.strategy.check_timer.stop()

        # Clear watchlist in strategy and DB
        if hasattr(self, 'strategy') and self.strategy:
            current_watchlist = list(self.strategy.watchlist.keys())
            for code in current_watchlist:
                self.strategy.remove_from_watchlist(code) # This should also handle DB
                if self.database:
                    self.database.remove_watchlist_item(code)
        QApplication.processEvents()

        # MainWindow 참조를 먼저 해제
        if hasattr(self, 'main_window') and self.main_window:
            self.main_window.close()
            self.main_window = None # 참조 해제
            QApplication.processEvents() # 창이 완전히 닫히도록 함
            # self.main_window.deleteLater() # 명시적 삭제

        # Reset mocks, especially for emitters or persistent state
        if hasattr(self, 'mock_kiwoom'):
             self.mock_kiwoom.send_order_call_history.clear()
             self.mock_kiwoom.subscribed_real_data.clear()
             # self.mock_kiwoom._mock_stock_data_cache.clear() # 해당 속성이 없으므로 제거
             self.mock_kiwoom._mock_real_data_active_screens.clear()
             if self.mock_kiwoom._mock_real_data_timer:
                 self.mock_kiwoom._mock_real_data_timer.stop()


        # Reset strategy state if it's persistent across tests or if instance is reused
        if hasattr(self, 'strategy'):
            self.strategy.watchlist.clear()
            self.strategy.portfolio.clear()
            self.strategy.strategy_state.clear()
            self.strategy.buy_prices.clear()
            self.strategy.buy_quantities.clear()
            self.strategy.high_prices.clear()
            self.strategy.order_sent_flags.clear()
            self.strategy.current_real_data_count = 0
            self.strategy.suppress_signals_for_test = False # 기본값으로 복원
            if self.strategy.is_running:
                self.strategy.stop()
        
        # Add database close
        if hasattr(self, 'database') and self.database:
            self.database.close()
            self.logger.info("Database connection closed in tearDown.")
            del self.database # 데이터베이스 객체 참조 명시적 제거
            QTest.qWait(50) # 파일 핸들 해제를 위한 짧은 대기 (50ms)
            self.logger.info("Database object deleted and waited in tearDown.")

        QApplication.processEvents()
        self.test_logger.info("TestIntegration: Finished tearDown.")

    def test_full_trading_cycle_with_realtime_data(self):
        self.test_logger.info("Starting test_full_trading_cycle_with_realtime_data")
        try:
            # --- 시나리오 준비 ---
            code_to_test = "000660" 
            name_to_test = "SK하이닉스"
            target_screen_no = "2060" 

            self.strategy.suppress_signals_for_test = True

            # --- 1. 계좌 정보 로드 확인 (setUp에서 이미 로드 시도됨) ---
            self.test_logger.info("[TC_CYCLE] Step 1: Verifying Account Info Load (initiated in setUp)...")

            # 예수금 정보가 로드될 때까지 최대 5초 대기 (setUp에서 이미 처리되었을 가능성 높음)
            load_timeout_ms = 5000 
            start_time = time.monotonic()
            if self.strategy.account_info.get('예수금', 0) <= 0: # setUp에서 로드 안됐을 경우 대비
                self.test_logger.info(f"[TC_CYCLE] Deposit info not yet loaded from setUp. Waiting (max {load_timeout_ms}ms). Current: {self.strategy.account_info.get('예수금', 0)}")
                while self.strategy.account_info.get('예수금', 0) <= 0 and (time.monotonic() - start_time) * 1000 < load_timeout_ms:
                    QApplication.processEvents() 
                    time.sleep(0.05) 
            
            if self.strategy.account_info.get('예수금', 0) <= 0:
                self.test_logger.error(f"[TC_CYCLE] TIMEOUT or FAILED to load deposit info. Current: {self.strategy.account_info.get('예수금', 0)}")
            else:
                self.test_logger.info(f"[TC_CYCLE] Deposit info verified/loaded: {self.strategy.account_info.get('예수금')}")
            
            self.assertGreater(self.strategy.account_info.get('예수금', 0), 0, "예수금 정보가 로드되어야 합니다.")
            self.assertEqual(len(self.strategy.portfolio), 0, "초기 포트폴리오는 비어있어야 합니다.")
            self.test_logger.info(f"[TC_CYCLE] Account info loaded: 예수금({self.strategy.account_info.get('예수금')}), 포트폴리오 개수({len(self.strategy.portfolio)})")

            # --- 관심종목/일봉 데이터용 TR 핸들러 확장/설정 ---
            # 기존 setUp의 핸들러를 저장해두고, 이 테스트에 필요한 부분만 추가/변경한 새 핸들러를 설정
            original_tr_handler = self.mock_kiwoom.mock_tr_data_handler

            def mock_tr_handler_for_test_cycle(rq_name, tr_code, prev_next=None, screen_no=None, **kwargs):
                self.test_logger.info(f"[MockTRHandler_Cycle] Test-specific TR: rq_name={rq_name}, tr_code={tr_code}")
                if tr_code == "opt10001":
                    code_arg = kwargs.get('code')
                    current_data_for_tr = {
                        '현재가': "150000", '종목명': name_to_test if code_arg == code_to_test else f"테스트종목_{code_arg}", '등락율': "0.00"
                    }
                    data_to_emit = {
                        'tr_code': tr_code,
                        'opt10001': current_data_for_tr
                    }
                    self.mock_kiwoom.current_tr_data = data_to_emit # 필요 시 설정
                    self.test_logger.info(f"[MockTRHandler_Cycle] Mocking opt10001 for {code_arg}. Emitting.")
                    self.mock_kiwoom.tr_data_received.emit(rq_name, tr_code, data_to_emit)
                    return current_data_for_tr # opt10001 데이터 부분 반환 (KiwoomAPI.get_stock_basic_info 반환타입과 유사)
                elif tr_code == "opt10081":
                    code_arg = kwargs.get('code')
                    mock_daily_data_parsed = [
                        {'일자': datetime.now().strftime('%Y%m%d'), '시가': 150000, '고가': 155000, '저가': 148000, '종가': 152000, '거래량': 100000},
                        {'일자': (datetime.now() - timedelta(days=1)).strftime('%Y%m%d'), '시가': 140000, '고가': 145000, '저가': 138000, '종가': 142000, '거래량': 120000},
                        {'일자': (datetime.now() - timedelta(days=2)).strftime('%Y%m%d'), '시가': 130000, '고가': 135000, '저가': 128000, '종가': 132000, '거래량': 110000},
                    ]
                    data_to_emit = {
                        'tr_code': tr_code,
                        'multi_data': mock_daily_data_parsed,
                        'repeat_cnt': len(mock_daily_data_parsed)
                    }
                    self.mock_kiwoom.current_tr_data = data_to_emit # 필요 시 설정
                    self.test_logger.info(f"[MockTRHandler_Cycle] Mocking opt10081 for {code_arg}. Emitting.")
                    self.mock_kiwoom.tr_data_received.emit(rq_name, tr_code, data_to_emit)
                    is_next_page = prev_next == '2' 
                    return mock_daily_data_parsed, is_next_page
                elif tr_code == "opw00018": # 계좌평가잔고내역 (이 테스트 사이클용)
                    self.test_logger.info(f"[MockTRHandler_Cycle] Mocking opw00018 for test cycle. Current strategy portfolio: {self.strategy.portfolio}")
                    multi_data = []
                    total_purchase_amount = 0
                    total_eval_amount = 0
                    for code, item in self.strategy.portfolio.items():
                        multi_data.append({
                            "종목번호": f"A{code}", # 'A' 접두사 포함
                            "종목명": item.get('종목명', f'TestStock_{code}'),
                            "보유수량": str(item.get('보유수량', 0)),
                            "매입가": str(item.get('매입가', 0)),
                            "현재가": str(item.get('현재가', item.get('매입가', 0))), # 현재가는 매입가 또는 API에서 받은 현재가 사용
                            "평가손익": str( (item.get('현재가', item.get('매입가',0)) - item.get('매입가',0)) * item.get('보유수량',0) ),
                            "수익률(%)": str( ((item.get('현재가', item.get('매입가',0)) / item.get('매입가',0) - 1) * 100) if item.get('매입가',0) > 0 else "0" )
                        })
                        total_purchase_amount += item.get('매입가', 0) * item.get('보유수량', 0)
                        total_eval_amount += item.get('현재가', item.get('매입가', 0)) * item.get('보유수량', 0)
                    
                    data_to_emit = {
                        'tr_code': tr_code,
                        'opw00018': {
                            '총매입금액': str(total_purchase_amount),
                            '총평가금액': str(total_eval_amount),
                            '총평가손익금액': str(total_eval_amount - total_purchase_amount),
                            '총수익률(%)': "0", # 간단하게 0으로 설정 또는 계산
                            '추정예탁자산': str(self.strategy.account_info.get('예수금',0) + total_eval_amount), # 예수금 + 평가금액
                            'repeat_cnt': len(multi_data),
                            'multi_data': multi_data
                        }
                    }
                    self.mock_kiwoom.current_tr_data = data_to_emit
                    self.test_logger.info(f"[MockTRHandler_Cycle] Mocking opw00018 with {len(multi_data)} items. Emitting.")
                    self.mock_kiwoom.tr_data_received.emit(rq_name, tr_code, data_to_emit)
                    return True # 핸들러가 처리했음을 알림

                # 이 테스트용 핸들러에서 처리하지 않은 TR은 setUp에 설정된 핸들러로 전달
                if original_tr_handler:
                    self.test_logger.debug(f"[MockTRHandler_Cycle] Passing TR {tr_code} to original_tr_handler.")
                    return original_tr_handler(rq_name, tr_code, prev_next, screen_no, **kwargs)
                return False # 기본적으로 처리 안 함
            
            self.mock_kiwoom.mock_tr_data_handler = mock_tr_handler_for_test_cycle
            self.test_logger.info("[TC_CYCLE] Test-specific TR handler (for opt10001, opt10081) set.")

            # --- 2. 관심 종목 추가 및 실시간 데이터 구독 ---
            self.test_logger.info(f"[TC_CYCLE] Step 2: Adding watchlist item {name_to_test}({code_to_test}) and subscribing to real-time data...")
            
            # mock_tr_handler가 opt10001과 opt10081에 대한 응답을 제공하므로, _mock_stock_data_cache 직접 조작 불필요
            init_success = self.strategy.initialize_stock_data(code_to_test, name_to_test, screen_no=target_screen_no)
            QApplication.processEvents() # initialize_stock_data 내 TR 요청(opt10001, opt10081) 처리
            
            self.assertTrue(init_success, f"{name_to_test}({code_to_test}) 관심종목 초기화에 성공해야 합니다.")
            self.assertIn(code_to_test, self.strategy.watchlist, f"{code_to_test}가 watchlist에 있어야 합니다.")
            self.assertIn(target_screen_no, self.mock_kiwoom._mock_real_data_active_screens, f"화면번호 {target_screen_no}이 active_screens에 등록되어야 합니다.")
            self.assertIn(code_to_test, self.mock_kiwoom._mock_real_data_active_screens[target_screen_no]['codes'], f"{code_to_test}가 화면번호 {target_screen_no}의 구독 목록에 있어야 합니다.")
            
            # mock_tr_handler에서 opt10081로 제공한 값을 기준으로 검증
            # mock_daily_data_parsed[1]['종가']는 어제 종가, mock_daily_data_parsed[0]['시가']는 오늘 시가
            expected_yesterday_close = 142000 
            expected_today_open = 150000
            self.assertEqual(self.strategy.watchlist[code_to_test]['yesterday_close'], expected_yesterday_close, "어제 종가 불일치")
            self.assertEqual(self.strategy.watchlist[code_to_test]['market_open_price'], expected_today_open, "오늘 시가 불일치") # 'today_open' -> 'market_open_price'
            self.test_logger.info(f"[TC_CYCLE] Watchlist item added. Watchlist: {self.strategy.watchlist.get(code_to_test)}")

            # --- 3. 실시간 시세 수신 및 매수 조건 감지 ---
            self.test_logger.info(f"[TC_CYCLE] Step 3: Receiving real-time data and detecting buy condition for {name_to_test}({code_to_test})...")
            
            # 조건 1: 현재가 < 전일 종가 (expected_yesterday_close)
            price_below_yesterday_close = expected_yesterday_close - 500
            self.mock_kiwoom.real_data_received.emit(code_to_test, "주식시세", {'현재가': price_below_yesterday_close}) # real_data_updated -> real_data_received
            QApplication.processEvents()
            QTest.qWait(50) # 시그널 처리를 위한 충분한 시간 대기
            self.assertTrue(self.strategy.watchlist[code_to_test].get('below_yesterday_close'), "below_yesterday_close 플래그가 True여야 합니다.")
            
            # 조건 2: 현재가 > 전일 종가 (돌파) -> READY 상태로 변경
            price_crossed_yesterday_close = expected_yesterday_close + 500 # 매수 트리거 가격
            initial_real_data_count = self.strategy.current_real_data_count
            
            self.mock_kiwoom.real_data_received.emit(code_to_test, "주식시세", {'현재가': price_crossed_yesterday_close}) # real_data_updated -> real_data_received
            QApplication.processEvents()
            QTest.qWait(50) # 시그널 처리를 위한 충분한 시간 대기
            
            self.assertGreater(self.strategy.current_real_data_count, initial_real_data_count, "실시간 데이터 카운트가 증가해야 합니다.")
            self.assertEqual(self.strategy.watchlist[code_to_test]['current_price'], price_crossed_yesterday_close)
            self.assertTrue(self.strategy.watchlist[code_to_test].get('crossed_yesterday_close'), "crossed_yesterday_close 플래그가 True여야 합니다.")
            
            # 당일 시가 (expected_today_open) > 전일 종가 (expected_yesterday_close) 조건 확인
            self.assertGreater(self.strategy.watchlist[code_to_test]['market_open_price'], self.strategy.watchlist[code_to_test]['yesterday_close'], "당일 시가가 전일 종가보다 높아야 매수 조건 충족 가능") # 'today_open' -> 'market_open_price'
            self.assertEqual(self.strategy.strategy_state.get(code_to_test), TradingStrategy.TradingState.READY, "매수 조건 충족 시 상태는 READY여야 합니다.")
            self.test_logger.info(f"[TC_CYCLE] Price crossed yesterday's close. Current price: {price_crossed_yesterday_close}. State: {self.strategy.strategy_state.get(code_to_test)}")

            # --- 4. 매수 주문 실행 및 체결 처리 ---
            self.test_logger.info(f"[TC_CYCLE] Step 4: Executing buy order and processing execution for {name_to_test}({code_to_test})...")
            
            # check_conditions 호출 직전에 장운영 시간 강제 설정
            self.strategy.market_open_time = datetime.strptime("00:00:00", "%H:%M:%S").time() # market_start_time -> market_open_time
            self.strategy.market_close_time = datetime.strptime("23:59:59", "%H:%M:%S").time() # market_end_time -> market_close_time
            self.logger.info(f"[TC_CYCLE_FORCE_TIME] Market times forced before check_conditions: {self.strategy.market_open_time} - {self.strategy.market_close_time}") # 변수명 수정

            self.strategy.check_conditions() 
            QApplication.processEvents()

            self.assertTrue(self.mock_kiwoom.send_order_call_history, "매수 주문이 전송되어야 합니다.")
            sent_buy_order = None
            for order_call in reversed(self.mock_kiwoom.send_order_call_history):
                if order_call['code'] == code_to_test and order_call['order_type'] == 1:
                    sent_buy_order = order_call
                    break
            self.assertIsNotNone(sent_buy_order, f"{code_to_test}에 대한 매수 주문 기록을 찾을 수 없습니다.")

            self.assertEqual(sent_buy_order['code'], code_to_test)
            self.assertEqual(sent_buy_order['order_type'], 1) # 신규매수
            self.assertIn(code_to_test, self.strategy.order_sent_flags, "매수 주문 플래그가 설정되어야 합니다.")
            self.test_logger.info(f"Buy order sent for {name_to_test}({code_to_test}). RQ_NAME: {sent_buy_order['rq_name']}")
            
            buy_price = price_crossed_yesterday_close
            buy_quantity = self.config.get_setting('매수금액') // buy_price
            
            chejan_data_buy = {
                '9001': f"A{code_to_test}", '302': name_to_test, '907': '+매수',
                '913': '체결', '910': str(buy_price), '911': str(buy_quantity),
                '9201': sent_buy_order['rq_name'],
                '9203': 'ORDER001_BUY'
            }
            self.mock_kiwoom.chejan_data_received.emit('0', chejan_data_buy)
            QApplication.processEvents()

            self.assertEqual(self.strategy.strategy_state.get(code_to_test), TradingStrategy.TradingState.BOUGHT)
            self.assertIn(code_to_test, self.strategy.portfolio)
            self.assertEqual(self.strategy.portfolio[code_to_test]['보유수량'], buy_quantity)
            self.assertEqual(self.strategy.portfolio[code_to_test]['매입가'], buy_price)
            db_buy_trades = self.database.get_trades(code=code_to_test, trade_type='매수') # DB 조회 수정
            self.assertEqual(len(db_buy_trades), 1, "DB에 매수 거래 내역이 1건 기록되어야 합니다.")
            self.test_logger.info(f"[TC_CYCLE] Buy order executed. Portfolio: {self.strategy.portfolio.get(code_to_test)}. DB Trades: {db_buy_trades}")

            # --- 5. (선택 사항) 매도 조건 감지, 매도 주문 실행 및 체결 처리 (익절 시나리오) ---
            self.test_logger.info(f"[TC_CYCLE] Step 5: Detecting sell condition (profit-taking) and processing for {name_to_test}({code_to_test})...")
            profit_take_rate = self.config.get_setting('매매전략', '익절_수익률') / 100.0 # 수정: get_setting 사용
            profit_sell_price = int(buy_price * (1 + profit_take_rate + 0.005)) 
            
            self.mock_kiwoom.real_data_received.emit(code_to_test, "주식시세", {'현재가': profit_sell_price}) # real_data_updated -> real_data_received
            QApplication.processEvents()
            QTest.qWait(50) # 시그널 처리 대기
            self.strategy.check_conditions() 
            QApplication.processEvents()
            QTest.qWait(50) # 시그널 처리 대기 (check_conditions가 추가 시그널을 발생시킬 수 있으므로)

            sell_order_key = f"sell_{code_to_test}"
            self.assertIn(sell_order_key, self.strategy.order_sent_flags, "익절 매도 주문 플래그가 설정되어야 합니다.")
            sent_sell_order_profit = None
            for order_call in reversed(self.mock_kiwoom.send_order_call_history):
                if order_call['code'] == code_to_test and order_call['order_type'] == 2:
                    sent_sell_order_profit = order_call
                    break
            self.assertIsNotNone(sent_sell_order_profit, f"{code_to_test}에 대한 익절 매도 주문 기록을 찾을 수 없습니다.")
            
            self.assertEqual(sent_sell_order_profit['code'], code_to_test)
            self.assertEqual(sent_sell_order_profit['order_type'], 2) 
            
            sell_ratio_conf = self.config.get_setting('매매전략', '익절_매도비율') / 100.0 # 수정: get_setting 사용
            expected_sell_quantity_profit = int(buy_quantity * sell_ratio_conf)
            self.assertEqual(sent_sell_order_profit['quantity'], expected_sell_quantity_profit, "익절 매도 수량이 예상과 일치해야 합니다.")

            sell_order_rq_name_profit = sent_sell_order_profit['rq_name']
            sell_order_number_mock_profit = f"mock_sell_profit_{int(time.time())}"
            
            chejan_data_sell_profit_executed = {
                '9001': f"A{code_to_test}", '302': name_to_test,
                '9201': sell_order_rq_name_profit,
                '913': '체결', '907': '-매도',
                '911': str(expected_sell_quantity_profit), '910': str(profit_sell_price),
                '9203': sell_order_number_mock_profit
            }
            self.mock_kiwoom.chejan_data_received.emit('0', chejan_data_sell_profit_executed)
            QApplication.processEvents()

            self.assertNotIn(sell_order_key, self.strategy.order_sent_flags, "익절 체결 후 매도 주문 플래그가 해제되어야 합니다.")
            self.assertEqual(self.strategy.strategy_state.get(code_to_test), TradingStrategy.TradingState.PARTIAL_SOLD, "부분 익절 후 상태는 PARTIAL_SOLD여야 합니다.")
            remaining_quantity_after_profit_sell = buy_quantity - expected_sell_quantity_profit
            self.assertEqual(self.strategy.portfolio[code_to_test]['보유수량'], remaining_quantity_after_profit_sell)
            self.assertEqual(self.strategy.high_prices.get(code_to_test), profit_sell_price, "부분 익절 후 고점은 익절 가로 업데이트되어야 합니다.")
            
            db_sell_trades_profit = self.database.get_trades(code=code_to_test, trade_type='매도', trade_reason=f"익절({int(self.config.get_setting('매매전략', '익절_매도비율'))}%)") # 수정: get_setting 사용
            self.assertEqual(len(db_sell_trades_profit), 1, "DB에 익절 매도 거래 내역이 1건 기록되어야 합니다.")
            self.test_logger.info(f"[TC_CYCLE] Profit-taking sell executed. Portfolio: {self.strategy.portfolio.get(code_to_test)}. DB Trades: {db_sell_trades_profit}")

            # --- 6. 관심 종목 제거 및 실시간 데이터 구독 해제 ---
            self.test_logger.info(f"[TC_CYCLE] Step 6: Removing watchlist item {name_to_test}({code_to_test}) and unsubscribing real-time data...")
            self.strategy.remove_from_watchlist(code_to_test, screen_no=target_screen_no)
            QApplication.processEvents()

            self.assertNotIn(code_to_test, self.strategy.watchlist, f"{code_to_test}가 watchlist에서 제거되어야 합니다.")
            if target_screen_no in self.mock_kiwoom._mock_real_data_active_screens: 
                 self.assertNotIn(code_to_test, self.mock_kiwoom._mock_real_data_active_screens[target_screen_no]['codes'], f"{code_to_test}가 화면번호 {target_screen_no}의 구독 목록에서 제거되어야 합니다.")
            
            self.test_logger.info(f"[TC_CYCLE] Watchlist item removed. Active screens: {self.mock_kiwoom._mock_real_data_active_screens}")
            
            self.strategy.suppress_signals_for_test = False 
            self.test_logger.info("test_full_trading_cycle_with_realtime_data PASSED")

        except AssertionError as ae: 
            self.strategy.suppress_signals_for_test = False 
            self.test_logger.error(f"ASSERTION FAILED in test_full_trading_cycle_with_realtime_data: {ae}")
            self.test_logger.error(traceback.format_exc())
            self.test_logger.error(f"Current strategy state for {code_to_test}: {self.strategy.strategy_state.get(code_to_test)}")
            self.test_logger.error(f"Current watchlist for {code_to_test}: {self.strategy.watchlist.get(code_to_test)}")
            self.test_logger.error(f"Current portfolio for {code_to_test}: {self.strategy.portfolio.get(code_to_test)}")
            self.test_logger.error(f"Current order_sent_flags for {code_to_test}: {self.strategy.order_sent_flags.get(code_to_test)} and sell_{code_to_test}: {self.strategy.order_sent_flags.get(f'sell_{code_to_test}')}")
            self.test_logger.error(f"MockKiwoom send_order_call_history: {self.mock_kiwoom.send_order_call_history}")
            self.test_logger.error(f"MockKiwoom _mock_real_data_active_screens: {self.mock_kiwoom._mock_real_data_active_screens}")
            self.fail(f"Test assertion failed: {ae}")
        except Exception as e:
            self.strategy.suppress_signals_for_test = False 
            self.test_logger.error(f"EXCEPTION in test_full_trading_cycle_with_realtime_data: {type(e).__name__} - {e}")
            self.test_logger.error(traceback.format_exc())
            self.fail(f"Test failed due to unhandled exception: {e}")

    def test_concurrent_buy_orders_and_logging(self):
        """
        여러 관심종목이 동시에 매수 조건을 만족할 때 주문 생성 및 로깅을 테스트합니다.
        """
        self.logger.info("테스트 시작: test_concurrent_buy_orders_and_logging")

        # 1. 준비 (Arrange)
        # 모의 API, 전략 등 설정은 setUp 메소드에서 처리되었다고 가정합니다.
        # 테스트용 관심종목 설정
        test_codes = ["000020", "000040", "000060"] # 예시 종목 코드
        stock_names = {code: f"테스트종목_{code}" for code in test_codes}

        # 각 종목에 대한 초기 데이터 설정 (매수 조건 발동 직전 상태로)
        for code in test_codes:
            self.strategy.initialize_stock_data(code, stock_names[code])
            # 초기 상태: 시가는 어제 종가보다 높고, 현재가는 어제 종가 바로 아래
            self.strategy.watchlist[code].update({
                'yesterday_close': 10000,
                'market_open_price': 10100, # 시가는 어제 종가보다 높음
                'current_price': 9900, # 현재가는 어제 종가보다 낮음
                'below_yesterday_close': True,
                'crossed_yesterday_close': False,
                'market_open_price_higher_than_yesterday_close': True # 초기 조건 만족
            })
            self.strategy.strategy_state[code] = TradingStrategy.TradingState.WAITING
            self.logger.debug(f"초기 설정 - {code}: {self.strategy.watchlist[code]}")

        # 매수 로직에서 사용할 설정값 (config에서 가져오거나 직접 설정)
        # self.config.update_setting("매수금액", 100000) # 필요시 설정

        # Mock KiwoomAPI의 send_order 메소드를 모니터링하지 않고, send_order_call_history를 직접 사용
        # self.mock_kiwoom.send_order = MagicMock(return_value="12345") # 주문 성공(주문번호 반환) 모의 -> 제거
        # with patch.object(self.mock_kiwoom, 'send_order', return_value="12345") as mock_send_order: -> 제거

        # 2. 실행 (Act)
        self.strategy.start() # 자동매매 시작

        # 각 종목에 대해 매수 조건 만족하는 실시간 데이터 주입
        # 모든 test_codes 종목은 이 테스트 내에서 yc=10000, mop=10100으로 설정됨.
        for code in test_codes:
            self.logger.info(f"ConTest: Processing {code} for real data emission. Current state: {self.strategy.strategy_state.get(code)}")
            # 1. 현재가 < 전일 종가 (어제 종가: 10000)
            data_below = {'현재가': "9900", '전일대비': "-100", '등락률': "-1.00", '거래량': "500"}
            self.logger.debug(f"ConTest: Emitting data_below for {code}: {data_below}")
            self.strategy.on_actual_real_data_received(code, "주식체결", data_below)
            # QTest.qWait(50) # 각 emit 후 짧은 대기보다는 모든 emit 후 한번에 대기

            # 2. 현재가 > 전일 종가 (돌파)
            data_crossed = {'현재가': "10200", '전일대비': "200", '등락률': "2.00", '거래량': "1000"}
            self.logger.debug(f"ConTest: Emitting data_crossed for {code}: {data_crossed}")
            self.strategy.on_actual_real_data_received(code, "주식체결", data_crossed)
            # QTest.qWait(50)
            self.logger.info(f"ConTest: Finished real data for {code}. State: {self.strategy.strategy_state.get(code)}, CrossedFlag: {self.strategy.watchlist[code].get('crossed_yesterday_close')}")
        
        QApplication.processEvents() # 모든 실시간 데이터 처리 후 이벤트 루프 실행
        QTest.qWait(100) # 추가적인 안정화 대기

        # check_conditions 타이머가 충분히 돌도록 잠시 대기
        self.logger.info(f"Waiting for check_conditions timer (interval: {self.strategy.check_timer.interval()}ms * 3)")
        QTest.qWait(self.strategy.check_timer.interval() * 5) # 타이머 주기 5배만큼 대기 (넉넉하게)
        self.logger.info("Finished waiting for check_conditions timer.")

        # 최종 상태 로깅 추가
        for code in test_codes:
            self.logger.info(f"Final state for {code}: {self.strategy.strategy_state.get(code)}")
        self.logger.info(f"Final order_sent_flags: {self.strategy.order_sent_flags}")

        # 3. 검증 (Assert)
        # 각 종목에 대해 send_order가 호출되었는지 확인 (send_order_call_history 사용)
        self.logger.info(f"send_order_call_history length: {len(self.mock_kiwoom.send_order_call_history)}")
        self.logger.info(f"send_order_call_history content: {self.mock_kiwoom.send_order_call_history}")

        self.assertEqual(len(self.mock_kiwoom.send_order_call_history), len(test_codes),
                            f"send_order 호출 횟수 불일치: 예상 {len(test_codes)}, 실제 {len(self.mock_kiwoom.send_order_call_history)}")

        ordered_codes_from_history = set()
        for call_detail in self.mock_kiwoom.send_order_call_history:
            ordered_codes_from_history.add(call_detail["code"])
            self.assertEqual(call_detail["order_type"], 1, f"{call_detail['code']} 주문 유형 불일치 (예상: 매수(1))")
            self.assertGreater(call_detail["quantity"], 0, f"{call_detail['code']} 주문 수량 오류")
            self.assertEqual(call_detail["price"], 0, f"{call_detail['code']} 주문 가격 오류 (예상: 시장가 0)") # 시장가 주문
            self.assertEqual(call_detail["hoga_gb"], "03", f"{call_detail['code']} 주문 구분 오류 (예상: 시장가 '03')") # 시장가 주문

        self.assertEqual(ordered_codes_from_history, set(test_codes), "주문된 종목 코드 불일치 (call_history 기반)")

        # 각 종목의 상태가 BOUGHT 또는 주문 전송 관련 상태로 변경되었는지 확인
        for code in test_codes:
            # 체결 데이터가 아직 오지 않았으므로, order_sent_flags에 있어야 하고, 상태는 READY일 수 있음 (또는 BOUGHT가 아님)
            # self.assertIn(self.strategy.strategy_state.get(code),
            #               [TradingStrategy.TradingState.BOUGHT, TradingStrategy.TradingState.READY], 
            #               f"{code}의 최종 상태 오류: {self.strategy.strategy_state.get(code)}")
            # execute_buy 호출 후 order_sent_flags는 설정되지만, 상태는 체결 데이터 수신 후 BOUGHT로 변경됨.
            # 따라서 여기서는 order_sent_flags 존재 여부만 확인.
            self.assertIn(code, self.strategy.order_sent_flags, f"{code}가 order_sent_flags에 없음")
            self.logger.info(f"Final state for {code}: {self.strategy.strategy_state.get(code)}, order_sent_flag: {self.strategy.order_sent_flags.get(code)}")


        # 4. 정리 (Teardown)
        self.strategy.stop()
        self.logger.info("테스트 종료: test_concurrent_buy_orders_and_logging")


    # test_integration.py 파일의 TestIntegrationScenarios 클래스 내에 추가될 메소드입니다.

    def test_buy_order_api_error_handling(self):
        """
        매수 주문 시 API 오류 발생 및 체결 실패 시 처리 과정을 테스트합니다.
        """
        self.logger.info("테스트 시작: test_buy_order_api_error_handling")

        # 1. 준비 (Arrange)
        code_to_test = "000070" # 삼양홀딩스 예시
        stock_name = "테스트_API오류종목"
        initial_yesterday_close = 11000 # initial_stock_data_buy_error의 yesterday_close와 일치
        # 매수 트리거 가격은 initial_yesterday_close 보다 커야 함
        price_to_cross_yesterday_close = initial_yesterday_close + 100 # 예: 11100

        # 관심종목 초기화 및 매수 준비 상태 만들기
        # setUp에서 initial_stock_data_buy_error를 사용하여 데이터가 설정됨
        # self.strategy.initialize_stock_data(code_to_test, stock_name) # setUp에서 이미 수행할 수 있음
        # 필요한 경우 watchlist 상태를 직접 확인하거나 설정
        if code_to_test not in self.strategy.watchlist:
            self.strategy.initialize_stock_data(code_to_test, stock_name)
            # initialize_stock_data 이후 watchlist 상태를 테스트 의도에 맞게 조정
            self.strategy.watchlist[code_to_test].update({
                'yesterday_close': initial_yesterday_close,
                'market_open_price': initial_yesterday_close + 50, # 시가 > 전일종가
                'current_price': initial_yesterday_close - 100, # 현재가 < 전일종가
                'below_yesterday_close': True,
                'crossed_yesterday_close': False,
                'market_open_price_higher_than_yesterday_close': True
            })
        else: # watchlist에 이미 있다면, 필요한 값만 업데이트 또는 확인
            self.strategy.watchlist[code_to_test]['yesterday_close'] = initial_yesterday_close
            self.strategy.watchlist[code_to_test]['market_open_price'] = initial_yesterday_close + 50
            self.strategy.watchlist[code_to_test]['current_price'] = initial_yesterday_close - 100
            self.strategy.watchlist[code_to_test]['below_yesterday_close'] = True
            self.strategy.watchlist[code_to_test]['crossed_yesterday_close'] = False
            self.strategy.watchlist[code_to_test]['market_open_price_higher_than_yesterday_close'] = True

        self.strategy.strategy_state[code_to_test] = TradingStrategy.TradingState.WAITING
        self.logger.debug(f"초기 설정 - {code_to_test}: {self.strategy.watchlist[code_to_test]}")
        
        # TradingStrategy의 order_feedback 시그널을 받을 mock 객체
        mock_order_feedback_slot = MagicMock()
        self.strategy.order_feedback.connect(mock_order_feedback_slot)

        # 2. 실행 (Act)
        # 매수 조건 만족시키기 (현재가 > 어제 종가)
        real_data_packet_buy_trigger = {
            '현재가': str(price_to_cross_yesterday_close),
            '전일대비': str(price_to_cross_yesterday_close - initial_yesterday_close), 
            '등락률': f"{(price_to_cross_yesterday_close / initial_yesterday_close - 1) * 100:.2f}"
        }
        self.logger.info(f"Triggering buy for {code_to_test} with real data: {real_data_packet_buy_trigger}")
        self.strategy.on_actual_real_data_received(code_to_test, "주식체결", real_data_packet_buy_trigger)
        QTest.qWait(100) # 시그널 처리
        self.logger.info(f"State after real data for {code_to_test}: {self.strategy.strategy_state.get(code_to_test)}")

        # self.strategy.check_conditions()를 호출하여 READY 상태에서 매수 주문이 나가도록 유도
        QTest.qWait(self.strategy.check_timer.interval() * 5) # 타이머가 execute_buy를 호출할 시간 (넉넉하게)
        self.logger.info(f"Finished waiting for check_conditions. order_sent_flags: {self.strategy.order_sent_flags}")

        # 주문이 전송되었는지 확인 (send_order_call_history 사용)
        self.assertGreater(len(self.mock_kiwoom.send_order_call_history), 0, "send_order가 호출되어야 합니다.")
        
        call_for_this_test = None
        for call_item in reversed(self.mock_kiwoom.send_order_call_history):
            if call_item['code'] == code_to_test and call_item['order_type'] == 1: # 매수 주문
                call_for_this_test = call_item
                break
        self.assertIsNotNone(call_for_this_test, f"{code_to_test}에 대한 매수 send_order 호출을 찾을 수 없습니다.")
        
        sent_order_rq_name = call_for_this_test['rq_name']
        generated_order_no_for_chejan = call_for_this_test['generated_order_no']
        self.logger.info(f"Order sent for {code_to_test}. RQName: {sent_order_rq_name}, GeneratedOrderNo: {generated_order_no_for_chejan}")

        # API 주문 실패에 대한 체결 데이터(오류) 주입
        chejan_data_order_failure = {
            '9203': generated_order_no_for_chejan, # MockKiwoomAPIForIntegration.send_order에서 생성/저장된 주문번호
            '9001': f"A{code_to_test}",      
            '302': stock_name,            
            '913': '주문실패', # KiwoomAPI에서 실제 사용하는 주문 상태 문자열 확인 필요 (예: "주문거부", "주문실패" 등)            
            '907': '+매수',                
            '901': str(call_for_this_test['quantity']), # 주문수량
            '911': '0',                   # 체결수량
            '910': str(price_to_cross_yesterday_close), # 주문가격 (실제로는 체결데이터에 따라 다를 수 있음)
            '905': 'API 주문 오류 메시지 예시 (테스트)', # 실제 FID 919 (체결통보 확인 메시지) 또는 유사 필드를 사용해야 할 수 있음
            '9201': sent_order_rq_name      # TradingStrategy.execute_buy에서 생성한 요청명
        }
        self.logger.info(f"Current order_sent_flags before injecting chejan failure: {self.strategy.order_sent_flags}") # 로깅 추가
        self.logger.info(f"Injecting chejan data for order failure: {chejan_data_order_failure}")
        self.strategy.on_chejan_data_received('0', chejan_data_order_failure) # '0'은 주문체결 통보
        QTest.qWait(100) # 체결 데이터 처리 시간

        # 3. 검증 (Assert)
        # 주문 피드백 시그널 확인 (실패 상태)
        # self.logger.info(f"Checking order_feedback_slot. called: {mock_order_feedback_slot.called}, call_count: {mock_order_feedback_slot.call_count}") # 아래에서 상세 로깅으로 대체
        # if mock_order_feedback_slot.called: # 아래에서 상세 로깅으로 대체
        #     self.logger.info(f"Order feedback call_args: {mock_order_feedback_slot.call_args_list}")

        self.app.processEvents() # 이벤트 루프가 보류 중인 이벤트를 처리하도록 명시적 호출
        QTest.qWait(50) # 안정성을 위해 짧은 대기 시간 추가
        self.logger.info(f"After processEvents/qWait, mock_order_feedback_slot called: {mock_order_feedback_slot.called}, call_count: {mock_order_feedback_slot.call_count}")
        if mock_order_feedback_slot.called:
            self.logger.info(f"Order feedback call_args_list after processEvents: {mock_order_feedback_slot.call_args_list}")

        mock_order_feedback_slot.assert_called_once()
        feedback_args = mock_order_feedback_slot.call_args[0]
        self.assertEqual(feedback_args[0], "매수") # order_type
        self.assertIn(feedback_args[1].lower(), ["실패", "주문실패", "오류", "거부"], f"주문 피드백 상태 오류: {feedback_args[1]}") # status
        self.assertEqual(feedback_args[2]['code'], code_to_test)

        # 전략 상태 확인
        # 주문 실패 시 WAITING으로 돌아가야 함
        self.assertEqual(self.strategy.strategy_state.get(code_to_test), TradingStrategy.TradingState.WAITING,
                         f"{code_to_test}의 상태가 주문 실패 후 WAITING여야 합니다. 현재: {self.strategy.strategy_state.get(code_to_test)}")

        # 포트폴리오에 해당 종목이 없어야 함
        self.assertNotIn(code_to_test, self.strategy.portfolio,
                         f"{code_to_test}가 포트폴리오에 없어야 합니다.")

        # order_sent_flags에서 해당 주문이 제거되었거나 실패 처리되었는지 확인
        self.assertNotIn(code_to_test, self.strategy.order_sent_flags, 
                         f"주문 실패 후 {code_to_test}가 order_sent_flags에서 제거되어야 합니다.")
        
        # 4. 정리 (Teardown)
        self.strategy.order_feedback.disconnect(mock_order_feedback_slot) # 시그널 연결 해제
        self.logger.info("테스트 종료: test_buy_order_api_error_handling")


    # test_integration.py 파일의 TestIntegrationScenarios 클래스 내에 추가될 메소드입니다.

    def test_tr_data_request_error_handling(self):
        """
        TR 데이터(예: opt10001 - 종목기본정보) 요청 시 API 오류 발생 상황을 테스트합니다.
        """
        self.logger.info("테스트 시작: test_tr_data_request_error_handling")

        # 1. 준비 (Arrange)
        code_to_test = "005930" # 삼성전자 예시
        stock_name = "테스트_TR오류종목"
        
        # Mock KiwoomAPI의 comm_rq_data가 TR 요청 시 오류를 시뮬레이션하도록 설정
        # 여기서는 comm_rq_data가 직접 TR 오류 관련 시그널을 보내거나,
        # on_receive_tr_data 슬롯으로 오류 데이터를 전달하는 것을 모의합니다.
        
        # TR 데이터 수신 슬롯(on_tr_data_received)을 모니터링하기 위한 mock
        # 또는 strategy 내부의 특정 상태 변화를 관찰
        # 여기서는 TR 요청 후 watchlist 상태 변화 및 로그를 주로 확인

        # 특정 TR 요청(opt10001)에 대해 오류를 반환하도록 mock_tr_data_handler를 설정
        # setUp에서 설정된 기본 mock_tr_data_handler를 저장하고, 이 테스트용으로 일시 변경
        original_tr_handler = self.mock_kiwoom.mock_tr_data_handler

        def mock_tr_handler_for_tr_error(rq_name, tr_code, prev_next=None, screen_no=None, **kwargs):
            self.logger.debug(f"[MockTRHandler_ErrorTest] TR 요청 수신: {rq_name}, {tr_code}")
            if tr_code == "opt10001" and kwargs.get('code') == code_to_test:
                self.logger.info(f"[MockTRHandler_ErrorTest] {tr_code} ({rq_name}) 요청에 대해 오류 데이터 emit 시도.")
                tr_error_payload = {
                    'error': 'TR_REQUEST_FAILED_TEST',
                    'error_code': '-100',
                    'message': 'TR 서비스 처리실패 [TEST_ERROR]'
                }
                self.mock_kiwoom.tr_data_received.emit(rq_name, tr_code, tr_error_payload)
                # return True # 핸들러가 처리했음을 알림 (이전 코드)
                return None # TR 요청 실패 시 None을 반환하여 initialize_stock_data가 오류로 인지하도록 함
            
            # 다른 TR 요청은 원래 핸들러에게 위임 (또는 기본 mock 동작)
            if original_tr_handler:
                return original_tr_handler(rq_name, tr_code, prev_next, screen_no, **kwargs)
            return False

        self.mock_kiwoom.mock_tr_data_handler = mock_tr_handler_for_tr_error
        self.logger.info("[MockTRHandler_ErrorTest] TR 오류 테스트용 핸들러 설정됨.")

        # 로거에 오류 메시지가 기록되는지 확인하기 위한 준비 (선택적)
        # 예: self.test_logger.error = MagicMock() 또는 로그 캡처 핸들러 사용

        # 2. 실행 (Act)
        # TradingStrategy가 내부적으로 TR을 요청하는 동작을 유도
        # 예: 관심종목 추가 시 initialize_stock_data 호출
        self.strategy.initialize_stock_data(code_to_test, stock_name)
        QTest.qWait(200) # 비동기 TR 처리 및 시그널 처리 대기

        # 3. 검증 (Assert)
        # watchlist에 해당 종목 정보가 비정상적으로 추가되지 않았거나,
        # 오류 처리 후 정리되었는지 확인
        # TradingStrategy.initialize_stock_data의 반환값을 보거나, 내부 상태를 확인
        stock_data_in_watchlist = self.strategy.watchlist.get(code_to_test)
        
        self.assertIsNone(stock_data_in_watchlist,
                          f"TR 오류 발생 시 {code_to_test} 정보가 watchlist에 남지 않거나 초기화되어야 합니다. 현재: {stock_data_in_watchlist}")
        # 또는, stock_data_in_watchlist가 특정 '오류 상태'를 나타내는 값을 가져야 함
        # 예: self.assertTrue(stock_data_in_watchlist.get('error_state', False))

        # Logger에 오류 관련 메시지가 기록되었는지 확인 (실제 로그 메시지 형식에 따라 수정 필요)
        # 예: self.test_logger.error.assert_any_call(부분_오류_메시지_포함)
        # 또는 로그 파일 내용을 직접 확인하거나, 테스트용 로그 핸들러를 통해 캡처된 로그 검증
        # 여기서는 TradingStrategy.log 메소드가 "ERROR" 레벨로 호출되었는지 간접적으로 확인 가능 (만약 logger가 mock이라면)

        # 프로그램의 다른 부분(예: 다른 관심종목)은 정상적으로 동작하는지 간접적으로 확인 (필요시)

        # TradingStrategy의 error_occurred 시그널이 발생했는지 확인 (선택적)
        # mock_error_signal_slot = MagicMock()
        # self.strategy.error_occurred.connect(mock_error_signal_slot)
        # ... (실행) ...
        # mock_error_signal_slot.assert_called_with(포함될_오류_메시지)

        # 4. 정리 (Teardown)
        # 테스트용 TR 핸들러를 원래대로 복구
        self.mock_kiwoom.mock_tr_data_handler = original_tr_handler
        # if hasattr(self.strategy, 'error_occurred') and mock_error_signal_slot.called:
        #     self.strategy.error_occurred.disconnect(mock_error_signal_slot)
        self.logger.info("테스트 종료: test_tr_data_request_error_handling")


    # test_integration.py 파일의 TestIntegrationScenarios 클래스 내에 추가될 메소드입니다.

    def test_realtime_data_format_error_handling(self):
        """
        실시간 데이터 수신 시 형식 오류 (예: 현재가가 숫자가 아님) 또는 
        필수 값 누락 상황을 테스트합니다.
        """
        self.logger.info("테스트 시작: test_realtime_data_format_error_handling")

        # 1. 준비 (Arrange)
        code_normal = "000100" # 정상 데이터용 종목
        name_normal = "정상종목"
        code_error_format = "000200" # 현재가 형식 오류용 종목
        name_error_format = "형식오류종목"
        code_error_missing = "000300" # 현재가 누락용 종목
        name_error_missing = "누락종목"

        initial_price = 5000

        # 관심종목들 초기화
        for code, name in [(code_normal, name_normal), 
                           (code_error_format, name_error_format), 
                           (code_error_missing, name_error_missing)]:
            self.strategy.initialize_stock_data(code, name)
            self.strategy.watchlist[code].update({
                'yesterday_close': initial_price,
                'market_open_price': initial_price,
                'current_price': initial_price,
                'below_yesterday_close': False,
                'crossed_yesterday_close': False,
                'market_open_price_higher_than_yesterday_close': False 
            })
            self.strategy.strategy_state[code] = TradingStrategy.TradingState.WAITING
            self.logger.debug(f"초기 설정 - {code}: {self.strategy.watchlist[code]}")

        # TradingStrategy의 stock_data_updated 시그널을 받을 mock 객체 (선택적)
        mock_stock_data_updated_slot = MagicMock()
        self.strategy.stock_data_updated.connect(mock_stock_data_updated_slot)
        
        # Logger의 error 메소드를 mock하여 호출 여부 확인 (선택적)
        # self.test_logger.error = MagicMock() 

        # 2. 실행 (Act) 및 검증 (Assert)

        # --- 시나리오 1: 현재가 값 형식 오류 (숫자가 아닌 문자열) ---
        self.logger.info("실행: 현재가 형식 오류 데이터 주입")
        invalid_format_data_packet = {
            '현재가': "가격정보없음", # 숫자로 변환될 수 없는 값
            '전일대비': "0",
            '등락률': "0.00"
        }
        # TradingStrategy.on_actual_real_data_received가 예외를 발생시키지 않아야 함
        try:
            self.strategy.on_actual_real_data_received(code_error_format, "주식체결", invalid_format_data_packet)
            QTest.qWait(100) # 시그널 처리 시간
        except Exception as e:
            self.fail(f"{code_error_format}에 대한 형식 오류 데이터 처리 중 예외 발생: {e}")

        # watchlist의 해당 종목 'current_price'가 업데이트되지 않았거나, 오류 처리되었는지 확인
        # (오류 발생 시 이전 값을 유지하거나, 특정 오류 상태를 표시할 수 있음)
        self.assertEqual(self.strategy.watchlist[code_error_format]['current_price'], initial_price,
                         f"{code_error_format}의 current_price는 형식 오류 시 이전 값을 유지해야 합니다.")
        # 또는 self.assertIsNone(self.strategy.watchlist[code_error_format].get('current_price')) 등
        
        # 로그에 오류가 기록되었는지 확인 (실제 로그 메시지 확인 필요)
        # 예: self.test_logger.error.assert_any_call(형식_오류_관련_메시지)

        # --- 시나리오 2: 현재가 키 누락 ---
        self.logger.info("실행: 현재가 키 누락 데이터 주입")
        missing_key_data_packet = {
            # '현재가': 누락
            '전일대비': "0",
            '등락률': "0.00"
        }
        try:
            self.strategy.on_actual_real_data_received(code_error_missing, "주식체결", missing_key_data_packet)
            QTest.qWait(100)
        except Exception as e:
            self.fail(f"{code_error_missing}에 대한 키 누락 데이터 처리 중 예외 발생: {e}")

        self.assertEqual(self.strategy.watchlist[code_error_missing]['current_price'], initial_price,
                         f"{code_error_missing}의 current_price는 키 누락 시 이전 값을 유지해야 합니다.")
        # 로그에 오류가 기록되었는지 확인

        # --- 시나리오 3: 정상적인 데이터는 정상 처리되는지 확인 ---
        self.logger.info("실행: 정상 데이터 주입")
        normal_price = initial_price + 100
        normal_data_packet = {
            '현재가': str(normal_price),
            '전일대비': "100",
            '등락률': "2.00"
        }
        self.strategy.on_actual_real_data_received(code_normal, "주식체결", normal_data_packet)
        QTest.qWait(100)

        self.assertEqual(self.strategy.watchlist[code_normal]['current_price'], normal_price,
                         f"{code_normal}의 current_price는 정상적으로 업데이트되어야 합니다.")
        
        # stock_data_updated 시그널이 정상 종목에 대해서는 발생했는지 확인
        # mock_stock_data_updated_slot.assert_any_call(code_normal, self.strategy.watchlist[code_normal])
        # 오류 종목에 대해서는 발생하지 않았거나, 다른 형태로 발생했는지 확인 (선택적)
        
        # 오류 발생 후에도 strategy가 여전히 실행 중인지 확인
        self.assertTrue(self.strategy.is_running, "오류 데이터 처리 후에도 전략은 계속 실행 중이어야 합니다.")

        # 3. 정리 (Teardown)
        self.strategy.stock_data_updated.disconnect(mock_stock_data_updated_slot)
        # self.test_logger.error.reset_mock() # Mock 사용 시
        self.logger.info("테스트 종료: test_realtime_data_format_error_handling")


if __name__ == '__main__':
    print("TestIntegration: Running tests via unittest.main()")
    unittest.main() 