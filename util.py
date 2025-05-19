#!/usr/bin/env python
# -*- coding: utf-8 -*-

print("util.py: Starting to load util.py module...") # util.py 로딩 시작

import re
print("util.py: Imported re.")

print("util.py: About to import pandas...")
import pandas as pd
print("util.py: Successfully imported pandas.")

print("util.py: About to import datetime...")
from datetime import datetime, timedelta
print("util.py: Successfully imported datetime.")

import threading
from typing import Union, Optional
import logging

def format_number(number, with_sign=False):
    """
    숫자를 천 단위 구분 기호가 있는 문자열로 변환
    
    Args:
        number: 변환할 숫자
        with_sign (bool): 부호 표시 여부
    
    Returns:
        str: 포맷된 문자열
    """
    if number is None:
        return "0"
    
    try:
        number = float(number)
        if number.is_integer():
            formatted = format(int(number), ',')
        else:
            formatted = format(number, ',.2f')
            
        if with_sign and number > 0:
            return f"+{formatted}"
        return formatted
    except (ValueError, TypeError):
        return str(number)

def format_percentage(number, decimal_points=2):
    """
    숫자를 백분율 문자열로 변환
    
    Args:
        number: 변환할 숫자 (예: 0.05)
        decimal_points (int): 소수점 자릿수
    
    Returns:
        str: 백분율 문자열 (예: "5.00%")
    """
    if number is None:
        return "0.00%"
    
    try:
        number = float(number)
        # 백분율로 변환 (0.05 → 5.00%)
        percentage = number * 100
        formatted = f"{percentage:.{decimal_points}f}%"
        
        # 부호 추가
        if number > 0:
            formatted = f"+{formatted}"
            
        return formatted
    except (ValueError, TypeError):
        return str(number)

def get_current_time_str(format="%Y-%m-%d %H:%M:%S"):
    """
    현재 시간을 지정된 형식의 문자열로 반환
    
    Args:
        format (str): 시간 형식 (기본값: "%Y-%m-%d %H:%M:%S")
    
    Returns:
        str: 형식에 맞는 현재 시간 문자열
    """
    return datetime.now().strftime(format)

def convert_to_date(date_str, input_format="%Y%m%d"):
    """
    문자열을 날짜 객체로 변환
    
    Args:
        date_str (str): 날짜 문자열
        input_format (str): 입력 날짜 형식
    
    Returns:
        datetime.date: 날짜 객체
    """
    try:
        return datetime.strptime(date_str, input_format).date()
    except ValueError:
        return None

def is_market_open():
    """
    현재 장 운영 시간인지 확인
    
    Returns:
        bool: 장 운영 시간 여부
    """
    now = datetime.now()
    
    # 주말 체크
    if now.weekday() >= 5:  # 5: 토요일, 6: 일요일
        return False
    
    # 시간 체크 (9:00 ~ 15:30)
    market_start = now.replace(hour=9, minute=0, second=0, microsecond=0)
    market_end = now.replace(hour=15, minute=30, second=0, microsecond=0)
    
    return market_start <= now <= market_end

def is_valid_stock_code(code):
    """
    주식 종목코드 유효성 검사
    
    Args:
        code (str): 검사할 종목코드
    
    Returns:
        bool: 유효한 종목코드이면 True, 아니면 False
    """
    # 종목코드는 6자리 숫자
    if not code or len(code) != 6:
        return False
    
    # 숫자로만 구성되어 있는지 확인
    if not code.isdigit():
        return False
    
    return True

def parse_date_str(date_str, format="%Y%m%d"):
    """
    문자열을 datetime 객체로 변환
    
    Args:
        date_str (str): 변환할 날짜 문자열
        format (str): 날짜 형식 (기본값: "%Y%m%d")
    
    Returns:
        datetime: 변환된 datetime 객체
    """
    try:
        return datetime.strptime(date_str, format)
    except ValueError:
        return None

def format_date(date, format="%Y-%m-%d"):
    """
    datetime 객체를 문자열로 변환
    
    Args:
        date (datetime): 변환할 datetime 객체
        format (str): 날짜 형식 (기본값: "%Y-%m-%d")
    
    Returns:
        str: 변환된 날짜 문자열
    """
    try:
        return date.strftime(format)
    except (ValueError, AttributeError):
        return str(date)

def calculate_profit_loss(buy_price, current_price):
    """
    손익률 계산
    
    Args:
        buy_price (float): 매수가
        current_price (float): 현재가
    
    Returns:
        float: 손익률 (예: 0.05 = 5%)
    """
    try:
        buy_price = float(buy_price)
        current_price = float(current_price)
        
        if buy_price <= 0:
            return 0
            
        return (current_price - buy_price) / buy_price
    except (ValueError, TypeError, ZeroDivisionError):
        return 0

def calculate_quantity(amount, price):
    """
    주문 가능 수량 계산
    
    Args:
        amount (float): 주문 금액
        price (float): 주가
    
    Returns:
        int: 주문 가능 수량
    """
    try:
        amount = float(amount)
        price = float(price)
        
        if price <= 0:
            return 0
            
        # 정수로 내림 (최대 주문 가능 수량)
        return int(amount / price)
    except (ValueError, TypeError, ZeroDivisionError):
        return 0

def parse_message(message):
    """
    메시지에서 키워드 추출
    
    Args:
        message (str): 메시지
        
    Returns:
        dict: 추출된 키워드 딕셔너리
    """
    result = {}
    
    # 종목 코드/이름 추출
    code_pattern = re.compile(r'종목[코드]?[:\s]+([A-Za-z0-9]+)')
    code_match = code_pattern.search(message)
    if code_match:
        result['code'] = code_match.group(1)
    
    # 가격 추출
    price_pattern = re.compile(r'가격[:\s]+([\d,]+)')
    price_match = price_pattern.search(message)
    if price_match:
        result['price'] = int(price_match.group(1).replace(',', ''))
    
    # 수량 추출
    quantity_pattern = re.compile(r'수량[:\s]+([\d,]+)')
    quantity_match = quantity_pattern.search(message)
    if quantity_match:
        result['quantity'] = int(quantity_match.group(1).replace(',', ''))
    
    return result 

# ScreenManager 클래스 정의 추가
class ScreenManager:
    def __init__(self, logger=None, start_screen_no=2000, num_screens=100, kiwoom_ocx=None): # 화면번호 범위 지정, kiwoom_ocx 추가
        self.logger = logger if logger else self._get_default_logger()
        self.kiwoom_ocx = kiwoom_ocx # kiwoom_ocx 인스턴스 저장
        self.lock = threading.Lock()

        self.start_screen_no = start_screen_no
        self.num_screens = num_screens
        
        self.available_screens = [str(i) for i in range(self.start_screen_no, self.start_screen_no + self.num_screens)]
        self.screen_map = {}  # {identifier: screen_no}
        self.used_screens = {} # {screen_no: identifier} # 사용중인 화면 추적 (해제 시 identifier를 모를 경우 사용)

        self.logger.debug(f"ScreenManager 초기화 완료. 사용 가능 화면: {len(self.available_screens)}개 ({self.start_screen_no}~{self.start_screen_no + self.num_screens - 1})")

    def log_portfolio_details(self, portfolio_summary_text):
        """포트폴리오 상세 정보를 로깅합니다."""
        if not self.logger:
            print("[ScreenManager] Logger not available for portfolio logging.")
            return
        
        self.logger.info("--- Portfolio Details ---")
        self.logger.info(portfolio_summary_text)
        self.logger.info("-------------------------")

    def _get_default_logger(self):
        logger = logging.getLogger("ScreenManager_Default")
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.DEBUG)
        return logger

    def get_available_screen(self, identifier: str) -> Optional[str]:
        with self.lock:
            if identifier in self.screen_map:
                screen_no = self.screen_map[identifier]
                self.logger.debug(f"[ScreenManager_GET] 기존 화면 재사용: Identifier='{identifier}' -> ScreenNo='{screen_no}'. 사용중: {len(self.used_screens)}, 사용가능: {len(self.available_screens)}")
                return screen_no

            if not self.available_screens:
                self.logger.error(f"[ScreenManager_GET] 사용 가능한 화면 번호 없음! 요청 Identifier='{identifier}'. 현재 사용중: {len(self.used_screens)}개")
                # LRU 또는 다른 화면 회수 정책을 여기에 구현할 수 있음
                # 현재는 단순 실패 처리
                return None
            
            screen_no = self.available_screens.pop(0) # 가장 앞 번호 사용
            self.screen_map[identifier] = screen_no
            self.used_screens[screen_no] = identifier
            self.logger.info(f"[ScreenManager_GET] 새 화면 할당: Identifier='{identifier}' -> ScreenNo='{screen_no}'. 사용중: {len(self.used_screens)}, 사용가능: {len(self.available_screens)}")
            return screen_no

    def release_screen(self, screen_no: str, identifier: str = None):
        with self.lock:
            released_identifier_from_used = self.used_screens.pop(screen_no, None)
            
            actual_identifier_to_remove_from_map = identifier if identifier else released_identifier_from_used

            if actual_identifier_to_remove_from_map:
                removed_screen_from_map = self.screen_map.pop(actual_identifier_to_remove_from_map, None)
                if removed_screen_from_map and removed_screen_from_map != screen_no:
                    # 비일관성 경고 (identifier로 찾은 screen과 제공된 screen_no가 다름)
                    self.logger.warning(f"[ScreenManager_RELEASE] 불일치 경고: ScreenNo='{screen_no}' 해제 시 Identifier='{actual_identifier_to_remove_from_map}'의 맵된 화면은 '{removed_screen_from_map}'였습니다.")
            
            if released_identifier_from_used is None and identifier is None : # 어떤 정보로도 화면을 찾지 못함
                self.logger.warning(f"[ScreenManager_RELEASE_FAIL] 반환 시도 화면/Identifier 없음 또는 이미 해제됨: ScreenNo='{screen_no}', 제공된 Identifier='{identifier}'")
                return False

            if screen_no not in self.available_screens:
                self.available_screens.append(screen_no)
                # 필요시 정렬: self.available_screens.sort() 하지만 pop(0)과 append 조합이면 순서 유지 불필요할 수도
                self.logger.info(f"[ScreenManager_RELEASE] 화면 반환 완료: ScreenNo='{screen_no}', Identifier='{actual_identifier_to_remove_from_map if actual_identifier_to_remove_from_map else released_identifier_from_used}'. 사용중: {len(self.used_screens)}, 사용가능: {len(self.available_screens)}")
                return True
            else:
                self.logger.warning(f"[ScreenManager_RELEASE] 화면 '{screen_no}'는 이미 사용 가능 목록에 있습니다. (Identifier: '{actual_identifier_to_remove_from_map if actual_identifier_to_remove_from_map else released_identifier_from_used}')")
                return False # 이미 사용 가능한 상태였음

    def get_screen_for_identifier(self, identifier: str) -> Optional[str]:
        with self.lock:
            return self.screen_map.get(identifier)

    def is_screen_used_by_identifier(self, identifier: str, screen_no: str) -> bool:
        with self.lock:
            return self.screen_map.get(identifier) == screen_no and screen_no in self.used_screens

    def cleanup_screens(self):
        """현재 사용 중인 모든 화면을 해제합니다."""
        with self.lock:
            self.logger.info(f"[ScreenManager_CLEANUP] 모든 사용 중인 화면 정리 시작. 현재 사용중: {len(self.used_screens)}개")
            # used_screens의 키 목록 복사 후 반복 (반복 중 수정 방지)
            screens_to_release = list(self.used_screens.keys())
            for screen_no in screens_to_release:
                identifier = self.used_screens.get(screen_no) # 실제 identifier 가져오기
                self.release_screen(screen_no, identifier) 
            
            # 안전장치: 모든 화면을 사용 가능하도록 초기화 (극단적이지만 확실한 정리)
            # self.available_screens = [str(i) for i in range(self.start_screen_no, self.start_screen_no + self.num_screens)]
            # self.screen_map.clear()
            # self.used_screens.clear()
            self.logger.info(f"[ScreenManager_CLEANUP] 모든 화면 정리 완료. 사용중: {len(self.used_screens)}, 사용가능: {len(self.available_screens)}")

    def release_all_managed_screens(self):
        """API를 통해 이 ScreenManager가 관리하고 있는 모든 화면의 연결을 해제하고 내부 상태를 초기화합니다."""
        with self.lock:
            self.logger.info(f"[ScreenManager_RELEASE_ALL] 관리 중인 모든 화면 해제 시작. 현재 사용중: {len(self.used_screens)}개")
            
            if not self.kiwoom_ocx:
                self.logger.warning("[ScreenManager_RELEASE_ALL] Kiwoom OCX 인스턴스가 없어 API 호출(DisconnectRealData)을 스킵합니다. 내부 상태만 초기화합니다.")
            
            screens_to_disconnect_api = list(self.used_screens.keys()) # 현재 사용 중인 화면 번호 목록
            
            for screen_no in screens_to_disconnect_api:
                identifier = self.used_screens.get(screen_no, "N/A")
                if self.kiwoom_ocx:
                    try:
                        # 실제로 API에 화면 연결 해제 요청 (TR/실시간 데이터 수신 중단)
                        self.kiwoom_ocx.dynamicCall("DisconnectRealData(QString)", screen_no)
                        self.logger.info(f"[ScreenManager_RELEASE_ALL] 화면 [{screen_no}] (Identifier: {identifier}) DisconnectRealData API 호출 완료.")
                    except Exception as e:
                        self.logger.error(f"[ScreenManager_RELEASE_ALL] 화면 [{screen_no}] DisconnectRealData API 호출 중 예외 발생: {e}", exc_info=True)
                else:
                    self.logger.debug(f"[ScreenManager_RELEASE_ALL] 화면 [{screen_no}] (Identifier: {identifier}) Kiwoom OCX 없음, API DisconnectRealData 호출 스킵.")
            
            # 내부 관리 상태 전체 초기화
            self.available_screens = [str(i) for i in range(self.start_screen_no, self.start_screen_no + self.num_screens)]
            self.screen_map.clear()  # {identifier: screen_no}
            self.used_screens.clear() # {screen_no: identifier}
            
            self.logger.info(f"[ScreenManager_RELEASE_ALL] 모든 화면 해제 및 내부 상태 초기화 완료. 사용 가능 화면: {len(self.available_screens)}개")

print("util.py: Finished loading util.py module.") # util.py 로딩 완료 