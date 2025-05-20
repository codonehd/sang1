#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import time
from PyQt5.QtWidgets import QApplication
from PyQt5.QAxContainer import QAxWidget
from PyQt5.QtCore import QEventLoop, QTimer, QObject
from datetime import datetime, timedelta
from util import ScreenManager # ScreenManager 임포트
import traceback # 스택 트레이스 로깅을 위해 추가
from typing import Dict, Optional
import logging

# --- ATS 관련 상수 및 매핑 --- #
# 종목코드 접미사와 시장 컨텍스트 매핑
ATS_SUFFIX_MARKET_MAP = {
    '_NX': 'NXT',  # Nextrade
    '_AL': 'ALL'   # 통합시세 (NXT + KRX)
}

# TR별 "거래소구분" 파라미터 설정 정보
# Key: TR Code
# Value: dict -> {"param_name": "거래소구분", "values": {"KRX": "1", "NXT": "2", "ALL": "3"}}
# 실제 API 문서("[붙임]대체거래소(ATS) 도입에 따른 키움 Open API + 변경 안내") 기준으로 작성.
TR_MARKET_PARAM_CONFIG = {
    # 유형 1: 거래소구분=1:KRX, 2:NXT, 3:통합 (43개 TR)
    "OPT10016": {"param_name": "거래소구분", "values": {"KRX": "1", "NXT": "2", "ALL": "3"}},
    "OPT10017": {"param_name": "거래소구분", "values": {"KRX": "1", "NXT": "2", "ALL": "3"}},
    "OPT10018": {"param_name": "거래소구분", "values": {"KRX": "1", "NXT": "2", "ALL": "3"}},
    "OPT10019": {"param_name": "거래소구분", "values": {"KRX": "1", "NXT": "2", "ALL": "3"}},
    "OPT10020": {"param_name": "거래소구분", "values": {"KRX": "1", "NXT": "2", "ALL": "3"}},
    "OPT10021": {"param_name": "거래소구분", "values": {"KRX": "1", "NXT": "2", "ALL": "3"}},
    "OPT10022": {"param_name": "거래소구분", "values": {"KRX": "1", "NXT": "2", "ALL": "3"}},
    "OPT10023": {"param_name": "거래소구분", "values": {"KRX": "1", "NXT": "2", "ALL": "3"}},
    "OPT10024": {"param_name": "거래소구분", "values": {"KRX": "1", "NXT": "2", "ALL": "3"}},
    "OPT10025": {"param_name": "거래소구분", "values": {"KRX": "1", "NXT": "2", "ALL": "3"}},
    "OPT10026": {"param_name": "거래소구분", "values": {"KRX": "1", "NXT": "2", "ALL": "3"}},
    "OPT10027": {"param_name": "거래소구분", "values": {"KRX": "1", "NXT": "2", "ALL": "3"}},
    "OPT10028": {"param_name": "거래소구분", "values": {"KRX": "1", "NXT": "2", "ALL": "3"}},
    "OPT10029": {"param_name": "거래소구분", "values": {"KRX": "1", "NXT": "2", "ALL": "3"}},
    "OPT10030": {"param_name": "거래소구분", "values": {"KRX": "1", "NXT": "2", "ALL": "3"}},
    "OPT10031": {"param_name": "거래소구분", "values": {"KRX": "1", "NXT": "2", "ALL": "3"}},
    "OPT10032": {"param_name": "거래소구분", "values": {"KRX": "1", "NXT": "2", "ALL": "3"}},
    "OPT10033": {"param_name": "거래소구분", "values": {"KRX": "1", "NXT": "2", "ALL": "3"}},
    "OPT10034": {"param_name": "거래소구분", "values": {"KRX": "1", "NXT": "2", "ALL": "3"}},
    "OPT10035": {"param_name": "거래소구분", "values": {"KRX": "1", "NXT": "2", "ALL": "3"}},
    "OPT10036": {"param_name": "거래소구분", "values": {"KRX": "1", "NXT": "2", "ALL": "3"}},
    "OPT10037": {"param_name": "거래소구분", "values": {"KRX": "1", "NXT": "2", "ALL": "3"}},
    "OPT10038": {"param_name": "거래소구분", "values": {"KRX": "1", "NXT": "2", "ALL": "3"}},
    "OPT10039": {"param_name": "거래소구분", "values": {"KRX": "1", "NXT": "2", "ALL": "3"}},
    "OPT10042": {"param_name": "거래소구분", "values": {"KRX": "1", "NXT": "2", "ALL": "3"}},
    "OPT10043": {"param_name": "거래소구분", "values": {"KRX": "1", "NXT": "2", "ALL": "3"}},
    "OPT10044": {"param_name": "거래소구분", "values": {"KRX": "1", "NXT": "2", "ALL": "3"}},
    "OPT10048": {"param_name": "거래소구분", "values": {"KRX": "1", "NXT": "2", "ALL": "3"}},
    "OPT10049": {"param_name": "거래소구분", "values": {"KRX": "1", "NXT": "2", "ALL": "3"}},
    "OPT10050": {"param_name": "거래소구분", "values": {"KRX": "1", "NXT": "2", "ALL": "3"}},
    "OPT10051": {"param_name": "거래소구분", "values": {"KRX": "1", "NXT": "2", "ALL": "3"}},
    "OPT10052": {"param_name": "거래소구분", "values": {"KRX": "1", "NXT": "2", "ALL": "3"}},
    "OPT10054": {"param_name": "거래소구분", "values": {"KRX": "1", "NXT": "2", "ALL": "3"}},
    "OPT10058": {"param_name": "거래소구분", "values": {"KRX": "1", "NXT": "2", "ALL": "3"}},
    "OPT10069": {"param_name": "거래소구분", "values": {"KRX": "1", "NXT": "2", "ALL": "3"}},
    "OPT10070": {"param_name": "거래소구분", "values": {"KRX": "1", "NXT": "2", "ALL": "3"}},
    "OPT10071": {"param_name": "거래소구분", "values": {"KRX": "1", "NXT": "2", "ALL": "3"}},
    "OPT10072": {"param_name": "거래소구분", "values": {"KRX": "1", "NXT": "2", "ALL": "3"}},
    "OPT10073": {"param_name": "거래소구분", "values": {"KRX": "1", "NXT": "2", "ALL": "3"}},
    "OPT10131": {"param_name": "거래소구분", "values": {"KRX": "1", "NXT": "2", "ALL": "3"}},
    "OPT40004": {"param_name": "거래소구분", "values": {"KRX": "1", "NXT": "2", "ALL": "3"}},
    "OPT90001": {"param_name": "거래소구분", "values": {"KRX": "1", "NXT": "2", "ALL": "3"}}, # ~ OPT90009 까지 동일
    "OPT90002": {"param_name": "거래소구분", "values": {"KRX": "1", "NXT": "2", "ALL": "3"}},
    "OPT90003": {"param_name": "거래소구분", "values": {"KRX": "1", "NXT": "2", "ALL": "3"}},
    "OPT90004": {"param_name": "거래소구분", "values": {"KRX": "1", "NXT": "2", "ALL": "3"}},
    "OPT90005": {"param_name": "거래소구분", "values": {"KRX": "1", "NXT": "2", "ALL": "3"}},
    "OPT90006": {"param_name": "거래소구분", "values": {"KRX": "1", "NXT": "2", "ALL": "3"}},
    "OPT90007": {"param_name": "거래소구분", "values": {"KRX": "1", "NXT": "2", "ALL": "3"}},
    "OPT90008": {"param_name": "거래소구분", "values": {"KRX": "1", "NXT": "2", "ALL": "3"}},
    "OPT90009": {"param_name": "거래소구분", "values": {"KRX": "1", "NXT": "2", "ALL": "3"}},

    # 유형 2: 거래소구분=0:통합, 1:KRX, 2:NXT (3개 TR)
    "OPT10075": {"param_name": "거래소구분", "values": {"ALL": "0", "KRX": "1", "NXT": "2"}},
    "OPT10076": {"param_name": "거래소구분", "values": {"ALL": "0", "KRX": "1", "NXT": "2"}},
    "OPT10085": {"param_name": "거래소구분", "values": {"ALL": "0", "KRX": "1", "NXT": "2"}},

    # 유형 3: 거래소구분=KRX:한국거래소, NXT:대체거래소 (3개 TR) - ALL(통합) 미지원으로 해석
    "OPW00004": {"param_name": "거래소구분", "values": {"KRX": "KRX", "NXT": "NXT"}},
    "OPW00005": {"param_name": "거래소구분", "values": {"KRX": "KRX", "NXT": "NXT"}},
    "OPW00018": {"param_name": "거래소구분", "values": {"KRX": "KRX", "NXT": "NXT"}},

    # 유형 4: 거래소구분=%:전체, KRX:한국거래소, NXT:대체거래소, SOR:최선주문집행 (3개 TR)
    "OPW00007": {"param_name": "거래소구분", "values": {"ALL": "%", "KRX": "KRX", "NXT": "NXT", "SOR": "SOR"}},
    "OPW00009": {"param_name": "거래소구분", "values": {"ALL": "%", "KRX": "KRX", "NXT": "NXT", "SOR": "SOR"}},
    "OPW00015": {"param_name": "거래소구분", "values": {"ALL": "%", "KRX": "KRX", "NXT": "NXT", "SOR": "SOR"}},
}

# 종목코드에 직접 _NX, _AL 접미사를 사용하는 TR 목록 (문서 확인 결과, "종목코드" 입력 TR 중 "거래소구분" 파라미터가 없는 TR들)
# "OPT10001", "OPT10002", ..., "OPT10087", (OPT4xxxx, OPT5xxxx 시리즈 등) - 문서의 2.1.1 및 2.1.2 항목 참고
TR_USES_SUFFIX_IN_STOCK_CODE = {
    "OPT10001", "OPT10002", "OPT10003", "OPT10004", "OPT10005", "OPT10006", "OPT10007", "OPT10008", "OPT10009", "OPT10010",
    "OPT10011", "OPT10012", "OPT10013", "OPT10014", "OPT10015", "OPT10053", "OPT10055", "OPT10056", "OPT10057",
    "OPT10074", "OPT10077", "OPT10078", "OPT10079", "OPT10080", "OPT10081", "OPT10082", "OPT10083", "OPT10084", "OPT10086", "OPT10087",
    # OPT4XXXX, OPT5XXXX 시리즈 등 문서 참고하여 추가 필요. 예: "OPT40001", "OPT50001"
}

# API 기본 시장 컨텍스트 (KRX를 기본으로 가정)
DEFAULT_MARKET_CONTEXT = 'KRX'

# Helper function to safely convert to int
def _safe_int(value_str, default=0):
    value_str = str(value_str).strip()
    if not value_str or value_str == '+' or value_str == '-':
        return default
    try:
        cleaned_value = value_str.replace('+', '').replace('-', '')
        if not cleaned_value:
            return default
        return int(cleaned_value)
    except ValueError:
        return default

# Helper function to safely convert to float
def _safe_float(value_str, default=0.0):
    value_str = str(value_str).strip()
    if not value_str or value_str == '+' or value_str == '-':
        return default
    try:
        cleaned_value = value_str.replace('%', '').replace('+', '').replace('-', '')
        if not cleaned_value:
            return default
        return float(cleaned_value)
    except ValueError:
        return default

def non_blocking_sleep_using_process_events(seconds):
    start_time = time.time()
    while time.time() - start_time < seconds:
        QApplication.processEvents()
        time.sleep(0.01)

class KiwoomAPI(QObject):
    def __init__(self, logger=None, config_manager=None, strategy_instance=None, screen_manager=None):
        super().__init__()
        self.logger = logger if logger else self._get_default_logger()
        self.config_manager = config_manager
        self.strategy_instance = strategy_instance
        self.log("키움 API 초기화 시작", "DEBUG")

        self.ocx = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1") # OCX 인스턴스 먼저 생성

        # ScreenManager 초기화 시 self.ocx 전달
        self.screen_manager = screen_manager if screen_manager else ScreenManager(logger=self.logger, kiwoom_ocx=self.ocx)
        self.log(f"ScreenManager 초기화 완료 (외부 제공: {screen_manager is not None}, OCX 전달됨)", "DEBUG")

        # self.ocx = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1") # 원래 위치
        self.connected = False
        self.tr_event_loop = None
        self.account_number = None
        self.account_list = []
        self.real_data_handlers = {}
        self.account_deposit_info = None
        self.subscribed_real_data = {}
        self.received_conditions = {}
        self.shutdown_mode = False # 종료 모드 플래그 추가

        self.last_request_time = time.time()
        if self.config_manager:
            # self.request_interval = self.config_manager.get_setting("API_Limit", "TR_REQUEST_INTERVAL", 0.21)
            interval_ms = self.config_manager.get_setting("API_Limit", "tr_request_interval_ms", 210) # 키 이름 및 기본값(ms) 수정
            self.request_interval = float(interval_ms) / 1000.0 # 초 단위로 변환
            self.continuous_request_interval = self.config_manager.get_setting("API_Limit", "TR_CONTINUOUS_REQUEST_INTERVAL", 1.0)
        else:
            self.request_interval = 0.21
            self.continuous_request_interval = 1.0

        self.log(f"TR 요청 간격 설정됨: 기본 {self.request_interval}초, 연속 {self.continuous_request_interval}초", "DEBUG")

        self.fid_map = {
            "주식시세": ["10", "11", "12", "27", "28", "15", "13", "14", "16", "17", "18", "25", "26", "30"], 
            "주식체결": ["20", "10", "11", "12", "27", "28", "15", "13", "14", "16", "17", "18", "292"], 
        }
        
        self.login_event_loop = None
        self.account_password = ""
        if self.config_manager:
            self.account_password = self.config_manager.get_setting("계좌정보", "비밀번호", "")
            self.log(f"설정에서 계좌 비밀번호 로드: {'비밀번호 있음' if self.account_password else '비밀번호 없음'}", "DEBUG")
        
        self._opt10081_timers = {}
        self.tr_data_cache = {}
        self.connect_events()

    def set_shutdown_mode(self, mode: bool):
        """API 종료 모드를 설정합니다. True로 설정되면 새로운 TR/주문 요청이 차단됩니다."""
        self.shutdown_mode = mode
        status_str = "활성화" if mode else "비활성화"
        self.log(f"종료 모드가 {status_str}되었습니다.", "INFO")

    def _parse_stock_code(self, full_code_str: str):
        """
        종목코드 문자열(예: "005930_NX")을 순수 종목코드, ATS 접미사, 시장 컨텍스트로 분리합니다.
        Returns:
            tuple: (pure_code, suffix, market_context_from_suffix, original_full_code)
                   market_context_from_suffix는 ATS_SUFFIX_MARKET_MAP의 value (예: 'NXT', 'ALL')이며, 없으면 None.
        """
        full_code = str(full_code_str).strip()
        pure_code = full_code
        suffix = None
        market_context_from_suffix = None

        for s, market_ctx in ATS_SUFFIX_MARKET_MAP.items():
            if full_code.endswith(s):
                potential_pure_code = full_code[:-len(s)]
                if (len(potential_pure_code) == 6 and potential_pure_code.isdigit()) or \
                   (len(potential_pure_code) > 0 and potential_pure_code[0].isalpha() and len(potential_pure_code[1:]) == 6 and potential_pure_code[1:].isdigit()):
                    pure_code = potential_pure_code
                    suffix = s
                    market_context_from_suffix = market_ctx
                    self.log(f"_parse_stock_code: ATS 접미사 '{s}' 감지. 입력 '{full_code}', 순수코드 '{pure_code}', 시장컨텍스트 '{market_context_from_suffix}'", "DEBUG")
                    break
        
        if not suffix:
            if (len(full_code) == 6 and full_code.isdigit()) or \
               (len(full_code) > 0 and full_code[0].isalpha() and len(full_code[1:]) == 6 and full_code[1:].isdigit()):
                self.log(f"_parse_stock_code: ATS 접미사 없음. 입력 '{full_code}'를 순수 코드로 간주.", "DEBUG")

        return pure_code, suffix, market_context_from_suffix, full_code

    def get_code_market_info(self, full_code_str: str):
        """
        종목코드 문자열을 분석하여 순수 종목코드와 시장 컨텍스트를 반환합니다.
        _parse_stock_code의 결과를 더 사용하기 쉽게 래핑합니다.
        Returns:
            tuple: (pure_code, market_context) 
                   market_context는 'KRX', 'NXT', 'ALL' 또는 None.
        """
        pure_code, suffix, market_context_from_suffix, _ = self._parse_stock_code(full_code_str)
        if market_context_from_suffix:
            return pure_code, market_context_from_suffix
        
        # 접미사가 없으면 KRX로 간주 (기본 시장)
        # 단, _parse_stock_code는 순수 코드만 잘 분리해주고 market_context_from_suffix는 None을 반환할 것임.
        # 따라서 여기서 KRX를 명시적으로 설정.
        if (len(pure_code) == 6 and pure_code.isdigit()) or \
           (len(pure_code) > 0 and pure_code[0].isalpha() and len(pure_code[1:]) == 6 and pure_code[1:].isdigit()):
            return pure_code, DEFAULT_MARKET_CONTEXT # DEFAULT_MARKET_CONTEXT는 'KRX'
            
        # 유효하지 않은 코드 형식일 경우
        self.log(f"get_code_market_info: 유효하지 않은 종목코드 형식으로 시장 컨텍스트를 결정할 수 없음: '{full_code_str}'", "WARNING")
        return pure_code, None

    def _get_api_market_param_value(self, tr_code: str, market_context: str):
        """ 
        주어진 TR 코드와 시장 컨텍스트(KRX, NXT, ALL)에 대해 
        "거래소구분"과 같은 파라미터에 설정할 실제 API 값을 반환합니다.
        Args:
            tr_code (str): 조회하려는 TR 코드
            market_context (str): KRX, NXT, ALL 등 시장 컨텍스트. None일 경우 DEFAULT_MARKET_CONTEXT 사용.
        Returns: 
            tuple: (param_name, param_value) - 설정할 파라미터 이름과 값.
                   설정할 파라미터가 없거나, 주어진 market_context에 대한 값이 TR_MARKET_PARAM_CONFIG에 없으면 (None, None).
        """
        eff_market_context = market_context.upper() if market_context else DEFAULT_MARKET_CONTEXT

        config = TR_MARKET_PARAM_CONFIG.get(tr_code)
        if config:
            param_name = config.get("param_name")
            param_value = config.get("values", {}).get(eff_market_context)
            
            if param_name and param_value is not None:
                self.log(f"TR [{tr_code}]에 대한 시장 파라미터: 컨텍스트='{eff_market_context}', 파라미터명='{param_name}', 설정값='{param_value}'", "DEBUG")
                return param_name, param_value
            else:
                self.log(f"TR [{tr_code}]에 대한 시장 컨텍스트 '{eff_market_context}'의 파라미터 값 정의를 TR_MARKET_PARAM_CONFIG에서 찾을 수 없음 (param_name: {param_name}, value_found: {param_value is not None}).", "WARNING")
        return None, None

    def _determine_code_for_tr_input(self, tr_code: str, original_full_code: str):
        """
        TR 조회 시 "종목코드" SetInputValue에 사용할 최종 코드 문자열을 결정합니다.
        - TR_USES_SUFFIX_IN_STOCK_CODE 목록에 있으면 접미사 포함 코드를 반환 (단, 접미사가 원래 있었던 경우).
        - 그렇지 않으면 (즉, "거래소구분" 파라미터를 사용하는 TR이면) 항상 순수 코드를 반환.
        Args:
            tr_code (str): 조회하려는 TR 코드
            original_full_code (str): 사용자가 입력한 원본 종목코드 (예: "005930", "005930_NX")
        Returns:
            str: SetInputValue에 사용할 최종 종목코드 문자열
        """
        pure_code, suffix, _, _ = self._parse_stock_code(original_full_code)

        if tr_code in TR_USES_SUFFIX_IN_STOCK_CODE:
            if suffix:
                self.log(f"TR [{tr_code}]은(는) 종목코드에 ATS 접미사를 직접 사용합니다. 코드: [{original_full_code}] 사용.", "INFO")
                return original_full_code
            else:
                self.log(f"TR [{tr_code}]은(는) 종목코드에 ATS 접미사를 사용할 수 있으나, 입력코드 [{original_full_code}]에 접미사 없음. KRX 조회로 간주하여 [{pure_code}] 사용.", "INFO")
                return pure_code
        else:
            self.log(f"TR [{tr_code}]은(는) '거래소구분' 파라미터를 사용할 가능성이 있으며, 종목코드는 순수 코드 [{pure_code}]를 사용합니다. (원본: {original_full_code})", "INFO")
            return pure_code

    def request_account_info(self, account_number_to_use=None):
        self.log("request_account_info 호출됨", "DEBUG")
        selected_account = account_number_to_use if account_number_to_use else self.account_number
        if not selected_account:
            self.log("계좌번호가 설정되지 않아 예수금 상세 현황을 요청할 수 없습니다.", "WARNING")
            return

        self.log(f"예수금 상세 현황 요청 시작: 계좌번호({selected_account})", "INFO")
        
        input_values = {
            "계좌번호": selected_account,
            "비밀번호": self.account_password,
            "비밀번호입력매체구분": "00",
            "조회구분": "2"
        }
        rq_name = "계좌예수금요청"
        screen_no = self.screen_manager.get_available_screen(rq_name)
        if not screen_no:
            self.log(f"'{rq_name}' 요청에 사용할 수 있는 화면 번호가 없습니다.", "ERROR")
            return
        
        # OPW00001은 "거래소구분" 파라미터 없음 (문서 확인)
        ret = self.comm_rq_data(rq_name, "opw00001", 0, screen_no, input_values_override=input_values, market_context=None)

        if ret == 0:
            self.log(f"'{rq_name}' 요청 성공 (TR: opw00001)", "DEBUG")
        else:
            self.log(f"'{rq_name}' 요청 실패 (TR: opw00001), 반환값: {ret}", "ERROR")
            self.screen_manager.release_screen(screen_no, rq_name) # 실패 시 화면 반환
        
    def connect_events(self):
        self.ocx.OnEventConnect.connect(self.on_event_connect)
        self.ocx.OnReceiveTrData.connect(self.on_receive_tr_data)
        self.ocx.OnReceiveRealData.connect(self.on_receive_real_data)
        self.ocx.OnReceiveChejanData.connect(self.on_receive_chejan_data)
        self.ocx.OnReceiveMsg.connect(self.on_receive_msg)
        
    def login(self):
        is_dry_run = False
        if self.config_manager:
            is_dry_run = self.config_manager.get_setting("매매전략", "dry_run_mode", False)

        if is_dry_run:
            self.log("[Dry Run] 로그인 처리 시작...", "INFO")
            self.connected = True
            
            configured_account = ""
            if self.config_manager:
                configured_account = self.config_manager.get_setting('계좌정보', '계좌번호', "")
            
            if configured_account and configured_account.strip():
                self.account_number = configured_account.strip()
                self.log(f"[Dry Run] 설정 파일에서 계좌번호 사용: {self.account_number}", "INFO")
            else:
                self.account_number = "DRYRUN_ACCOUNT_001" # 임시 계좌번호
                self.log(f"[Dry Run] 설정 파일에 계좌번호 없음. 임시 계좌번호 사용: {self.account_number}", "INFO")

            self.log(f"[Dry Run] 가상 로그인 성공. 계좌번호: {self.account_number}", "IMPORTANT")
            if self.strategy_instance and hasattr(self.strategy_instance, '_on_login_completed'):
                # QTimer를 사용하여 비동기적으로 _on_login_completed 호출 (실제 API와 유사한 흐름)
                QTimer.singleShot(100, lambda: self.strategy_instance._on_login_completed(self.account_number))
                self.log("[Dry Run] Strategy의 _on_login_completed 호출 예정 (비동기)", "DEBUG")
            else:
                self.log("[Dry Run] Strategy 인스턴스 또는 _on_login_completed 콜백 없음.", "WARNING")
            return True

        if self.connected:
            self.log(f"이미 로그인됨. 계좌번호: {self.account_number}")
            if self.strategy_instance and hasattr(self.strategy_instance, '_on_login_completed'):
                self.strategy_instance._on_login_completed(self.account_number)
            return True
            
        self.log("로그인 시도")
        self.ocx.dynamicCall("CommConnect()")
        self.login_event_loop = QEventLoop()
        self.login_event_loop.exec_()
        
        if self.connected:
            account_list_raw = self.get_login_info("ACCNO")
            parsed_acc_list = [acc.strip() for acc in account_list_raw.split(';') if acc.strip()]
            self.log(f"[LOGIN_DEBUG] Account list from API (raw): '{account_list_raw}', Parsed list: {parsed_acc_list}", "DEBUG")

            preferred_account = None
            if self.config_manager:
                preferred_account = self.config_manager.get_setting('계좌정보', '계좌번호')
            
            self.log(f"[LOGIN_DEBUG] Preferred account from config: '{preferred_account}'", "DEBUG")

            selected_account_for_login = ""
            found_preferred = False

            if preferred_account and preferred_account.strip():
                preferred_account_stripped = preferred_account.strip()
                for acc_from_api in parsed_acc_list:
                    if acc_from_api.strip() == preferred_account_stripped:
                        selected_account_for_login = preferred_account_stripped
                        self.log(f"[LOGIN_DEBUG] Using preferred account from settings: '{selected_account_for_login}'", "DEBUG")
                        found_preferred = True
                        break
            
            if not found_preferred:
                if parsed_acc_list:
                    selected_account_for_login = parsed_acc_list[0].strip()
                    self.log(f"[LOGIN_DEBUG] Preferred account not found. Using first account from API: '{selected_account_for_login}'", "WARNING")
                else:
                    self.log("[LOGIN_DEBUG] No accounts found from API list.", "ERROR")

            self.account_number = selected_account_for_login

            if self.account_number:
                self.log(f"로그인 성공. 계좌번호: {self.account_number}")
                # self.request_account_info(self.account_number) # Strategy에서 로그인 완료 후 계좌정보 요청을 담당
                if self.strategy_instance and hasattr(self.strategy_instance, '_on_login_completed'):
                    self.strategy_instance._on_login_completed(self.account_number)
                return True
            else:
                self.log("계좌번호 설정 실패.", "ERROR")
                self.connected = False
                if self.strategy_instance and hasattr(self.strategy_instance, '_on_login_completed'):
                    self.strategy_instance._on_login_completed("")
                return False
        else:
            self.log("로그인 실패 (self.connected is False)", "ERROR")
            if self.strategy_instance and hasattr(self.strategy_instance, '_on_login_completed'):
                self.strategy_instance._on_login_completed("")
            return False
            
    def get_login_info(self, tag):
        return self.ocx.dynamicCall("GetLoginInfo(QString)", tag).strip()

    def get_account_info(self):
        if self.account_deposit_info:
            self.log(f"저장된 계좌 정보 반환: {self.account_deposit_info.get('예수금')}", "DEBUG")
        else:
            self.log("저장된 계좌 정보 없음.", "DEBUG")
        return self.account_deposit_info
        
    def get_connect_state(self):
        ret = self.ocx.dynamicCall("GetConnectState()")
        return ret == 1
        
    def set_input_value(self, id_key, value):
        # self.ocx.dynamicCall(\\"SetInputValue(QString, QString)\\", id_key, value)
        # ATS 도입에 따라, SetInputValue는 CommRqData 호출 직전에 모아서 처리하는 방식으로 변경될 수 있음.
        # 여기서는 TR 요청별로 입력값을 임시 저장해두는 방식을 고려. (개선된 설계에서)
        # 중요: 이 메서드는 CommRqData 내부에서 input_values를 설정하는 방식으로 대체/보강되어야 합니다.
        # 현재 구현은 직접 API 호출을 하지 않으므로, shutdown_mode 체크는 CommRqData에서 합니다.
        pass # 이 함수는 더 이상 직접 사용되지 않을 수 있습니다.

    def comm_rq_data(self, rq_name: str, tr_code: str, prev_next: int, screen_no: str, input_values_override: Optional[Dict[str, str]] = None, market_context: str = None):
        """
        TR 요청을 서버로 전송합니다.
        ATS 지원을 위해 종목코드 및 거래소구분 파라미터를 내부적으로 조정합니다.
        """
        self.log(f"[KiwoomAPI] comm_rq_data PARAMS CHECK: rq_name='{rq_name}', tr_code='{tr_code}', input_values_override IS {'NOT None' if input_values_override is not None else 'None'}, market_context='{market_context}'", "DEBUG")
        if input_values_override is not None:
            self.log(f"[KiwoomAPI] comm_rq_data PARAMS CHECK: input_values_override CONTENT: {input_values_override}", "DEBUG")

        # === 드라이런 모드 TR 요청 처리 시작 ===
        is_dry_run = False
        if self.config_manager:
            is_dry_run = self.config_manager.get_setting("매매전략", "dry_run_mode", False)

        if is_dry_run and tr_code in ["opw00001", "opw00018"]: # 계좌 정보 관련 TR만 우선 처리
            self.log(f"[Dry Run] TR 요청 ({rq_name}, {tr_code}) 가상 처리 시작...", "INFO")
            
            current_time = time.time()
            if rq_name not in self.tr_data_cache or not isinstance(self.tr_data_cache.get(rq_name), dict):
                self.tr_data_cache[rq_name] = {} 
            
            self.tr_data_cache[rq_name].update({
                'status': 'pending_dry_run_callback', 
                'request_time': current_time,
                'tr_code': tr_code,
                'screen_no': screen_no,
                'params': { 
                    'rq_name': rq_name, 
                    'tr_code': tr_code, 
                    'prev_next': prev_next, 
                    'screen_no': screen_no, 
                    'input_values': input_values_override if input_values_override is not None else (getattr(self, 'tr_input_values', {}).copy() if hasattr(self, 'tr_input_values') else {}),
                    'market_context': market_context
                },
                'single_data': {}, 
                'multi_data': [],
                'error_code': None, 
                'error_message': None
            })
            self.log(f"[Dry Run] TR 요청 '{rq_name}'에 대한 캐시 준비 완료 (status: pending_dry_run_callback).", "DEBUG")

            QTimer.singleShot(50, lambda: self._emulate_tr_receive_for_dry_run(screen_no, rq_name, tr_code))
            self.log(f"[Dry Run] {tr_code} TR에 대한 가상 응답 콜백이 예약되었습니다 (RQName: {rq_name}, ScreenNo: {screen_no}).", "DEBUG")
            return 0 
        # === 드라이런 모드 TR 요청 처리 끝 ===

        if self.shutdown_mode:
            self.log(f"종료 모드 활성화 중. TR 요청 ({rq_name}, {tr_code})을 보내지 않습니다.", "WARNING")
            return -999 

        self.log(f"[KiwoomAPI] comm_rq_data 호출 시작: RQName={rq_name}, TRCode={tr_code}, PrevNext={prev_next}, ScreenNo={screen_no}, OverrideInputs={input_values_override is not None}, MarketCtx={market_context}", "CRITICAL" if self.logger.log_level <= logging.DEBUG else "DEBUG")

        current_time = time.time()
        elapsed_time = current_time - self.last_request_time
        required_interval = self.continuous_request_interval if prev_next == 2 else self.request_interval
        
        if elapsed_time < required_interval:
            sleep_duration = required_interval - elapsed_time
            self.log(f"[KiwoomAPI] TR 요청 간격 조절: {sleep_duration:.3f}초 대기 (이전 요청 후 {elapsed_time:.3f}초 경과, 필요 간격 {required_interval}초)", "DEBUG")
            non_blocking_sleep_using_process_events(sleep_duration)

        try:
            self.log(f"[KiwoomAPI] CommRqData TR요청 시작: {rq_name}, {tr_code}, scr:{screen_no}", "DEBUG")
            
            if rq_name not in self.tr_data_cache or not isinstance(self.tr_data_cache.get(rq_name), dict) or \
               self.tr_data_cache[rq_name].get('status') in ['completed', 'error', 'exception']:
                self.log(f"[KiwoomAPI][CACHE_SETUP] RQName '{rq_name}' 캐시 초기화/재초기화.", "DEBUG")
                self.tr_data_cache[rq_name] = {}

            if not isinstance(self.tr_data_cache.get(rq_name), dict): 
                self.log(f"[KiwoomAPI][CACHE_CRITICAL_ERROR] '{rq_name}' 캐시가 dict가 아님! 강제 초기화.", "CRITICAL")
                self.tr_data_cache[rq_name] = {}

            self.tr_data_cache[rq_name].update({
                'status': 'pending_api_call',
                'request_time': current_time, 
                'tr_code': tr_code,
                'screen_no': screen_no,
                'params': { 
                    'rq_name': rq_name, 
                    'tr_code': tr_code, 
                    'prev_next': prev_next, 
                    'screen_no': screen_no, 
                    'input_values': input_values_override if input_values_override is not None else (self.tr_input_values.copy() if hasattr(self, 'tr_input_values') else {}),
                    'market_context': market_context
                },
                'chunks': self.tr_data_cache[rq_name].get('chunks', []),
                'multi_data': self.tr_data_cache[rq_name].get('multi_data', []),
                'single_data': self.tr_data_cache[rq_name].get('single_data', {}),
                'error_code': None,
                'error_message': None
            })
            self.log(f"[KiwoomAPI][CACHE_SETUP_SUCCESS] RQName: '{rq_name}' 캐시 업데이트 완료 (status: pending_api_call).", "DEBUG")

            current_inputs = {}
            if hasattr(self, 'tr_input_values') and self.tr_input_values:
                current_inputs.update(self.tr_input_values)
            
            if input_values_override:
                current_inputs.update(input_values_override)

            self.log(f"[KiwoomAPI] [CommRqData_INPUT_PREP] 최종 입력값 설정 전: {current_inputs}", "DEBUG")
            
            original_stock_code_from_inputs = current_inputs.get("종목코드")
            market_for_code = None 
            if original_stock_code_from_inputs:
                final_stock_code = self._determine_code_for_tr_input(tr_code, original_stock_code_from_inputs)
                _pure_code, _suffix, market_context_from_suffix, _ = self._parse_stock_code(original_stock_code_from_inputs)
                market_for_code = market_context if market_context else market_context_from_suffix 

                if final_stock_code:
                    current_inputs["종목코드"] = final_stock_code
                    self.log(f"[KiwoomAPI] ATS 종목코드 자동 조정: TR='{tr_code}', 원본코드='{original_stock_code_from_inputs}', 조정코드='{final_stock_code}', 최종 사용 컨텍스트 추정='{market_for_code if market_for_code else DEFAULT_MARKET_CONTEXT}'", "DEBUG")

            if tr_code in TR_MARKET_PARAM_CONFIG:
                param_name, param_value = self._get_api_market_param_value(tr_code, market_context if market_context else (market_for_code if market_for_code else DEFAULT_MARKET_CONTEXT))
                if param_name and param_value is not None:
                    current_inputs[param_name] = param_value
                    self.log(f"[KiwoomAPI] ATS 거래소구분 자동 설정: TR='{tr_code}', 파라미터='{param_name}', 값='{param_value}', 사용된 컨텍스트='{market_context if market_context else (market_for_code if market_for_code else DEFAULT_MARKET_CONTEXT)}'", "DEBUG")

            self.log(f"[KiwoomAPI] [CommRqData_INPUT_FINAL] 최종 입력값 API 전달: {current_inputs}", "DEBUG")
            for key, value in current_inputs.items():
                self.log(f"[KiwoomAPI] SetInputValue: Key='{key}', Value='{str(value)}'", "DEBUG")
                self.ocx.SetInputValue(key, str(value))

            ret = self.ocx.dynamicCall("CommRqData(QString, QString, int, QString)", 
                                       rq_name, tr_code, prev_next, screen_no)
            
            self.log(f"[KiwoomAPI] [CommRqData_CALL] CommRqData 호출: RQName='{rq_name}', TRCode='{tr_code}', PrevNext={prev_next}, ScreenNo='{screen_no}', ReturnCode={ret}", "CRITICAL")

            if hasattr(self, 'tr_input_values'): 
                self.tr_input_values.clear()

            if ret != 0:
                error_msg = self.get_error_message(ret)
                self.log(f"[KiwoomAPI] CommRqData 요청 실패: RQName='{rq_name}', TRCode='{tr_code}', ErrorCode={ret}, Msg={error_msg}", "ERROR")
                if rq_name in self.tr_data_cache:
                    self.tr_data_cache[rq_name]['status'] = 'error'
                    self.tr_data_cache[rq_name]['error_code'] = ret
                    self.tr_data_cache[rq_name]['error_message'] = error_msg
            else:
                self.log(f"[KiwoomAPI] CommRqData 요청 성공: RQName='{rq_name}', TRCode='{tr_code}'. 데이터 수신 대기 중...", "DEBUG")
                if rq_name in self.tr_data_cache:
                     self.tr_data_cache[rq_name]['status'] = 'pending_response'
            
            self.last_request_time = time.time() 
            return ret

        except Exception as e:
            detailed_error = traceback.format_exc()
            self.log(f"[KiwoomAPI] comm_rq_data 중 예외 발생: {e}\n{detailed_error}", "ERROR")
            if rq_name in self.tr_data_cache: 
                self.tr_data_cache[rq_name]['status'] = 'exception'
                self.tr_data_cache[rq_name]['error_message'] = str(e)
            return -999

    def get_repeat_cnt(self, tr_code, rq_name):
        return self.ocx.dynamicCall("GetRepeatCnt(QString, QString)", tr_code, rq_name)
        
    def get_comm_data(self, tr_code, rq_name, index, item_name):
        data = self.ocx.dynamicCall("GetCommData(QString, QString, int, QString)", tr_code, rq_name, index, item_name)
        return data.strip()
        
    def get_comm_real_data(self, code, fid):
        data = self.ocx.dynamicCall("GetCommRealData(QString, int)", code, fid)
        return data.strip()
        
    def get_chejan_data(self, fid):
        data = self.ocx.dynamicCall("GetChejanData(int)", fid)
        return data.strip()

    def get_error_message(self, err_code):
        # ... (오류 메시지 함수 내용은 동일하게 유지) ...
        if err_code == 0: return "정상처리"
        if err_code == -100: return "사용자 정보교환 실패"
        if err_code == -101: return "서버 접속 실패"
        if err_code == -102: return "버전 처리 실패"
        if err_code == -200: return "시세조회 과부하"
        if err_code == -201: return "전문작성 역오류"
        if err_code == -202: return "시세조회 제한"
        if err_code == -300: return "입력값 오류"
        return f"알 수 없는 에러 ({err_code})"
        
    def set_real_reg(self, screen_no, code_list_str, fid_list_str, opt_type):
        self.log(f"실시간 데이터 등록 요청: 화면({screen_no}), 종목({code_list_str}), FID({fid_list_str}), 타입({opt_type})")
        ret = self.ocx.dynamicCall("SetRealReg(QString, QString, QString, QString)", screen_no, code_list_str, fid_list_str, opt_type)
        if ret == 0:
            self.log(f"실시간 데이터 등록 성공: 화면({screen_no})")
        else:
            self.log(f"실시간 데이터 등록 실패: {ret} - 화면({screen_no})", "ERROR")
        return ret
        
    def unsubscribe_real_data(self, screen_no, code=None):
        self.log(f"실시간 데이터 구독 해제 요청: 화면({screen_no}), 코드({code if code else 'ALL'})", "INFO")
        self.ocx.dynamicCall("DisconnectRealData(QString)", screen_no)
        if screen_no in self.subscribed_real_data:
            removed_subs = self.subscribed_real_data.pop(screen_no, None)
            if removed_subs:
                self.log(f"{screen_no} 화면의 모든 실시간 구독 관리 정보 제거됨: {removed_subs}", "DEBUG")
        self.log(f"화면번호 {screen_no}의 실시간 데이터 구독 해제 완료.")

    def disconnect_real_data(self, screen_no):
        self.ocx.dynamicCall("DisconnectRealData(QString)", screen_no)

    def unsubscribe_all_real_data(self):
        """모든 실시간 데이터 구독을 해제합니다."""
        try:
            self.ocx.dynamicCall("SetRealRemove(QString, QString)", "ALL", "ALL")
            self.log("모든 실시간 데이터 구독 해제 요청됨 (SetRealRemove ALL, ALL).", "INFO")
            # 내부 구독 관리 상태도 초기화
            for code in list(self.subscribed_real_data.keys()):
                if "subscribed_fids" in self.subscribed_real_data[code]:
                    self.subscribed_real_data[code]["subscribed_fids"].clear()
                if "screen_no" in self.subscribed_real_data[code]:
                    # 화면번호 자체는 DisconnectRealData에서 처리하므로 여기서는 FID 목록만 정리
                    pass 
            # self.subscribed_real_data.clear() # screen_no 정보는 유지될 수 있도록 FID만 비움
            self.log("내부 실시간 데이터 구독 상태 (FID 목록) 초기화 완료.", "DEBUG")
        except Exception as e:
            self.log(f"모든 실시간 데이터 구독 해제 중 예외 발생: {e}", "ERROR", exc_info=True)

    def send_order(self, rq_name, screen_no, acc_no, order_type, code, quantity, price, hoga_gb, org_order_no=""):
        self.log(f"[KiwoomAPI_SEND_ORDER_ENTRY_DEBUG] send_order 진입. acc_no: '{acc_no}', order_type: {order_type}, code: {code}", "DEBUG")
        cleaned_acc_no = str(acc_no).strip() if acc_no else ""
        if not cleaned_acc_no:
            self.log(f"[KiwoomAPI_SEND_ORDER_ERROR] acc_no 공백 또는 유효하지 않음! RQName: {rq_name}, Code: {code}", "ERROR")
            current_stack = "".join(traceback.format_stack())
            self.log(f"[KiwoomAPI_SEND_ORDER_ERROR] 호출 스택:\n{current_stack}", "ERROR")
            return -999

        original_code_input_for_order = str(code)
        pure_code_for_order, suffix_in_code, _, _ = self._parse_stock_code(original_code_input_for_order)

        if suffix_in_code:
            self.log(f"경고: 주문 시 입력된 종목코드 '{original_code_input_for_order}'에 ATS 접미사 '{suffix_in_code}' 포함. 주문에는 순수 종목코드 '{pure_code_for_order}' 사용.", "WARNING")
        
        final_code_for_api_order = pure_code_for_order
        self.log(f"주문 처리: 최종 API 전달 종목코드='{final_code_for_api_order}' (원본: '{original_code_input_for_order}'), 주문유형='{order_type}' (시장 정보 포함 가정)", "INFO")

        order_args = [
            str(rq_name), str(screen_no), cleaned_acc_no, int(order_type),
            final_code_for_api_order, int(quantity), int(price), str(hoga_gb),
            str(org_order_no) if org_order_no else ""
        ]
        self.log(f"[KiwoomAPI_SEND_ORDER_ARGS_DEBUG] SendOrder 인자 리스트 (ATS 처리 후): {order_args}", "DEBUG")

        is_dry_run = False
        if self.config_manager:
            is_dry_run = self.config_manager.get_setting("매매전략", "dry_run_mode", False)

        if is_dry_run:
            self.log(f"[Dry Run] 주문 요청: {order_args}", "INFO")
            dry_run_order_no = f"DRYRUN_{final_code_for_api_order}_{int(time.time())}"
            chejan_data = {
                'gubun': '0', '9201': cleaned_acc_no, '9001': final_code_for_api_order,
                '913': '2', '908': datetime.now().strftime('%H%M%S'),
                '9203': dry_run_order_no, '904': str(price), '905': str(quantity),
                '906': '0', '910': str(price), '911': str(quantity),
                '902': "+매수" if order_type == 1 else ("-매도" if order_type == 2 else "정정취소"),
                '919': str(hoga_gb), 'original_rq_name': str(rq_name)
            }
            self.log(f"[Dry Run] 가상 체결 데이터 생성: {chejan_data}", "DEBUG")
            if self.strategy_instance and hasattr(self.strategy_instance, 'on_chejan_data_received'):
                QTimer.singleShot(100, lambda: self.strategy_instance.on_chejan_data_received('0', chejan_data.copy()))
                self.log(f"[Dry Run] 가상 체결 전달 예정", "DEBUG")
            else:
                self.log(f"[Dry Run] strategy_instance 또는 on_chejan_data_received 없음. 가상 체결 전달 불가", "WARNING")
            return 0
        else:
            return_code = self.ocx.dynamicCall(
                "SendOrder(QString, QString, QString, int, QString, int, int, QString, QString)", order_args
            )
            if return_code == 0:
                self.log(f"주문 전송 성공: {rq_name}, 화면번호: {screen_no}")
            else:
                self.log(f"주문 전송 실패: {return_code} - {self.get_error_message(return_code)} ({rq_name}, 화면번호: {screen_no})", "ERROR")
            return return_code

    def cancel_order(self, rq_name_cancel, screen_no, acc_no, original_order_type_str, stock_code, quantity_to_cancel, original_order_no):
        """
        기존 주문을 취소합니다.
        Args:
            rq_name_cancel (str): 취소 주문에 대한 새로운 요청명
            screen_no (str): 사용할 화면 번호
            acc_no (str): 계좌번호
            original_order_type_str (str): 원주문의 유형 ("매수" 또는 "매도")
            stock_code (str): 취소할 주문의 종목코드 (순수 코드)
            quantity_to_cancel (int): 취소할 수량 (보통 전량 취소)
            original_order_no (str): 취소할 원주문의 주문번호
        Returns:
            int: API 호출 결과 (0: 성공, 나머지: 실패)
        """
        self.log(f"[KiwoomAPI_CANCEL_ORDER_ENTRY] cancel_order 진입. RQName: {rq_name_cancel}, 원주문번호: {original_order_no}", "DEBUG")
        cleaned_acc_no = str(acc_no).strip() if acc_no else ""
        if not cleaned_acc_no:
            self.log(f"[KiwoomAPI_CANCEL_ORDER_ERROR] 계좌번호 유효하지 않음! RQName: {rq_name_cancel}", "ERROR")
            return -998 # 내부 정의 에러 코드

        if not original_order_no:
            self.log(f"[KiwoomAPI_CANCEL_ORDER_ERROR] 원주문번호 누락! RQName: {rq_name_cancel}", "ERROR")
            return -997 # 내부 정의 에러 코드
            
        pure_stock_code, _, _, _ = self._parse_stock_code(stock_code) # 순수 종목코드 사용

        # 원주문 유형에 따라 취소 주문 유형 결정
        cancel_order_type_code = 0
        if original_order_type_str.lower() == "매수":
            cancel_order_type_code = 3  # 매수취소
        elif original_order_type_str.lower() == "매도":
            cancel_order_type_code = 4  # 매도취소
        else:
            self.log(f"[KiwoomAPI_CANCEL_ORDER_ERROR] 알 수 없는 원주문 유형: {original_order_type_str}. RQName: {rq_name_cancel}", "ERROR")
            return -996 # 내부 정의 에러 코드

        self.log(f"주문 취소 요청: RQName='{rq_name_cancel}', 화면='{screen_no}', 계좌='{cleaned_acc_no}', "
                   f"취소유형코드='{cancel_order_type_code}', 종목코드='{pure_stock_code}', 수량='{quantity_to_cancel}', "
                   f"가격=0 (취소 시 무의미), 호가구분='00' (지정가 - 취소 시 보통 사용), 원주문번호='{original_order_no}'", "INFO")

        # 주문 취소 시 가격은 0, 호가구분은 "00"(지정가) 또는 "03"(시장가) 중 API가 허용하는 방식 사용 (보통 지정가 "00")
        # SendOrder(sRQName, sScreenNo, sAccNo, nOrderType, sCode, nQty, nPrice, sHogaGb, sOrgOrderNo)
        order_args = [
            str(rq_name_cancel),
            str(screen_no),
            cleaned_acc_no,
            cancel_order_type_code,
            str(pure_stock_code),
            int(quantity_to_cancel),
            0,  # 취소 시 가격은 0
            "00", # 취소 시 호가구분 (지정가)
            str(original_order_no)
        ]
        self.log(f"[KiwoomAPI_CANCEL_ORDER_ARGS_DEBUG] SendOrder 인자 리스트: {order_args}", "DEBUG")
        
        # Dry Run 모드에서는 실제 주문 전송 안 함 (필요 시 추가 로직)
        is_dry_run = False
        if self.config_manager:
            is_dry_run = self.config_manager.get_setting("매매전략", "dry_run_mode", False)

        if is_dry_run:
            self.log(f"[Dry Run] 주문 취소 요청 (실제 전송 안함): {order_args}", "INFO")
            # Dry Run 시 가상 체결 데이터 생성 및 on_chejan_data_received 호출 로직 (send_order 참조)
            # 여기서는 취소 성공을 가정하고 0 반환
            # 실제로는 취소에 대한 체결 데이터도 모방해야 함
            # gubun '0', 주문상태 '취소', 미체결량 0 등
            return 0 
        else:
            return_code = self.ocx.dynamicCall(
                "SendOrder(QString, QString, QString, int, QString, int, int, QString, QString)",
                order_args
            )
            if return_code == 0:
                self.log(f"주문 취소 전송 성공: {rq_name_cancel}, 원주문번호: {original_order_no}")
            else:
                self.log(f"주문 취소 전송 실패: {return_code} - {self.get_error_message(return_code)} ({rq_name_cancel}, 원주문번호: {original_order_no})", "ERROR")
            return return_code
        
    def on_event_connect(self, err_code):
        if err_code == 0:
            self.connected = True
            self.log("로그인 성공 (이벤트 수신) - 연결 상태만 변경")
        else:
            self.connected = False
            self.log(f"로그인 실패 (이벤트 수신): {err_code} ({self.get_error_message(err_code)})", "ERROR")
        if self.login_event_loop and self.login_event_loop.isRunning():
            self.login_event_loop.exit()
        
    def on_receive_tr_data(self, sScrNo, sRQName, sTrCode, sRecordName, sPrevNext, nDataLength, sErrorCode, sMessage, sSplmMsg):
        self.log(f"[EVENT_HANDLER_ENTRY] on_receive_tr_data: Scr='{sScrNo}', RQ='{sRQName}', TR='{sTrCode}', PrevNext='{sPrevNext}', ErrCode='{sErrorCode}', Msg='{sMessage}'", "CRITICAL")

        processed_error_code = 0
        if isinstance(sErrorCode, str) and sErrorCode.strip().lstrip('-').isdigit():
            processed_error_code = int(sErrorCode.strip())
        elif sErrorCode and str(sErrorCode).strip(): # 에러코드가 있지만 숫자 변환 실패 시
            self.log(f"TR 오류 코드 형식 오류: '{sErrorCode}' ({type(sErrorCode)}). 0으로 처리. ({sRQName}, {sTrCode})", "WARNING")

        # 캐시가 comm_rq_data에서 미리 준비되었는지 확인 및 업데이트
        if sRQName not in self.tr_data_cache or not isinstance(self.tr_data_cache.get(sRQName), dict):
            self.log(f"on_receive_tr_data: {sRQName} 캐시가 없거나 dict가 아님! 비정상. 강제 초기화 시도.", "ERROR")
            self.tr_data_cache[sRQName] = {
                'status': 'error', 'error': 'Cache not initialized by comm_rq_data',
                'tr_code': sTrCode, 'screen_no': sScrNo, 'prev_next': sPrevNext,
                'single_data':{}, 'multi_data':[], 'data':[] # 'data' 추가
            }
        
        # 에러 발생 시 우선 처리
        if processed_error_code != 0:
            full_error_message = f"TR API 오류: {self.get_error_message(processed_error_code)} (코드:{processed_error_code}) - 서버메시지: {sMessage} ({sSplmMsg})"
            self.log(f"{full_error_message} ({sRQName}, {sTrCode})", "ERROR")
            if sRQName in self.tr_data_cache and isinstance(self.tr_data_cache[sRQName], dict): # 방어 코드
                self.tr_data_cache[sRQName]['error'] = full_error_message
                self.tr_data_cache[sRQName]['status'] = 'error'
            self.screen_manager.release_screen(sScrNo, sRQName) # 에러 시 화면번호 즉시 반환
            self.log(f"화면번호 반납 (TR API 오류): {sScrNo} ({sRQName})", "DEBUG")
            if self.tr_event_loop and self.tr_event_loop.isRunning(): self.tr_event_loop.exit()
            # Strategy에 오류 알림 (선택적)
            if self.strategy_instance and hasattr(self.strategy_instance, 'on_tr_request_failed'):
                 self.strategy_instance.on_tr_request_failed(sRQName, sTrCode, full_error_message)
            return

        # 정상 응답 데이터 파싱
        parsed_data = self._parse_tr_data(sTrCode, sRQName, sScrNo, sPrevNext) # 수정된 _parse_tr_data 사용
        if sRQName in self.tr_data_cache and isinstance(self.tr_data_cache[sRQName], dict): # 방어 코드
            self.tr_data_cache[sRQName].update(parsed_data) # 파싱된 결과를 캐시에 반영 (single_data, multi_data 등)
        else: # 캐시가 여전히 없다면 (위에서 초기화 실패 등 극히 예외적 상황)
            self.log(f"on_receive_tr_data: 파싱 후에도 {sRQName} 캐시 없거나 dict 아님. 데이터 처리 불가.", "ERROR")
            self.screen_manager.release_screen(sScrNo, sRQName)
            if self.tr_event_loop and self.tr_event_loop.isRunning(): self.tr_event_loop.exit()
            return

        # TR 코드별 핸들러 호출 또는 직접 처리
        if sTrCode == "opt10001":
            self._handle_opt10001(sRQName, parsed_data)
        elif sTrCode == "opt10081":
            # _handle_opt10081은 데이터 누적 및 최종 완료 시 콜백 역할만 하도록 변경 가능
            # 또는 연속 조회 로직을 _handle_opt10081 내부에 두되, QTimer 대신 직접 CommRqData 호출하도록 수정
            # 여기서는 사용자 지침에 따라 on_receive_tr_data 내에서 직접 처리 시도
            
            current_data_chunk = parsed_data.get('multi_data', [])
            self.log(f"on_receive_tr_data (opt10081, RQ='{sRQName}'): 수신 청크 {len(current_data_chunk)}건, PrevNext={sPrevNext}", "DEBUG")

            # 캐시의 'data' 필드는 모든 청크를 누적하기 위해 사용
            if 'data' not in self.tr_data_cache[sRQName] or not isinstance(self.tr_data_cache[sRQName]['data'], list): # None 또는 list가 아닌 경우 대비
                 self.tr_data_cache[sRQName]['data'] = []
            self.tr_data_cache[sRQName]['data'].extend(current_data_chunk)
            self.tr_data_cache[sRQName]['multi_data'] = current_data_chunk # 현재 청크 반영
            self.log(f"opt10081 데이터 캐시에 누적 (RQ='{sRQName}'): 이번 청크 {len(current_data_chunk)}건, 총 {len(self.tr_data_cache[sRQName]['data'])}건", "DEBUG")

            if sPrevNext == '2': # 연속 조회
                self.log(f"opt10081 연속 조회 진행 (RQ='{sRQName}', Screen='{sScrNo}')", "INFO")
                
                # 다음 요청을 위한 파라미터 가져오기 (comm_rq_data에서 저장한 값)
                request_info = self.tr_data_cache[sRQName].get('params', {})
                if not request_info:
                    self.log(f"opt10081 연속 조회 중단: RQ='{sRQName}'에 대한 캐시된 요청 파라미터 없음.", "ERROR")
                    self.tr_data_cache[sRQName]['status'] = 'error'
                    self.tr_data_cache[sRQName]['error_message'] = '연속조회 파라미터 누락(캐시)'
                    self.screen_manager.release_screen(sScrNo, sRQName) # 화면 반납
                    if self.tr_event_loop and self.tr_event_loop.isRunning(): self.tr_event_loop.exit()
                    return

                original_input_values = request_info.get('input_values', {})
                stock_code_for_next = original_input_values.get('종목코드') # CommRqData에 전달된 종목코드 (접미사 포함 가능)
                base_date_for_next = original_input_values.get('기준일자') # 수정주가구분 등도 여기서 가져올 수 있음
                # market_context_for_next = request_info.get('market_context') # opt10081은 market_context 직접 사용 안함

                if not stock_code_for_next or not base_date_for_next:
                    self.log(f"opt10081 연속 조회 중단: 다음 요청을 위한 종목코드 또는 기준일자 누락. RQ='{sRQName}', CachedInputs: {original_input_values}", "ERROR")
                    self.tr_data_cache[sRQName]['status'] = 'error'
                    self.tr_data_cache[sRQName]['error_message'] = '연속조회 파라미터 부족(입력값)'
                    self.screen_manager.release_screen(sScrNo, sRQName) # 화면 반납
                    if self.tr_event_loop and self.tr_event_loop.isRunning(): self.tr_event_loop.exit()
                    return

                # 연속 조회 시 요청 간격 준수
                current_time = time.time()
                elapsed_time = current_time - self.last_request_time # self.last_request_time은 comm_rq_data에서 업데이트됨
                required_interval = self.continuous_request_interval
                
                if elapsed_time < required_interval:
                    sleep_duration = required_interval - elapsed_time
                    self.log(f"[KiwoomAPI] opt10081 연속 조회 간격 조절: {sleep_duration:.3f}초 대기 (이전 요청 후 {elapsed_time:.3f}초 경과, 필요 간격 {required_interval}초)", "DEBUG")
                    non_blocking_sleep_using_process_events(sleep_duration)
                
                # SetInputValue는 comm_rq_data 내부에서 처리하므로, 여기서는 input_values_override로 전달
                # sRQName (최초 요청명), sTrCode ("opt10081"), nPrevNext (2), sScreenNo (최초 화면번호) 사용
                self.log(f"opt10081 연속 조회 CommRqData 직접 호출: RQ='{sRQName}', TR='{sTrCode}', PrevNext=2, Screen='{sScrNo}'", "DEBUG")
                
                # 연속 조회 로직 비활성화 (사용자 요청: 단일 조회로 변경)
                # ret_continuous = self.comm_rq_data(...)
                # 관련 로직 모두 주석 처리 또는 삭제
                self.log(f"opt10081 수신 (RQ='{sRQName}', Screen='{sScrNo}'): PrevNext='2' 이지만, 단일 조회 원칙에 따라 추가 TR 요청은 하지 않고 현재까지 수신된 데이터로 처리합니다.", "INFO")
                
                # 현재까지 누적된 모든 데이터를 Strategy로 전달
                cached_item = self.tr_data_cache[sRQName]
                original_params = cached_item.get('params', {})
                code_for_signal_raw = original_params.get('input_values', {}).get('종목코드')
                pure_code_for_signal, _, _, _ = self._parse_stock_code(str(code_for_signal_raw))
                
                all_accumulated_data = cached_item.get('data', []) # 누적된 전체 데이터
                self.log(f"opt10081 (PrevNext='2' 처리): RQ='{sRQName}', Code='{pure_code_for_signal}'. 총 {len(all_accumulated_data)}건. Strategy로 전달.", "INFO")
                if self.strategy_instance and hasattr(self.strategy_instance, 'on_daily_chart_data_ready'):
                    self.strategy_instance.on_daily_chart_data_ready(sRQName, pure_code_for_signal, all_accumulated_data)
                
                self.tr_data_cache[sRQName]['status'] = 'completed_continuous_stopped' # 상태 명시 (이전: completed_partial_continuous_stopped)
                self.screen_manager.release_screen(sScrNo, sRQName) # 화면 반환
                # 이벤트 루프는 on_receive_tr_data의 마지막 공통 로직에서 처리될 것임 (sPrevNext !='2' 분기에서)
                # 하지만 sPrevNext=='2'일때도 return 전에 루프 종료가 필요할 수 있으므로, 아래 공통 로직 재확인 필요.
                # 현재 공통 로직은 sPrevNext=='2' and opt10081일때 루프 종료를 안 하므로, 여기서 명시적으로 할 필요는 없음.
                return # 여기서 핸들러 종료 (중요: 아래 로직 실행 안 되도록)

            
            # sPrevNext != '2' (단일 조회 완료 또는 이전 로직에 따른 연속 조회의 마지막) 에 대한 처리:
            # 위에서 sPrevNext == '2'인 경우 return 했으므로, 이 'else'는 항상 sPrevNext != '2'인 경우를 의미하게 됩니다.
            # 따라서 아래 코드는 sPrevNext != '2'일 때 실행됩니다.
            # else: # sPrevNext != '2', 즉 연속 조회 아님 (조회 완료) -> 이 else는 위 if 조건과 대비되므로 유지합니다.
                cached_item = self.tr_data_cache[sRQName]
                original_params = cached_item.get('params', {})
                code_for_signal_raw = original_params.get('input_values', {}).get('종목코드')
                pure_code_for_signal, _, _, _ = self._parse_stock_code(str(code_for_signal_raw)) # 순수 코드 추출

                all_accumulated_data = cached_item.get('data', [])
                self.log(f"opt10081 모든 데이터 수신 완료 (RQ='{sRQName}', CodeForSignal='{pure_code_for_signal}'). 총 {len(all_accumulated_data)}건. Strategy로 전달.", "INFO")
                if self.strategy_instance and hasattr(self.strategy_instance, 'on_daily_chart_data_ready'):
                    self.strategy_instance.on_daily_chart_data_ready(sRQName, pure_code_for_signal, all_accumulated_data)
                
                # 화면번호 반환 및 루프 종료는 아래 공통 로직에서 처리됨.
                self.tr_data_cache[sRQName]['status'] = 'completed' # 최종 완료 상태로 명시
                # 화면 반환 및 이벤트 루프 관련 처리는 on_receive_tr_data의 공통 로직으로 이동

        elif sTrCode == "opw00001":
            self._handle_opw00001(sRQName, parsed_data)
        elif sTrCode == "opw00018":
            self._handle_opw00018(sRQName, parsed_data)
        else:
            self.log(f"기타 TR 코드({sTrCode}) 수신. 일반 핸들러 호출. RQName({sRQName})", "DEBUG")
            self._handle_generic_tr(sTrCode, sRQName, parsed_data)

        # 이벤트 루프 및 화면번호 관리 (공통)
        # opt10081 연속 조회(sPrevNext=='2') 시에는 위에서 직접 다음 요청을 보내고,
        # 현재 요청에 대한 루프는 종료되어야 다음 요청의 루프가 돌 수 있음.
        # 화면번호는 연속 조회 중에는 유지되어야 함.
        if sTrCode == "opt10081" and sPrevNext == '2':
            self.log(f"opt10081 연속 조회 중 (RQ='{sRQName}', Screen='{sScrNo}'). 화면 유지. 현재 이벤트 루프 종료 준비.", "DEBUG")
            # if self.tr_event_loop and self.tr_event_loop.isRunning(): # REMOVED: Should not exit global/shared event loop from TR callback
            #     self.tr_event_loop.exit()
        elif sPrevNext != '2': # 연속 조회가 아니거나, opt10081이 아닌 TR의 최종/단일 응답
            self.log(f"TR({sTrCode}, RQ='{sRQName}') 단일/최종 응답. 화면번호({sScrNo}) 반환 예정.", "DEBUG")
            self.screen_manager.release_screen(sScrNo, sRQName)
            if sRQName in self.tr_data_cache and isinstance(self.tr_data_cache[sRQName], dict) and \
               self.tr_data_cache[sRQName].get('status') != 'error': # 에러가 아니었다면 completed
                self.tr_data_cache[sRQName]['status'] = 'completed'
            
            # if self.tr_event_loop and self.tr_event_loop.isRunning(): # REMOVED: Should not exit global/shared event loop from TR callback
            #     self.log(f"이벤트 루프 종료 (TR: {sTrCode}, RQ: {sRQName})", "CRITICAL")
            #     self.tr_event_loop.exit()
        # sPrevNext == '2' 이지만 opt10081이 아닌 경우는 없다고 가정 (KOA는 opt10081만 연속조회 sPrevNext 사용)
        # 만약 다른 TR도 sPrevNext '2'를 쓴다면 위 조건 수정 필요.

    def _parse_tr_data(self, sTrCode, sRQName, sScrNo, sPrevNext):
        """TR 응답 데이터를 파싱하여 싱글/멀티 데이터로 구조화합니다."""
        parsed_data = {
            'single_data': {},
            'multi_data': [],
            'tr_code': sTrCode,
            'rq_name': sRQName,
            'screen_no': sScrNo,
            'prev_next': sPrevNext
        }
        self.log(f"_parse_tr_data: TR Code '{sTrCode}', RQName '{sRQName}'", "DEBUG")

        # TR 코드별 Output 필드 정의 (주요 TR에 대해서만 우선 정의)
        # 필드명은 KOA Studio TR 목록의 Output 필드명과 일치해야 함
        tr_output_fields = {
            "opt10001": [ # 주식기본정보
                "종목코드", "종목명", "결산월", "액면가", "자본금", "상장주식", "신용비율", "연중최고", "연중최저",
                "시가총액", "시가총액비중", "외인소진률", "대용가", "PER", "EPS", "ROE", "PBR", "EV", "BPS",
                "매출액", "영업이익", "당기순이익", "250최고", "250최저", "시가", "고가", "저가", "상한가", "하한가",
                "기준가", "예상체결가", "예상체결수량", "250최고가일", "250최고가대비율", "250최저가일",
                "250최저가대비율", "현재가", "전일대비기호", "전일대비", "등락율", "거래량", "거래대금", "체결량",
                "체결강도", "전일거래량", "매도호가", "매수호가", "매도1차호가", "매도2차호가", "매도3차호가",
                "매도4차호가", "매도5차호가", "매수1차호가", "매수2차호가", "매수3차호가", "매수4차호가",
                "매수5차호가", "상장일", "유통주식", "유통비율"
            ],
            "opt10081": [ # 일봉/주봉/월봉
                "일자", "시가", "고가", "저가", "현재가", "거래량", "거래대금", "수정주가구분", "수정비율", "대업종구분", "소업종구분", "종목정보", "수정주가이벤트", "전일종가"
            ],
            "opw00001": { # 예수금상세현황 (싱글 데이터만 가정)
                'single': ["예수금", "d+1추정예수금", "d+2추정예수금", "출금가능금액", "미수금", "대용금", "권리대용금", "주문가능금액", "예탁자산평가액", "총매입금액", "총평가금액", "총손익금액", "총손익률", "총재사용금액"]
            },
            "opw00018": { # 계좌평가잔고내역 (싱글 + 멀티)
                'single': ["총매입금액", "총평가금액", "총평가손익금액", "총수익률(%)", "추정예탁자산", "총대출금", "총융자금액", "총대주금액", "조회건수"],
                'multi': ["종목번호", "종목명", "평가손익", "수익률(%)", "매입가", "보유수량", "매매가능수량", "현재가", "전일종가", "매입금액", "평가금액", "대출일자", "만기일자", "신용구분", "신용금액", "신용이자", "담보대출수량"]
            }
            # 기타 필요한 TR 코드에 대한 필드 정의 추가...
        }

        fields_to_parse = tr_output_fields.get(sTrCode)
        if not fields_to_parse:
            self.log(f"TR 코드 '{sTrCode}'에 대한 Output 필드 정의가 없어 GetCommData 직접 호출. (싱글 데이터만 시도)", "WARNING")
            try:
                parsed_data['single_data']['Data'] = self.get_comm_data(sTrCode, sRQName, 0, "Data") # 예시 필드명
            except Exception as e:
                self.log(f"정의되지 않은 TR '{sTrCode}'의 'Data' 필드 GetCommData 실패: {e}", "ERROR")
            return parsed_data

        if isinstance(fields_to_parse, list): # 싱글 데이터 또는 멀티 데이터 필드 목록만 있는 경우 (예: opt10001, opt10081)
            if self.get_repeat_cnt(sTrCode, sRQName) > 0: # 멀티 데이터로 간주
                count = self.get_repeat_cnt(sTrCode, sRQName)
                for i in range(count):
                    item_data = {}
                    # opt10081의 경우 '일자' 필드를 먼저 가져와서 로깅에 사용
                    current_date_for_log = "N/A"
                    if sTrCode == "opt10081":
                        # '일자' 필드가 fields_to_parse에 있는지 확인하고 가져옴
                        if "일자" in fields_to_parse:
                             current_date_for_log = self.get_comm_data(sTrCode, sRQName, i, "일자").strip()
                             item_data["일자"] = current_date_for_log # 미리 저장

                    for field_name in fields_to_parse:
                        if sTrCode == "opt10081" and field_name == "일자" and "일자" in item_data: # 위에서 이미 처리했으면 스킵
                            continue

                        raw_value = self.get_comm_data(sTrCode, sRQName, i, field_name).strip()
                        if sTrCode == "opt10081":
                            try:
                                if field_name in ["시가", "고가", "저가", "현재가", "전일비", "수정비율"]: # 현재가 = KOA Studio 기준 해당일의 종가
                                    item_data[field_name] = _safe_float(raw_value, 0.0)
                                elif field_name == "거래량":
                                    item_data[field_name] = _safe_int(raw_value, 0)
                                #elif field_name == "거래대금": # 거래대금은 보통 큰 정수이므로 int 처리
                                #    item_data[field_name] = _safe_int(raw_value, 0) # 필요시 추가
                                else:
                                    item_data[field_name] = raw_value # 기타 필드는 문자열 유지 (예: 일자, 수정주가구분 등)
                            except ValueError as ve:
                                # 로깅 시 종목코드 정보 추가
                                stock_code_for_log = "N/A"
                                if sRQName in self.tr_data_cache and 'params' in self.tr_data_cache[sRQName] and \
                                   'input_values' in self.tr_data_cache[sRQName]['params']:
                                    stock_code_for_log = self.tr_data_cache[sRQName]['params']['input_values'].get('종목코드', 'N/A')
                                
                                self.log(f"opt10081 데이터 변환 오류: RQName({sRQName}), Code({stock_code_for_log}), Date({current_date_for_log}), Field({field_name}), Value('{raw_value}'), Error: {ve}", "ERROR")
                                if field_name in ["시가", "고가", "저가", "현재가", "전일비", "수정비율"]:
                                    item_data[field_name] = 0.0
                                elif field_name == "거래량":
                                    item_data[field_name] = 0
                                #elif field_name == "거래대금":
                                #    item_data[field_name] = 0
                                else:
                                    item_data[field_name] = raw_value # 오류 시 원본 값 유지
                        else: # opt10081이 아닌 다른 TR
                            item_data[field_name] = raw_value
                    
                    # opt10081은 위에서 필드별 처리 했으므로 _ensure_numeric_fields_for_api_data 호출 불필요.
                    # 다른 TR들은 기존 _ensure_numeric_fields_for_api_data 호출하여 일반적인 숫자 변환 시도.
                    if sTrCode == "opt10081":
                        parsed_data['multi_data'].append(item_data)
                    else:
                        parsed_data['multi_data'].append(self._ensure_numeric_fields_for_api_data(item_data))
            else: # 싱글 데이터로 간주
                single_item_data = {}
                for field_name in fields_to_parse:
                    single_item_data[field_name] = self.get_comm_data(sTrCode, sRQName, 0, field_name).strip()
                # opt10081은 멀티데이터 TR이므로 이 분기로 올 가능성 낮음. 오더라도 일반처리.
                parsed_data['single_data'] = self._ensure_numeric_fields_for_api_data(single_item_data)
        
        elif isinstance(fields_to_parse, dict): # 싱글/멀티 필드 목록이 명확히 구분된 경우 (예: opw00001, opw00018)
            if 'single' in fields_to_parse:
                single_item_data = {}
                for field_name in fields_to_parse['single']:
                    single_item_data[field_name] = self.get_comm_data(sTrCode, sRQName, 0, field_name).strip()
                parsed_data['single_data'] = self._ensure_numeric_fields_for_api_data(single_item_data)
            
            if 'multi' in fields_to_parse:
                count = self.get_repeat_cnt(sTrCode, sRQName)
                for i in range(count):
                    item_data = {}
                    for field_name in fields_to_parse['multi']:
                        item_data[field_name] = self.get_comm_data(sTrCode, sRQName, i, field_name).strip()
                    parsed_data['multi_data'].append(self._ensure_numeric_fields_for_api_data(item_data))

        self.log(f"_parse_tr_data 완료: TR({sTrCode}), RQName({sRQName}), SingleDataKeys({len(parsed_data['single_data'])}), MultiDataCount({len(parsed_data['multi_data'])})", "DEBUG")
        return parsed_data

    def _ensure_numeric_fields_for_api_data(self, data_dict):
        """API에서 받은 데이터 딕셔너리의 특정 필드를 숫자형으로 변환합니다."""
        # 이 함수는 Strategy의 _ensure_numeric_fields와 유사하나, API 직접 응답 처리에 특화될 수 있음
        # 예를 들어, API 응답의 필드명과 Strategy 내부 필드명이 다를 수 있으므로, 여기서 API 필드명 기준으로 처리
        cleaned_dict = data_dict.copy()
        for field, value_str in data_dict.items():
            # 일반적으로 숫자형일 가능성이 높은 필드들 (KOA Studio 필드 타입 참고)
            # 여기서는 간단히 _safe_int, _safe_float 시도
            # 좀 더 정교하게 하려면, 필드명에 따라 int/float 변환 대상을 지정해야 함.
            # 예를 들어 '현재가', '등락률'은 float, '거래량', '보유수량'은 int.
            # 여기서는 모든 문자열 값에 대해 시도.
            if isinstance(value_str, str):
                if '.' in value_str or '%' in value_str: # 소수점이나 %가 있으면 float 시도
                    cleaned_dict[field] = _safe_float(value_str) 
                elif value_str.strip().lstrip('-').isdigit(): # 부호있는 정수 형태면 int 시도
                    cleaned_dict[field] = _safe_int(value_str)
                # 그 외는 문자열 유지
        return cleaned_dict

    def _handle_opt10001(self, sRQName, parsed_data):
        """opt10001 (주식기본정보) TR 응답을 처리합니다."""
        # parsed_data는 _parse_tr_data의 반환값 ({single_data: ..., multi_data: ...})
        item = parsed_data.get('single_data', {})

        requested_code_info = self.tr_data_cache.get(sRQName, {})
        requested_pure_code = requested_code_info.get('code') # 캐시 생성 시 저장된 순수 코드 (comm_rq_data에서 설정)
        requested_market_ctx = requested_code_info.get('market_context') # 캐시 생성 시 저장된 시장 컨텍스트
        
        received_code_with_suffix = str(item.get("종목코드", "")).strip()
        received_pure_code, _, _, _ = self._parse_stock_code(received_code_with_suffix)
        stock_name = str(item.get("종목명", "")).strip()

        self.log(f"_handle_opt10001: Validation for RQ('{sRQName}'): ReqPure='{requested_pure_code}', ReqCtx='{requested_market_ctx}', RcvFull='{received_code_with_suffix}', RcvPure='{received_pure_code}', Name='{stock_name}'", "DEBUG")

        validation_success = stock_name and requested_pure_code and received_pure_code == requested_pure_code
        if validation_success:
            # data 키에 싱글 데이터 전체를 리스트 형태로 저장 (기존 로직 호환성 및 일관성)
            self.tr_data_cache[sRQName]['data'] = [item] 
            self.tr_data_cache[sRQName]['single_data'] = item # 명시적으로 single_data도 채움
            self.tr_data_cache[sRQName]['status'] = 'completed'
            self.tr_data_cache[sRQName]['error'] = None
            self.log(f"opt10001 데이터 캐시 저장 완료: {sRQName} - {stock_name} ({received_pure_code}, Market: {requested_market_ctx})", "DEBUG")
        else:
            error_detail = f"요청순수코드: '{requested_pure_code}', 수신순수코드: '{received_pure_code}', 수신종목명: '{stock_name}'"
            error_msg = f"데이터 파싱 실패 또는 불일치. {error_detail}"
            self.tr_data_cache[sRQName]['error'] = error_msg
            self.tr_data_cache[sRQName]['status'] = 'error'
            self.log(f"opt10001 {error_msg} ({sRQName})", "WARNING")

    def _handle_opt10081(self, sRQName, sPrevNext, parsed_data):
        """opt10081 (일봉/주봉/월봉) TR 응답을 처리합니다."""
        current_data_chunk = parsed_data.get('multi_data', [])
        self.log(f"_handle_opt10081 ({sRQName}): 수신 청크 {len(current_data_chunk)}건, PrevNext={sPrevNext}", "DEBUG")

        # 캐시의 'data' 필드는 모든 청크를 누적하기 위해 사용
        if 'data' not in self.tr_data_cache[sRQName] or self.tr_data_cache[sRQName]['data'] is None:
             self.tr_data_cache[sRQName]['data'] = []
        self.tr_data_cache[sRQName]['data'].extend(current_data_chunk)
        # 'multi_data' 필드는 현재 청크만 반영 (선택적)
        self.tr_data_cache[sRQName]['multi_data'] = current_data_chunk 
        self.log(f"opt10081 데이터 캐시에 누적 ({sRQName}): 이번 청크 {len(current_data_chunk)}건, 총 {len(self.tr_data_cache[sRQName]['data'])}건", "DEBUG")

        if sPrevNext == '2': # 연속 조회
            cached_item = self.tr_data_cache[sRQName] # comm_rq_data에서 'params'에 필요한 정보 저장됨
            original_params = cached_item.get('params', {})
            code_from_params = original_params.get('input_values', {}).get('종목코드')
            base_date_from_params = original_params.get('input_values', {}).get('기준일자')
            market_context_from_params = original_params.get('market_context')
            
            self.log(f"opt10081 연속 조회 데이터 수신. 다음 요청 준비. RQName='{sRQName}', Code='{code_from_params}', BaseDate='{base_date_from_params}', MarketCtx='{market_context_from_params}'", "DEBUG")
            if code_from_params and base_date_from_params:
                QTimer.singleShot(int(self.continuous_request_interval * 1000),
                                lambda: self._request_next_opt10081_chunk(sRQName, code_from_params, base_date_from_params, market_context_from_params, prev_next_val=2))
                self.log(f"opt10081 다음 청크 요청 스케줄됨: {sRQName}", "DEBUG")
            else:
                self.log(f"opt10081 연속 조회 중단: 다음 요청을 위한 파라미터(종목코드 또는 기준일자)가 캐시에 없거나 유효하지 않습니다. RQName='{sRQName}', CachedParams: {original_params}", "ERROR")
                # 연속 조회 실패 시, 관련 리소스 정리
                cached_screen_no = original_params.get('screen_no') # comm_rq_data에서 저장한 screen_no
                if cached_screen_no:
                    self.log(f"opt10081 연속 조회 실패로 화면번호 반환 시도: ScreenNo='{cached_screen_no}', RQName='{sRQName}'", "ERROR")
                    self.screen_manager.release_screen(cached_screen_no, sRQName)
                else:
                    self.log(f"opt10081 연속 조회 실패: RQName='{sRQName}'에 대한 캐시된 화면 번호가 없어 반환 불가.", "ERROR")
                
                if self.tr_event_loop and self.tr_event_loop.isRunning():
                    # 현재 TR 요청에 대한 이벤트 루프를 종료해야 함.
                    # 이 루프는 _request_next_opt10081_chunk를 호출하는 QTimer가 아닌, 
                    # 이 _handle_opt10081을 호출한 comm_rq_data에 의해 시작된 루프일 수 있음.
                    # on_receive_tr_data의 말미에서 sPrevNext == '2'일 때도 loop.exit()를 호출하므로, 여기서 중복 호출될 수 있음.
                    # on_receive_tr_data의 루프 종료 로직을 신뢰하고 여기서는 추가적인 exit()을 하지 않거나, 
                    # 명확히 이 핸들러가 특정 루프를 종료해야 하는 경우에만 호출.
                    # 현재 on_receive_tr_data의 로직은 sPrevNext=='2'인 경우에도 loop.exit()을 호출하므로 여기선 로깅만 남김.
                    self.log(f"opt10081 연속 조회 중단. 이벤트 루프는 on_receive_tr_data에서 처리될 것으로 예상. (RQName: {sRQName})", "ERROR")
                    # self.tr_event_loop.exit() # 만약 on_receive_tr_data에서 sPrevNext=='2'시 exit 안한다면 여기서 필요
                self.tr_data_cache[sRQName]['status'] = 'error' # 상태를 에러로 명시
                self.tr_data_cache[sRQName]['error_message'] = '연속조회 중단: 파라미터 부족'
        else: # 연속 조회 아님 (조회 완료)
            cached_item = self.tr_data_cache[sRQName]
            # code, base_date 등은 comm_rq_data에서 캐시 생성 시 'params' 또는 별도 키로 저장된 값을 사용해야 함.
            # 여기서는 sRQName 자체를 식별자로 사용하고, Strategy에서 code를 알고 있다고 가정.
            original_params = cached_item.get('params', {})
            code_for_signal = original_params.get('input_values', {}).get('종목코드')
            # _parse_stock_code를 통해 순수 코드를 추출하여 시그널에 전달하는 것이 더 좋을 수 있음
            pure_code_for_signal, _, _, _ = self._parse_stock_code(str(code_for_signal))

            all_accumulated_data = cached_item.get('data', [])
            self.log(f"opt10081 모든 데이터 수신 완료 ({sRQName}, CodeForSignal: {pure_code_for_signal}). 총 {len(all_accumulated_data)}건. Strategy로 전달.", "INFO")
            if self.strategy_instance and hasattr(self.strategy_instance, 'on_daily_chart_data_ready'):
                self.strategy_instance.on_daily_chart_data_ready(sRQName, pure_code_for_signal, all_accumulated_data)
            # 화면번호 반환은 on_receive_tr_data 메인 로직에서 sPrevNext != '2' 일 때 처리

    def _handle_opw00001(self, sRQName, parsed_data):
        """opw00001 (예수금상세현황) TR 응답을 처리합니다."""
        item = parsed_data.get('single_data', {})
        if item.get("예수금") is not None: # 주요 필드 존재 여부로 성공 판단
            item['계좌번호'] = self.account_number # 응답에는 없으므로 직접 추가
            self.account_deposit_info = item # API 인스턴스 변수에 저장
            self.tr_data_cache[sRQName]['single_data'] = item # 캐시에도 저장 (일관성)
            self.tr_data_cache[sRQName]['status'] = 'completed'
            self.log(f"opw00001 (계좌정보) 수신 및 저장: 예수금({item.get('예수금')}) - RQ: {sRQName}", "INFO")
            if self.strategy_instance and hasattr(self.strategy_instance, 'on_tr_data_received'): # 일반 TR 시그널 사용
                self.strategy_instance.on_tr_data_received(sRQName, "opw00001", {'single_data': item.copy()})
        else:
            self.log(f"opw00001 데이터 파싱 실패 또는 주요 데이터 누락: {sRQName}", "WARNING")
            self.tr_data_cache[sRQName]['error'] = "주요 데이터 누락"
            self.tr_data_cache[sRQName]['status'] = 'error'

    def _handle_opw00018(self, sRQName, parsed_data):
        """opw00018 (계좌평가잔고내역) TR 응답을 처리합니다."""
        single_item = parsed_data.get('single_data', {})
        multi_data_list = parsed_data.get('multi_data', [])

        if single_item.get("총매입금액") is not None: # 주요 싱글 필드 존재 여부
            self.tr_data_cache[sRQName]['single_data'] = single_item
            self.tr_data_cache[sRQName]['multi_data'] = multi_data_list
            self.tr_data_cache[sRQName]['status'] = 'completed'
            self.log(f"opw00018 데이터 캐시 저장: {sRQName} - 보유종목 {len(multi_data_list)}건, 총매입 {single_item.get('총매입금액')}", "DEBUG")
            if self.strategy_instance and hasattr(self.strategy_instance, 'on_tr_data_received'): # 일반 TR 시그널 사용
                # Strategy에서는 combined_data 형태를 기대하고 있을 수 있음. _parse_tr_data 결과 전체를 전달.
                self.strategy_instance.on_tr_data_received(sRQName, "opw00018", parsed_data.copy())
        else:
            self.log(f"opw00018 데이터 파싱 실패 또는 주요 싱글 데이터 누락: {sRQName}", "WARNING")
            self.tr_data_cache[sRQName]['error'] = "주요 싱글 데이터 누락"
            self.tr_data_cache[sRQName]['status'] = 'error'

    def _handle_generic_tr(self, sTrCode, sRQName, parsed_data):
        """일반적인 TR 응답을 처리합니다 (위에서 특별히 핸들링되지 않은 TR들)."""
        self.log(f"일반 TR 응답 처리 ({sTrCode}, {sRQName}). Strategy에 전달 시도.", "DEBUG")
        # 싱글/멀티 데이터가 모두 있을 수 있으므로 parsed_data 전체를 캐시에 저장하고 전달
        self.tr_data_cache[sRQName].update(parsed_data) # single_data, multi_data 등 덮어쓰기
        self.tr_data_cache[sRQName]['status'] = 'completed'
        
        if self.strategy_instance and hasattr(self.strategy_instance, 'on_tr_data_received'):
            self.strategy_instance.on_tr_data_received(sRQName, sTrCode, parsed_data.copy())
        else:
            self.log(f"Strategy 인스턴스 또는 on_tr_data_received 콜백 없음. 일반 TR({sTrCode}, {sRQName}) 전달 불가.", "WARNING")

    def on_receive_real_data(self, code, real_type, real_data_raw):
        # ... (기존 내용과 거의 동일, ATS 관련 특별한 변경 없음) ...
        parsed_real_data = {'code': code, 'real_type': real_type}
        fids_to_parse = {}
        if real_type == "주식시세" or real_type == "주식체결":
            fids_to_parse = {
                10: {'name': '현재가', 'type': 'int'}, 11: {'name': '전일대비', 'type': 'int'},
                12: {'name': '등락률', 'type': 'float'}, 13: {'name': '누적거래량', 'type': 'int'},
                14: {'name': '누적거래대금', 'type': 'int'}, 15: {'name': '거래량', 'type': 'int'}, 
                16: {'name': '시가', 'type': 'int'}, 17: {'name': '고가', 'type': 'int'},
                18: {'name': '저가', 'type': 'int'}, 27: {'name': '최우선매도호가', 'type': 'int'},
                28: {'name': '최우선매수호가', 'type': 'int'}, 30: {'name': '전일대비기호', 'type': 'str'},
                20: {'name': '체결시간', 'type': 'str'}, 228: {'name': '체결강도', 'type': 'float'},
                25: {'name': '전일거래량대비부호', 'type': 'str'}, 26: {'name': '전일거래량대비율', 'type': 'float'}
            }
            if real_type == "주식체결": fids_to_parse[15] = {'name': '체결량', 'type': 'int'} 
        elif real_type == "장시작시간":
            fids_to_parse = {214: {'name': '장운영구분', 'type': 'str'}, 215: {'name': '장시작예상잔여시간', 'type': 'str'}}

        if not fids_to_parse:
            self.log(f"처리할 FID 목록 없음 (실시간 데이터): {code}, {real_type}", "DEBUG")
            if self.strategy_instance and hasattr(self.strategy_instance, 'on_actual_real_data_received'):
                self.strategy_instance.on_actual_real_data_received(code, real_type, parsed_real_data)
            return

        for fid, info in fids_to_parse.items():
            value_str = self.get_comm_real_data(code, fid)
            if info['type'] == 'int': parsed_real_data[info['name']] = _safe_int(value_str)
            elif info['type'] == 'float': parsed_real_data[info['name']] = _safe_float(value_str)
            else: parsed_real_data[info['name']] = value_str.strip()
        
        if len(parsed_real_data) > 2:
            self.log(f"실시간 데이터 파싱 완료: {code}, {real_type}, 데이터키개수={len(parsed_real_data)-2}", "DEBUG")
            if self.strategy_instance and hasattr(self.strategy_instance, 'on_actual_real_data_received'):
                self.strategy_instance.on_actual_real_data_received(code, real_type, parsed_real_data)
            else: self.log(f"Strategy 인스턴스 없어 실시간 데이터 전달 불가: {code}, {real_type}", "WARNING")

    def on_receive_chejan_data(self, gubun, item_cnt, fid_list_str):
        # ... (기존 내용과 거의 동일, ATS 관련 특별한 변경 없음) ...
        gubun_map = {'0': "주문체결통보", '1': "잔고통보", '3': "특이신호", '4':"파생잔고"}
        self.log(f"체결 데이터 수신: 구분({gubun_map.get(gubun, gubun)}) FID목록({fid_list_str})")
        current_chejan_data = {'gubun': gubun}
        for fid_str in fid_list_str.split(';'):
            if not fid_str.strip(): continue
            try:
                current_chejan_data[str(int(fid_str))] = self.get_chejan_data(int(fid_str))
            except ValueError: self.log(f"잘못된 FID 형식: {fid_str}", "WARNING")

        log_detail = f"구분: {gubun_map.get(gubun, gubun)}"
        if gubun == '0': 
            log_detail += f", 종목: {current_chejan_data.get('9001', '')}, 주문번호: {current_chejan_data.get('9203', '')}, 상태: {current_chejan_data.get('913', '')}, 체결가: {current_chejan_data.get('910', '')}, 체결량: {current_chejan_data.get('911', '')}"
        elif gubun == '1': 
            log_detail += f", 종목: {current_chejan_data.get('9001', '')}, 보유수량: {current_chejan_data.get('930', '')}, 매입단가: {current_chejan_data.get('931', '')}"
        self.log(f"체결 데이터 상세: {log_detail}")

        if self.strategy_instance and hasattr(self.strategy_instance, 'on_chejan_data_received'):
            # current_chejan_data 대신 item_cnt 와 fid_list_str 를 전달해야 합니다.
            # on_receive_chejan_data의 인자로 item_cnt와 fid_list_str이 이미 존재합니다.
            self.strategy_instance.on_chejan_data_received(gubun, current_chejan_data)  # fid_list_str 대신 파싱된 dict 전달
        else: self.log(f"Strategy 인스턴스 없어 체결 데이터 전달 불가: {gubun}", "WARNING")

    def on_receive_msg(self, screen_no, rq_name, tr_code, msg):
        log_message_detail = f"화면: {screen_no if screen_no and screen_no.strip() else 'N/A'}, RQ: {rq_name if rq_name and rq_name.strip() else 'N/A'}, TR: {tr_code if tr_code and tr_code.strip() else 'N/A'}, 메시지: {msg}"
        log_level = "INFO" # 기본 로그 레벨 INFO로 변경
        log_prefix = "서버 정보 메시지 수신"
        release_screen_and_exit_loop = False

        # 화면번호, RQName, TR코드가 모두 유효한지 확인 (TR 관련 메시지일 가능성)
        is_tr_related_message = bool(screen_no and screen_no.strip() and screen_no != "0000" and \
                                     rq_name and rq_name.strip() and \
                                     tr_code and tr_code.strip())

        if "조회과다" in msg or "시세조회제한" in msg or "[OPCODEQCBP]" in msg or "초당 5회" in msg:
            log_level = "ERROR"; log_prefix = "API 제한 관련 오류"
            if is_tr_related_message:
                release_screen_and_exit_loop = True
                if rq_name in self.tr_data_cache: # Null safety
                    if isinstance(self.tr_data_cache[rq_name], dict): # Type safety
                        self.tr_data_cache[rq_name]['status'] = 'error'
                        self.tr_data_cache[rq_name]['error_message'] = msg
                    else:
                        self.log(f"비정상 캐시 상태(on_receive_msg): RQName {rq_name}의 캐시가 dict가 아님.", "ERROR")

        elif "오류" in msg or "실패" in msg or "에러" in msg or "잔고부족" in msg or "없습니다" in msg or "초과" in msg or "거부" in msg:
            log_level = "WARNING"; log_prefix = "서버 오류/경고"
            if is_tr_related_message:
                if ("주문" in msg and ("실패" in msg or "거부" in msg)) or tr_code: # 주문 실패는 명확히 에러
                    log_level = "ERROR"; log_prefix = "주문/TR 관련 중요 오류"
                release_screen_and_exit_loop = True
                if rq_name in self.tr_data_cache: # Null safety
                    if isinstance(self.tr_data_cache[rq_name], dict): # Type safety
                        self.tr_data_cache[rq_name]['status'] = 'error'
                        self.tr_data_cache[rq_name]['error_message'] = msg
                    else:
                        self.log(f"비정상 캐시 상태(on_receive_msg): RQName {rq_name}의 캐시가 dict가 아님.", "ERROR")

        elif is_tr_related_message and ("정상" in msg or "완료" in msg) and not ("오류" in msg or "실패" in msg or "에러" in msg): # 성공 메시지 처리 강화 (부정 키워드 명시적 제외)
            log_level = "INFO"; log_prefix = "TR 처리 성공 메시지"
            # on_receive_tr_data가 호출될 것이고 거기서 최종 상태(completed)를 설정하는 것이 일반적.
            # 여기서 TR 상태를 'completed'로 단정하기보다는, 메시지 수신 사실만 기록하거나,
            # on_receive_tr_data가 호출되지 않는 특정 TR/메시지 패턴에 대해서만 제한적으로 상태 변경.
            # 현재는 로깅만 강화하고, 상태 변경은 on_receive_tr_data에 더 의존.
            # 만약 이 메시지가 TR의 유일한 완료 알림이라면 아래 로직 필요.
            if rq_name in self.tr_data_cache: # Null safety
                if isinstance(self.tr_data_cache[rq_name], dict): # Type safety
                    # 이미 error로 설정된 경우, 성공 메시지가 뒤늦게 와도 상태를 바꾸지 않도록 주의
                    if self.tr_data_cache[rq_name].get('status') != 'error':
                        # 'completed_by_msg' 보다는, 이 메시지가 실제 데이터 수신 완료를 의미하는지 불분명하므로
                        # 'message_received' 와 같은 중간 상태 또는 단순 로그로 처리하는 것이 안전할 수 있음.
                        # 여기서는 일단 메시지만 기록.
                        self.tr_data_cache[rq_name]['last_message'] = msg
                        self.log(f"TR 관련 성공 메시지 수신 ({rq_name}, {tr_code}): {msg}", "DEBUG")
                        # 만약 이 메시지가 'TR 데이터 수신 완료'를 확실히 의미한다면, 
                        # 그리고 on_receive_tr_data가 호출되지 않을 수 있다면, 여기서 status='completed' 및 화면 해제 고려.
                        # ex: if tr_code == "특정TR코드" and "정상처리되었습니다" in msg: release_screen_and_exit_loop = True
                else:
                    self.log(f"비정상 캐시 상태(on_receive_msg): RQName {rq_name}의 캐시가 dict가 아님.", "ERROR")

        elif "잠시 후 다시 시도" in msg:
            log_level = "INFO"; log_prefix = "서버 재시도 요구"
            # 재시도 요구 메시지는 해당 TR 요청이 아직 끝나지 않았음을 의미할 수 있음.
            # 따라서 화면 해제나 루프 종료는 하지 않는 것이 일반적.
            if is_tr_related_message and rq_name in self.tr_data_cache:
                if isinstance(self.tr_data_cache[rq_name], dict):
                    self.tr_data_cache[rq_name]['status'] = 'retry_suggested'
                    self.tr_data_cache[rq_name]['message'] = msg
                else:
                    self.log(f"비정상 캐시 상태(on_receive_msg): RQName {rq_name}의 캐시가 dict가 아님.", "ERROR")


        elif screen_no == "0000": # 시스템 메시지 (TR과 직접 관련 없음)
            log_prefix = "시스템 메시지"
            log_level = "DEBUG" # 시스템 메시지는 DEBUG 레벨로 조정

        self.log(f"{log_prefix}: {log_message_detail}", log_level)

        if release_screen_and_exit_loop and is_tr_related_message:
            self.log(f"화면({screen_no}), RQ({rq_name})에 대한 리소스 해제 및 루프 종료 시도 ({log_prefix})", "DEBUG")
            
            # ScreenManager의 release_screen이 중복 호출에 안전하다고 가정
            self.screen_manager.release_screen(screen_no, rq_name) 
            
            if self.tr_event_loop and self.tr_event_loop.isRunning():
                # comm_rq_data 호출 시 event_loop와 rq_name을 매핑하여 관리했다면 더 정확한 종료 가능
                # 예를 들어 self.current_tr_event_loops[rq_name] = self.tr_event_loop 와 같이.
                # 현재는 self.tr_event_loop가 가장 최근 요청의 루프라고 가정.
                # 좀 더 안전하게 하려면, 루프 종료 전에 현재 루프가 이 rq_name을 위한 것인지 확인하는 장치가 필요.
                # 아래는 단순화된 확인 로직 (comm_rq_data 에서 tr_event_loop 생성 시 rq_name 정보를 어딘가에 저장했다고 가정)
                # cached_rq_name_for_loop = getattr(self.tr_event_loop, '_rq_name_for_loop', None)
                # if cached_rq_name_for_loop == rq_name:
                self.log(f"이벤트 루프 종료 예정 (메시지 수신: RQName={rq_name}, TRCode={tr_code})", "DEBUG")
                self.tr_event_loop.exit()
                # else:
                #    self.log(f"실행 중인 이벤트 루프({cached_rq_name_for_loop})가 현재 메시지({rq_name})와 다를 수 있어 자동 종료 안 함.", "WARNING")

    def log(self, message, level="INFO"):
        if self.logger:
            log_func = getattr(self.logger, level.lower(), self.logger.info)
            log_func(f"[KiwoomAPI] {message}")
        else: print(f"[{level}][KiwoomAPI] {message}")

    def _get_default_logger(self):
        # ... (기존 내용과 동일) ...
        import logging
        logger = logging.getLogger("KiwoomAPI_Default")
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.DEBUG)
        return logger

    def _event_loop_timeout(self, event_loop, rq_name):
        self.log(f"[KiwoomAPI_TimeoutHandler] EVENT_LOOP_TIMEOUT for RQName: '{rq_name}'.", "ERROR")
        
        screen_no_to_release = None
        tr_code_for_signal = 'N/A'
        
        if rq_name in self.tr_data_cache and isinstance(self.tr_data_cache[rq_name], dict):
            cached_request = self.tr_data_cache[rq_name]
            cached_request['status'] = 'timeout' # 또는 'error'
            cached_request['error_code'] = 'TIMEOUT'
            cached_request['error_message'] = f'TR 요청 ({cached_request.get("tr_code", "N/A")})에 대한 응답 시간 초과.'
            screen_no_to_release = cached_request.get('screen_no')
            tr_code_for_signal = cached_request.get('tr_code', 'N/A')
            self.log(f"[KiwoomAPI_TimeoutHandler] RQName '{rq_name}' 상태를 'timeout'으로 업데이트. ScreenNo 캐시값: '{screen_no_to_release}'", "ERROR")
        else:
            self.log(f"[KiwoomAPI_TimeoutHandler] RQName '{rq_name}'에 대한 캐시 정보를 찾을 수 없거나 유효하지 않아 화면번호 확보 불가.", "WARNING")

        if screen_no_to_release and rq_name: # 화면번호와 rq_name이 모두 있어야 안전하게 해제
            self.log(f"[KiwoomAPI_TimeoutHandler] 타임아웃으로 화면 반환 시도: ScreenNo='{screen_no_to_release}', RQName='{rq_name}'", "ERROR")
            self.screen_manager.release_screen(screen_no_to_release, rq_name)
        elif screen_no_to_release:
             self.log(f"[KiwoomAPI_TimeoutHandler][WARNING] 타임아웃 발생. ScreenNo='{screen_no_to_release}'는 알지만 RQName 불명확하여 자동 화면 반환 보류.", "WARNING")
        else:
            self.log(f"[KiwoomAPI_TimeoutHandler][WARNING] 타임아웃 발생. RQName='{rq_name}'에 대한 화면번호를 알 수 없어 자동 화면 반환 불가.", "WARNING")

        if event_loop and event_loop.isRunning():
            self.log(f"[KiwoomAPI_TimeoutHandler] 이벤트 루프 종료: RQName='{rq_name}'", "ERROR")
            event_loop.exit()
        
        # Strategy에 타임아웃 알림 (선택적)
        if self.strategy_instance and hasattr(self.strategy_instance, 'on_tr_request_timeout'):
            self.strategy_instance.on_tr_request_timeout(rq_name, tr_code_for_signal)
            self.log(f"[KiwoomAPI_TimeoutHandler] Strategy에 타임아웃 알림 전달: RQName='{rq_name}', TRCode='{tr_code_for_signal}'", "INFO")

    def _request_next_opt10081_chunk(self, rq_name, code, base_date, market_context, prev_next_val=2):
        self.log(f"_request_next_opt10081_chunk 호출: rq_name={rq_name}, code={code}, base_date={base_date}, market_ctx={market_context}, prev_next={prev_next_val}", "DEBUG")
        input_values = {"종목코드": code, "기준일자": base_date, "수정주가구분": "1"}
        # 다음 청크 요청 시에도 market_context를 명시적으로 전달 (comm_rq_data가 이를 사용)
        # 화면 번호를 TR 캐시에서 가져옴
        cached_request_info = self.tr_data_cache.get(rq_name)
        if not cached_request_info or not isinstance(cached_request_info, dict):
            self.log(f"_request_next_opt10081_chunk: RQName '{rq_name}'에 대한 캐시 정보가 없거나 유효하지 않아 다음 요청을 진행할 수 없습니다.", "ERROR")
            return
        
        screen_no_for_next_chunk = cached_request_info.get('screen_no')
        if not screen_no_for_next_chunk:
            self.log(f"_request_next_opt10081_chunk: RQName '{rq_name}'에 대한 캐시된 화면 번호가 없습니다. 다음 요청을 진행할 수 없습니다.", "ERROR")
            # 이 경우, 화면 번호가 이미 해제되었거나 문제가 있는 상황일 수 있으므로, 추가적인 에러 처리나 리소스 정리 필요 가능성
            return

        self.log(f"_request_next_opt10081_chunk: 다음 요청에 사용할 화면 번호 '{screen_no_for_next_chunk}' (RQName: {rq_name})", "DEBUG")
        self.comm_rq_data(rq_name=rq_name, tr_code="opt10081", prev_next=prev_next_val, screen_no=screen_no_for_next_chunk, input_values_override=input_values, market_context=market_context)
        
    def get_daily_chart(self, code: str, *, date_to: str = "", date_from: str = "", market_context: str = None):
        """
        지정된 종목의 일봉 데이터를 조회합니다. (TR: opt10081)
        Args:
            code (str): 종목코드 (예: "005930", "005930_NX", "005930_AL").
            date_to (str): 조회 기준일자 (YYYYMMDD). 기본값은 오늘.
            date_from (str): 조회 시작일자 (YYYYMMDD). 현재 구현에서는 사용되지 않음.
            market_context (str, optional): 명시적 시장 컨텍스트 (예: "KRX", "NXT", "ALL"). 
                                         None이면 code의 접미사로 추론, 그것도 없으면 DEFAULT_MARKET_CONTEXT 사용.
        ATS 처리:
        - OPT10081은 TR_USES_SUFFIX_IN_STOCK_CODE에 포함되어, 종목코드에 ATS 접미사를 직접 사용합니다.
        - comm_rq_data는 _determine_code_for_tr_input을 통해 code를 처리합니다.
        - 명시적 market_context는 "거래소구분" 파라미터 설정에 사용되지 않습니다 (OPT10081은 해당 파라미터 없음).
        """
        self.log(f"일봉 데이터 요청 시작: 종목코드({code}), 기준일자({date_to}), 명시적 MarketContext({market_context})", "INFO")
        
        _pure_code, _suffix, market_ctx_from_suffix, original_full_code = self._parse_stock_code(code)
        effective_market_context_for_rq_name = market_context if market_context else (market_ctx_from_suffix if market_ctx_from_suffix else DEFAULT_MARKET_CONTEXT)

        effective_date_to = date_to if date_to else datetime.now().strftime("%Y%m%d")
        rq_name = f"opt10081_chart_{_pure_code}_{effective_market_context_for_rq_name}_{effective_date_to.replace('-', '')}"
        screen_no = self.screen_manager.get_available_screen(rq_name)
        if not screen_no:
            self.log(f"'{rq_name}' 요청에 사용할 수 있는 화면 번호가 없습니다.", "ERROR")
            return None # 또는 적절한 오류 값

        input_values = {"종목코드": original_full_code, "기준일자": effective_date_to, "수정주가구분": "1"}

        # OPT10081은 "거래소구분" 파라미터가 없으므로 comm_rq_data에 market_context를 None으로 전달.
        # _determine_code_for_tr_input이 종목코드 자체에 접미사를 넣거나 빼므로, 별도 시장 파라미터 불필요.
        self.log(f"get_daily_chart TR PARAMS: original_full_code='{original_full_code}', effective_date_to='{effective_date_to}', input_values={input_values}, rq_name='{rq_name}', screen_no='{screen_no}'", "DEBUG")
        ret = self.comm_rq_data(rq_name, "opt10081", 0, screen_no, input_values_override=input_values, market_context=None) # 명시적으로 None 전달

        if ret == 0:
            # on_receive_tr_data에서 루프가 종료되고 데이터가 채워질 때까지 기다려야 함.
            # comm_rq_data가 동기적으로 작동한다고 가정하고 바로 캐시 접근 (이전 로직)
            # 실제로는 비동기 처리 후 콜백이나 시그널을 통해 데이터를 받아야 함.
            # 현재 구조에서는 comm_rq_data 호출 후 바로 반환하므로, 이 시점에 캐시가 채워져 있지 않을 가능성 높음.
            # 이 부분은 프로그램 전체의 동기/비동기 처리 방식에 대한 검토가 필요함.
            # 일단은 기존 로직처럼 즉시 캐시를 확인하고, 실패 시 로그를 남기고 화면 반환.
            if rq_name in self.tr_data_cache and 'data' in self.tr_data_cache[rq_name] and self.tr_data_cache[rq_name]['data'] is not None: # None도 체크
                self.log(f"일봉 데이터 수신 완료 (캐시 확인): {code} (컨텍스트: {effective_market_context_for_rq_name}), {len(self.tr_data_cache[rq_name]['data'])}개", "INFO")
                return self.tr_data_cache[rq_name]['data']
            else: 
                self.log(f"일봉 데이터 요청은 성공(ret=0)했으나, 즉시 캐시 확인 시 데이터 없음: {code} (컨텍스트: {effective_market_context_for_rq_name}), rq_name: {rq_name}. 비동기 처리 결과 기다려야 함.", "WARNING")
                # 성공적으로 요청했으나, 아직 데이터가 없는 경우 (비동기로 처리될 때)
                # 이 경우, 화면 번호는 on_receive_tr_data에서 최종적으로 release 되어야 함.
                # 여기서는 요청 실패가 아니므로 화면번호를 release 하지 않음.
                return [] # 빈 리스트 또는 None 반환 (호출 측에서 처리 방식 정의 필요)
        else:
            self.log(f"일봉 데이터 요청 실패: {code} (컨텍스트: {effective_market_context_for_rq_name}), ret: {ret}", "ERROR")
            self.screen_manager.release_screen(screen_no, rq_name) # 실패 시 화면 반환
            return None

    def get_stock_basic_info(self, code: str, market_context: str = None):
        """
        opt10001 TR을 사용하여 특정 종목의 기본 정보를 조회합니다.
        Args:
            code (str): 종목코드 (예: "005930", "005930_NX", "005930_AL").
            market_context (str, optional): 명시적 시장 컨텍스트 (예: "KRX", "NXT", "ALL"). 
                                         None이면 code의 접미사로 추론, 그것도 없으면 DEFAULT_MARKET_CONTEXT 사용.
        ATS 처리:
        - OPT10001은 TR_USES_SUFFIX_IN_STOCK_CODE에 포함되어, 종목코드에 ATS 접미사를 직접 사용합니다.
        - comm_rq_data는 _determine_code_for_tr_input을 통해 code를 처리합니다.
        - 명시적 market_context는 "거래소구분" 파라미터 설정에 사용되지 않습니다 (OPT10001은 해당 파라미터 없음).
        """
        self.log(f"종목 기본 정보 요청 시작: 종목코드({code}), 명시적 MarketContext({market_context})", "INFO") 
        
        _pure_code, _suffix, market_ctx_from_suffix, original_full_code = self._parse_stock_code(code)
        effective_market_context_for_rq_name = market_context if market_context else (market_ctx_from_suffix if market_ctx_from_suffix else DEFAULT_MARKET_CONTEXT)

        rq_name = f"opt10001_{_pure_code}_{effective_market_context_for_rq_name}" 
        screen_no = self.screen_manager.get_available_screen(rq_name)
        if not screen_no:
            self.log(f"'{rq_name}' 요청에 사용할 수 있는 화면 번호가 없습니다.", "ERROR")
            return None

        input_values = {"종목코드": original_full_code}
        
        self.log(f"get_stock_basic_info: CommRqData 호출 예정 - RQName: {rq_name}, ScreenNo: {screen_no}, MarketContextToCommRq: None", "DEBUG")
        ret = self.comm_rq_data(rq_name, "opt10001", 0, screen_no, input_values_override=input_values, market_context=None) # 명시적으로 None 전달

        self.log(f"get_stock_basic_info: comm_rq_data 호출 완료 for {rq_name}. API 반환값: {ret}", "DEBUG")

        if ret == 0:
            # 비동기 처리 가능성 고려 (get_daily_chart와 유사)
            if rq_name in self.tr_data_cache and isinstance(self.tr_data_cache[rq_name], dict) and \
               'data' in self.tr_data_cache[rq_name] and self.tr_data_cache[rq_name]['data']:
                basic_info_item = self.tr_data_cache[rq_name]['data'][0]
                self.log(f"종목 기본 정보 수신 (캐시 확인): {code} (컨텍스트: {effective_market_context_for_rq_name}) - {basic_info_item.get('종목명')}", "INFO")
                return basic_info_item
            else:
                self.log(f"종목 기본 정보 요청은 성공(ret=0)했으나, 즉시 캐시 확인 시 데이터 없음: 코드({code}), RQ명({rq_name}), 컨텍스트({effective_market_context_for_rq_name}). 비동기 처리 결과 기다려야 함.", "WARNING")
                return None # 또는 빈 dict {} 반환
        else: 
            self.log(f"종목 기본 정보 요청 실패: {code} (컨텍스트: {effective_market_context_for_rq_name}), API반환값: {ret}", "ERROR")
            self.screen_manager.release_screen(screen_no, rq_name) # 실패 시 화면 반환
            return None

    def get_yesterday_close_price(self, code: str, base_date_str: str = None, market_context: str = None):
        """
        opt10081 TR을 사용하여 특정 종목의 전일 종가를 조회합니다.
        Args:
            code (str): 종목코드 (예: "005930", "005930_NX").
            base_date_str (str, optional): 조회 기준일자 (YYYYMMDD). 기본값은 어제.
            market_context (str, optional): 명시적 시장 컨텍스트 (예: "KRX", "NXT", "ALL").
        ATS 처리: get_daily_chart와 동일.
        """
        self.log(f"전일 종가 요청 시작: 종목코드({code}), 기준일({base_date_str}), 명시적 MarketContext({market_context})", "INFO") 

        _pure_code, _suffix, market_ctx_from_suffix, original_full_code = self._parse_stock_code(code)
        effective_market_context_for_rq_name = market_context if market_context else (market_ctx_from_suffix if market_ctx_from_suffix else DEFAULT_MARKET_CONTEXT)

        if base_date_str is None:
            base_date_str = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
        
        rq_name = f"opt10081_yc_{_pure_code}_{effective_market_context_for_rq_name}_{base_date_str}" 
        screen_no = self.screen_manager.get_available_screen(rq_name)
        if not screen_no:
            self.log(f"'{rq_name}' 요청에 사용할 수 있는 화면 번호가 없습니다.", "ERROR")
            return 0 # 또는 적절한 오류 값

        input_values = {"종목코드": original_full_code, "기준일자": base_date_str, "수정주가구분": "1"}

        ret = self.comm_rq_data(rq_name, "opt10081", 0, screen_no, input_values_override=input_values, market_context=None)

        if ret == 0:
            # 비동기 처리 가능성 고려
            if rq_name in self.tr_data_cache and 'data' in self.tr_data_cache[rq_name] and self.tr_data_cache[rq_name]['data']:
                all_days_data = self.tr_data_cache[rq_name]['data']
                if all_days_data:
                    latest_data_for_base = all_days_data[0]
                    yesterday_close = _safe_int(latest_data_for_base.get('현재가', 0)) # opt10081 응답에서 '현재가'가 해당일 종가
                    data_date = latest_data_for_base.get('일자', '')
                    self.log(f"전일 종가 수신 (캐시 확인): {code} (컨텍스트: {effective_market_context_for_rq_name}) - {yesterday_close} (데이터날짜: {data_date}, 기준일: {base_date_str})", "INFO")
                    return yesterday_close
                else:
                    self.log(f"전일 종가 데이터 요청 성공(ret=0)했으나, 캐시 내 데이터 리스트 비어있음: {code} (컨텍스트: {effective_market_context_for_rq_name}), 기준일: {base_date_str}", "WARNING")
                    return 0 
            else:
                self.log(f"전일 종가 데이터 요청 성공(ret=0)했으나, 즉시 캐시 확인 시 데이터 없음: {code} (컨텍스트: {effective_market_context_for_rq_name}), 기준일: {base_date_str}, rq_name: {rq_name}. 비동기 처리 결과 기다려야 함.", "WARNING")
                return 0 
        else: 
            self.log(f"전일 종가 요청 실패: {code} (컨텍스트: {effective_market_context_for_rq_name}), API반환값: {ret}", "ERROR")
            self.screen_manager.release_screen(screen_no, rq_name) # 실패 시 화면 반환
            return 0

    def _emulate_tr_receive_for_dry_run(self, screen_no, rq_name, tr_code):
        """드라이런 모드에서 TR 요청에 대한 가상 응답을 생성하고 on_receive_tr_data를 호출합니다."""
        self.log(f"[Dry Run] _emulate_tr_receive_for_dry_run 호출됨: ScreenNo='{screen_no}', RQName='{rq_name}', TRCode='{tr_code}'", "DEBUG")

        if rq_name not in self.tr_data_cache or not isinstance(self.tr_data_cache.get(rq_name), dict):
            self.log(f"[Dry Run] _emulate_tr_receive_for_dry_run: {rq_name}에 대한 캐시 정보를 찾을 수 없음. 가상 응답 생성 불가.", "ERROR")
            return

        cached_request_info = self.tr_data_cache[rq_name]
        original_input_values = cached_request_info.get('params', {}).get('input_values', {})
        self.log(f"[Dry Run] 가상 응답 생성 시작. 원본 입력값: {original_input_values}", "DEBUG")

        sPrevNext = '0' 
        simulated_error_code = "0" 
        simulated_message = "DRYRUN_OK"
        simulated_splm_msg = "DryRun Success"

        if tr_code == "opw00001": 
            cached_request_info['single_data'] = {
                "예수금": "10000000", "d+1추정예수금": "10000000", "d+2추정예수금": "10000000",
                "출금가능금액": "10000000", "미수금": "0", "대용금": "0", "권리대용금": "0",
                "주문가능금액": "10000000", "예탁자산평가액": "10000000", "총매입금액": "0",
                "총평가금액": "0", "총손익금액": "0", "총손익률": "0.00", "총재사용금액": "0"
            }
            self.log(f"[Dry Run] opw00001 가상 데이터 생성 완료.", "DEBUG")
        elif tr_code == "opw00018": 
            cached_request_info['single_data'] = {
                "총매입금액": "0", "총평가금액": "0", "총평가손익금액": "0", "총수익률(%)": "0.00",
                "추정예탁자산": "10000000", "총대출금": "0", "총융자금액": "0", "총대주금액": "0", "조회건수": "0"
            }
            cached_request_info['multi_data'] = [] 
            self.log(f"[Dry Run] opw00018 가상 데이터 생성 완료 (보유 종목 없음 초기 상태).", "DEBUG")
        else:
            self.log(f"[Dry Run] TR 코드 '{tr_code}'에 대한 특정 가상 데이터 생성 로직 없음. 기본 성공으로 처리.", "WARNING")

        cached_request_info['status'] = 'simulating_callback' 
        self.log(f"[Dry Run] {rq_name} 캐시 상태 업데이트: simulating_callback", "DEBUG")

        self.on_receive_tr_data(
            screen_no, rq_name, tr_code, tr_code, sPrevNext, "0", 
            simulated_error_code, simulated_message, simulated_splm_msg
        )
        self.log(f"[Dry Run] on_receive_tr_data 가상 호출 완료 for {rq_name}.", "DEBUG")

    def disconnect_api(self):
        self.log("Kiwoom API 연결 종료 절차 시작...", "INFO")
        
        self.set_shutdown_mode(True)

        self.log("모든 실시간 데이터 구독 해제 시도...", "INFO")
        try:
            self.unsubscribe_all_real_data() 
            self.log("모든 실시간 데이터 구독 해제 요청 완료.", "INFO")
        except Exception as e:
            self.log(f"모든 실시간 데이터 구독 해제 중 예외 발생: {e}", "ERROR", exc_info=True)

        if self.screen_manager and hasattr(self.screen_manager, 'release_all_managed_screens'):
            self.log("ScreenManager를 통해 모든 화면 리소스 해제 시도...", "INFO")
            try:
                self.screen_manager.release_all_managed_screens()
                self.log("ScreenManager를 통한 화면 리소스 해제 완료.", "INFO")
            except Exception as e:
                self.log(f"ScreenManager 화면 리소스 해제 중 예외 발생: {e}", "ERROR", exc_info=True)
        else:
            self.log("ScreenManager 또는 release_all_managed_screens 메소드를 찾을 수 없어 화면 리소스 자동 해제 스킵.", "WARNING")

        try:
            self.log("Kiwoom OpenAPI CommTerminate 호출 시도...", "INFO")
            is_dry_run = False
            if self.config_manager:
                 is_dry_run = self.config_manager.get_setting("매매전략", "dry_run_mode", False)
            
            if not is_dry_run: 
                self.ocx.dynamicCall("CommTerminate()")
                self.log("CommTerminate 호출 완료. API 연결이 종료되었을 것입니다.", "INFO")
            else:
                self.log("[Dry Run] CommTerminate 호출 스킵.", "INFO")
            self.connected = False 
        except Exception as e:
            self.log(f"CommTerminate 호출 중 예외 발생 (또는 드라이런 스킵 중): {e}", "ERROR", exc_info=True)
        
        self.log("Kiwoom API 연결 종료 절차 완료됨.", "INFO")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    kiwoom = KiwoomAPI() 
    kiwoom.login()
    if kiwoom.connected:
        pass
    sys.exit(app.exec_())
