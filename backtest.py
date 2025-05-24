#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
from datetime import datetime, timedelta
import pandas as pd
import logging
import time # 시간 관련 모듈 추가

# 기존 모듈 임포트
from config import ConfigManager
from logger import Logger
from database import Database # 백테스트 결과 저장을 위해 필요할 수 있음
from strategy import TradingStrategy, TradingState, AccountState, StrategySettings, StockTrackingData, ExternalModules
from kiwoom_api import KiwoomAPI, _safe_int, _safe_float # KiwoomAPI의 일부 유틸리티 함수 사용 가능성
from util import ScreenManager # ScreenManager도 필요
# BaseMockKiwoomAPI 임포트 (경로 문제 해결 필요 가정)
# 예를 들어, `tests` 폴더가 PYTHONPATH에 있거나, mock_api_base.py가 접근 가능한 위치에 있어야 함.
# 여기서는 tests 폴더가 PYTHONPATH에 추가되었다고 가정합니다.
from tests.mock_api_base import BaseMockKiwoomAPI


# --- 백테스트용 가상 API (MockKiwoomAPI) ---
class MockKiwoomAPI(BaseMockKiwoomAPI):
    def __init__(self, logger, config_manager, strategy_instance, historical_data_path, initial_balance=10000000):
        super().__init__(logger=logger if logger else Logger(log_level=logging.DEBUG, name="MockKiwoomBacktest"))
        self.config_manager = config_manager
        self.strategy_instance = strategy_instance # Base에도 있지만, 여기서 다시 할당 (명시적)
        self.historical_data_path = historical_data_path
        self.initial_balance = initial_balance
        self.current_balance = initial_balance
        self.portfolio: Dict[str, Dict[str, Any]] = {} 
        self.orders: List[Dict[str, Any]] = [] 
        self.current_time_index = 0 # 백테스팅 시 시간 진행 상태
        self.market_data: Dict[str, pd.DataFrame] = {}
        self.trade_log: List[Dict[str, Any]] = []
        self.daily_snapshot: List[Dict[str, Any]] = []

        # self.connected = False # Base에서 처리
        self.account_number = "MOCK_BACKTEST_ACC" # Base에서 설정한 것을 오버라이드하거나, Base에서 기본값 사용
        # self.request_interval = 0.01 # Base에 없으므로 유지
        self.last_order_id = 0 # Base에 없음 (주문번호 생성용)

        self.screen_manager = ScreenManager(logger=self.logger, kiwoom_ocx=None) # 유지
        self.log(f"MockKiwoomAPI for Backtest initialized. Initial Balance: {self.initial_balance}", "INFO")

    # log, get_connect_state, get_login_info는 BaseMockKiwoomAPI의 것을 사용

    def login(self): # Base의 CommConnect와 유사한 역할
        super().CommConnect() # Base의 CommConnect 호출하여 self.connected=True 및 콜백 시뮬레이션
        # self.log("가상 로그인 시도...", "INFO") # Base에서 로깅
        # self.connected = True # Base에서 처리
        # self.log(f"가상 로그인 성공. 계좌번호: {self.account_number}", "IMPORTANT") # Base에서 로깅
        # if self.strategy_instance and hasattr(self.strategy_instance, \'_on_login_completed\'):
        #     self.strategy_instance._on_login_completed(self.account_number) # Base CommConnect가 처리
        #     self.log("Strategy의 _on_login_completed 호출됨.", "DEBUG") # Base에서 처리
        return True

    def request_account_info(self, account_number_to_use=None):
        # This method needs to simulate the TR data that Strategy expects
        self.log(f"계좌 정보 요청 (가상): {self.account_number}", "INFO")
        # 가상 계좌 정보 생성
        account_data = {
            \'single_data\': {
                "예수금": str(self.current_balance),
                "d+2추정예수금": str(self.current_balance), # 단순화
                "주문가능금액": str(self.current_balance), # 단순화
                "총매입금액": str(sum(p[\'avg_buy_price\'] * p[\'quantity\'] for p in self.portfolio.values())),
                "총평가금액": str(sum(p[\'current_price\'] * p[\'quantity\'] for p in self.portfolio.values())),
                "총손익금액": str(sum(p[\'profit_loss\'] for p in self.portfolio.values())),
                "총손익률": "0.00" # 단순화, 필요시 계산
            }
        }
        rq_name = "모의계좌예수금요청"
        tr_code = "opw00001" # 이 TR을 모방

        # Strategy에 데이터 전달 (on_tr_data_received 사용)
        if self.strategy_instance and hasattr(self.strategy_instance, \'on_tr_data_received\'):
            self.strategy_instance.on_tr_data_received(rq_name, tr_code, account_data)
            self.log(f"{tr_code} 가상 데이터 Strategy로 전달됨.", "DEBUG")
        return 0 # 성공

    def request_portfolio_info(self, account_number_to_use=None):
        self.log(f"포트폴리오 정보 요청 (가상): {self.account_number}", "INFO")
        multi_data = []
        total_purchase_amount = 0
        total_eval_amount = 0
        total_profit_loss = 0

        for code, stock_info in self.portfolio.items():
            purchase_amount = stock_info[\'avg_buy_price\'] * stock_info[\'quantity\']
            eval_amount = stock_info[\'current_price\'] * stock_info[\'quantity\']
            profit_loss = eval_amount - purchase_amount
            profit_loss_rate = (profit_loss / purchase_amount * 100) if purchase_amount > 0 else 0

            total_purchase_amount += purchase_amount
            total_eval_amount += eval_amount
            total_profit_loss += profit_loss

            multi_data.append({
                "종목번호": stock_info[\'code\'], # 실제 API는 \'A\' + 코드 형식일 수 있으나, 여기서는 순수 코드로 통일
                "종목명": stock_info[\'name\'],
                "평가손익": str(int(profit_loss)),
                "수익률(%)": f"{profit_loss_rate:.2f}",
                "매입가": str(int(stock_info[\'avg_buy_price\'])),
                "보유수량": str(stock_info[\'quantity\']),
                "매매가능수량": str(stock_info[\'quantity\']), # 단순화
                "현재가": str(int(stock_info[\'current_price\'])),
                "매입금액": str(int(purchase_amount)),
                "평가금액": str(int(eval_amount)),
            })

        total_profit_loss_rate = (total_profit_loss / total_purchase_amount * 100) if total_purchase_amount > 0 else 0

        portfolio_data = {
            \'single_data\': {
                "총매입금액": str(int(total_purchase_amount)),
                "총평가금액": str(int(total_eval_amount)),
                "총평가손익금액": str(int(total_profit_loss)),
                "총수익률(%)": f"{total_profit_loss_rate:.2f}",
                "추정예탁자산": str(int(self.current_balance + total_eval_amount)),
                "조회건수": str(len(self.portfolio))
            },
            \'multi_data\': multi_data
        }
        rq_name = "모의계좌평가잔고내역요청"
        tr_code = "opw00018" # 이 TR을 모방

        if self.strategy_instance and hasattr(self.strategy_instance, \'on_tr_data_received\'):
            self.strategy_instance.on_tr_data_received(rq_name, tr_code, portfolio_data)
            self.log(f"{tr_code} 가상 포트폴리오 데이터 Strategy로 전달됨.", "DEBUG")
        return 0 # 성공

    def get_daily_chart(self, code: str, *, date_to: str = "", date_from: str = "", market_context: str = None):
        self.log(f"일봉 데이터 요청 (가상): 종목({code}), 기준일({date_to})", "INFO")
        pure_code, _, _, _ = self._parse_stock_code(code) # _parse_stock_code는 KiwoomAPI에서 가져오거나 여기서 간단히 구현

        if pure_code not in self.market_data:
            self.log(f"종목 {pure_code}에 대한 과거 데이터 없음.", "WARNING")
            return []

        df = self.market_data[pure_code]
        # date_to 이전 데이터만 필터링
        # date_to가 없으면 모든 데이터 사용 (실제 API는 최근 600개 정도)
        # 여기서는 단순화를 위해 date_to를 기준으로 그 이전 데이터를 제공한다고 가정
        # 백테스트에서는 보통 전체 과거 데이터를 한 번에 로드하므로, 이 함수는 특정 시점의 데이터를 가져오는 것보다
        # Strategy가 특정 종목의 차트 데이터가 필요하다고 \'요청\'하는 시점에, 이미 로드된 데이터를 Strategy에 전달하는 역할.
        # 실제로는 Strategy의 watchlist에 종목 추가 시 또는 시작 시점에 일괄적으로 전달.
        
        # KiwoomAPI의 opt10081 응답 형식과 유사하게 변환
        # columns: [\"일자\", \"시가\", \"고가\", \"저가\", \"현재가\", \"거래량\"] (필요시 추가)
        # \'현재가\'는 종가를 의미
        
        # 여기서는 Strategy가 데이터를 요청하면, 해당 종목의 전체 DataFrame을 반환하는 대신,
        # Strategy의 `on_daily_chart_data_ready` 콜백을 직접 호출하는 방식으로 에뮬레이트
        if self.strategy_instance and hasattr(self.strategy_instance, \'on_daily_chart_data_ready\'):
            # DataFrame을 API 응답 형식(list of dicts)으로 변환
            chart_data_list = []
            # 날짜를 \'YYYYMMDD\' 형식 문자열로 변환
            # \'일자\', \'시가\', \'고가\', \'저가\', \'현재가\'(종가), \'거래량\' 컬럼만 선택
            # 컬럼명이 다를 수 있으므로, 과거 데이터 로드 시 표준화 필요.
            # 여기서는 df에 \'date\', \'open\', \'high\', \'low\', \'close\', \'volume\'이 있다고 가정
            temp_df = df.copy()
            if \'date\' not in temp_df.columns: # \'date\' 컬럼이 없으면 인덱스를 사용
                temp_df[\'date\'] = temp_df.index

            for _, row in temp_df.iterrows():
                chart_data_list.append({
                    "일자": row[\'date\'].strftime(\'%Y%m%d\') if isinstance(row[\'date\'], datetime) else str(row[\'date\']),
                    "시가": int(row[\'open\']),
                    "고가": int(row[\'high\']),
                    "저가": int(row[\'low\']),
                    "현재가": int(row[\'close\']), # 종가를 \'현재가\'로 매핑
                    "거래량": int(row[\'volume\'])
                    # 필요시 "거래대금", "수정주가구분" 등 추가
                })
            
            rq_name = f"모의_opt10081_chart_{pure_code}"
            self.strategy_instance.on_daily_chart_data_ready(rq_name, pure_code, chart_data_list)
            self.log(f"종목 {pure_code}의 가상 일봉 데이터 ({len(chart_data_list)}건) Strategy로 전달됨.", "DEBUG")
            return chart_data_list # 실제 KiwoomAPI 처럼 반환값도 유지 (사용될 수도 있으므로)
        return []

    def get_stock_basic_info(self, code: str, market_context: str = None):
        self.log(f"종목 기본 정보 요청 (가상): {code}", "INFO")
        pure_code, _, _, _ = self._parse_stock_code(code)
        
        # Strategy가 이 정보를 직접 사용하기보다, watchlist 추가 시 이름 등을 활용.
        # 여기서는 간단히 종목명만 반환.
        # 실제로는 Config의 watchlist 정보나, historical data에서 가져올 수 있음.
        stock_name = f"모의_{pure_code}" # 임시 이름
        # config에서 watchlist를 가져와서 이름 매핑 시도
        watchlist_from_config = self.config_manager.get_setting("watchlist", [])
        for item in watchlist_from_config:
            if item.get("code") == pure_code:
                stock_name = item.get("name", stock_name)
                break
        
        basic_info = {
            "종목코드": pure_code,
            "종목명": stock_name,
            "현재가": "0", # 실시간 시세에서 업데이트되므로 여기서는 중요하지 않음
             # ... 기타 필요한 기본 정보 필드 (Strategy에서 사용한다면)
        }
        # Strategy에 TR 데이터 형식으로 전달
        if self.strategy_instance and hasattr(self.strategy_instance, \'on_tr_data_received\'):
            rq_name = f"모의_opt10001_{pure_code}"
            self.strategy_instance.on_tr_data_received(rq_name, "opt10001", {\'single_data\': basic_info})
            self.log(f"종목 {pure_code}의 가상 기본 정보 Strategy로 전달됨.", "DEBUG")
        return basic_info # 실제 KiwoomAPI 처럼 반환

    def send_order(self, rq_name, screen_no, acc_no, order_type, code, quantity, price, hoga_gb, org_order_no=""):
        self.log(f"주문 요청 (가상): RQ({rq_name}), 종목({code}), 유형({order_type}), 수량({quantity}), 가격({price}), 호가({hoga_gb})", "INFO")
        pure_code, _, _, _ = self._parse_stock_code(code)

        self.last_order_id += 1
        order_no = f"MOCK_{self.last_order_id:06d}"
        
        order_event_type_map = {1: "매수", 2: "매도", 3: "매수취소", 4: "매도취소"} # 실제 API 값과 매핑
        order_action_str = order_event_type_map.get(order_type, "알수없음")

        # 현재 시점의 시장가 (다음 캔들의 시가 또는 현재 캔들의 종가 - 백테스트 방식에 따라 결정)
        # 여기서는 현재 market_data에서 해당 종목, 해당 시간의 종가를 체결가로 사용
        # self.current_time_index는 run_backtest에서 현재 데이터 포인터를 가리킴
        current_market_price = 0
        current_data_point = None
        if pure_code in self.market_data and self.current_time_index < len(self.market_data[pure_code]):
            current_data_point = self.market_data[pure_code].iloc[self.current_time_index]
            # hoga_gb에 따라 체결가 달라질 수 있음 (\'00\': 지정가, \'03\': 시장가)
            # 여기서는 단순화를 위해 지정가 주문도 현재 시장가에 체결된다고 가정 (슬리피지 0)
            # 또는 지정가와 시장가를 구분하여 처리.
            # 시장가 주문이면 현재 시점의 가격 (예: 시가 또는 종가) 사용
            # 지정가 주문이면 해당 가격에 도달해야 체결 (더 복잡한 로직 필요)
            # 여기서는 price를 우선 사용하되, 0이면 (시장가 가정) current_data_point[\'close\'] 사용
            
            execution_price = price
            if hoga_gb == "03": # 시장가
                execution_price = current_data_point[\'close\'] # 현재 종가를 시장가로 간주
            elif price == 0 and order_type in [1, 2]: # 가격 0인 매수/매도는 시장가로 간주 (실제 API 동작과 다를 수 있음)
                 execution_price = current_data_point[\'close\']

            if execution_price == 0 and order_type in [1,2]: # 여전히 가격이 0이면 (예: 지정가 주문인데 가격 0으로 들어옴) 체결 불가 처리
                 self.log(f"주문 실패 (가상): 가격 0인 지정가 주문. 코드({pure_code})", "ERROR")
                 # Strategy에 체결 실패 알림 (필요시)
                 return -1 # 실패


            current_market_price = execution_price # 최종 체결 가격
        else:
            self.log(f"주문 실패 (가상): 종목({pure_code})에 대한 현재 시장 데이터 없음.", "ERROR")
            # Strategy에 체결 실패 알림 (필요시)
            return -1 # 실패

        # 주문 기록
        self.orders.append({
            \'order_no\': order_no, \'code\': pure_code, \'type\': order_action_str, 
            \'quantity\': quantity, \'price\': current_market_price, # 체결 가격으로 기록
            \'status\': \'filled\', # 백테스트에서는 모든 주문이 즉시 체결된다고 가정 (단순화)
            \'timestamp\': current_data_point.name if current_data_point is not None else datetime.now() # 데이터의 인덱스(시간) 사용
        })

        # 가상 체결 데이터 생성 및 Strategy로 전달 (on_chejan_data_received)
        chejan_data = {
            \'gubun\': \'0\', # 주문체결통보
            \'9201\': self.account_number, # 계좌번호
            \'9001\': pure_code,          # 종목코드 (실제로는 \'A\' + 코드 형식일 수 있음)
            \'9203\': order_no,           # 주문번호
            \'9205\': order_no,           # 원주문번호 (신규 주문 시 동일)
            \'913\': \'00\',               # 주문상태 (00: 접수, 10: 확인, 20: 체결) -> 여기서는 즉시 체결 \'20\' 가정
                                        # 실제 API는 접수, 체결 순으로 여러번 올 수 있음. 여기서는 단순화.
                                        # Strategy의 상태 전이를 위해, 접수 -> 체결 순으로 두 번 호출하는 것도 고려 가능.
                                        # 여기서는 한 번의 \'체결\' 통보로 처리.
            \'908\': (current_data_point.name if current_data_point is not None else datetime.now()).strftime(\'%H%M%S\'), # 주문/체결시간
            \'909\': (current_data_point.name if current_data_point is not None else datetime.now()).strftime(\'%H%M%S\'), # 체결시간
            \'302\': self.config_manager.get_stock_name(pure_code, f"모의_{pure_code}"), # 종목명
            \'900\': str(order_type),      # 주문구분 (+매수, -매도 등 실제 API는 문자열) -> 여기서는 숫자 그대로
            \'901\': str(quantity),        # 주문수량
            \'902\': str(quantity),        # 체결수량 (전량 체결 가정)
            \'903\': "0",                # 미체결수량
            \'904\': str(price),           # 주문가격
            \'910\': str(current_market_price), # 체결가
            \'911\': str(quantity),        # 체결량
            \'10\': str(current_market_price), # 현재가 (체결 시점의 현재가)
            \'27\': str(current_market_price), # (최우선)매도호가
            \'28\': str(current_market_price), # (최우선)매수호가
            # ... 기타 필요한 체결 데이터 필드
        }
        
        # 주문 상태를 \'체결\'로 설정하기 위한 FID
        # 실제 API 체결 데이터에서 \'주문상태\' FID (예: 913)가 \'체결\'을 의미하는 값으로 설정되어야 함.
        # 예: \'00\' 접수, \'01\' 확인, \'02\' 체결 (KOA 스튜디오 확인 필요)
        # 여기서는 \'913\'에 대해 Strategy가 해석할 수 있는 값 (TradingStrategy의 상태값과 연동 필요)
        # KiwoomAPI OnReceiveChejanData의 gubun \'0\'일 때 주문 상태를 파싱하는 로직 참고.
        # 지금은 chejan_data[\'913\'] = \'2\' (체결) 또는 \'00\'(접수), \'체결\' 두번 호출 등으로 단순화.
        # TradingStrategy는 \'체결\' 메시지를 받고 포트폴리오를 업데이트함.
        
        # 여기서는 \'접수\'와 \'체결\'을 순차적으로 모방하여 Strategy의 상태 머신이 동작하도록 함.
        # 1. 주문 접수 통보
        chejan_data_receipt = chejan_data.copy()
        chejan_data_receipt[\'913\'] = \'00\' # \'접수\' 상태 (실제 API 값 확인 필요)
        chejan_data_receipt[\'902\'] = "0" # 체결수량 0
        chejan_data_receipt[\'911\'] = "0" # 체결량 0
        # 주문구분 (+매수, -매도 등 실제 API는 문자열이나, KiwoomAPI에서 숫자->문자열 변환 후 strategy에 전달하기도 함)
        # 여기서는 strategy가 chejan_data_receipt[\'900\'] (주문구분 숫자)을 직접 사용한다고 가정.

        # 매수/매도 문자열 표기 (KiwoomAPI의 GetChejanData 참고)
        order_type_str_map_chejan = {1: "+매수", 2: "-매도", 3: "+매수취소", 4: "+매도취소"} # 수정필요
        chejan_data_receipt[\'906\'] = order_type_str_map_chejan.get(order_type, "기타") # 주문/체결구분명

        if self.strategy_instance and hasattr(self.strategy_instance, \'on_chejan_data_received\'):
            self.strategy_instance.on_chejan_data_received(\'0\', chejan_data_receipt) # \'0\'은 주문체결
            self.log(f"가상 주문 접수 통보: {pure_code}, {order_action_str}, 수량 {quantity}, 주문가 {price}", "DEBUG")

        # 약간의 시간차를 두고 체결 통보 (필요시)
        # time.sleep(0.001) 

        # 2. 주문 체결 통보
        chejan_data_filled = chejan_data.copy()
        chejan_data_filled[\'913\'] = \'20\' # \'체결\' 상태 (또는 API가 사용하는 다른 \'체결\' 값, 예: \'체결완료\') 
                                        # Strategy의 _parse_chejan_execution_details에서 이 값을 해석함.
        chejan_data_filled[\'902\'] = str(quantity) # 체결수량
        chejan_data_filled[\'911\'] = str(quantity) # 체결량
        chejan_data_filled[\'906\'] = order_type_str_map_chejan.get(order_type, "기타")

        # 실제 거래 처리 및 잔고/포트폴리오 업데이트
        fee_rate = self.config_manager.get_setting("매매수수료", "default_fee_rate", 0.00015) # 예시 수수료율
        tax_rate = self.config_manager.get_setting("매매세금", "sell_tax_rate", 0.0020) # 예시 매도세율 (KOSPI 2023년 기준, 실제로는 더 낮아짐)
        
        trade_executed = False
        if order_type == 1: # 매수
            cost = quantity * current_market_price
            fee = cost * fee_rate
            total_deduction = cost + fee
            if self.current_balance >= total_deduction:
                self.current_balance -= total_deduction
                
                # 포트폴리오 업데이트
                if pure_code not in self.portfolio:
                    self.portfolio[pure_code] = {\'code\': pure_code, \'name\': chejan_data_filled[\'302\'], \'quantity\': 0, \'avg_buy_price\': 0, \'current_price\': current_market_price, \'eval_amount\':0, \'profit_loss\':0, \'profit_loss_rate\':0}
                
                current_quantity = self.portfolio[pure_code][\'quantity\']
                current_avg_price = self.portfolio[pure_code][\'avg_buy_price\']
                
                new_quantity = current_quantity + quantity
                new_avg_price = ((current_avg_price * current_quantity) + (current_market_price * quantity)) / new_quantity if new_quantity > 0 else 0
                
                self.portfolio[pure_code][\'quantity\'] = new_quantity
                self.portfolio[pure_code][\'avg_buy_price\'] = new_avg_price
                trade_executed = True
                self.log(f"매수 체결 (가상): {pure_code}, {quantity}주 @ {current_market_price}, 수수료: {fee:.2f}, 총차감: {total_deduction:.2f}", "TRADE")
                self.trade_log.append({\'timestamp\': current_data_point.name, \'code\': pure_code, \'name\': chejan_data_filled[\'302\'], \'type\': \'buy\', \'quantity\': quantity, \'price\': current_market_price, \'fee\': fee, \'total_amount\': total_deduction})

            else:
                self.log(f"매수 주문 실패 (가상): 잔고 부족. 필요금액 {total_deduction}, 현재잔고 {self.current_balance}", "WARNING")
                # 주문 실패 체결 데이터 전송 (미체결 처리)
                chejan_data_filled[\'913\'] = \'미체결\' # 또는 주문거부 상태값
                chejan_data_filled[\'903\'] = str(quantity) # 미체결수량
                chejan_data_filled[\'902\'] = "0"
                chejan_data_filled[\'911\'] = "0"
        elif order_type == 2: # 매도
            if pure_code in self.portfolio and self.portfolio[pure_code][\'quantity\'] >= quantity:
                revenue = quantity * current_market_price
                fee = revenue * fee_rate
                tax = revenue * tax_rate # 매도 시 세금
                total_addition = revenue - fee - tax
                
                self.current_balance += total_addition
                
                # 포트폴리오 업데이트
                self.portfolio[pure_code][\'quantity\'] -= quantity
                if self.portfolio[pure_code][\'quantity\'] == 0:
                    # 전량 매도 시 평균 매수가 등은 유지하거나, 해당 종목을 portfolio에서 제거할 수 있음.
                    # 여기서는 단순화를 위해 quantity만 0으로. Strategy가 잔고 0인 종목 관리.
                    pass 
                trade_executed = True
                self.log(f"매도 체결 (가상): {pure_code}, {quantity}주 @ {current_market_price}, 수수료: {fee:.2f}, 세금: {tax:.2f}, 총증가: {total_addition:.2f}", "TRADE")
                self.trade_log.append({\'timestamp\': current_data_point.name, \'code\': pure_code, \'name\': chejan_data_filled[\'302\'], \'type\': \'sell\', \'quantity\': quantity, \'price\': current_market_price, \'fee\': fee, \'tax\': tax, \'total_amount\': total_addition})
            else:
                self.log(f"매도 주문 실패 (가상): 보유 수량 부족. 요청수량 {quantity}, 보유수량 {self.portfolio.get(pure_code, {}).get(\'quantity\', 0)}", "WARNING")
                chejan_data_filled[\'913\'] = \'미체결\' 
                chejan_data_filled[\'903\'] = str(quantity)
                chejan_data_filled[\'902\'] = "0"
                chejan_data_filled[\'911\'] = "0"
        
        if trade_executed or order_type in [3,4]: # 매수/매도 체결 또는 취소 주문의 경우 체결 통보
            if self.strategy_instance and hasattr(self.strategy_instance, \'on_chejan_data_received\'):
                self.strategy_instance.on_chejan_data_received(\'0\', chejan_data_filled)
                self.log(f"가상 주문 체결/처리 통보: {pure_code}, {order_action_str}, 수량 {quantity}, 체결가 {current_market_price if trade_executed else \'N/A\'}", "DEBUG")
            return 0 # 성공
        else: # 매수/매도 주문 실패 (잔고부족, 수량부족 등)
            if self.strategy_instance and hasattr(self.strategy_instance, \'on_chejan_data_received\'):
                 # 실패에 대한 체결 정보 전달 (예: 주문 거부)
                 # chejan_data_filled의 상태를 \'거부\' 또는 \'실패\'로 설정하고 전달할 수 있음
                 # 여기서는 이미 로그를 남겼으므로, 별도 체결 메시지 생략 또는 간단한 실패 메시지 전달.
                 # 혹은 Strategy가 특정 TR 에러 메시지를 기대한다면 on_receive_msg 모방.
                 # 지금은 위에서 이미 실패 로그를 남겼고, trade_executed가 False이므로 return -1로 처리.
                pass
            return -1 # 실패


    def cancel_order(self, rq_name_cancel, screen_no, acc_no, original_order_type_str, stock_code, quantity_to_cancel, original_order_no):
        self.log(f"주문 취소 요청 (가상): RQ({rq_name_cancel}), 원주문번호({original_order_no}), 종목({stock_code}), 수량({quantity_to_cancel})", "INFO")
        # 백테스트에서는 주문이 즉시 체결되므로, \'미체결\' 상태의 주문이 없음.
        # 따라서 취소할 주문이 없다고 가정하거나, 매우 단순하게 처리.
        # 만약 주문 후 일정 시간 동안 미체결 상태를 유지하는 복잡한 백테스터라면 로직 필요.
        
        # 취소 성공/실패에 대한 체결 데이터(OnReceiveChejanData)를 모방하여 Strategy에 전달해야 함.
        # gubun=\'0\' (주문체결), 주문상태 FID가 \'취소확인\' 등.
        # 여기서는 모든 취소 요청이 성공한다고 가정.
        
        # 취소 주문에 대한 새로운 주문 번호 생성 (실제 API 동작 모방)
        self.last_order_id += 1
        cancel_order_no = f"MOCK_CANCEL_{self.last_order_id:03d}"

        current_data_point_time = datetime.now() # 기본값
        if stock_code in self.market_data and self.current_time_index < len(self.market_data[stock_code]):
            current_data_point_time = self.market_data[stock_code].iloc[self.current_time_index].name


        chejan_data_cancel = {
            \'gubun\': \'0\',
            \'9201\': self.account_number,
            \'9001\': stock_code,
            \'9203\': cancel_order_no, # 취소 주문 자체의 번호
            \'9205\': original_order_no, # 원주문 번호
            \'913\': \'취소\', # 주문상태: \'취소\', \'정정취소\' 등 Strategy가 해석 가능한 값
            \'908\': current_data_point_time.strftime(\'%H%M%S\'),
            \'302\': self.config_manager.get_stock_name(stock_code, f"모의_{stock_code}"),
            \'900\': "3" if original_order_type_str == "매수" else ("4" if original_order_type_str == "매도" else "0"), # 주문구분 (매수취소:3, 매도취소:4)
            \'901\': str(quantity_to_cancel), # 주문수량(취소수량)
            \'902\': str(quantity_to_cancel), # 체결수량(취소된 수량)
            \'903\': "0",                     # 미체결수량
            \'904\': "0",                     # 주문가격 (취소 시 의미 없을 수 있음)
             # ... 기타 필요한 체결 데이터 필드
        }
        if self.strategy_instance and hasattr(self.strategy_instance, \'on_chejan_data_received\'):
            self.strategy_instance.on_chejan_data_received(\'0\', chejan_data_cancel)
            self.log(f"가상 주문 취소 통보: 원주문({original_order_no}), 종목({stock_code}), 취소수량({quantity_to_cancel})", "DEBUG")
        
        # orders 리스트에서 원주문 상태를 \'canceled\'로 변경 (필요시)
        for order in self.orders:
            if order[\'order_no\'] == original_order_no and order[\'status\'] == \'open\': # \'open\' 상태인 주문만 취소 가능
                order[\'status\'] = \'canceled\'
                self.log(f"내부 주문 목록에서 원주문 {original_order_no} 상태를 \'canceled\'로 변경.", "DEBUG")
                break
        return 0 # 성공 가정

    def set_real_reg(self, screen_no, code_list_str, fid_list_str, opt_type):
        self.log(f"실시간 데이터 등록 요청 (가상): 화면({screen_no}), 종목({code_list_str}), FID({fid_list_str}), 타입({opt_type})", "INFO")
        # 백테스트에서는 과거 데이터를 순차적으로 읽어오므로, 실제 실시간 등록/해제는 큰 의미가 없을 수 있음.
        # Strategy가 이 메서드를 호출하는지, 호출한다면 어떤 동작을 기대하는지 확인 필요.
        # 여기서는 성공적으로 등록되었다고 가정하고 0 반환.
        return 0

    def unsubscribe_real_data(self, screen_no, code=None):
        self.log(f"실시간 데이터 구독 해제 요청 (가상): 화면({screen_no}), 코드({code if code else \'ALL\'})", "INFO")
        # set_real_reg와 마찬가지로 백테스트에서는 큰 의미 없을 수 있음.
        pass

    def disconnect_api(self):
        self.log("가상 API 연결 종료.", "INFO")
        self.connected = False
        # 필요한 정리 작업 (예: 로그 파일 닫기 등)은 여기서 수행하지 않고, main의 finally에서.

    def load_historical_data(self, stock_codes, data_dir="data/historical"):
        """과거 데이터를 로드하여 self.market_data에 저장합니다."""
        # stock_codes: 로드할 종목 코드 리스트 (순수 코드)
        # data_dir: CSV 파일이 있는 디렉토리
        # 파일명 규칙: {종목코드}.csv (예: 005930.csv)
        # CSV 컬럼: Date,Open,High,Low,Close,Volume (필요에 따라 수정)
        self.log(f"과거 데이터 로드 시작. 대상 종목: {stock_codes}", "INFO")
        for code in stock_codes:
            pure_code, _, _, _ = self._parse_stock_code(code) # KiwoomAPI 것을 사용하거나 여기서 간단히 구현
            file_path = os.path.join(data_dir, f"{pure_code}.csv")
            if os.path.exists(file_path):
                try:
                    # 날짜 컬럼을 index로 파싱하도록 수정
                    df = pd.read_csv(file_path, index_col=\'Date\', parse_dates=True)
                    # 컬럼명 소문자로 통일 (일관성)
                    df.columns = [col.lower() for col in df.columns]
                    # 필요한 컬럼만 선택하거나, 컬럼명 표준화 (예: \'close\' -> \'종가\')
                    # 여기서는 \'date\', \'open\', \'high\', \'low\', \'close\', \'volume\' 사용 가정
                    # 날짜 오름차순 정렬 확인
                    df.sort_index(ascending=True, inplace=True)
                    
                    self.market_data[pure_code] = df
                    self.log(f"종목 {pure_code} 데이터 로드 완료 ({len(df)} 행). 경로: {file_path}", "DEBUG")
                except Exception as e:
                    self.log(f"종목 {pure_code} 데이터 로드 실패: {e}. 경로: {file_path}", "ERROR")
            else:
                self.log(f"종목 {pure_code} 데이터 파일 없음: {file_path}", "WARNING")
        self.log(f"과거 데이터 로드 완료. 총 {len(self.market_data)}개 종목 데이터 로드됨.", "INFO")

    def _parse_stock_code(self, full_code_str: str):
        """ KiwoomAPI의 _parse_stock_code 간소화 버전 또는 그대로 가져오기 """
        # 이 함수는 KiwoomAPI 클래스에서 복사해오거나, 간단히 순수 코드만 추출하도록 구현
        full_code = str(full_code_str).strip()
        # ATS 접미사 (_NX, _AL) 제거 로직 (KiwoomAPI 참조)
        # 여기서는 간단히 6자리 숫자 코드만 가정
        if "_" in full_code:
            parts = full_code.split("_")
            if len(parts[0]) == 6 and parts[0].isdigit():
                return parts[0], f"_{parts[1]}" if len(parts) > 1 else None, parts[1] if len(parts) > 1 else None, full_code
        
        if (len(full_code) == 6 and full_code.isdigit()) or \
           (len(full_code) > 0 and full_code[0].isalpha() and len(full_code[1:]) == 6 and full_code[1:].isdigit()): # ETN/ETF 등 고려
            return full_code, None, None, full_code
        
        self.log(f"_parse_stock_code: 유효하지 않은 코드 형식으로 추정: \'{full_code_str}\'. 원본 반환.", "WARNING")
        return full_code, None, None, full_code # 실패 시 원본 반환


    def get_current_market_data(self, code):
        """ 현재 시점(self.current_time_index)의 특정 종목 시장 데이터를 반환합니다. """
        pure_code, _, _, _ = self._parse_stock_code(code)
        if pure_code in self.market_data and self.current_time_index < len(self.market_data[pure_code]):
            return self.market_data[pure_code].iloc[self.current_time_index]
        return None

    def update_portfolio_current_prices(self, current_timestamp):
        """ 현재 시점의 가격으로 포트폴리오 내 보유 종목들의 현재가 및 평가금액 업데이트 """
        for code, stock_info in self.portfolio.items():
            if stock_info[\'quantity\'] > 0:
                market_data_for_stock = self.get_current_market_data(code)
                if market_data_for_stock is not None:
                    current_price = market_data_for_stock[\'close\'] # 현재 종가를 사용
                    stock_info[\'current_price\'] = current_price
                    stock_info[\'eval_amount\'] = current_price * stock_info[\'quantity\']
                    purchase_amount = stock_info[\'avg_buy_price\'] * stock_info[\'quantity\']
                    stock_info[\'profit_loss\'] = stock_info[\'eval_amount\'] - purchase_amount
                    stock_info[\'profit_loss_rate\'] = (stock_info[\'profit_loss\'] / purchase_amount * 100) if purchase_amount > 0 else 0
                else:
                    # 해당 시점에 시장 데이터가 없는 경우 (거래정지 등 모방) - 이전 가격 유지 또는 특정 값 처리
                    self.log(f"포트폴리오 업데이트: 종목 {code}의 현재 시점({current_timestamp}) 시장 데이터 없음. 이전 가격 유지.", "DEBUG")


    def _get_stock_name_from_market_data(self, code):
        """ (필요시) market_data에 종목명이 포함되어 있다면 가져오는 함수 """
        # 현재는 ConfigManager의 watchlist에서 가져오도록 되어 있음.
        return f"모의_{code}"


# --- 백테스트 실행 로직 ---
def run_backtest(config_path="settings.json", historical_data_dir="data/historical"):
    # 1. 설정 및 로거 초기화
    config = ConfigManager(config_file=config_path)
    log_level_str = config.get_setting("Logging", "level", "INFO")
    log_level_numeric = getattr(logging, log_level_str.upper(), logging.INFO)
    logger = Logger(log_level=log_level_numeric, name="Backtester") # 로거 이름 변경
    logger.info("백테스트 시작")
    logger.info(f"설정 파일: {config_path}, 과거 데이터 경로: {historical_data_dir}")

    # 백테스트 관련 설정 로드
    backtest_settings = config.get_setting("backtest", {})
    start_date_str = backtest_settings.get("start_date", (datetime.now() - timedelta(days=365)).strftime(\'%Y-%m-%d\'))
    end_date_str = backtest_settings.get("end_date", datetime.now().strftime(\'%Y-%m-%d\'))
    initial_balance = backtest_settings.get("initial_balance", 10000000)
    target_stocks_config = backtest_settings.get("target_stocks", []) # watchlist와 별개로 백테스트 대상 종목 지정 가능

    if not target_stocks_config: # target_stocks 설정이 없으면 watchlist 사용
        target_stocks_config = config.get_setting("watchlist", [])
        if not target_stocks_config:
            logger.error("백테스트 대상 종목이 설정되지 않았습니다 (settings.json의 backtest.target_stocks 또는 watchlist 확인).")
            return
    
    target_stock_codes = [item[\'code\'] for item in target_stocks_config if \'code\' in item]
    if not target_stock_codes:
        logger.error("백테스트 대상 종목 코드를 찾을 수 없습니다.")
        return

    logger.info(f"백테스트 기간: {start_date_str} ~ {end_date_str}")
    logger.info(f"초기 자본금: {initial_balance:,.0f} 원")
    logger.info(f"대상 종목: {target_stock_codes}")

    start_date = datetime.strptime(start_date_str, \'%Y-%m-%d\')
    end_date = datetime.strptime(end_date_str, \'%Y-%m-%d\')

    # 2. 가상 API 및 전략 모듈 초기화
    # Strategy 초기화 시 KiwoomAPI는 None으로, 나중에 MockAPI 주입
    # ScreenManager는 MockAPI가 내부적으로 더미를 생성하여 Strategy에 제공하거나,
    # Strategy가 ScreenManager 없이도 동작 가능하도록 수정 필요.
    # 현재 TradingStrategy는 ExternalModules를 통해 screen_manager를 받으므로,
    # MockAPI가 strategy_instance를 받을 때 ExternalModules 설정을 완료해야 함.

    # Database 인스턴스 (백테스트 결과 저장용)
    db_path_backtest = config.get_setting("Database", "path_backtest", "data/backtest_results.db")
    db_backtest = Database(db_file=db_path_backtest, logger=logger)

    # ScreenManager 단일 인스턴스 (MockAPI 내부에서 생성/관리 또는 여기서 전달)
    # 여기서는 MockAPI가 내부적으로 생성하도록 함.
    
    mock_api = MockKiwoomAPI(logger, config, None, historical_data_dir, initial_balance) # strategy는 나중에 주입

    # TradingStrategy 인스턴스 생성
    # KiwoomAPI 대신 mock_api의 인스턴스를 사용하도록 strategy_settings 수정 또는 ExternalModules 직접 설정
    # StrategySettings를 통해 modules를 전달하는 방식이 더 깔끔할 수 있음.
    # modules = ExternalModules(kiwoom_api=mock_api, db_manager=db_backtest, config_manager=config, screen_manager=mock_api.screen_manager, logger=logger)
    # strategy = TradingStrategy(config_manager=config, logger=logger, db_manager=db_backtest, modules=modules)
    
    # 기존 방식대로 TradingStrategy 생성 후 mock_api 주입
    strategy_modules = ExternalModules(
        kiwoom_api=mock_api,  # MockAPI 인스턴스 주입
        db_manager=db_backtest,
        config_manager=config,
        screen_manager=mock_api.screen_manager, # MockAPI가 제공하는 ScreenManager
        logger=logger
    )
    strategy = TradingStrategy(
        config_manager=config,
        logger=logger,
        db_manager=db_backtest, # db_manager는 올바른 db 인스턴스 전달
        modules=strategy_modules # 수정된 modules 전달
    )
    mock_api.strategy_instance = strategy # 순환 참조 설정 (MockAPI가 Strategy 콜백 호출용)
    
    logger.info("가상 API 및 매매 전략 모듈 초기화 완료.")

    # 3. 과거 데이터 로드
    mock_api.load_historical_data(target_stock_codes, historical_data_dir)
    if not mock_api.market_data:
        logger.error("로드된 과거 데이터가 없습니다. 백테스트를 진행할 수 없습니다.")
        return

    # 모든 종목의 데이터를 하나의 DataFrame으로 병합하고, 날짜 기준으로 정렬된 unique한 인덱스 생성
    # 가장 오래된 데이터 시작일부터 가장 최근 데이터 종료일까지의 모든 거래일을 포함하는 인덱스 생성
    # 이 부분은 데이터가 많은 경우 메모리 문제가 있을 수 있으므로, 주의해서 처리
    # 여기서는 첫 번째 대상 종목의 인덱스를 기준으로 사용 (단순화)
    # 또는 모든 종목 데이터의 날짜 인덱스를 합집합하여 사용
    
    all_dates = set()
    for code in mock_api.market_data:
        all_dates.update(mock_api.market_data[code].index)
    
    if not all_dates:
        logger.error("유효한 거래일 데이터가 없습니다.")
        return

    # 날짜 범위 필터링 (start_date, end_date)
    # pd.Timestamp로 변환하여 비교
    pd_start_date = pd.Timestamp(start_date)
    pd_end_date = pd.Timestamp(end_date)

    # all_dates를 pd.Timestamp 객체로 변환 (이미 parse_dates=True로 로드했으면 Timestamp 객체임)
    # 필터링 전 모든 날짜가 pd.Timestamp인지 확인
    filtered_dates = sorted([d for d in all_dates if pd_start_date <= d <= pd_end_date])
    
    if not filtered_dates:
        logger.error(f"지정된 기간 ({start_date_str} ~ {end_date_str})에 해당하는 데이터가 없습니다.")
        return
    
    logger.info(f"백테스트 실행 대상 거래일 수: {len(filtered_dates)}")

    # 4. 가상 로그인 및 전략 초기화
    mock_api.login() # 내부적으로 strategy._on_login_completed 호출
    # Strategy의 watchlist는 어떻게 채울 것인가?
    # 1. ConfigManager의 watchlist 설정을 그대로 사용 (main.py와 유사)
    # 2. 백테스트 대상 종목(target_stock_codes)을 watchlist에 추가
    
    # 여기서는 target_stock_codes를 watchlist에 추가
    logger.info("백테스트 대상 종목을 전략의 관심종목으로 추가합니다...")
    for code in target_stock_codes:
        # 종목명은 config의 watchlist 또는 historical data에서 가져오거나, mock_api가 임의로 생성
        stock_name = config.get_stock_name(code, f"모의_{code}") # ConfigManager에 get_stock_name 추가 필요 가정
        
        # 전일 종가: 백테스트 시작일 직전일의 종가가 필요.
        # 여기서는 일단 0으로 하고, Strategy가 첫날 데이터를 받을 때 내부적으로 업데이트하거나,
        # 또는 첫날 시가로 대체하는 등의 처리가 필요할 수 있음.
        # Strategy의 add_to_watchlist는 yesterday_close_price를 받음.
        # 이 값을 어떻게 정확히 설정할지가 중요.
        # 가장 간단하게는 첫날 시가를 사용하거나, 첫날 데이터를 미리 조회해서 설정.
        # 여기서는 0으로 두고, Strategy가 데이터를 받으며 처리하도록 기대.
        # 또는 historical_data에서 start_date 직전일 종가를 찾아 설정.
        
        # start_date 직전일 종가 찾기
        prev_day_close = 0
        if code in mock_api.market_data:
            df_stock = mock_api.market_data[code]
            # start_date 이전의 가장 마지막 날짜 데이터 찾기
            prev_day_data = df_stock[df_stock.index < pd_start_date]
            if not prev_day_data.empty:
                prev_day_close = prev_day_data.iloc[-1][\'close\']
        
        strategy.add_to_watchlist(code, stock_name, yesterday_close_price=prev_day_close)
    logger.info(f"{len(strategy.watchlist)}개의 관심종목이 전략에 추가되었습니다.")

    # Strategy에 일봉 데이터 미리 전달 (KiwoomAPI의 get_daily_chart 모방)
    for code in target_stock_codes:
        mock_api.get_daily_chart(code) # 내부적으로 strategy.on_daily_chart_data_ready 호출

    # Strategy 시작
    strategy.start() # is_running = True, 상태 업데이트 등
    logger.info("매매 전략 시작됨 (가상 환경).")

    # 5. 시간 순서대로 데이터 주입 및 전략 실행
    # filtered_dates는 이미 정렬된 상태
    for current_sim_time in filtered_dates:
        mock_api.current_time_index = -1 # 현재 날짜에 해당하는 데이터 인덱스를 찾아야 함
        
        # current_sim_time이 각 종목 데이터프레임의 인덱스에 있는지 확인하고, 있다면 그 행을 사용.
        # 이 방식보다, filtered_dates를 순회하면서, 각 날짜에 대해 모든 target_stock_codes의 데이터를 가져오는 것이 더 정확.
        # mock_api.market_data[code]의 인덱스가 filtered_dates[i]와 일치하는 행을 찾아야 함.
        
        # 현재 시뮬레이션 시간 로깅
        current_sim_time_str = current_sim_time.strftime(\'%Y-%m-%d %H:%M:%S\') if isinstance(current_sim_time, datetime) else str(current_sim_time)
        logger.debug(f"--- 시뮬레이션 시간: {current_sim_time_str} ---")

        # 포트폴리오 현재가 업데이트 (매일 시작 시)
        mock_api.update_portfolio_current_prices(current_sim_time)


        # 각 관심 종목에 대해 현재 시점의 시장 데이터 생성 및 Strategy에 전달
        for stock_code_obj in strategy.watchlist.values(): # strategy.watchlist는 StockTrackingData 객체들을 담고 있음
            code = stock_code_obj.code # 순수 코드
            
            # 현재 시뮬레이션 날짜(current_sim_time)에 해당하는 데이터 가져오기
            current_data_for_stock = None
            if code in mock_api.market_data:
                stock_df = mock_api.market_data[code]
                if current_sim_time in stock_df.index:
                    current_data_for_stock = stock_df.loc[current_sim_time]
                    # MockAPI의 current_time_index 업데이트 (send_order 등에서 사용)
                    # 이 로직은 특정 종목의 데이터프레임 내 인덱스를 찾아야 함.
                    # filtered_dates는 모든 종목의 날짜 합집합이므로, 특정 종목에는 해당 날짜 데이터가 없을 수도 있음.
                    # 여기서는 current_data_for_stock이 있으면, 그 종목의 current_time_index를 설정.
                    # 하지만 mock_api.current_time_index는 전역적이므로, 이렇게 하면 안됨.
                    # send_order 등에서는 current_sim_time을 기준으로 데이터를 직접 찾아야 함.
                    # mock_api.current_time_index 제거하고, current_sim_time을 직접 사용하도록 MockAPI 수정.
                else:
                    # logger.debug(f"종목 {code} 데이터에 현재 시뮬레이션 시간 {current_sim_time_str} 없음. 건너뜀.")
                    continue # 해당 날짜에 데이터 없는 종목은 건너뜀
            else:
                # logger.debug(f"종목 {code}에 대한 market_data 없음. 건너뜀.")
                continue
            
            if current_data_for_stock is None:
                continue

            # 실시간 데이터 모방 (on_actual_real_data_received 호출)
            # KiwoomAPI의 FID 값과 필드명 매핑 참고 필요
            # 예시: 주식시세 (종가, 시가, 고가, 저가, 거래량 등)
            real_data_payload = {
                \'code\': code,
                \'real_type\': "주식시세", # 또는 "주식체결" (더 세분화 가능)
                \'현재가\': int(current_data_for_stock[\'close\']),
                \'전일대비\': int(current_data_for_stock[\'close\'] - current_data_for_stock.get(\'prev_close\', current_data_for_stock[\'close\'])), # 전일종가 필요
                \'등락률\': float( (current_data_for_stock[\'close\'] / current_data_for_stock.get(\'prev_close\', current_data_for_stock[\'close\']) -1) * 100 if current_data_for_stock.get(\'prev_close\', 0) != 0 else 0),
                \'누적거래량\': int(current_data_for_stock[\'volume\']),
                \'시가\': int(current_data_for_stock[\'open\']),
                \'고가\': int(current_data_for_stock[\'high\']),
                \'저가\': int(current_data_for_stock[\'low\']),
                \'체결시간\': current_sim_time.strftime(\'%H%M%S\'), # 일봉 데이터면 시간은 의미 없을 수 있음 (예: 153000)
                # ... 기타 필요한 FID 값들
            }
            if strategy and hasattr(strategy, \'on_actual_real_data_received\'):
                strategy.on_actual_real_data_received(code, "주식시세", real_data_payload)
                # logger.debug(f"종목 {code} 실시간 데이터 주입: 현재가 {real_data_payload[\'현재가\']}")


        # Strategy의 주기적 로직 호출 (실제 프로그램에서는 타이머 기반)
        # 여기서는 매일 데이터 주입 후 한 번씩 호출 가정
        if strategy and hasattr(strategy, \'_process_all_strategies_and_report\'): # 이 이름의 함수가 있다고 가정
             # strategy._process_all_strategies_and_report()
             # 또는 TradingStrategy의 process_strategy를 직접 호출해야 할 수도 있음.
             # TradingStrategy의 메인 루프(start에서 시작되는)가 어떻게 동작하는지 확인 필요.
             # 현재 TradingStrategy.start()는 QTimer로 _run_strategy_cycle를 반복 호출.
             # 백테스트에서는 QTimer를 사용하지 않으므로, 해당 로직을 직접 호출.
             strategy.run_strategy_cycle() # 이 함수가 주기적인 작업들을 수행한다고 가정
             logger.debug(f"Strategy 주기적 로직 실행 완료 ({current_sim_time_str}).")
        
        # 일별 스냅샷 기록
        stock_value = sum(p[\'eval_amount\'] for p in mock_api.portfolio.values())
        total_assets = mock_api.current_balance + stock_value
        mock_api.daily_snapshot.append({
            \'date\': current_sim_time,
            \'total_assets\': total_assets,
            \'cash\': mock_api.current_balance,
            \'stock_value\': stock_value
        })
        logger.info(f"일별 스냅샷 ({current_sim_time_str}): 총자산 {total_assets:,.0f}, 현금 {mock_api.current_balance:,.0f}, 주식평가 {stock_value:,.0f}")


    # 6. 백테스트 종료 및 결과 분석/리포팅
    logger.info("백테스트 시뮬레이션 완료.")
    strategy.stop() # 전략 중지 (리소스 정리 등)
    mock_api.disconnect_api() # 가상 API 연결 종료

    final_balance = mock_api.current_balance + sum(p[\'eval_amount\'] for p in mock_api.portfolio.values())
    total_return = (final_balance / initial_balance - 1) * 100
    num_trades = len(mock_api.trade_log)

    logger.info("--- 백테스트 결과 ---")
    logger.info(f"시작일: {start_date_str}, 종료일: {end_date_str}")
    logger.info(f"초기 자본금: {initial_balance:,.0f} 원")
    logger.info(f"최종 자산: {final_balance:,.0f} 원")
    logger.info(f"총 수익률: {total_return:.2f}%")
    logger.info(f"총 거래 횟수: {num_trades}")

    # 거래 내역 출력
    if mock_api.trade_log:
        logger.info("--- 거래 내역 ---")
        trade_df = pd.DataFrame(mock_api.trade_log)
        logger.info(f"\\n{trade_df.to_string()}") # DataFrame을 문자열로 변환하여 로깅
        # trade_df.to_csv("data/backtest_tradelog.csv", index=False) # CSV로 저장
        # db_backtest에 저장할 수도 있음
    else:
        logger.info("거래 내역이 없습니다.")

    # 일별 자산 스냅샷 분석 (MDD 등 계산 가능)
    if mock_api.daily_snapshot:
        snapshot_df = pd.DataFrame(mock_api.daily_snapshot)
        snapshot_df.set_index(\'date\', inplace=True)
        logger.info("--- 일별 자산 변화 ---")
        logger.info(f"\\n{snapshot_df.to_string()}")
        # snapshot_df.to_csv("data/backtest_daily_snapshot.csv")

        # MDD 계산
        peak = snapshot_df[\'total_assets\'].expanding(min_periods=1).max()
        drawdown = (snapshot_df[\'total_assets\'] - peak) / peak
        mdd = drawdown.min() * 100
        logger.info(f"최대 낙폭 (MDD): {mdd:.2f}%")
    
    # 추가 분석: 승률, 평균 손익비 등


    # 필요시 Matplotlib 등으로 그래프 출력 (별도 함수로 분리 가능)
    try:
        import matplotlib.pyplot as plt
        if mock_api.daily_snapshot:
            snapshot_df[\'total_assets\'].plot(title=\'Portfolio Value Over Time\')
            plt.ylabel("Total Assets (KRW)")
            plt.xlabel("Date")
            plt.grid(True)
            # plt.savefig("data/backtest_portfolio_value.png") # 이미지 파일로 저장
            plt.show() # 화면에 표시
    except ImportError:
        logger.info("Matplotlib이 설치되지 않아 그래프를 표시할 수 없습니다.")
    except Exception as e_plot:
        logger.error(f"그래프 생성 중 오류: {e_plot}")


    db_backtest.close() # DB 연결 종료
    logger.info("백테스트 종료.")


if __name__ == "__main__":
    # 필요한 디렉토리 생성 (main.py의 create_directories와 유사)
    if not os.path.exists("data/historical"):
        os.makedirs("data/historical", exist_ok=True)
        print("Created directory: data/historical (샘플 과거 데이터 저장 위치)")
    if not os.path.exists("logs"): # Logger가 자동 생성하지만, 명시적으로 생성해도 무방
        os.makedirs("logs", exist_ok=True)
        print("Created directory: logs")
    
    # --- 샘플 과거 데이터 생성 (005930.csv) ---
    # 이 부분은 실제 과거 데이터를 준비하는 방법으로 대체해야 합니다.
    # 여기서는 아주 간단한 샘플 데이터를 생성합니다.
    sample_csv_path = "data/historical/005930.csv"
    if not os.path.exists(sample_csv_path):
        print(f"샘플 과거 데이터 ({sample_csv_path}) 생성 중...")
        date_today = datetime.today()
        dates = [date_today - timedelta(days=i) for i in range(30)][::-1] # 최근 30일
        data = {
            \'Date\': [d.strftime(\'%Y-%m-%d\') for d in dates],
            \'Open\': [70000 + i*100 for i in range(30)],
            \'High\': [70500 + i*100 for i in range(30)],
            \'Low\': [69500 + i*100 for i in range(30)],
            \'Close\': [70200 + i*100 for i in range(30)],
            \'Volume\': [1000000 + i*10000 for i in range(30)]
        }
        df_sample = pd.DataFrame(data)
        df_sample.to_csv(sample_csv_path, index=False)
        print(f"샘플 데이터 생성 완료: {sample_csv_path}")
        print("실제 백테스트를 위해서는 정확한 과거 데이터를 준비해야 합니다.")
        print("대상 종목: settings.json의 watchlist 또는 backtest.target_stocks에 지정")
        print("데이터 파일명: {종목코드}.csv (예: 005930.csv), 저장위치: data/historical/")
        print("CSV 컬럼: Date,Open,High,Low,Close,Volume (Date는 YYYY-MM-DD 형식)")

    # --- 샘플 settings.json 내용 (참고용) ---
    # 실제로는 settings.json 파일에 이와 유사한 내용을 작성해야 합니다.
    # {
    #   "Logging": { "level": "INFO" },
    #   "backtest": {
    #     "start_date": "2023-01-01", // 실제 데이터가 있는 날짜로 변경
    #     "end_date": "2023-12-31",   // 실제 데이터가 있는 날짜로 변경
    #     "initial_balance": 100000000,
    #     "target_stocks": [
    #       { "code": "005930", "name": "삼성전자" }
    #       // 추가 종목들...
    #     ]
    #   },
    #   "watchlist": [ // target_stocks가 없으면 이걸 사용
    #       { "code": "005930", "name": "삼성전자", "yesterday_close_price": 70000 }
    #   ],
    #   "매매전략": { // TradingStrategy가 사용하는 설정들
    #      // ... (예: max_stocks_to_hold, target_profit_ratio 등)
    #   }
    #   // ... 기타 필요한 설정들 (Database, API_Limit 등)
    # }
    
    run_backtest()