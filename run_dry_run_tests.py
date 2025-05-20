#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
from PyQt5.QtWidgets import QApplication

# 필요한 모듈 임포트 (실제 경로에 맞게 조정 필요)
from kiwoom_api import KiwoomAPI
from strategy import TradingStrategy
from config import ConfigManager
from logger import Logger
from database import Database
from util import ScreenManager # ScreenManager 추가

def main():
    app = QApplication(sys.argv)
    print("드라이런 테스트 스크립트 시작...")

    # 1. 모듈 초기화
    logger = Logger(log_file='logs/dry_run_test.log', log_level='DEBUG')
    logger.info("Logger 초기화 완료.")

    config_manager = ConfigManager(logger=logger, config_file='settings.json')
    logger.info("ConfigManager 초기화 완료.")

    # 드라이런 모드 확인
    is_dry_run = config_manager.get_setting("매매전략", "dry_run_mode", False)
    if not is_dry_run:
        logger.error("테스트 오류: 드라이런 테스트는 settings.json에서 'dry_run_mode': true 로 설정해야 합니다.")
        print("오류: settings.json에서 'dry_run_mode': true 로 설정하고 다시 실행해주세요.")
        return
    logger.info(f"드라이런 모드 활성화 확인됨: {is_dry_run}")

    db_path = config_manager.get_setting("Database", "path", "logs/trading_data.db")
    db_manager = Database(logger=logger, db_file=db_path)
    logger.info(f"DatabaseManager 초기화 완료 (DB 경로: {db_path})")

    # ScreenManager 초기화 시 kiwoom_ocx는 KiwoomAPI 내부에서 생성되므로 None으로 전달 가능
    # 또는 KiwoomAPI 생성 후 전달. 여기서는 KiwoomAPI가 내부적으로 ScreenManager를 관리하도록 함.
    screen_manager = ScreenManager(logger=logger)
    logger.info("ScreenManager 초기화 완료.")

    kiwoom_api = KiwoomAPI(logger=logger, config_manager=config_manager, screen_manager=screen_manager)
    logger.info("KiwoomAPI 초기화 시작됨.")

    strategy = TradingStrategy(
        kiwoom_api=kiwoom_api,
        config_manager=config_manager,
        logger=logger,
        db_manager=db_manager,
        screen_manager=screen_manager # Strategy에도 ScreenManager 전달
    )
    logger.info("TradingStrategy 초기화 완료.")

    # KiwoomAPI에 strategy_instance 연결 (KiwoomAPI가 Strategy의 콜백을 호출하기 위함)
    kiwoom_api.strategy_instance = strategy
    logger.info("KiwoomAPI에 Strategy 인스턴스 연결 완료.")

    # 2. 가상 로그인 시도 (드라이런 모드이므로 실제 API 호출 없음)
    if not kiwoom_api.login():
        logger.error("드라이런 가상 로그인 실패.")
        return
    logger.info(f"드라이런 가상 로그인 성공. 계좌번호: {kiwoom_api.account_number}")

    # _on_login_completed 콜백이 strategy의 초기화를 진행할 시간을 약간 줌 (QTimer.singleShot 때문)
    # QApplication.processEvents() # 이벤트 루프를 돌려 QTimer.singleShot 실행 유도
    # time.sleep(0.5) # 또는 잠시 대기
    # 위와 같은 명시적 대기보다는, strategy의 초기화 완료 상태를 확인하는 것이 더 좋음.
    # 현재 run_dry_run_test_scenario 내부에서 초기화 상태를 강제로 설정하므로 추가 대기 불필요.

    # 3. 테스트 시나리오 정의 및 실행
    logger.info("테스트 시나리오 실행 준비...")

    # 시나리오 1: 손절매 테스트 (전일 종가 기준)
    # 조건: 전일 종가 70,000원, 손절률 2% (손절가 68,600원)
    # 보유 상황: 005930 (삼성전자) 10주, 평균 매입가 71,000원
    # 테스트 현재가: 68,000원 (손절 조건 충족)
    scenario1_params = {
        "code": "005930",
        "stock_name": "삼성전자(DryRun)",
        "yesterday_close_price": 70000.0,
        "initial_portfolio": {
            "stock_name": "삼성전자(DryRun)",
            "보유수량": 10,
            "매입가": 71000.0,
            "현재가": 71000.0, # 초기 현재가는 매입가와 동일하게 설정 가능
            "평가금액": 710000.0,
            "매입금액": 710000.0,
            "평가손익": 0,
            "수익률": 0.0
        },
        "test_current_price": 68000.0,
        "stock_tracking_data_override": { # BOUGHT 상태 및 관련 정보 설정
            "strategy_state": "BOUGHT",
            "avg_buy_price": 71000.0,      # initial_portfolio와 일치
            "total_buy_quantity": 10,    # initial_portfolio와 일치
            "current_high_price_after_buy": 71000.0, # 초기엔 매입가
            "buy_timestamp_str": "now-10m" # 10분 전에 매수했다고 가정
        }
    }
    strategy.run_dry_run_test_scenario("손절매_시나리오1(전일종가기준)", scenario1_params)

    # 시나리오 2: 부분 익절 테스트
    # 조건: 부분 익절률 5% (settings.json 기본값), 매입가 50,000원, 부분 익절 목표가 52,500원
    # 보유 상황: 035720 (카카오) 20주, 평균 매입가 50,000원
    # 테스트 현재가: 53,000원 (부분 익절 조건 충족)
    scenario2_params = {
        "code": "035720",
        "stock_name": "카카오(DryRun)",
        "yesterday_close_price": 49000.0, # 참고용 전일 종가
        "initial_portfolio": {
            "stock_name": "카카오(DryRun)",
            "보유수량": 20,
            "매입가": 50000.0,
            "현재가": 50000.0,
            "평가금액": 1000000.0,
            "매입금액": 1000000.0,
            "평가손익": 0,
            "수익률": 0.0
        },
        "test_current_price": 53000.0,
        "stock_tracking_data_override": {
            "strategy_state": "BOUGHT",
            "avg_buy_price": 50000.0,
            "total_buy_quantity": 20,
            "current_high_price_after_buy": 50000.0,
            "buy_timestamp_str": "now-30m" # 30분 전에 매수했다고 가정
        }
    }
    strategy.run_dry_run_test_scenario("부분익절_시나리오2", scenario2_params)

    # 시나리오 3: 트레일링 스탑 활성화 및 첫 번째 발동 테스트
    # 조건: 트레일링 활성화 수익률 2% (settings.json), 트레일링 하락률 1.8% (settings.json)
    # 매입가: 100,000원. 트레일링 활성화 가격: 102,000원.
    # 활성화 후 고점: 105,000원 도달. 트레일링 스탑 발동 가격: 105,000 * (1 - 0.018) = 103,110원
    # 보유 상황: 105560 (AP시스템) 5주, 평균 매입가 100,000원
    # 테스트 현재가: 103,000원 (트레일링 스탑 첫 발동 조건 충족)
    scenario3_params = {
        "code": "105560", 
        "stock_name": "AP시스템(DryRun)",
        "yesterday_close_price": 98000.0, 
        "initial_portfolio": {
            "stock_name": "AP시스템(DryRun)",
            "보유수량": 5,
            "매입가": 100000.0,
            "현재가": 100000.0,
            "평가금액": 500000.0,
            "매입금액": 500000.0,
            "평가손익": 0,
            "수익률": 0.0
        },
        "test_current_price": 103000.0, # 이 가격에서 트레일링 스탑 발동 예상
        "stock_tracking_data_override": {
            "strategy_state": "BOUGHT",
            "avg_buy_price": 100000.0,
            "total_buy_quantity": 5,
            "is_trailing_stop_active": True, # 테스트를 위해 강제 활성화 (원래는 수익률 도달 시 자동 활성화)
            "current_high_price_after_buy": 105000.0, # 트레일링 스탑 발동 계산을 위한 고점 설정
            "buy_timestamp_str": "now-1h" # 1시간 전에 매수했다고 가정
        }
    }
    strategy.run_dry_run_test_scenario("트레일링스탑_첫발동_시나리오3", scenario3_params)

    logger.info("모든 드라이런 테스트 시나리오 실행 완료.")
    print("드라이런 테스트 스크립트 종료. 상세 내용은 logs/dry_run_test.log 파일을 확인하세요.")

    # QApplication 이벤트 루프가 필요하다면 유지, 필요 없다면 제거 또는 sys.exit(app.exec_()) 대신 app.quit() 사용
    # 여기서는 테스트 스크립트이므로 명시적으로 종료
    # sys.exit(app.exec_()) # GUI가 없으므로 exec_()는 필요 없을 수 있음
    app.quit()

if __name__ == "__main__":
    main()
