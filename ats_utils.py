#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
from util import _safe_to_int, _safe_to_float

# --- ATS 관련 상수 ---
ATS_SUFFIX_MARKET_MAP = {
    '_NX': 'NXT',  # Nextrade
    '_AL': 'ALL'   # 통합시세 (NXT + KRX)
}

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

TR_USES_SUFFIX_IN_STOCK_CODE = {
    "OPT10001", "OPT10002", "OPT10003", "OPT10004", "OPT10005", "OPT10006", "OPT10007", "OPT10008", "OPT10009", "OPT10010",
    "OPT10011", "OPT10012", "OPT10013", "OPT10014", "OPT10015", "OPT10053", "OPT10055", "OPT10056", "OPT10057",
    "OPT10074", "OPT10077", "OPT10078", "OPT10079", "OPT10080", "OPT10081", "OPT10082", "OPT10083", "OPT10084", "OPT10086", "OPT10087",
}

DEFAULT_MARKET_CONTEXT = 'KRX'

# --- ATS 관련 헬퍼 함수 ---

def _parse_stock_code(full_code_str: str, logger_instance=None):
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
                if logger_instance:
                    logger_instance.debug(f"[ATS_UTIL] _parse_stock_code: ATS 접미사 '{s}' 감지. 입력 '{full_code}', 순수코드 '{pure_code}', 시장컨텍스트 '{market_context_from_suffix}'")
                break
    
    if not suffix:
        if (len(full_code) == 6 and full_code.isdigit()) or \
           (len(full_code) > 0 and full_code[0].isalpha() and len(full_code[1:]) == 6 and full_code[1:].isdigit()):
            if logger_instance:
                logger_instance.debug(f"[ATS_UTIL] _parse_stock_code: ATS 접미사 없음. 입력 '{full_code}'를 순수 코드로 간주.")

    return pure_code, suffix, market_context_from_suffix, full_code

def get_code_market_info(full_code_str: str, logger_instance=None):
    """
    종목코드 문자열을 분석하여 순수 종목코드와 시장 컨텍스트를 반환합니다.
    _parse_stock_code의 결과를 더 사용하기 쉽게 래핑합니다.
    Returns:
        tuple: (pure_code, market_context) 
               market_context는 'KRX', 'NXT', 'ALL' 또는 None.
    """
    pure_code, suffix, market_context_from_suffix, _ = _parse_stock_code(full_code_str, logger_instance)
    if market_context_from_suffix:
        return pure_code, market_context_from_suffix
    
    if (len(pure_code) == 6 and pure_code.isdigit()) or \
       (len(pure_code) > 0 and pure_code[0].isalpha() and len(pure_code[1:]) == 6 and pure_code[1:].isdigit()):
        return pure_code, DEFAULT_MARKET_CONTEXT
            
    if logger_instance:
        logger_instance.warning(f"[ATS_UTIL] get_code_market_info: 유효하지 않은 종목코드 형식으로 시장 컨텍스트를 결정할 수 없음: '{full_code_str}'")
    return pure_code, None

def _get_api_market_param_value(tr_code: str, market_context: str, logger_instance=None):
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
            if logger_instance:
                logger_instance.debug(f"[ATS_UTIL] TR [{tr_code}]에 대한 시장 파라미터: 컨텍스트='{eff_market_context}', 파라미터명='{param_name}', 설정값='{param_value}'")
            return param_name, param_value
        else:
            if logger_instance:
                logger_instance.warning(f"[ATS_UTIL] TR [{tr_code}]에 대한 시장 컨텍스트 '{eff_market_context}'의 파라미터 값 정의를 TR_MARKET_PARAM_CONFIG에서 찾을 수 없음 (param_name: {param_name}, value_found: {param_value is not None}).")
    return None, None

def _determine_code_for_tr_input(tr_code: str, original_full_code: str, logger_instance=None):
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
    pure_code, suffix, _, _ = _parse_stock_code(original_full_code, logger_instance)

    if tr_code in TR_USES_SUFFIX_IN_STOCK_CODE:
        if suffix:
            if logger_instance:
                logger_instance.info(f"[ATS_UTIL] TR [{tr_code}]은(는) 종목코드에 ATS 접미사를 직접 사용합니다. 코드: [{original_full_code}] 사용.")
            return original_full_code
        else:
            if logger_instance:
                logger_instance.info(f"[ATS_UTIL] TR [{tr_code}]은(는) 종목코드에 ATS 접미사를 사용할 수 있으나, 입력코드 [{original_full_code}]에 접미사 없음. KRX 조회로 간주하여 [{pure_code}] 사용.")
            return pure_code
    else:
        if logger_instance:
            logger_instance.info(f"[ATS_UTIL] TR [{tr_code}]은(는) '거래소구분' 파라미터를 사용할 가능성이 있으며, 종목코드는 순수 코드 [{pure_code}]를 사용합니다. (원본: {original_full_code})")
        return pure_code
