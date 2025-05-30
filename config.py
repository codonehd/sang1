#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import json

# 기본 설정
DEFAULT_SETTINGS = {
    "계좌정보": {
        "계좌번호": "0000000000", 
        "비밀번호": "",
        "account_type": "실거래"  # <--- 이 줄 추가 (기본값은 "실거래" 또는 "모의투자" 중 선택)
    },
    "매수금액": 1000000, 
    "매매전략": {
        "익절_수익률": 5.0,      
        "익절_매도비율": 50.0,
        "트레일링_하락률": 2.0, 
        "손절_손실률": 3.0,      
        "종목당_최대시도횟수": 3,  # 종목당 최대 매수 시도 횟수 추가
        "MarketOpenTime": "09:00:00",
        "MarketCloseTime": "15:30:00",
        "dry_run_mode": False
    },
    "watchlist": [], # 변경: "매매대상종목" -> "watchlist", 객체 리스트를 위한 빈 리스트
    "Database": {
        "path": "logs/trading_data.test.db"
    },
    "Logging": {
        "level": "INFO",
        "max_bytes": 10485760,
        "backup_count": 5
    },
    "API_Limit": {
        "tr_request_interval_ms": 210 
    }, # 기존 API_Limit 섹션 쉼표 확인
    "fee_tax_rates": {
        "실거래": {
            "buy_fee_rate": 0.00015,  # 0.015%
            "sell_fee_rate": 0.00015, # 0.015%
            "sell_tax_rate": 0.0025   # 0.25% (코스피/코스닥 통합으로 가정)
        },
        "모의투자": {
            "buy_fee_rate": 0.0035,   # 0.35%
            "sell_fee_rate": 0.0035,  # 0.35%
            "sell_tax_rate": 0.0020   # 0.20%
        }
    },
    "AutoTrading": {
        "start_automatically": False
    },
    "PeriodicStatusReport": {
        "enabled": True,
        "interval_seconds": 60
    },
    "PeriodicPortfolioCheck": { # 새로운 섹션 추가
        "interval_seconds": 60 
    }
}

class ConfigManager:
    """
    프로그램 설정을 관리하는 클래스
    """
    def __init__(self, config_file="settings.json", logger=None):
        """
        ConfigManager 초기화
        
        Args:
            config_file (str): 설정 파일 경로
            logger: 로깅을 위한 로거 객체
        """
        self.config_file = config_file
        self.logger = logger
        self.settings = {} # 초기화 후 _validate_settings에서 DEFAULT_SETTINGS 기반으로 채워짐

        if not os.path.exists(self.config_file):
            self._log_message(f"설정 파일({self.config_file})이 존재하지 않아 기본 설정으로 새로 생성합니다.", "INFO")
            self.settings = DEFAULT_SETTINGS.copy() # 존재하지 않으면 기본 설정 사용
            self._validate_settings() # 기본 설정에 대해서도 유효성 검사
            self.save_settings()
        else:
            self.load_settings() # 파일이 존재하면 로드 (내부에서 _validate_settings 호출)
            # load_settings 실패 시 self.settings가 DEFAULT_SETTINGS.copy()로 설정되고 validate됨

    def _log_message(self, message, level="INFO"):
        if self.logger:
            if level == "DEBUG": self.logger.debug(message)
            elif level == "INFO": self.logger.info(message)
            elif level == "WARNING": self.logger.warning(message)
            elif level == "ERROR": self.logger.error(message)
            elif level == "CRITICAL": self.logger.critical(message)
            else: self.logger.info(message)
        else:
            print(f"[{level}][ConfigManager] {message}")

    def _validate_settings(self):
        """로드되거나 기본으로 설정된 self.settings의 유효성을 검사하고, 잘못된 경우 기본값으로 수정합니다."""
        self._log_message("설정값 유효성 검사 시작...", "DEBUG")
        current_settings = self.settings # 현재 설정을 기준으로 작업

        # 1. 계좌번호 (account_number)
        account_number = current_settings.get("계좌정보", {}).get("계좌번호", DEFAULT_SETTINGS["계좌정보"]["계좌번호"])
        account_settings = current_settings.get("계좌정보", DEFAULT_SETTINGS["계좌정보"].copy())
        default_account_settings = DEFAULT_SETTINGS["계좌정보"]

        account_number = account_settings.get("계좌번호", default_account_settings["계좌번호"])
        if not isinstance(account_number, str) or not account_number.strip():
            self._log_message(f"설정 오류: '계좌정보.계좌번호'가 유효하지 않습니다 (값: '{account_number}'). 기본값 '{default_account_settings['계좌번호']}'으로 대체합니다.", "WARNING")
            account_number = default_account_settings["계좌번호"]
        account_settings["계좌번호"] = account_number
        
        account_type = account_settings.get("account_type", default_account_settings["account_type"])
        if account_type not in ["실거래", "모의투자"]:
            self._log_message(f"설정 오류: '계좌정보.account_type'이 유효하지 않습니다 (값: '{account_type}'). 기본값 '{default_account_settings['account_type']}'으로 대체합니다.", "WARNING")
            account_type = default_account_settings["account_type"]
        account_settings["account_type"] = account_type

        current_settings["계좌정보"] = account_settings

        # 2. 종목당 매수 금액 (buy_amount_per_stock) - "매수금액" 키 사용
        buy_amount = current_settings.get("매수금액", DEFAULT_SETTINGS["매수금액"])
        if not isinstance(buy_amount, (int, float)) or buy_amount <= 0:
            self._log_message(f"설정 오류: '매수금액'이 유효하지 않습니다 (값: {buy_amount}). 기본값 {DEFAULT_SETTINGS['매수금액']}으로 대체합니다.", "WARNING")
            buy_amount = DEFAULT_SETTINGS["매수금액"]
        current_settings["매수금액"] = buy_amount

        # 매매전략 섹션 가져오기 (없으면 기본값으로 초기화)
        strategy_settings = current_settings.get("매매전략", DEFAULT_SETTINGS["매매전략"].copy())
        default_strategy = DEFAULT_SETTINGS["매매전략"]

        # 3. 익절 수익률 (target_profit_rate)
        target_profit = strategy_settings.get("익절_수익률", default_strategy["익절_수익률"])
        if not isinstance(target_profit, (int, float)) or target_profit <= 0:
            self._log_message(f"설정 오류: '매매전략.익절_수익률'이 유효하지 않습니다 (값: {target_profit}). 기본값 {default_strategy['익절_수익률']}으로 대체합니다.", "WARNING")
            target_profit = default_strategy["익절_수익률"]
        strategy_settings["익절_수익률"] = target_profit

        # 4. 손절 손실률 (stop_loss_rate)
        stop_loss = strategy_settings.get("손절_손실률", default_strategy["손절_손실률"])
        if not isinstance(stop_loss, (int, float)) or stop_loss <= 0:
            self._log_message(f"설정 오류: '매매전략.손절_손실률'이 유효하지 않습니다 (값: {stop_loss}). 기본값 {default_strategy['손절_손실률']}으로 대체합니다.", "WARNING")
            stop_loss = default_strategy["손절_손실률"]
        strategy_settings["손절_손실률"] = stop_loss
        
        # 5. 트레일링 스탑 하락률 (trailing_stop_fall_rate)
        trailing_stop = strategy_settings.get("트레일링_하락률", default_strategy["트레일링_하락률"])
        if not isinstance(trailing_stop, (int, float)) or trailing_stop <= 0:
            self._log_message(f"설정 오류: '매매전략.트레일링_하락률'이 유효하지 않습니다 (값: {trailing_stop}). 기본값 {default_strategy['트레일링_하락률']}으로 대체합니다.", "WARNING")
            trailing_stop = default_strategy["트레일링_하락률"]
        strategy_settings["트레일링_하락률"] = trailing_stop

        # 6. 종목당 최대 시도 횟수 (max_buy_attempts_per_stock)
        max_attempts = strategy_settings.get("종목당_최대시도횟수", default_strategy["종목당_최대시도횟수"])
        if not isinstance(max_attempts, int) or max_attempts <= 0:
            self._log_message(f"설정 오류: '매매전략.종목당_최대시도횟수'가 유효하지 않습니다 (값: {max_attempts}). 기본값 {default_strategy['종목당_최대시도횟수']}으로 대체합니다.", "WARNING")
            max_attempts = default_strategy["종목당_최대시도횟수"]
        strategy_settings["종목당_최대시도횟수"] = max_attempts

        # Dry Run 모드
        dry_run_mode = strategy_settings.get("dry_run_mode", default_strategy.get("dry_run_mode", False))
        if not isinstance(dry_run_mode, bool):
            self._log_message(f"설정 오류: '매매전략.dry_run_mode'가 유효하지 않습니다 (값: {dry_run_mode}). 기본값 False으로 대체합니다.", "WARNING")
            dry_run_mode = False
        strategy_settings["dry_run_mode"] = dry_run_mode
        
        current_settings["매매전략"] = strategy_settings

        # 7. 관심종목 (watchlist) - 객체 리스트 [{code, name, yesterday_close_price}, ...]
        watchlist = current_settings.get("watchlist", DEFAULT_SETTINGS["watchlist"])
        if not isinstance(watchlist, list):
            self._log_message(f"설정 오류: 'watchlist'가 리스트가 아닙니다 (값: {watchlist}). 기본값 {DEFAULT_SETTINGS['watchlist']}으로 대체합니다.", "WARNING")
            watchlist = DEFAULT_SETTINGS["watchlist"][:]
        
        validated_watchlist = []
        for item in watchlist:
            if not isinstance(item, dict):
                self._log_message(f"'watchlist' 항목이 딕셔너리가 아님: {item}. 무시합니다.", "WARNING")
                continue
            
            code = item.get("code")
            name = item.get("name", "") # 이름은 옵션
            yesterday_close = item.get("yesterday_close_price", 0) # 전일 종가도 옵션, 기본값 0

            if not isinstance(code, str) or not code.strip():
                self._log_message(f"'watchlist' 항목에 유효한 'code'가 없음: {item}. 무시합니다.", "WARNING")
                continue
            
            if not isinstance(name, str):
                self._log_message(f"'watchlist' 항목({code})의 'name'이 문자열이 아님: {name}. 빈 문자열로 처리.", "WARNING")
                name = ""
            
            try:
                yesterday_close = float(yesterday_close)
                if yesterday_close < 0:
                    self._log_message(f"'watchlist' 항목({code})의 'yesterday_close_price'가 음수: {yesterday_close}. 0으로 처리.", "WARNING")
                    yesterday_close = 0
            except (ValueError, TypeError):
                self._log_message(f"'watchlist' 항목({code})의 'yesterday_close_price'를 숫자로 변환 불가: {yesterday_close}. 0으로 처리.", "WARNING")
                yesterday_close = 0
            
            validated_watchlist.append({"code": code.strip(), "name": name, "yesterday_close_price": yesterday_close})
        
        current_settings["watchlist"] = validated_watchlist
        
        # 8. 주기적 상태 보고 (PeriodicStatusReport)
        report_settings = current_settings.get("PeriodicStatusReport", DEFAULT_SETTINGS["PeriodicStatusReport"].copy())
        default_report = DEFAULT_SETTINGS["PeriodicStatusReport"]

        report_enabled = report_settings.get("enabled", default_report["enabled"])
        if not isinstance(report_enabled, bool):
            self._log_message(f"설정 오류: 'PeriodicStatusReport.enabled'가 유효하지 않습니다 (값: {report_enabled}). 기본값 {default_report['enabled']}으로 대체합니다.", "WARNING")
            report_enabled = default_report["enabled"]
        report_settings["enabled"] = report_enabled

        report_interval = report_settings.get("interval_seconds", default_report["interval_seconds"])
        if not isinstance(report_interval, int) or report_interval < 10: # 최소 10초 간격
            self._log_message(f"설정 오류: 'PeriodicStatusReport.interval_seconds'가 유효하지 않거나 너무 짧습니다 (값: {report_interval}). 기본값 {default_report['interval_seconds']} (최소 10초)으로 대체합니다.", "WARNING")
            report_interval = default_report["interval_seconds"]
            if report_interval < 10: report_interval = 10 # 기본값도 10초보다 작으면 10으로 강제
        report_settings["interval_seconds"] = report_interval
        
        current_settings["PeriodicStatusReport"] = report_settings

        # 기타 DEFAULT_SETTINGS에 있는 모든 최상위 키들이 self.settings에 존재하도록 보장 (존재하지 않으면 기본값으로 추가)
        for key, default_value in DEFAULT_SETTINGS.items():
            if key not in current_settings:
                self._log_message(f"설정 파일에 '{key}' 항목이 없어 기본값으로 추가합니다: {default_value}", "INFO")
                current_settings[key] = default_value
            # 중첩된 딕셔너리(예: Database, Logging 등) 내부의 키들도 기본값으로 채워주기 (선택적)
            elif isinstance(default_value, dict) and isinstance(current_settings.get(key), dict):
                for sub_key, sub_default_value in default_value.items():
                    if sub_key not in current_settings[key]:
                        self._log_message(f"설정 파일 '{key}' 섹션에 '{sub_key}' 항목이 없어 기본값으로 추가합니다: {sub_default_value}", "INFO")
                        current_settings[key][sub_key] = sub_default_value
        
        self.settings = current_settings # 최종적으로 유효성 검사가 완료된 설정을 self.settings에 반영
        
        # 9. 수수료 및 세금 비율 (fee_tax_rates) - 선택적 유효성 검사
        fee_tax_settings = current_settings.get("fee_tax_rates", DEFAULT_SETTINGS["fee_tax_rates"].copy())
        default_fees = DEFAULT_SETTINGS["fee_tax_rates"]

        for account_type_key in ["실거래", "모의투자"]:
            if account_type_key not in fee_tax_settings:
                self._log_message(f"설정 오류: 'fee_tax_rates.{account_type_key}' 섹션이 없습니다. 기본값으로 대체합니다.", "WARNING")
                fee_tax_settings[account_type_key] = default_fees[account_type_key].copy()
                continue

            current_rates = fee_tax_settings[account_type_key]
            default_rates_for_type = default_fees[account_type_key]

            for rate_key, default_rate_val in default_rates_for_type.items():
                rate_val = current_rates.get(rate_key, default_rate_val)
                if not isinstance(rate_val, float) or rate_val < 0:
                    self._log_message(f"설정 오류: 'fee_tax_rates.{account_type_key}.{rate_key}'가 유효하지 않습니다 (값: {rate_val}). 기본값 {default_rate_val}으로 대체합니다.", "WARNING")
                    rate_val = default_rate_val
                current_rates[rate_key] = rate_val
            fee_tax_settings[account_type_key] = current_rates
        
        current_settings["fee_tax_rates"] = fee_tax_settings

        # 주기적 포트폴리오 확인 (PeriodicPortfolioCheck)
        portfolio_check_settings = current_settings.get("PeriodicPortfolioCheck", DEFAULT_SETTINGS["PeriodicPortfolioCheck"].copy())
        default_portfolio_check = DEFAULT_SETTINGS["PeriodicPortfolioCheck"]

        portfolio_check_interval = portfolio_check_settings.get("interval_seconds", default_portfolio_check["interval_seconds"])
        if not isinstance(portfolio_check_interval, int) or portfolio_check_interval < 10: # 최소 10초 간격
            self._log_message(f"설정 오류: 'PeriodicPortfolioCheck.interval_seconds'가 유효하지 않거나 너무 짧습니다 (값: {portfolio_check_interval}). 기본값 {default_portfolio_check['interval_seconds']} (최소 10초)으로 대체합니다.", "WARNING")
            portfolio_check_interval = default_portfolio_check["interval_seconds"]
            if portfolio_check_interval < 10: portfolio_check_interval = 10
        portfolio_check_settings["interval_seconds"] = portfolio_check_interval
        
        current_settings["PeriodicPortfolioCheck"] = portfolio_check_settings
        
        self._log_message("설정값 유효성 검사 완료.", "DEBUG")

    def save_settings(self):
        """
        설정을 파일에 저장
        
        Returns:
            bool: 저장 성공 여부
        """
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=4)
            self._log_message(f"설정을 '{self.config_file}' 파일에 저장했습니다.", "INFO")
            return True
        except Exception as e:
            self._log_message(f"설정 저장 실패: {e}", "ERROR")
            return False
        
    def load_settings(self):
        """
        파일에서 설정 로드. 로드 후 유효성 검사 수행.
        
        Returns:
            bool: 로드 성공 여부 (유효성 검사 후 기본값으로 대체될 수 있음)
        """
        if not os.path.exists(self.config_file):
            self._log_message(f"설정 파일 '{self.config_file}'을 찾을 수 없어 기본 설정을 사용하고 새로 저장합니다.", "WARNING")
            self.settings = DEFAULT_SETTINGS.copy()
            self._validate_settings() # 기본 설정도 유효성 검사
            self.save_settings()
            return True # 기본 설정으로 성공한 것으로 간주
        
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                loaded_settings = json.load(f)
            self._log_message(f"'{self.config_file}' 파일에서 설정을 로드했습니다.", "INFO")
            
            # 로드된 설정을 기본으로 하되, 기본 설정에 없는 키는 유지하고, 기본 설정에 있는 키가 로드된 설정에 없으면 기본값으로 채움
            # self.settings = DEFAULT_SETTINGS.copy() # 이렇게 하면 로드된 설정이 무시될 수 있음
            # self.settings.update(loaded_settings) # 이렇게 하면 중첩된 딕셔너리 업데이트가 제대로 안됨

            # 재귀적 업데이트 함수 (기존 로직 활용)
            def recursive_update(base, new_values):
                for key, value in new_values.items():
                    if isinstance(value, dict) and key in base and isinstance(base[key], dict):
                        recursive_update(base[key], value)
                    else:
                        base[key] = value
            
            # 기본 설정을 기준으로 시작하고, 파일에서 읽은 설정으로 덮어쓰되, 없는 키는 기본값을 유지
            # DEFAULT_SETTINGS의 모든 키가 존재하도록 보장하면서 파일 값 우선
            temp_settings = {}
            # 1. DEFAULT_SETTINGS의 모든 키를 temp_settings에 복사 (깊은 복사 필요 시 고려)
            for k, v in DEFAULT_SETTINGS.items():
                if isinstance(v, dict):
                    temp_settings[k] = v.copy()
                else:
                    temp_settings[k] = v
            
            # 2. loaded_settings의 값으로 temp_settings를 재귀적으로 업데이트
            recursive_update(temp_settings, loaded_settings)
            self.settings = temp_settings
            
            self._log_message(f"로드된 설정과 기본 설정 병합 완료. 유효성 검사 시작...", "DEBUG")
            self._validate_settings() # 로드 및 병합 후 유효성 검사
            self._log_message(f"최종 적용된 설정: {self.settings}", "DEBUG")

            return True
        except Exception as e:
            self._log_message(f"설정 로드 실패: {e}. 기본 설정을 사용합니다.", "ERROR")
            self.settings = DEFAULT_SETTINGS.copy() # 실패 시 기본 설정 사용
            self._validate_settings() # 기본 설정에 대한 유효성 검사
            return False # 로드 자체는 실패했음을 알림 (기본값으로 대체됨)
    
    def get_setting(self, section_or_key, key_or_default=None, default_val=None):
        """
        설정 값을 가져옵니다.
        사용법:
        1. get_setting(key, default_value) -> 최상위 키
           예: config.get_setting("매수금액", 100000)
        2. get_setting(section, key, default_value) -> 섹션 내의 키
           예: config.get_setting("매매전략", "익절_수익률", 5.0)
        """
        if isinstance(section_or_key, str) and isinstance(key_or_default, str):
            # 사용법 2: get_setting(section, key, default_value)
            section = section_or_key
            key = key_or_default
            default_to_use = default_val
            
            # self.settings에서 section을 먼저 가져오고, 그 안에서 key를 찾음
            current_section = self.settings.get(section)
            if isinstance(current_section, dict):
                return current_section.get(key, default_to_use)
            else: # section 자체가 없거나 dict가 아니면 기본값 반환
                # 기본값 구조에서도 찾아봄 (DEFAULT_SETTINGS) - 더 안전하게
                default_section_val = DEFAULT_SETTINGS.get(section)
                if isinstance(default_section_val, dict):
                     return default_section_val.get(key, default_to_use)
                return default_to_use
                
        elif isinstance(section_or_key, str):
            # 사용법 1: get_setting(key, default_value)
            key = section_or_key
            default_to_use = key_or_default 
            return self.settings.get(key, default_to_use)
        
        self._log_message(f"잘못된 인자 조합으로 get_setting 호출됨: ({section_or_key}, {key_or_default}, {default_val})", "WARNING")
        return default_val # 기본적으로 default_val 반환 (None일 수 있음)

    def set_setting(self, section_or_key, key_or_value, value_if_sectioned=None):
        """
        설정 값을 설정합니다. 설정 후 유효성 검사를 하고, 필요한 경우 파일에 저장합니다.
        사용법:
        1. set_setting(key, value) -> 최상위 키
        2. set_setting(section, key, value) -> 섹션 내의 키
        """
        changed = False
        if isinstance(section_or_key, str) and value_if_sectioned is not None:
            section = section_or_key
            key = key_or_value
            value = value_if_sectioned
            
            if section not in self.settings or not isinstance(self.settings[section], dict):
                self.settings[section] = {} 
            
            if self.settings[section].get(key) != value:
                self.settings[section][key] = value
                changed = True
            
        elif isinstance(section_or_key, str):
            key = section_or_key
            value = key_or_value
            if self.settings.get(key) != value:
                self.settings[key] = value
                changed = True
        else:
            self._log_message(f"잘못된 인자 조합으로 set_setting 호출됨: {section_or_key}, {key_or_value}, {value_if_sectioned}", "ERROR")
            return False

        if changed:
            key_path = section_or_key
            if value_if_sectioned is not None:
                key_path = f"{section_or_key}.{key_or_value}"
            value_to_log = value_if_sectioned if value_if_sectioned is not None else key_or_value
            self._log_message(f"설정 변경: '{key_path}' = {value_to_log}. 유효성 검사 수행.", "DEBUG")
            self._validate_settings() # 변경된 설정에 대해 유효성 검사
            # self.save_settings() # 변경 시 즉시 저장하려면 주석 해제. 보통은 일괄 저장.
            return True
        return False # 변경사항 없음
    
    def reset_settings(self):
        """
        설정을 기본값으로 초기화하고 저장합니다.
        
        Returns:
            bool: 초기화 및 저장 성공 여부
        """
        self._log_message("설정을 기본값으로 초기화합니다.", "INFO")
        self.settings = DEFAULT_SETTINGS.copy()
        self._validate_settings() # 기본 설정도 유효성 검사
        return self.save_settings()
    
    # validate_setting 과 update_setting은 _validate_settings로 통합되어 불필요해 보임.
    # 특정 키만 업데이트하고 싶다면 set_setting 사용.

# 테스트용 코드 (ConfigManager 사용 예시)
if __name__ == '__main__':
    # 로거 없이 테스트
    print("--- 로거 없이 테스트 시작 ---")
    cfg_no_logger = ConfigManager(config_file="test_settings_no_logger.json")
    print(f"계좌번호: {cfg_no_logger.get_setting('계좌정보', '계좌번호')}")
    print(f"매수금액: {cfg_no_logger.get_setting('매수금액')}")
    print(f"익절수익률: {cfg_no_logger.get_setting('매매전략', '익절_수익률')}")
    
    # 잘못된 값 설정 시도
    cfg_no_logger.set_setting("매수금액", -100) # 유효성 검사에 의해 기본값으로 돌아가야 함
    print(f"잘못된 값 설정 후 매수금액: {cfg_no_logger.get_setting('매수금액')}")
    cfg_no_logger.set_setting("매매전략", "익절_수익률", -5.0)
    print(f"잘못된 값 설정 후 익절수익률: {cfg_no_logger.get_setting('매매전략', '익절_수익률')}")
    
    cfg_no_logger.set_setting("매매대상종목", ["005930", "000660"])
    print(f"매매대상종목: {cfg_no_logger.get_setting('매매대상종목')}")
    cfg_no_logger.save_settings() # 변경사항 저장

    # 더미 로거 사용 테스트
    class DummyLogger:
        def debug(self, msg): print(f"[DEBUG] {msg}")
        def info(self, msg): print(f"[INFO] {msg}")
        def warning(self, msg): print(f"[WARNING] {msg}")
        def error(self, msg): print(f"[ERROR] {msg}")
        def critical(self, msg): print(f"[CRITICAL] {msg}")

    print("\n--- 더미 로거 사용 테스트 시작 ---")
    dummy_logger = DummyLogger()
    cfg_with_logger = ConfigManager(config_file="test_settings_with_logger.json", logger=dummy_logger)
    cfg_with_logger.get_setting("계좌정보", "계좌번호")
    cfg_with_logger.set_setting("매매전략", "MarketOpenTime", "08:30:00")
    cfg_with_logger.save_settings()

    # 특정 파일이 없을 때 새로 생성되는지 확인
    if os.path.exists("new_test_settings.json"):
        os.remove("new_test_settings.json")
    print("\n--- 새 파일 생성 테스트 --- ")
    cfg_new_file = ConfigManager(config_file="new_test_settings.json", logger=dummy_logger)
    print(f"새 파일 생성 후 계좌번호: {cfg_new_file.get_setting('계좌정보','계좌번호')}")


    # 기존 파일에 없는 키가 있을 경우 기본값으로 채워지는지 테스트
    # 예를 들어, settings.json에 "API_Limit" 섹션이 없다고 가정
    print("\n--- 누락된 키 기본값 채우기 테스트 --- ")
    # 테스트를 위해 settings.json을 직접 수정하거나, 더미 파일을 사용
    dummy_partial_settings_file = "dummy_partial_settings.json"
    with open(dummy_partial_settings_file, 'w', encoding='utf-8') as f:
        json.dump({
            "계좌정보": {"계좌번호": "12345"},
            "매수금액": 50000
            # Logging, API_Limit 등 누락
        }, f, indent=4)
    
    cfg_partial = ConfigManager(config_file=dummy_partial_settings_file, logger=dummy_logger)
    print(f"API 요청 간격 (기본값이어야 함): {cfg_partial.get_setting('API_Limit', 'tr_request_interval_ms')}")
    print(f"로깅 레벨 (기본값이어야 함): {cfg_partial.get_setting('Logging', 'level')}")
    print(f"부분 설정 로드 후 전체 설정: {cfg_partial.settings}")

    # 파일 정리
    if os.path.exists("test_settings_no_logger.json"): os.remove("test_settings_no_logger.json")
    if os.path.exists("test_settings_with_logger.json"): os.remove("test_settings_with_logger.json")
    if os.path.exists("new_test_settings.json"): os.remove("new_test_settings.json")
    if os.path.exists(dummy_partial_settings_file): os.remove(dummy_partial_settings_file)
 