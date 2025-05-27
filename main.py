#!/usr/bin/env python
# -*- coding: utf-8 -*-
print("DEBUG: main.py 실행 시작")

import sys
import os
import time
from PyQt5.QtWidgets import QApplication, QMessageBox # QSplashScreen 제거
print(f"DEBUG: QApplication imported: {QApplication}") # 디버깅 로그 추가
from PyQt5.QtCore import QTimer # Qt 제거, QTimer는 KiwoomAPI 등에서 사용 가능성 있어 유지
from kiwoom_api import KiwoomAPI
from config import ConfigManager
from strategy import TradingStrategy
from logger import Logger
from database import Database
import signal # signal 모듈 임포트
import logging # 로깅 수준 설정을 위해 추가
from util import ScreenManager # ScreenManager 임포트 추가

# exit_flag = False # 종료 플래그 전역 변수 (제거됨)
def check_api_installed(logger_instance): # logger 인스턴스 추가
    """
    키움 OpenAPI+ 설치 여부 확인
    
    Returns:
        bool: 설치 여부
    """
    try:
        from PyQt5.QAxContainer import QAxWidget
        api = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")
        return True
    except Exception as e:
        if logger_instance:
            logger_instance.critical(f"키움 OpenAPI+ 컴포넌트 로드 실패: {e}")
        else:
            print(f"CRITICAL: 키움 OpenAPI+ 컴포넌트 로드 실패: {e}")
        return False

def create_directories():
    """
    필요한 디렉토리 생성
    """
    # 로그 디렉토리
    # os.makedirs("logs", exist_ok=True) # Logger가 자체적으로 처리하므로 제거
    
    # 데이터 디렉토리
    os.makedirs("data", exist_ok=True)


def main():
    """
    프로그램 메인 진입점
    """
    from functools import partial # partial 임포트를 main 함수 시작 부분으로 이동

    # QApplication 인스턴스 생성
    app = QApplication(sys.argv)
    print("DEBUG: QApplication 인스턴스 생성 완료")
    
    # 디렉토리 생성 (로그 디렉토리 생성은 Logger 내부로 이동)
    create_directories()
    
    # 설정 관리자 초기화 (Logger보다 먼저, Logger가 설정을 사용할 수 있도록)
    config = ConfigManager(config_file="settings.json") # config_file 인자 유지
    print("DEBUG: ConfigManager 객체 생성 완료")
    # load_settings()는 ConfigManager 생성자에서 호출되므로 여기서 중복 호출 안함
    # logger.info("Using settings file: settings.json") # Logger 생성 전이므로 여기서는 로깅 불가

    # 로거 초기화 (설정값을 사용)
    log_level_str = config.get_setting("Logging", "level", "INFO")
    log_level_numeric = getattr(logging, log_level_str.upper(), logging.INFO)
    log_max_bytes = config.get_setting("Logging", "max_bytes", 10*1024*1024)
    log_backup_count = config.get_setting("Logging", "backup_count", 5)
    # log_file_path = config.get_setting("Logging", "file_path", "logs/app.log") # Logger의 기본값 사용
    logger = Logger(log_level=log_level_numeric, max_bytes=log_max_bytes, backup_count=log_backup_count)
    print("DEBUG: Logger 객체 생성 완료")
    
    logger.info(f"Using settings file: {config.config_file}") # Logger 생성 후 설정 파일 정보 로깅
    logger.info("프로그램 시작 (콘솔 모드)")

    # ScreenManager 단일 인스턴스 생성
    screen_manager_instance = ScreenManager(logger=logger)
    print("DEBUG: ScreenManager 객체 생성 완료")
    logger.info("ScreenManager 단일 인스턴스 생성 완료")
    
    # 키움 API 설치 확인
    print("DEBUG: Kiwoom OpenAPI 설치 여부 확인 시작...")
    if not check_api_installed(logger):
        logger.critical("키움 OpenAPI+가 설치되어 있지 않습니다. 프로그램을 종료합니다.")
        sys.exit(1)
    
    # 설정 관리자 초기화 (이 부분은 이미 위에서 수행되었으므로 주석 처리 또는 제거 검토. 현재는 유지)
    logger.info("Using settings file: settings.json")
    config.load_settings() # config 객체는 이미 load_settings()를 생성자에서 호출했을 수 있음. 중복 호출 가능성.
    
    # 데이터베이스 초기화
    db_path_from_config = config.get_setting("Database", "path", "auto_trader.db") 
    db_logs_dir = os.path.dirname(db_path_from_config)
    if db_logs_dir and not os.path.exists(db_logs_dir):
        os.makedirs(db_logs_dir, exist_ok=True)
        logger.info(f"DB 경로용 디렉토리 생성: {db_logs_dir}")

    db = Database(db_file=db_path_from_config, logger=logger)
    print("DEBUG: Database 객체 생성 완료")
    logger.info("데이터베이스 초기화 완료")

    # 매매 전략 초기화 (KiwoomAPI보다 먼저, screen_manager 주입)
    # KiwoomAPI 인스턴스 생성 전 strategy를 None으로 초기화하고, kiwoom_api 인자 전달은 나중에 합니다.
    strategy = TradingStrategy(kiwoom_api=None, config_manager=config, logger=logger, db_manager=db, screen_manager=screen_manager_instance)
    print("DEBUG: TradingStrategy 객체 생성 완료 (KiwoomAPI 주입 전)")
    logger.info("매매 전략 초기화 (KiwoomAPI 주입 전, ScreenManager 주입 완료)")

    # KiwoomAPI 초기화 (strategy_instance 및 screen_manager 주입)
    kiwoom = KiwoomAPI(logger=logger, config_manager=config, strategy_instance=strategy, screen_manager=screen_manager_instance)
    print("DEBUG: KiwoomAPI 객체 생성 완료")
    
    # Strategy 객체에 KiwoomAPI 인스턴스 주입
    strategy.modules.kiwoom_api = kiwoom # kiwoom_api -> modules.kiwoom_api 로 변경
    logger.info("KiwoomAPI 초기화 및 Strategy에 주입 완료")

    # 로그인
    print("DEBUG: KiwoomAPI 로그인 시도...")
    logger.info("키움 API 로그인 시도")
    if not kiwoom.login():
        logger.critical("키움 API 로그인 실패. 프로그램을 종료합니다.")
        sys.exit(1)
    
    logger.info("키움 API 로그인 성공")
    logger.info("매매 전략 최종 초기화 완료")

    # Ctrl+C (SIGINT) 핸들러 설정
    # functools.partial을 사용하여 핸들러에 필요한 객체들을 전달합니다.
    # app 객체도 전달하여 Qt 이벤트 루프를 안전하게 종료할 수 있도록 합니다.
    # custom_signal_handler = partial(enhanced_signal_handler, # 이전에 partial을 여기서 사용
    #                               kiwoom_instance=kiwoom, 
    #                               strategy_instance=strategy, 
    #                               logger_instance=logger, 
    #                               db_instance=db,
    #                               q_application_instance=app) # app 인스턴스 추가
    # signal.signal(signal.SIGINT, custom_signal_handler)
    # logger.info("Ctrl+C (SIGINT) 핸들러가 설정되었습니다. 프로그램을 종료하려면 Ctrl+C를 누르세요.")


    # (logger, kiwoom, strategy, db, app 객체들이 생성된 후 이 위치에 삽입)
    # from functools import partial # 기존 위치 주석 처리
    import asyncio # 비동기 처리를 위해 추가
    import time # time.sleep 및 시간 측정용

    # 향상된 signal_handler 정의
    def enhanced_signal_handler(signal_num, frame):
        """향상된 시그널 핸들러: 주요 리소스 정리 및 앱 종료 시퀀스"""
        nonlocal logger  # logger 변수 참조
        try:
            # 외부 함수(main)의 변수에 접근하기 위해 nonlocal 사용
            nonlocal app, kiwoom, db, strategy
            logger.info(f"[SIG_HANDLER] 시그널 {signal_num} 수신. 정상 종료 시퀀스 시작.")
            
            # 매매 전략 중지
            if strategy:
                try:
                    logger.info("[SIG_HANDLER] 매매 전략 중지 시작...")
                    strategy.stop()  # 정확한 stop 메서드 호출 확인
                    logger.info("[SIG_HANDLER] 매매 전략 중지 완료.")
                except Exception as e:
                    logger.error(f"[SIG_HANDLER] 매매 전략 중지 중 오류: {e}", exc_info=True)
            
            # API 연결 종료
            if kiwoom:
                try:
                    logger.info("[SIG_HANDLER] KiwoomAPI 리소스 해제 및 연결 종료 시작...")
                    kiwoom.disconnect_api()
                    logger.info("[SIG_HANDLER] KiwoomAPI disconnect_api 호출 완료 (실제 종료는 비동기적일 수 있음).")
                except Exception as e:
                    logger.error(f"[SIG_HANDLER] KiwoomAPI 연결 종료 중 오류: {e}", exc_info=True)
            
            # DB 연결 종료
            if db:
                try:
                    db.close()
                    logger.info("[SIG_HANDLER] DB 연결 종료 완료.")
                except Exception as e:
                    logger.error(f"[SIG_HANDLER] DB 연결 종료 중 오류: {e}", exc_info=True)
            
            # QApplication 종료
            if app:
                try:
                    logger.info("[SIG_HANDLER] QApplication.quit() 호출...")
                    app.quit()
                    logger.info("[SIG_HANDLER] QApplication.quit() 호출 완료.")
                except Exception as e:
                    logger.error(f"[SIG_HANDLER] QApplication 종료 중 오류: {e}", exc_info=True)
            
            logger.info("[SIG_HANDLER] enhanced_signal_handler 실행 완료. 프로그램이 정상적으로 종료됩니다.")
            
            # 프로세스 강제 종료를 추가 - quit()만으로는 완전히 종료되지 않는 문제 해결
            logger.info("[SIG_HANDLER] 프로세스 강제 종료 진행...")
            os._exit(0)  # 프로세스를 즉시 종료
        except Exception as e:
            logger.critical(f"[SIG_HANDLER] 종료 처리 중 예상치 못한 오류 발생: {e}", exc_info=True)
            # 심각한 오류 발생 시 즉시 종료
            os._exit(1)
        
        # 정상 종료 (여기까지 도달하지 않을 것임)
        # sys.exit(0)

    try:
        # 관심종목 추가 (설정 파일에서 로드 - ConfigManager가 유효성 검사 및 기본값 처리)
        # ConfigManager의 get_setting은 이제 유효성이 검증된 watchlist 객체 리스트를 반환함
        watchlist_items_from_config = config.get_setting("watchlist", [])
        
        if watchlist_items_from_config:
            logger.info(f"설정 파일에서 {len(watchlist_items_from_config)}개의 관심종목 로드 및 전략에 추가 시작...")
            for i, item in enumerate(watchlist_items_from_config):
                code = item.get("code")
                name = item.get("name", "")
                yesterday_close = item.get("yesterday_close_price", 0.0) # 기본값을 float으로 변경
                logger.debug(f"[MAIN_WATCHLIST_ADD] 항목 {i+1}: 코드({code}), 이름({name}), 전일종가({yesterday_close})")
                if code:
                    strategy.add_to_watchlist(code, name, yesterday_close_price=yesterday_close)
                else:
                    logger.warning(f"설정 파일의 {i+1}번째 관심종목 항목에 코드가 없습니다: {item}")
            logger.info(f"{len(strategy.watchlist)}개의 관심종목이 전략에 추가되었습니다.")
        else:
            logger.warning("설정 파일에 관심종목이 없거나 로드에 실패했습니다. TradingStrategy.watchlist가 비어있을 수 있습니다.")

        # 매매 전략 시작
        print("DEBUG: TradingStrategy 시작 시도...")
        strategy.start()
        logger.info("매매 전략 시작됨. Ctrl+C로 종료하세요.")

        # 이벤트 루프 실행
        print("DEBUG: QApplication 이벤트 루프 시작...")
        # SIGINT 핸들러는 이벤트 루프 시작 전에 설정되어야 합니다.
        # enhanced_signal_handler가 이 시점에 정의되어 있으므로 여기서 설정합니다.
        signal.signal(signal.SIGINT, enhanced_signal_handler)
        logger.info("Ctrl+C (SIGINT) 핸들러 최종 설정 완료. 이벤트 루프 시작 직전.")

        sys.exit(app.exec_())

    except Exception as e:
        logger.critical(f"메인 루프에서 예외 발생: {e}", exc_info=True)
        if strategy:
            strategy.stop()
        sys.exit(1)
    finally:
        # 정상 종료 시 signal_handler에서 이미 호출되었을 수 있지만, 만약을 위해 추가
        logger.info("프로그램 최종 정리 작업 수행...")
        if strategy and strategy.is_running: # strategy가 실행 중일 때만 stop 호출
            strategy.stop()
        logger.info("프로그램이 종료됩니다.")
        # 강제 종료 추가 - 종료되지 않는 문제 해결
        print("[MAIN] 프로세스 강제 종료 진행...")
        os._exit(0)

if __name__ == "__main__":
    main()