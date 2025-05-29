#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
from unittest.mock import MagicMock

# True 문자열과 비교해야 합니다.
IS_TESTING_ENVIRONMENT = os.environ.get('DISABLE_QT_FOR_TESTING') == 'True'

if IS_TESTING_ENVIRONMENT:
    # PyQt5.QAxContainer 모듈 자체를 MagicMock으로 대체
    sys.modules['PyQt5.QAxContainer'] = MagicMock()
    sys.modules['PyQt5.QtCore'] = MagicMock()
    sys.modules['PyQt5.QtWidgets'] = MagicMock()
    # QAxWidget 클래스를 MagicMock 인스턴스로 직접 제공할 수도 있습니다.
    # QAxWidget = MagicMock() # 이 방식보다는 sys.modules를 사용하는 것이 더 포괄적일 수 있음

# 실제 Qt 모듈 임포트는 위 조건부 로직 이후에 위치해야 합니다.
from PyQt5.QtWidgets import QApplication
from PyQt5.QAxContainer import QAxWidget # IS_TESTING_ENVIRONMENT가 True이면 MagicMock이 임포트됨
from PyQt5.QtCore import QEventLoop, QTimer, QObject 

import time
from datetime import datetime, timedelta
from util import ScreenManager, _safe_to_int as _safe_int, _safe_to_float as _safe_float
import ats_utils 
import traceback 
from typing import Dict, Optional
import logging

def non_blocking_sleep_using_process_events(seconds):
    if not IS_TESTING_ENVIRONMENT: # 실제 환경에서만 QApplication.processEvents() 호출
        start_time = time.time()
        while time.time() - start_time < seconds:
            QApplication.processEvents()
            time.sleep(0.01)
    else: # 테스트 환경에서는 단순 time.sleep 사용
        time.sleep(seconds)

class KiwoomAPI(QObject):
    def __init__(self, logger=None, config_manager=None, strategy_instance=None, screen_manager=None):
        super().__init__()
        self.logger = logger if logger else self._get_default_logger()
        self.config_manager = config_manager
        self.strategy_instance = strategy_instance
        self.log("키움 API 초기화 시작", "DEBUG")

        if not IS_TESTING_ENVIRONMENT:
            self.ocx = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")
        else:
            self.ocx = MagicMock() # 테스트 환경에서는 ocx를 MagicMock으로 설정
            self.ocx.dynamicCall = MagicMock(return_value=0) # 기본 성공 리턴
            self.ocx.GetLoginInfo = MagicMock(return_value="TESTACCT;") # 테스트 계좌 반환
            self.ocx.GetConnectState = MagicMock(return_value=1) # 연결된 상태로 모킹
            self.ocx.GetRepeatCnt = MagicMock(return_value=0)
            self.ocx.GetCommData = MagicMock(return_value="")
            self.ocx.GetCommRealData = MagicMock(return_value="")
            self.ocx.GetChejanData = MagicMock(return_value="")


        self.screen_manager = screen_manager if screen_manager else ScreenManager(logger=self.logger, kiwoom_ocx=self.ocx if not IS_TESTING_ENVIRONMENT else None)
        self.log(f"ScreenManager 초기화 완료 (외부 제공: {screen_manager is not None}, OCX 전달됨, IS_TESTING={IS_TESTING_ENVIRONMENT})", "DEBUG")

        self.connected = False
        self.tr_event_loop = None
        self.login_event_loop = None # login 메서드에서 QEventLoop()를 사용하므로, 테스트 환경 고려 필요
        if not IS_TESTING_ENVIRONMENT:
            self.login_event_loop = QEventLoop() # 실제 환경에서만 생성
        else:
            self.login_event_loop = MagicMock() # 테스트 환경에서는 모킹

        self.account_number = None
        self.account_list = []
        self.real_data_handlers = {}
        self.account_deposit_info = None
        self.subscribed_real_data = {}
        self.received_conditions = {}
        self.shutdown_mode = False

        self.last_request_time = time.time()
        if self.config_manager:
            interval_ms = self.config_manager.get_setting("API_Limit", "tr_request_interval_ms", 210)
            self.request_interval = float(interval_ms) / 1000.0
            self.continuous_request_interval = self.config_manager.get_setting("API_Limit", "TR_CONTINUOUS_REQUEST_INTERVAL", 1.0)
        else:
            self.request_interval = 0.21
            self.continuous_request_interval = 1.0

        self.log(f"TR 요청 간격 설정됨: 기본 {self.request_interval}초, 연속 {self.continuous_request_interval}초", "DEBUG")

        self.fid_map = {
            "주식시세": ["10", "11", "12", "27", "28", "15", "13", "14", "16", "17", "18", "25", "26", "30"], 
            "주식체결": ["20", "10", "11", "12", "27", "28", "15", "13", "14", "16", "17", "18", "292"], 
        }
        
        self.account_password = ""
        if self.config_manager:
            self.account_password = self.config_manager.get_setting("계좌정보", "비밀번호", "")
            self.log(f"설정에서 계좌 비밀번호 로드: {'비밀번호 있음' if self.account_password else '비밀번호 없음'}", "DEBUG")
        
        self._opt10081_timers = {}
        self.tr_data_cache = {}
        
        if not IS_TESTING_ENVIRONMENT:
            self.connect_events()
        else:
            self.log("테스트 환경: QT 이벤트 연결 스킵", "INFO")


    def connect_events(self):
        if not IS_TESTING_ENVIRONMENT: # 실제 환경에서만 이벤트 연결
            self.ocx.OnEventConnect.connect(self.on_event_connect)
            self.ocx.OnReceiveTrData.connect(self.on_receive_tr_data)
            self.ocx.OnReceiveRealData.connect(self.on_receive_real_data)
            self.ocx.OnReceiveChejanData.connect(self.on_receive_chejan_data)
            self.ocx.OnReceiveMsg.connect(self.on_receive_msg)
        else:
            self.log("테스트 환경(DISABLE_QT_FOR_TESTING=True): QT 이벤트 연결 스킵", "INFO")


    def set_shutdown_mode(self, mode: bool):
        self.shutdown_mode = mode
        status_str = "활성화" if mode else "비활성화"
        self.log(f"종료 모드가 {status_str}되었습니다.", "INFO")

    def request_account_info(self, account_number_to_use=None):
        # ... (이전 내용과 유사하나, comm_rq_data 호출은 환경변수 처리됨)
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
        
        ret = self.comm_rq_data(rq_name, "opw00001", 0, screen_no, input_values_override=input_values, market_context=None)

        if ret == 0:
            self.log(f"'{rq_name}' 요청 성공 (TR: opw00001)", "DEBUG")
        else:
            self.log(f"'{rq_name}' 요청 실패 (TR: opw00001), 반환값: {ret}", "ERROR")
            self.screen_manager.release_screen(screen_no, rq_name)
        
    def login(self):
        if IS_TESTING_ENVIRONMENT:
            self.log("테스트 환경: 실제 로그인 시도 스킵. 가상 로그인 처리.", "INFO")
            self.connected = True
            configured_account = self.config_manager.get_setting('계좌정보', '계좌번호', "TESTACCT_ENV") if self.config_manager else "TESTACCT_ENV_DEFAULT"
            self.account_number = configured_account
            self.log(f"가상 로그인 성공 (테스트 환경). 계좌번호: {self.account_number}", "IMPORTANT")
            if self.strategy_instance and hasattr(self.strategy_instance, '_on_login_completed'):
                # QTimer 대신 직접 호출 또는 테스트용 스케줄러 사용 고려
                # 여기서는 QTimer.singleShot을 사용하되, QApplication이 없을 수 있으므로 주의
                try:
                    QTimer.singleShot(10, lambda: self.strategy_instance._on_login_completed(self.account_number))
                except RuntimeError as e: # QApplication 인스턴스가 없는 경우
                    self.log(f"QTimer 사용 불가 (QApplication 없음): {e}. _on_login_completed 직접 호출 시도.", "WARNING")
                    self.strategy_instance._on_login_completed(self.account_number)

            return True

        is_dry_run = False
        if self.config_manager:
            is_dry_run = self.config_manager.get_setting("매매전략", "dry_run_mode", False)

        if is_dry_run: # 드라이런 모드 (실제 API 호출 안함)
            self.log("[Dry Run] 로그인 처리 시작...", "INFO")
            self.connected = True
            configured_account = self.config_manager.get_setting('계좌정보', '계좌번호', "DRYRUN_ACCOUNT_001")
            self.account_number = configured_account
            self.log(f"[Dry Run] 가상 로그인 성공. 계좌번호: {self.account_number}", "IMPORTANT")
            if self.strategy_instance and hasattr(self.strategy_instance, '_on_login_completed'):
                try:
                    QTimer.singleShot(100, lambda: self.strategy_instance._on_login_completed(self.account_number))
                except RuntimeError as e:
                    self.log(f"QTimer 사용 불가 (QApplication 없음, DryRun): {e}. _on_login_completed 직접 호출 시도.", "WARNING")
                    self.strategy_instance._on_login_completed(self.account_number)
            return True

        if self.connected: # 실제 환경에서 이미 연결된 경우
            self.log(f"이미 로그인됨. 계좌번호: {self.account_number}")
            if self.strategy_instance and hasattr(self.strategy_instance, '_on_login_completed'):
                self.strategy_instance._on_login_completed(self.account_number)
            return True
            
        self.log("로그인 시도")
        self.ocx.dynamicCall("CommConnect()")
        if self.login_event_loop: # 실제 환경에서만 exec_() 호출
             self.login_event_loop.exec_()
        else: # 테스트 환경에서는 login_event_loop가 MagicMock일 수 있음
            self.log("테스트 환경: login_event_loop.exec_() 스킵", "DEBUG")


        if self.connected:
            account_list_raw = self.get_login_info("ACCNO")
            parsed_acc_list = [acc.strip() for acc in account_list_raw.split(';') if acc.strip()]
            self.log(f"[LOGIN_DEBUG] Account list from API (raw): '{account_list_raw}', Parsed list: {parsed_acc_list}", "DEBUG")

            preferred_account = self.config_manager.get_setting('계좌정보', '계좌번호') if self.config_manager else None
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
        if IS_TESTING_ENVIRONMENT:
            if tag == "ACCNO": return (self.account_number if self.account_number else "TEST_ACC_NO;") + ";"
            if tag == "USER_ID": return "test_user"
            if tag == "USER_NAME": return "테스트사용자"
            return ""
        return self.ocx.dynamicCall("GetLoginInfo(QString)", tag).strip()

    def get_account_info(self):
        # ... (이전과 동일)
        if self.account_deposit_info:
            self.log(f"저장된 계좌 정보 반환: {self.account_deposit_info.get('예수금')}", "DEBUG")
        else:
            self.log("저장된 계좌 정보 없음.", "DEBUG")
        return self.account_deposit_info
        
    def get_connect_state(self):
        if IS_TESTING_ENVIRONMENT:
            return 1 if self.connected else 0
        ret = self.ocx.dynamicCall("GetConnectState()")
        return ret == 1 # 0:미연결, 1:연결완료
        
    def set_input_value(self, id_key, value):
        if not IS_TESTING_ENVIRONMENT:
            self.ocx.dynamicCall("SetInputValue(QString, QString)", id_key, value)
        else:
            self.log(f"[TEST_MODE_SKIP] SetInputValue: Key='{id_key}', Value='{str(value)}'", "DEBUG")


    def comm_rq_data(self, rq_name: str, tr_code: str, prev_next: int, screen_no: str, input_values_override: Optional[Dict[str, str]] = None, market_context: str = None):
        # ... (기존 로직 유지, 단 self.ocx 호출 부분은 IS_TESTING_ENVIRONMENT로 감싸거나 처리)
        self.log(f"[KiwoomAPI] comm_rq_data PARAMS CHECK: rq_name='{rq_name}', tr_code='{tr_code}', input_values_override IS {'NOT None' if input_values_override is not None else 'None'}, market_context='{market_context}'", "DEBUG")
        if input_values_override is not None:
            self.log(f"[KiwoomAPI] comm_rq_data PARAMS CHECK: input_values_override CONTENT: {input_values_override}", "DEBUG")

        is_dry_run = self.config_manager.get_setting("매매전략", "dry_run_mode", False) if self.config_manager else False

        if (IS_TESTING_ENVIRONMENT or is_dry_run) and tr_code in ["opw00001", "opw00018", "opt10001", "opt10081"]: # 테스트/드라이런 시 가상 응답 처리 TR 확장
            self.log(f"[TEST/Dry Run] TR 요청 ({rq_name}, {tr_code}) 가상 처리 시작...", "INFO")
            current_time = time.time()
            if rq_name not in self.tr_data_cache or not isinstance(self.tr_data_cache.get(rq_name), dict):
                self.tr_data_cache[rq_name] = {} 
            
            self.tr_data_cache[rq_name].update({
                'status': 'pending_dry_run_callback', 
                'request_time': current_time, 'tr_code': tr_code, 'screen_no': screen_no,
                'params': { 
                    'rq_name': rq_name, 'tr_code': tr_code, 'prev_next': prev_next, 'screen_no': screen_no, 
                    'input_values': input_values_override if input_values_override is not None else {},
                    'market_context': market_context
                },
                'single_data': {}, 'multi_data': [], 'error_code': None, 'error_message': None
            })
            self.log(f"[TEST/Dry Run] TR 요청 '{rq_name}'에 대한 캐시 준비 완료.", "DEBUG")

            try:
                QTimer.singleShot(10, lambda: self._emulate_tr_receive_for_dry_run(screen_no, rq_name, tr_code)) # 지연시간 줄임
            except RuntimeError as e:
                 self.log(f"QTimer 사용 불가 (QApplication 없음, TEST/DryRun): {e}. _emulate_tr_receive_for_dry_run 직접 호출.", "WARNING")
                 self._emulate_tr_receive_for_dry_run(screen_no, rq_name, tr_code)
            return 0 

        if self.shutdown_mode:
            self.log(f"종료 모드 활성화 중. TR 요청 ({rq_name}, {tr_code})을 보내지 않습니다.", "WARNING")
            return -999 

        # ... (기존 TR 요청 간격 조절 로직) ...
        current_time = time.time()
        elapsed_time = current_time - self.last_request_time
        required_interval = self.continuous_request_interval if prev_next == 2 else self.request_interval
        
        if elapsed_time < required_interval:
            sleep_duration = required_interval - elapsed_time
            self.log(f"[KiwoomAPI] TR 요청 간격 조절: {sleep_duration:.3f}초 대기", "DEBUG")
            non_blocking_sleep_using_process_events(sleep_duration)


        try:
            # ... (기존 캐시 설정 로직) ...
            if rq_name not in self.tr_data_cache or not isinstance(self.tr_data_cache[rq_name], dict) or \
               self.tr_data_cache[rq_name].get('status') in ['completed', 'error', 'exception']:
                self.tr_data_cache[rq_name] = {}

            self.tr_data_cache[rq_name].update({
                'status': 'pending_api_call', 'request_time': current_time, 'tr_code': tr_code, 'screen_no': screen_no,
                'params': { 'rq_name': rq_name, 'tr_code': tr_code, 'prev_next': prev_next, 'screen_no': screen_no, 
                            'input_values': input_values_override if input_values_override is not None else {},
                            'market_context': market_context },
                'chunks': [], 'multi_data': [], 'single_data': {}, 'error_code': None, 'error_message': None
            })
            
            current_inputs = input_values_override.copy() if input_values_override else {}
            # ... (기존 ATS 종목코드/거래소구분 자동 조정 로직) ...
            original_stock_code_from_inputs = current_inputs.get("종목코드")
            market_for_code = None 
            if original_stock_code_from_inputs:
                final_stock_code = self._determine_code_for_tr_input(tr_code, original_stock_code_from_inputs)
                _pure_code, _suffix, market_context_from_suffix, _ = self._parse_stock_code(original_stock_code_from_inputs)
                market_for_code = market_context if market_context else market_context_from_suffix 

                if final_stock_code:
                    current_inputs["종목코드"] = final_stock_code

            if tr_code in ats_utils.TR_MARKET_PARAM_CONFIG:
                param_name, param_value = self._get_api_market_param_value(tr_code, market_context if market_context else (market_for_code if market_for_code else ats_utils.DEFAULT_MARKET_CONTEXT))
                if param_name and param_value is not None:
                    current_inputs[param_name] = param_value
            
            if not IS_TESTING_ENVIRONMENT:
                for key, value in current_inputs.items():
                    self.ocx.SetInputValue(key, str(value))
                ret = self.ocx.dynamicCall("CommRqData(QString, QString, int, QString)", rq_name, tr_code, prev_next, screen_no)
            else: # 테스트 환경
                self.log(f"[TEST_MODE_SKIP] CommRqData 호출 스킵 (실제 API 호출 안함): RQ='{rq_name}'", "DEBUG")
                ret = 0 # 성공으로 가정하고, _emulate_tr_receive_for_dry_run 에서 처리


            # ... (기존 결과 처리 및 캐시 업데이트 로직) ...
            if ret != 0:
                error_msg = self.get_error_message(ret)
                self.tr_data_cache[rq_name]['status'] = 'error'; self.tr_data_cache[rq_name]['error_code'] = ret; self.tr_data_cache[rq_name]['error_message'] = error_msg
            else:
                 self.tr_data_cache[rq_name]['status'] = 'pending_response' if not IS_TESTING_ENVIRONMENT else 'simulating_callback' # 테스트 환경에서는 바로 시뮬레이션 상태로

            self.last_request_time = time.time() 
            return ret
        except Exception as e:
            # ... (예외 처리 로직)
            detailed_error = traceback.format_exc()
            self.log(f"[KiwoomAPI] comm_rq_data 중 예외 발생: {e}\n{detailed_error}", "ERROR")
            if rq_name in self.tr_data_cache: 
                self.tr_data_cache[rq_name]['status'] = 'exception'
                self.tr_data_cache[rq_name]['error_message'] = str(e)
            return -999


    def get_repeat_cnt(self, tr_code, rq_name):
        if IS_TESTING_ENVIRONMENT:
            if rq_name in self.tr_data_cache and isinstance(self.tr_data_cache[rq_name], dict) and 'multi_data' in self.tr_data_cache[rq_name]:
                return len(self.tr_data_cache[rq_name]['multi_data'])
            return 0
        return self.ocx.dynamicCall("GetRepeatCnt(QString, QString)", tr_code, rq_name)
        
    def get_comm_data(self, tr_code, rq_name, index, item_name):
        if IS_TESTING_ENVIRONMENT:
            if rq_name in self.tr_data_cache and isinstance(self.tr_data_cache[rq_name], dict):
                data_source = None
                multi_data = self.tr_data_cache[rq_name].get('multi_data', [])
                single_data = self.tr_data_cache[rq_name].get('single_data', {})
                if multi_data and index < len(multi_data):
                    data_source = multi_data[index]
                elif index == 0 and single_data:
                    data_source = single_data
                
                if data_source and item_name in data_source:
                    return str(data_source.get(item_name, "")).strip()
            return ""
        data = self.ocx.dynamicCall("GetCommData(QString, QString, int, QString)", tr_code, rq_name, index, item_name)
        return data.strip()
        
    def get_comm_real_data(self, code, fid):
        if IS_TESTING_ENVIRONMENT: return ""
        data = self.ocx.dynamicCall("GetCommRealData(QString, int)", code, fid)
        return data.strip()
        
    def get_chejan_data(self, fid):
        if IS_TESTING_ENVIRONMENT: return ""
        data = self.ocx.dynamicCall("GetChejanData(int)", fid)
        return data.strip()

    def get_error_message(self, err_code):
        # ... (내용 동일)
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
        if IS_TESTING_ENVIRONMENT:
            self.log(f"[TEST_MODE_SKIP] SetRealReg: Screen({screen_no}), Codes({code_list_str})", "DEBUG")
            return 0 # 성공으로 가정
        # ... (기존 로직)
        self.log(f"실시간 데이터 등록 요청: 화면({screen_no}), 종목({code_list_str}), FID({fid_list_str}), 타입({opt_type})")
        ret = self.ocx.dynamicCall("SetRealReg(QString, QString, QString, QString)", screen_no, code_list_str, fid_list_str, opt_type)
        if ret == 0:
            self.log(f"실시간 데이터 등록 성공: 화면({screen_no})")
        else:
            self.log(f"실시간 데이터 등록 실패: {ret} - 화면({screen_no})", "ERROR")
        return ret
        
    def unsubscribe_real_data(self, screen_no, code=None):
        if IS_TESTING_ENVIRONMENT:
            self.log(f"[TEST_MODE_SKIP] UnsubscribeRealData: Screen({screen_no})", "DEBUG")
            return
        # ... (기존 로직)
        self.log(f"실시간 데이터 구독 해제 요청: 화면({screen_no}), 코드({code if code else 'ALL'})", "INFO")
        self.ocx.dynamicCall("DisconnectRealData(QString)", screen_no)
        if screen_no in self.subscribed_real_data:
            removed_subs = self.subscribed_real_data.pop(screen_no, None)
            if removed_subs:
                self.log(f"{screen_no} 화면의 모든 실시간 구독 관리 정보 제거됨: {removed_subs}", "DEBUG")
        self.log(f"화면번호 {screen_no}의 실시간 데이터 구독 해제 완료.")


    def disconnect_real_data(self, screen_no):
        if IS_TESTING_ENVIRONMENT:
            self.log(f"[TEST_MODE_SKIP] DisconnectRealData: Screen({screen_no})", "DEBUG")
            return
        self.ocx.dynamicCall("DisconnectRealData(QString)", screen_no)

    def unsubscribe_all_real_data(self):
        if IS_TESTING_ENVIRONMENT:
            self.log("[TEST_MODE_SKIP] UnsubscribeAllRealData", "DEBUG")
            return
        # ... (기존 로직)
        try:
            self.ocx.dynamicCall("SetRealRemove(QString, QString)", "ALL", "ALL")
            self.log("모든 실시간 데이터 구독 해제 요청됨 (SetRealRemove ALL, ALL).", "INFO")
            # 내부 구독 관리 상태도 초기화
            for code_key in list(self.subscribed_real_data.keys()): # dict 변경 중 순회를 피하기 위해 list로 복사
                if "subscribed_fids" in self.subscribed_real_data[code_key]:
                    self.subscribed_real_data[code_key]["subscribed_fids"].clear()
            self.log("내부 실시간 데이터 구독 상태 (FID 목록) 초기화 완료.", "DEBUG")
        except Exception as e:
            self.log(f"모든 실시간 데이터 구독 해제 중 예외 발생: {e}", "ERROR", exc_info=True)


    def send_order(self, rq_name, screen_no, acc_no, order_type, code, quantity, price, hoga_gb, org_order_no=""):
        # ... (기존 로직과 유사, self.ocx.dynamicCall 부분만 IS_TESTING_ENVIRONMENT로 감쌈)
        self.log(f"[KiwoomAPI_SEND_ORDER_ENTRY_DEBUG] send_order 진입. acc_no: '{acc_no}', order_type: {order_type}, code: {code}", "DEBUG")
        cleaned_acc_no = str(acc_no).strip() if acc_no else ""
        if not cleaned_acc_no:
            self.log(f"[KiwoomAPI_SEND_ORDER_ERROR] acc_no 공백 또는 유효하지 않음! RQName: {rq_name}, Code: {code}", "ERROR")
            return -999

        original_code_input_for_order = str(code)
        pure_code_for_order, suffix_in_code, _, _ = ats_utils._parse_stock_code(original_code_input_for_order, logger_instance=self.logger)

        if suffix_in_code:
            self.log(f"경고: 주문 시 입력된 종목코드 '{original_code_input_for_order}'에 ATS 접미사 '{suffix_in_code}' 포함. 주문에는 순수 종목코드 '{pure_code_for_order}' 사용.", "WARNING")
        
        final_code_for_api_order = pure_code_for_order
        self.log(f"주문 처리: 최종 API 전달 종목코드='{final_code_for_api_order}' (원본: '{original_code_input_for_order}'), 주문유형='{order_type}'", "INFO")

        order_args = [
            str(rq_name), str(screen_no), cleaned_acc_no, int(order_type),
            final_code_for_api_order, int(quantity), int(price), str(hoga_gb),
            str(org_order_no) if org_order_no else ""
        ]
        self.log(f"[KiwoomAPI_SEND_ORDER_ARGS_DEBUG] SendOrder 인자 리스트 (ATS 처리 후): {order_args}", "DEBUG")

        is_dry_run = self.config_manager.get_setting("매매전략", "dry_run_mode", False) if self.config_manager else False

        if IS_TESTING_ENVIRONMENT or is_dry_run:
            self.log(f"[TEST/Dry Run] 주문 요청: {order_args}", "INFO")
            dry_run_order_no = f"DRYRUN_{final_code_for_api_order}_{int(time.time())}"
            # 필요한 체결 데이터 필드만 포함하도록 단순화
            chejan_data = {
                'gubun': '0', # 주문 체결
                '9001': final_code_for_api_order, # 종목코드
                '9203': dry_run_order_no,      # 주문번호
                '913': '00',                   # 주문상태 (접수 -> 체결로 변경 가정)
                '905': "+매수" if order_type in [1, 11] else ("-매도" if order_type in [2, 12] else str(order_type)), # 주문구분 (+매수, -매도)
                '911': str(quantity),          # 체결량
                '10': str(price if price > 0 else self.mock_kiwoom_api.GetCommRealData(final_code_for_api_order, 10) or "10000"), # 체결가 (시장가면 현재가 모의)
                '900': str(quantity),          # 주문수량
                '902': '0',                    # 미체결수량
                'original_rq_name': str(rq_name) # Strategy에서 참조할 수 있도록 원 RQName 추가
            }
            # 체결 상태로 즉시 변경 시뮬레이션
            chejan_data_filled = chejan_data.copy()
            chejan_data_filled['913'] = '00' # 체결
            
            self.log(f"[TEST/Dry Run] 가상 체결 데이터 생성: {chejan_data_filled}", "DEBUG")
            if self.strategy_instance and hasattr(self.strategy_instance, 'on_chejan_data_received'):
                try:
                    QTimer.singleShot(10, lambda: self.strategy_instance.on_chejan_data_received('0', chejan_data_filled))
                except RuntimeError as e:
                    self.log(f"QTimer 사용 불가 (QApplication 없음, TEST/DryRun SendOrder): {e}. on_chejan_data_received 직접 호출.", "WARNING")
                    self.strategy_instance.on_chejan_data_received('0', chejan_data_filled)

            return 0 # 성공으로 가정
        else: # 실제 환경
            return_code = self.ocx.dynamicCall(
                "SendOrder(QString, QString, QString, int, QString, int, int, QString, QString)", order_args
            )
            if return_code == 0:
                self.log(f"주문 전송 성공: {rq_name}, 화면번호: {screen_no}")
            else:
                self.log(f"주문 전송 실패: {return_code} - {self.get_error_message(return_code)} ({rq_name}, 화면번호: {screen_no})", "ERROR")
            return return_code

    def cancel_order(self, rq_name_cancel, screen_no, acc_no, original_order_type_str, stock_code, quantity_to_cancel, original_order_no):
        # ... (send_order와 유사하게 self.ocx.dynamicCall 부분만 IS_TESTING_ENVIRONMENT로 감쌈)
        self.log(f"[KiwoomAPI_CANCEL_ORDER_ENTRY] cancel_order 진입. RQName: {rq_name_cancel}, 원주문번호: {original_order_no}", "DEBUG")
        # ... (파라미터 검증 로직)
        cleaned_acc_no = str(acc_no).strip() if acc_no else ""
        if not cleaned_acc_no: return -998 
        if not original_order_no: return -997
            
        pure_stock_code, _, _, _ = ats_utils._parse_stock_code(stock_code, logger_instance=self.logger) 

        cancel_order_type_code = 0
        if original_order_type_str.lower() == "매수": cancel_order_type_code = 3
        elif original_order_type_str.lower() == "매도": cancel_order_type_code = 4
        else: return -996

        order_args = [
            str(rq_name_cancel), str(screen_no), cleaned_acc_no, cancel_order_type_code,
            str(pure_stock_code), int(quantity_to_cancel), 0, "00", str(original_order_no)
        ]
        
        is_dry_run = self.config_manager.get_setting("매매전략", "dry_run_mode", False) if self.config_manager else False

        if IS_TESTING_ENVIRONMENT or is_dry_run:
            self.log(f"[TEST/Dry Run] 주문 취소 요청 (실제 전송 안함): {order_args}", "INFO")
            # TODO: 취소에 대한 가상 체결 데이터 생성 및 on_chejan_data_received 호출
            return 0 
        else: # 실제 환경
            return_code = self.ocx.dynamicCall(
                "SendOrder(QString, QString, QString, int, QString, int, int, QString, QString)", order_args
            )
            # ... (결과 로깅)
            return return_code
        
    def on_event_connect(self, err_code):
        if IS_TESTING_ENVIRONMENT: # 테스트 환경에서는 이 이벤트 핸들러가 호출되지 않도록 connect_events에서 막음
            self.log("테스트 환경: on_event_connect 호출됨 (비정상, connect_events 수정 필요)", "WARNING")
            return

        if err_code == 0:
            self.connected = True
            self.log("로그인 성공 (이벤트 수신) - 연결 상태만 변경")
        else:
            self.connected = False
            self.log(f"로그인 실패 (이벤트 수신): {err_code} ({self.get_error_message(err_code)})", "ERROR")
        
        if self.login_event_loop and self.login_event_loop.isRunning():
            self.login_event_loop.exit()
        
    def on_receive_tr_data(self, sScrNo, sRQName, sTrCode, sRecordName, sPrevNext, nDataLength, sErrorCode, sMessage, sSplmMsg):
        # ... (기존 로직과 유사, 단 Strategy 콜백 부분은 IS_TESTING_ENVIRONMENT에 따라 QTimer 사용 여부 결정 가능)
        # ... (또는 _emulate_tr_receive_for_dry_run에서 직접 Strategy 콜백 호출하므로 여기선 중복 호출 방지)
        if IS_TESTING_ENVIRONMENT and self.tr_data_cache.get(sRQName, {}).get('status') == 'simulating_callback':
            self.log(f"테스트 환경: on_receive_tr_data 호출 (이미 _emulate_tr_receive_for_dry_run에서 처리됨). RQ='{sRQName}'", "DEBUG")
            # _emulate_tr_receive_for_dry_run에서 직접 Strategy의 on_tr_data_received를 호출하게 되므로,
            # 여기서 또 호출하면 중복. 여기서는 캐시 상태만 업데이트하거나 로깅만.
            cached_request_info = self.tr_data_cache.get(sRQName, {})
            if not cached_request_info.get('error_code'): # 에러가 없었다면
                cached_request_info['status'] = 'completed_from_emulation'
            return

        # 실제 환경 또는 _emulate_tr_receive_for_dry_run에서 직접 호출되지 않은 경우에 대한 처리
        # ... (기존 on_receive_tr_data 내용)
        self.log(f"[EVENT_HANDLER_ENTRY] on_receive_tr_data: Scr='{sScrNo}', RQ='{sRQName}', TR='{sTrCode}', PrevNext='{sPrevNext}'", "DEBUG")
        # ... (에러코드 처리, 데이터 파싱, 핸들러 호출 등)
        # ... (이하 기존 on_receive_tr_data 로직과 거의 동일하게 유지, 필요시 수정)

        processed_error_code = _safe_int(sErrorCode.strip()) if isinstance(sErrorCode, str) else 0
        cached_request_info = self.tr_data_cache.get(sRQName, {})
        
        if processed_error_code != 0:
            # ... (에러 처리)
            self.screen_manager.release_screen(sScrNo, sRQName)
            if not IS_TESTING_ENVIRONMENT and self.tr_event_loop and self.tr_event_loop.isRunning(): self.tr_event_loop.exit()
            return

        parsed_data = self._parse_tr_data(sTrCode, sRQName, sScrNo, sPrevNext)
        cached_request_info.update(parsed_data)

        # ... (TR 코드별 핸들러 호출) ...
        # 예: if sTrCode == "opt10081": self._handle_opt10081(sRQName, sPrevNext, parsed_data)
        # else: self._handle_generic_tr(sTrCode, sRQName, parsed_data)
        if self.strategy_instance and hasattr(self.strategy_instance, 'on_tr_data_received'):
            self.strategy_instance.on_tr_data_received(sRQName, sTrCode, parsed_data.copy(), sPrevNext)


        if sTrCode == "opt10081" and sPrevNext == '2':
            # 연속 조회 로직 (이전과 동일, 단 comm_rq_data는 환경 변수 처리됨)
            pass 
        elif sPrevNext != '2': 
            self.screen_manager.release_screen(sScrNo, sRQName)
            if cached_request_info.get('status') != 'error':
                cached_request_info['status'] = 'completed'
            if not IS_TESTING_ENVIRONMENT and self.tr_event_loop and self.tr_event_loop.isRunning():
                self.tr_event_loop.exit()


    def on_receive_real_data(self, code, real_type, real_data_raw):
        # ... (기존 로직과 거의 동일)
        if self.strategy_instance and hasattr(self.strategy_instance, 'on_actual_real_data_received'):
            # 파싱 로직 후 전달
            parsed_real_data = {} # 파싱 로직 (이전 코드 참조)
            # ...
            self.strategy_instance.on_actual_real_data_received(code, real_type, parsed_real_data)


    def on_receive_chejan_data(self, gubun, item_cnt, fid_list_str):
        # ... (기존 로직과 거의 동일)
        current_chejan_data = {'gubun': gubun}
        if not IS_TESTING_ENVIRONMENT:
            for fid_str in fid_list_str.split(';'):
                if not fid_str.strip(): continue
                try:
                    current_chejan_data[str(int(fid_str))] = self.get_chejan_data(int(fid_str))
                except ValueError: self.log(f"잘못된 FID 형식: {fid_str}", "WARNING")
        else: # 테스트 환경에서는 fid_list_str이 실제 FID 리스트가 아닐 수 있음. chejan_data는 직접 생성됨.
            # 이 부분은 send_order의 dry_run/test 모드에서 직접 strategy의 on_chejan_data_received를 호출하므로,
            # 실제 이 이벤트 핸들러가 테스트 중 호출될 가능성은 낮음.
            self.log(f"[TEST_MODE] on_receive_chejan_data 호출됨 (일반적으로는 직접 strategy 콜백 사용): Gubun={gubun}", "DEBUG")


        if self.strategy_instance and hasattr(self.strategy_instance, 'on_chejan_data_received'):
            self.strategy_instance.on_chejan_data_received(gubun, current_chejan_data)


    def on_receive_msg(self, screen_no, rq_name, tr_code, msg):
        # ... (기존 로직과 거의 동일, 단 이벤트 루프 종료는 실제 환경에서만)
        release_screen_and_exit_loop = False
        # ... (메시지 분석 로직)
        if release_screen_and_exit_loop and not IS_TESTING_ENVIRONMENT:
            # ... (리소스 해제 및 루프 종료)
            pass

    def log(self, message, level="INFO"):
        # ... (기존과 동일)
        if self.logger:
            log_func = getattr(self.logger, level.lower(), self.logger.info)
            log_func(f"[KiwoomAPI] {message}")
        else: print(f"[{level}][KiwoomAPI] {message}")


    def _get_default_logger(self):
        # ... (기존과 동일)
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
        # ... (기존과 동일, 단 이벤트 루프 종료는 실제 환경에서만)
        if not IS_TESTING_ENVIRONMENT and event_loop and event_loop.isRunning():
            event_loop.exit()

    def _request_next_opt10081_chunk(self, rq_name, code, base_date, market_context, prev_next_val=2):
        # ... (기존과 동일, comm_rq_data는 환경변수 처리됨)
        pass
        
    def get_daily_chart(self, code: str, *, date_to: str = "", date_from: str = "", market_context: str = None):
        # ... (기존과 동일, comm_rq_data는 환경변수 처리됨)
        pass

    def get_stock_basic_info(self, code: str, market_context: str = None):
        # ... (기존과 동일, comm_rq_data는 환경변수 처리됨)
        pass

    def get_yesterday_close_price(self, code: str, base_date_str: str = None, market_context: str = None):
        # ... (기존과 동일, comm_rq_data는 환경변수 처리됨)
        pass

    def _emulate_tr_receive_for_dry_run(self, screen_no, rq_name, tr_code):
        # ... (기존과 동일, 단 Strategy 콜백 부분은 IS_TESTING_ENVIRONMENT에 따라 QTimer 사용 여부 결정 가능)
        self.log(f"[TEST/Dry Run] _emulate_tr_receive_for_dry_run 호출됨: ScreenNo='{screen_no}', RQName='{rq_name}', TRCode='{tr_code}'", "DEBUG")

        if rq_name not in self.tr_data_cache or not isinstance(self.tr_data_cache.get(rq_name), dict):
            self.log(f"[TEST/Dry Run] {rq_name}에 대한 캐시 정보를 찾을 수 없음. 가상 응답 생성 불가.", "ERROR")
            return

        cached_request_info = self.tr_data_cache[rq_name]
        # ... (가상 데이터 생성 로직, 이전 코드 참조)
        if tr_code == "opw00001": 
            cached_request_info['single_data'] = {"예수금": "50000000", "주문가능금액": "50000000"}
        elif tr_code == "opw00018": 
            cached_request_info['single_data'] = {"총매입금액": "0", "총평가금액": "0"}
            cached_request_info['multi_data'] = []
        elif tr_code == "opt10001":
            code_from_input = cached_request_info.get('params',{}).get('input_values',{}).get('종목코드', '005930')
            cached_request_info['single_data'] = {"종목코드": code_from_input, "종목명": f"가상_{code_from_input}", "현재가": "70000"}
            cached_request_info['data'] = [cached_request_info['single_data']] # _handle_opt10001 호환성
        elif tr_code == "opt10081":
            cached_request_info['multi_data'] = [{"일자":"20240101", "현재가":"10000", "거래량":"100"}] # 예시
            cached_request_info['data'] = cached_request_info['multi_data'] # _handle_opt10081 호환성

        # Strategy의 on_tr_data_received 직접 호출 (QTimer 대신)
        if self.strategy_instance and hasattr(self.strategy_instance, 'on_tr_data_received'):
            self.log(f"[TEST/Dry Run] Strategy의 on_tr_data_received 직접 호출: RQ='{rq_name}', TR='{tr_code}'", "DEBUG")
            # _parse_tr_data를 여기서 호출하여 Strategy에 전달할 데이터 포맷을 맞춤
            parsed_data_for_strategy = self._parse_tr_data(tr_code, rq_name, screen_no, '0') # sPrevNext='0'으로 가정
            self.strategy_instance.on_tr_data_received(rq_name, tr_code, parsed_data_for_strategy, '0')
        else:
            self.log(f"[TEST/Dry Run] Strategy 인스턴스 또는 on_tr_data_received 콜백 없음. RQ='{rq_name}'", "WARNING")
        
        # 캐시 상태 업데이트
        cached_request_info['status'] = 'completed_from_emulation'



    def disconnect_api(self):
        # ... (기존과 동일, self.ocx.dynamicCall 부분만 IS_TESTING_ENVIRONMENT로 감쌈)
        if not IS_TESTING_ENVIRONMENT:
            self.ocx.dynamicCall("CommTerminate()")
        else:
            self.log("[TEST_MODE_SKIP] CommTerminate 호출 스킵", "DEBUG")
        self.connected = False

    # ATS 관련 내부 헬퍼 함수 (_parse_stock_code, _determine_code_for_tr_input, _get_api_market_param_value)는
    # self.ocx를 직접 사용하지 않으므로 IS_TESTING_ENVIRONMENT 처리가 불필요할 수 있음. (기존 코드 유지)
    def _parse_stock_code(self, stock_code_with_suffix: str):
        return ats_utils._parse_stock_code(stock_code_with_suffix, logger_instance=self.logger)

    def _determine_code_for_tr_input(self, tr_code: str, stock_code_with_suffix: str) -> str:
        return ats_utils._determine_code_for_tr_input(tr_code, stock_code_with_suffix, logger_instance=self.logger)

    def _get_api_market_param_value(self, tr_code: str, market_context: Optional[str]):
        return ats_utils._get_api_market_param_value(tr_code, market_context, logger_instance=self.logger)


if __name__ == '__main__':
    if not IS_TESTING_ENVIRONMENT:
        app = QApplication(sys.argv)
        kiwoom = KiwoomAPI() 
        kiwoom.login()
        if kiwoom.connected:
            # 간단한 TR 요청 예시 (테스트용)
            # kiwoom.get_stock_basic_info("005930") 
            pass
        sys.exit(app.exec_())
    else:
        print("DISABLE_QT_FOR_TESTING is True. KiwoomAPI direct execution skipped.")
        # 테스트 환경에서는 KiwoomAPI 객체 생성 및 사용은 테스트 스크립트에서 담당
        # 예시: logger = Logger(); api = KiwoomAPI(logger=logger); api.login()
        pass
