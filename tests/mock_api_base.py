#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import time
from typing import Dict, List, Optional, Any

# 프로젝트 루트 경로를 sys.path에 추가 (필요시)
# import os
# import sys
# project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
# if project_root not in sys.path:
#     sys.path.insert(0, project_root)

from logger import Logger # Assuming logger.py is in the project root or accessible

class BaseMockKiwoomAPI:
    """
    Base class for mock Kiwoom API implementations.
    Provides common attributes and simple versions of API methods.
    This class does NOT inherit from QObject to allow derived classes
    the flexibility to inherit from it (or not) for signal/slot mechanisms.
    """
    def __init__(self, logger: Optional[Logger] = None):
        self.logger = logger if logger else Logger(log_level=logging.DEBUG, name="BaseMockKiwoomAPI")
        self.connected: bool = False
        self.account_number: Optional[str] = "1234567890" # Default mock account
        self.user_id: Optional[str] = "MockUser"
        self.user_name: Optional[str] = "모의사용자"
        
        self.tr_data_cache: Dict[str, Any] = {} # For storing TR request results
        self.send_order_call_history: List[Dict[str, Any]] = []
        self.current_input_values: Dict[str, str] = {} # Stores values set by SetInputValue

        self.mock_comm_rq_data_results: Dict[str, int] = {} # rq_name -> return_code for comm_rq_data

        self.logger.info(f"BaseMockKiwoomAPI initialized (Logger: {self.logger.logger.name})")

    def log(self, message: str, level: str = "INFO"):
        # Helper method if direct logger usage is not preferred everywhere
        log_func = getattr(self.logger, level.lower(), self.logger.info)
        log_func(f"[{self.__class__.__name__}] {message}")

    def get_connect_state(self) -> int:
        self.log(f"get_connect_state called. Returning: {1 if self.connected else 0}", "DEBUG")
        return 1 if self.connected else 0

    def get_login_info(self, tag: str) -> str:
        self.log(f"get_login_info called with tag: {tag}", "DEBUG")
        if tag == "ACCNO":
            return f"{self.account_number};" if self.account_number else ""
        elif tag == "USER_ID":
            return self.user_id if self.user_id else ""
        elif tag == "USER_NAME":
            return self.user_name if self.user_name else ""
        # Add other common tags if needed
        return ""

    def set_input_value(self, item_name: str, value: str):
        self.log(f"SetInputValue: {item_name} = {value}", "DEBUG")
        self.current_input_values[item_name] = str(value)

    def send_order(self, rq_name: str, screen_no: str, acc_no: str, order_type: int, code: str, quantity: int, price: int, hoga_gb: str, org_order_no: str = "") -> int:
        self.log(f"send_order called: RQName({rq_name}), Screen({screen_no}), Acc({acc_no}), Type({order_type}), Code({code}), Qty({quantity}), Price({price}), Hoga({hoga_gb}), OrgOrderNo({org_order_no})")
        call_detail = {
            "rq_name": rq_name, "screen_no": screen_no, "acc_no": acc_no,
            "order_type": order_type, "code": code, "quantity": quantity,
            "price": price, "hoga_gb": hoga_gb, "org_order_no": org_order_no,
            "timestamp": time.time(),
            "generated_order_no": f"mock_ord_{int(time.time())}_{len(self.send_order_call_history)}"
        }
        self.send_order_call_history.append(call_detail)
        # Default behavior: success (0)
        return 0

    def comm_rq_data(self, rq_name: str, tr_code: str, prev_next: int, screen_no: str) -> int:
        self.log(f"comm_rq_data called: RQName({rq_name}), TRCode({tr_code}), PrevNext({prev_next}), ScreenNo({screen_no})", "DEBUG")
        
        # Allow specific tests to pre-set return codes for comm_rq_data
        if rq_name in self.mock_comm_rq_data_results:
            return self.mock_comm_rq_data_results[rq_name]

        # Basic TR data simulation (can be overridden by derived classes)
        # This is a very simple mock. Derived classes should provide more specific data.
        self.tr_data_cache[rq_name] = {
            'tr_code': tr_code,
            'rq_name': rq_name,
            'single_data': {'종목코드': self.current_input_values.get("종목코드", "") , '종목명': f"모의종목_{tr_code}"},
            'multi_data': [],
            'prev_next': str(prev_next)
        }
        # In a real scenario, OnReceiveTrData would be triggered.
        # Derived classes might need to emit a signal here.
        self.current_input_values.clear() # Clear inputs after use
        return 0 # Success

    def get_comm_data(self, tr_code: str, rq_name: str, index: int, item_name: str) -> str:
        self.log(f"get_comm_data: TR({tr_code}), RQName({rq_name}), Index({index}), Item({item_name})", "DEBUG")
        data_for_rq = self.tr_data_cache.get(rq_name)
        if not data_for_rq:
            return ""
        
        if index == 0 and 'single_data' in data_for_rq and item_name in data_for_rq['single_data']:
            return str(data_for_rq['single_data'][item_name])
        
        if 'multi_data' in data_for_rq and index < len(data_for_rq['multi_data']):
            if item_name in data_for_rq['multi_data'][index]:
                return str(data_for_rq['multi_data'][index][item_name])
        return ""

    def get_repeat_cnt(self, tr_code: str, rq_name: str) -> int:
        self.log(f"get_repeat_cnt: TR({tr_code}), RQName({rq_name})", "DEBUG")
        data_for_rq = self.tr_data_cache.get(rq_name)
        if data_for_rq and 'multi_data' in data_for_rq:
            return len(data_for_rq['multi_data'])
        return 0

    def set_real_reg(self, screen_no: str, code_list_str: str, fid_list_str: str, opt_type: str) -> int:
        self.log(f"set_real_reg: Screen({screen_no}), Codes({code_list_str}), FIDs({fid_list_str}), Type({opt_type})", "INFO")
        # Basic implementation for logging. Derived classes can manage actual subscriptions.
        return 0 # Success

    def disconnect_real_data(self, screen_no: str):
        self.log(f"disconnect_real_data: Screen({screen_no})", "INFO")
        # Basic implementation for logging.

    # --- Methods often specialized in derived classes ---
    def get_stock_basic_info(self, code: str, market_context: Optional[str] = None, screen_no: Optional[str] = None):
        self.log(f"get_stock_basic_info (base) for {code}. Market: {market_context}, Screen: {screen_no}. Returning generic mock data.", "DEBUG")
        # This should be overridden by derived classes for more specific behavior
        return {'종목코드': code, '종목명': f"모의_{code}", '현재가': "10000"}

    def get_daily_chart(self, code: str, *, date_to: str = "", date_from: str = "", market_context: Optional[str] = None, screen_no_override: Optional[str] = None, rq_name_override: Optional[str] = None):
        self.log(f"get_daily_chart (base) for {code}. DateTo: {date_to}, Market: {market_context}, ScreenOverride: {screen_no_override}, RQOverride: {rq_name_override}. Returning empty list.", "DEBUG")
        # This should be overridden by derived classes
        return [] # (data_list, is_next_page=False) - KiwoomAPI returns list directly
    
    def get_code_market_info(self, full_code_str: str):
        self.log(f"get_code_market_info (base) for {full_code_str}. Returning default KRX.", "DEBUG")
        # Basic mock, derived classes might use ats_utils or more specific logic
        if full_code_str.endswith('_NX'):
            return full_code_str[:-3], 'NXT'
        elif full_code_str.endswith('_AL'):
            return full_code_str[:-3], 'ALL'
        return full_code_str, 'KRX'

    def parse_chejan_data(self, fid_list_str: str) -> dict:
        self.log(f"parse_chejan_data (base) for FID list: {fid_list_str}", "DEBUG")
        parsed = {}
        if fid_list_str:
            fids = fid_list_str.split(';')
            for fid_str in fids:
                if fid_str:
                    # Provide some very basic default values for common FIDs
                    if fid_str == '9001': # 종목코드
                        parsed[fid_str] = "A000020" 
                    elif fid_str == '913': # 주문상태
                        parsed[fid_str] = "체결"
                    elif fid_str == '910': # 체결가
                        parsed[fid_str] = "10000"
                    elif fid_str == '911': # 체결량
                        parsed[fid_str] = "10"
                    else:
                        parsed[fid_str] = f"mock_val_{fid_str}"
        return parsed

    def set_strategy_instance(self, strategy_instance: Any):
        """Allows linking a strategy instance, useful for tests where the mock needs to callback."""
        self.strategy_instance = strategy_instance
        self.log(f"Strategy instance {'set' if strategy_instance else 'cleared'}.", "DEBUG")

    # Placeholder for CommConnect, should be overridden if login sequence needs to be tested
    def CommConnect(self):
        self.log("CommConnect called. Simulating successful connection.", "INFO")
        self.connected = True
        # In a real scenario, OnEventConnect would be triggered.
        # Derived classes needing to test login sequence should override this
        # and potentially emit a signal or call a callback.
        if hasattr(self, 'OnEventConnect') and callable(self.OnEventConnect):
             self.OnEventConnect(0) # 0 for success
        elif hasattr(self, 'login_completed') and hasattr(self.login_completed, 'emit'): # PyQt signal
             self.login_completed.emit(self.account_number)


if __name__ == '__main__':
    # Example usage:
    mock_api = BaseMockKiwoomAPI()
    mock_api.CommConnect()
    print(f"Connection State: {mock_api.get_connect_state()}")
    print(f"Account Number: {mock_api.get_login_info('ACCNO')}")
    
    mock_api.set_input_value("종목코드", "005930")
    mock_api.set_input_value("주문수량", "10")
    mock_api.comm_rq_data("주식주문", "opt10001", 0, "0101")
    
    print(f"TR Data for '주식주문': {mock_api.tr_data_cache.get('주식주문')}")
    print(f"종목명 from cache: {mock_api.get_comm_data('opt10001', '주식주문', 0, '종목명')}")
    
    mock_api.send_order("매수요청", "0102", mock_api.account_number, 1, "005930", 10, 70000, "03")
    print(f"Send order history: {mock_api.send_order_call_history}")
