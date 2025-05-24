#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
중복 매수 문제 진단 및 테스트 스크립트
044490 종목 4회 매수 문제 재현 테스트
"""

import sys
import os

# 프로젝트 루트 디렉토리를 Python 경로에 추가
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from strategy import TradingStrategy, TradingState
from config import ConfigManager
from logger import Logger
from database import Database
from util import ScreenManager

def initialize_test_environment():
    """테스트 환경 초기화"""
    print("🔧 테스트 환경 초기화 중...")
    
    # 모듈 초기화
    config_manager = ConfigManager()
    logger = Logger()
    db_manager = Database(config_manager.get_setting("Database", "path", "logs/trading_data.test.db"))
    screen_manager = ScreenManager()
    
    # 개선된 KiwoomAPI Mock 객체
    class MockKiwoomAPI:
        def __init__(self):
            self.account_number = "DRYRUN_ACCOUNT"
            self.order_counter = 1000  # 주문번호 생성용
            
        def send_order(self, rq_name, screen_no, acc_no, order_type, code, quantity, price, hoga_gb, org_order_no):
            """매수/매도 주문 시뮬레이션"""
            order_no = str(self.order_counter)
            self.order_counter += 1
            
            print(f"🔷 [MOCK_ORDER] {order_type} 주문 접수: {code}, 수량: {quantity}, 가격: {price}, 주문번호: {order_no}")
            
            # 항상 체결 시뮬레이션 실행 (Mock 환경)
            import threading
            import time
            
            def simulate_execution():
                time.sleep(0.1)  # 짧은 지연
                # 체결 이벤트 시뮬레이션 (chejan_data 형태)
                chejan_data = {
                    "9001": code,  # 종목코드 (FID 9001)
                    "9203": code,  # 종목코드 (FID 9203)
                    "302": stock_name_map.get(code, f"테스트종목_{code}"),  # 종목명
                    "900": str(quantity),  # 주문수량
                    "901": str(quantity),  # 체결수량
                    "902": "0",      # 미체결수량
                    "910": str(int(price)) if price > 0 else "10100",    # 체결가 (0이면 기본값 사용)
                    "908": order_no, # 주문번호
                    "913": "체결",  # 주문상태 
                    "914": "2" if order_type == 1 else "1"  # 매매구분 (1:매도, 2:매수)
                }
                
                print(f"🎭 [MOCK_EXECUTION] {code} 체결 시뮬레이션: {quantity}주 @ {chejan_data['910']}원")
                
                # TradingStrategy의 체결 처리 함수 호출
                if hasattr(strategy_instance, 'on_chejan_data_received'):
                    strategy_instance.on_chejan_data_received("0", chejan_data)
            
            # 백그라운드에서 체결 시뮬레이션 실행
            threading.Thread(target=simulate_execution, daemon=True).start()
            
            return 0  # 성공
            
        def set_real_reg(self, **kwargs):
            pass
            
        def get_login_info(self, tag):
            """로그인 정보 제공"""
            if tag == "ACCNO":
                return "DRYRUN_ACCOUNT;8101891811;"  # 계좌번호 목록
            elif tag == "USER_ID":
                return "TESTUSER"
            return ""
            
        def get_code_market_info(self, code):
            """코드 시장 정보 반환 (Mock)"""
            return code, "KRX"  # 기본적으로 KRX 시장으로 반환
    
    # 종목명 매핑 (체결 시뮬레이션용)
    global stock_name_map, strategy_instance
    stock_name_map = {}
    
    mock_kiwoom = MockKiwoomAPI()
    
    # TradingStrategy 초기화
    strategy = TradingStrategy(mock_kiwoom, config_manager, logger, db_manager, screen_manager)
    strategy_instance = strategy  # 전역 참조용
    
    # Mock 모드 설정 - dry_run_mode를 False로 설정하여 MockKiwoomAPI가 작동하도록 함
    strategy.settings.dry_run_mode = False  # 중요: Mock 환경에서는 False로 설정
    
    # 🔧 Mock 계좌 정보 설정 (주문가능금액 충분히 설정)
    strategy.account_state.account_number = "DRYRUN_ACCOUNT"
    strategy.account_state.account_summary = {
        "주문가능금액": 10000000,  # 1천만원
        "총평가금액": 10000000,
        "총매입금액": 0,
        "총평가손익금액": 0,
        "총수익률": 0.0,
        "추정예탁자산": 10000000
    }
    
    # 계좌 초기화 완료 시그널 발생
    strategy.account_state.account_number = "DRYRUN_ACCOUNT"
    
    return strategy, config_manager, logger, db_manager

def test_scenario_1_normal_case():
    """시나리오 1: 정상 케이스 - 1차 방어선 작동 확인"""
    print("\n" + "="*60)
    print("🧪 시나리오 1: 정상 케이스 테스트")
    print("="*60)
    
    strategy, _, _, _ = initialize_test_environment()
    
    # 044490 종목으로 테스트 (실제 문제 발생 종목)
    test_params = {
        "code": "044490",
        "stock_name": "테스트종목_044490",
        "yesterday_close_price": 10000,
        "test_current_price": 9800,  # 전일종가 하회 → 매수 조건 충족
        "initial_portfolio": {},  # 빈 포트폴리오로 시작
        "stock_tracking_data_override": {
            "strategy_state": "WAITING",
            "buy_completion_count": 0,
            "is_yesterday_close_broken_today": False
        }
    }
    
    print("📋 테스트 조건:")
    print(f"   - 종목: {test_params['code']} ({test_params['stock_name']})")
    print(f"   - 전일종가: {test_params['yesterday_close_price']:,}원")
    print(f"   - 현재가: {test_params['test_current_price']:,}원")
    print(f"   - 초기 포트폴리오: 빈 상태")
    print(f"   - 초기 상태: WAITING")
    print(f"   - buy_completion_count: 0")
    
    # 첫 번째 테스트 실행 - 전일종가 하회
    print("\n📉 1단계: 전일종가 하회 (9800원)...")
    strategy.run_dry_run_test_scenario("정상_케이스_1단계_하회", test_params)
    
    # 상태 확인
    stock_info = strategy.watchlist.get("044490")
    if stock_info:
        print(f"   - is_yesterday_close_broken_today: {stock_info.is_yesterday_close_broken_today}")
        print(f"   - strategy_state: {stock_info.strategy_state.name}")
    
    # 두 번째 테스트 실행 - 전일종가 재돌파 (매수 실행!)
    print("\n📈 2단계: 전일종가 재돌파 (10100원) - 매수 실행!")
    test_params["test_current_price"] = 10100  # 전일종가 이상으로 회복
    strategy.run_dry_run_test_scenario("정상_케이스_2단계_재돌파", test_params)
    
    # 상태 확인
    if stock_info:
        print(f"\n📊 매수 후 상태:")
        print(f"   - strategy_state: {stock_info.strategy_state.name}")
        print(f"   - buy_completion_count: {stock_info.buy_completion_count}")
        print(f"   - total_buy_quantity: {stock_info.total_buy_quantity}")
        print(f"   - 포트폴리오 보유량: {strategy.account_state.portfolio.get('044490', {}).get('보유수량', 0)}")
    
    # 세 번째 테스트 실행 - 추가 재돌파 시도 (중복 매수 테스트)
    print("\n🔄 3단계: 추가 재돌파 시도 (10200원) - 중복 매수 방지 확인")
    test_params["test_current_price"] = 10200  # 더 상승한 상황
    strategy.run_dry_run_test_scenario("정상_케이스_3단계_중복방지", test_params)
    
    return strategy

def test_scenario_2_problem_case():
    """시나리오 2: 문제 케이스 - 중복 매수 재현 시도"""
    print("\n" + "="*60)
    print("🚨 시나리오 2: 문제 케이스 테스트 (중복 매수 재현)")
    print("="*60)
    
    strategy, _, _, _ = initialize_test_environment()
    
    print("📋 문제 상황 시뮬레이션:")
    print(f"   - 시나리오: 044490 종목 4회 연속 매수 재현")
    print(f"   - 방법: 매수 후 상태 초기화하여 중복 매수 발생시키기")
    
    # 1차 매수
    print("\n🔥 1차 매수...")
    test_params = {
        "code": "044490",
        "stock_name": "문제종목_044490",
        "yesterday_close_price": 10000,
        "test_current_price": 9800,  # 하회
        "initial_portfolio": {},
        "stock_tracking_data_override": {
            "strategy_state": "WAITING",
            "buy_completion_count": 0,
            "is_yesterday_close_broken_today": False
        }
    }
    
    # 1단계: 전일종가 하회
    strategy.run_dry_run_test_scenario("문제_케이스_1차_하회", test_params)
    
    # 2단계: 재돌파 매수
    test_params["test_current_price"] = 10100
    strategy.run_dry_run_test_scenario("문제_케이스_1차_매수", test_params)
    
    stock_info = strategy.watchlist.get("044490")
    if stock_info:
        print(f"   ✅ 1차 매수 완료: buy_completion_count={stock_info.buy_completion_count}")
    
    # 2차~4차 매수 (문제 상황 시뮬레이션)
    for i in range(2, 5):
        print(f"\n🔥 {i}차 매수...")
        
        # 문제 상황: 포트폴리오가 업데이트되지 않은 상태로 시뮬레이션
        test_params = {
            "code": "044490",
            "stock_name": "문제종목_044490",
            "yesterday_close_price": 10000,
            "test_current_price": 9800 - (i * 20),  # 더 하락
            "initial_portfolio": {},  # 여전히 빈 포트폴리오 (동기화 문제)
            "stock_tracking_data_override": {
                "strategy_state": "WAITING",  # 잘못된 상태 (본래는 BOUGHT여야 함)
                "buy_completion_count": 0,    # 잘못된 카운트 (본래는 1이상이어야 함)
                "is_yesterday_close_broken_today": False
            }
        }
        
        # 하회 → 재돌파 시뮬레이션
        strategy.run_dry_run_test_scenario(f"문제_케이스_{i}차_하회", test_params)
        test_params["test_current_price"] = 10100 + (i * 50)  # 재돌파
        strategy.run_dry_run_test_scenario(f"문제_케이스_{i}차_매수", test_params)
        
        if stock_info:
            print(f"   📊 {i}차 매수 후: buy_completion_count={stock_info.buy_completion_count}")
    
    return strategy

def test_scenario_3_edge_cases():
    """시나리오 3: 엣지 케이스 테스트"""
    print("\n" + "="*60)
    print("🔬 시나리오 3: 엣지 케이스 테스트")
    print("="*60)
    
    strategy, _, _, _ = initialize_test_environment()
    
    # 3회 매수 완료 후 4회차 시도 (2차 방어선 테스트)
    test_params = {
        "code": "044490",
        "stock_name": "엣지케이스_044490",
        "yesterday_close_price": 10000,
        "test_current_price": 9800,
        "initial_portfolio": {},
        "stock_tracking_data_override": {
            "strategy_state": "WAITING",
            "buy_completion_count": 3,  # 이미 3회 매수 완료
            "is_yesterday_close_broken_today": False
        }
    }
    
    print("📋 엣지 케이스 조건:")
    print(f"   - buy_completion_count: 3 (최대치)")
    print(f"   - max_buy_attempts_per_stock: 3")
    print(f"   - 예상 결과: 2차 방어선에서 차단")
    
    print("\n🛡️ 2차 방어선 테스트...")
    strategy.run_dry_run_test_scenario("엣지케이스_2차방어선", test_params)
    
    stock_info = strategy.watchlist.get("044490")
    if stock_info:
        print(f"\n📊 2차 방어선 테스트 결과:")
        print(f"   - strategy_state: {stock_info.strategy_state.name}")
        print(f"   - buy_completion_count: {stock_info.buy_completion_count}")
        expected_state = "COMPLETE" if stock_info.buy_completion_count >= 3 else "기타"
        print(f"   - 예상 상태: {expected_state}")
    
    return strategy

def test_scenario_duplicate_buy_reproduction():
    """핵심 시나리오: 중복 매수 문제 재현 테스트"""
    print("\n" + "="*60)
    print("🔥 핵심 시나리오: 중복 매수 문제 재현 테스트")
    print("="*60)
    
    strategy, _, _, _ = initialize_test_environment()
    
    # 044490 종목으로 테스트 (실제 문제 발생 종목)
    test_code = "044490"
    
    # 종목명 등록
    global stock_name_map
    stock_name_map[test_code] = "테스트종목_044490"
    
    print("📋 테스트 조건:")
    print(f"   - 종목: {test_code}")
    print(f"   - 시나리오: 매수 완료 후 중복 매수 조건 재충족")
    print(f"   - 목표: 중복 매수 방지 확인")
    
    # 종목 추가 및 초기 상태 설정
    strategy.add_to_watchlist(test_code, "테스트종목_044490", 10000)
    
    import time
    time.sleep(0.1)  # 초기화 대기
    
    # Step 1: 첫 번째 매수 시뮬레이션
    print("\n🔹 Step 1: 첫 번째 매수 시뮬레이션")
    
    # 전일종가 하회 후 재돌파 상황 시뮬레이션
    strategy.watchlist[test_code].yesterday_close_price = 10000
    strategy.watchlist[test_code].strategy_state = TradingState.WAITING
    strategy.watchlist[test_code].buy_completion_count = 0
    strategy.watchlist[test_code].is_yesterday_close_broken_today = False
    
    # 포트폴리오 비우기 (첫 매수 허용)
    strategy.account_state.portfolio = {}
    
    print(f"   - 전일종가: {strategy.watchlist[test_code].yesterday_close_price}원")
    print(f"   - 포트폴리오 상태: {strategy.account_state.portfolio}")
    print(f"   - 매수 완료 횟수: {strategy.watchlist[test_code].buy_completion_count}")
    
    # 첫 번째 전일종가 하회 시뮬레이션 (9,800원)
    print(f"   📉 전일종가 하회 ({9800:,}원)")
    strategy.process_strategy(test_code)
    
    time.sleep(0.1)
    
    # 첫 번째 전일종가 재돌파 시뮬레이션 (10,100원) - 매수 실행됨
    print(f"   📈 전일종가 재돌파 ({10100:,}원)")
    
    # 현재가 업데이트 (전일종가 이상으로 회복)
    strategy.watchlist[test_code].current_price = 10100
    strategy.process_strategy(test_code)
    
    time.sleep(0.5)  # 체결 시뮬레이션 대기
    
    # 첫 번째 매수 후 상태 확인
    print(f"\n   📊 첫 번째 매수 후 상태:")
    print(f"   - 상태 플래그: {strategy.watchlist[test_code].strategy_state}")
    print(f"   - 매수 완료 횟수: {strategy.watchlist[test_code].buy_completion_count}")
    print(f"   - 포트폴리오: {strategy.account_state.portfolio}")
    print(f"   - 전일종가 돌파 플래그: {strategy.watchlist[test_code].is_yesterday_close_broken_today}")
    
    # Step 2: 전일종가 재돌파 매수 실행
    print(f"\n🔹 Step 2: 전일종가 재돌파 매수 실행")
    print(f"   📈 전일종가 재돌파 ({10100:,}원)")
    
    # 현재가 업데이트 (전일종가 이상으로 회복)
    strategy.watchlist[test_code].current_price = 10100
    strategy.process_strategy(test_code)
    
    time.sleep(0.5)  # 체결 시뮬레이션 대기
    
    # 첫 번째 매수 후 상태 확인
    print(f"\n   📊 첫 번째 매수 후 상태:")
    print(f"   - 상태 플래그: {strategy.watchlist[test_code].strategy_state}")
    print(f"   - 매수 완료 횟수: {strategy.watchlist[test_code].buy_completion_count}")
    print(f"   - 포트폴리오: {strategy.account_state.portfolio}")
    
    # Step 3: 결과 분석
    print("\n🔹 Step 3: 중복 매수 방지 결과 분석")
    
    portfolio_quantity = 0
    if test_code in strategy.account_state.portfolio:
        portfolio_quantity = strategy.account_state.portfolio[test_code].get('보유수량', 0)
    
    buy_count = strategy.watchlist[test_code].buy_completion_count
    
    print(f"   - 실제 보유 수량: {portfolio_quantity}주")
    print(f"   - 매수 완료 횟수: {buy_count}회")
    
    if buy_count == 1 and portfolio_quantity > 0:
        print("   ✅ 중복 매수 방지 성공!")
        return True
    elif buy_count > 1:
        print(f"   ❌ 중복 매수 발생! {buy_count}회 매수됨")
        return False
    else:
        print("   ⚠️  매수가 전혀 실행되지 않음")
        return False

def main():
    """메인 테스트 실행"""
    print("🎯 중복 매수 문제 진단 테스트 시작")
    print("="*60)
    print("목표: 044490 종목 4회 매수 문제 재현 및 방어선 검증")
    print("="*60)
    
    try:
        # 시나리오 1: 정상 케이스
        strategy1 = test_scenario_1_normal_case()
        
        # 시나리오 2: 문제 케이스
        strategy2 = test_scenario_2_problem_case()
        
        # 시나리오 3: 엣지 케이스  
        strategy3 = test_scenario_3_edge_cases()
        
        # 시나리오 4: 중복 매수 재현 테스트
        strategy4 = test_scenario_duplicate_buy_reproduction()
        
        print("\n" + "="*60)
        print("📋 테스트 완료 - 결과 요약")
        print("="*60)
        print("✅ 시나리오 1: 정상 케이스 완료")
        print("✅ 시나리오 2: 문제 케이스 완료")
        print("✅ 시나리오 3: 엣지 케이스 완료")
        print("✅ 시나리오 4: 중복 매수 재현 테스트 완료")
        print("\n📊 로그를 확인하여 각 방어선의 작동 상태를 분석하세요.")
        print("📁 로그 위치: logs/app.log")
        
    except Exception as e:
        print(f"❌ 테스트 실행 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main() 