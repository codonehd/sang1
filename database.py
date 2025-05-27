#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import json
import sqlite3
from datetime import datetime


class Database:
    """
    데이터베이스 관리 클래스
    """
    def __init__(self, db_file="auto_trader.db", logger=None):
        """
        Database 초기화
        
        Args:
            db_file (str): 데이터베이스 파일 경로
            logger (Logger, optional): 로거 인스턴스. Defaults to None.
        """
        self.db_file = db_file
        self.logger = logger
        self.conn = None
        self.initialize_db()
        
    def initialize_db(self):
        """
        데이터베이스 초기화 및 테이블 생성
        """
        try:
            self.conn = sqlite3.connect(self.db_file)
            cursor = self.conn.cursor()
            
            # 관심종목 테이블 생성
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS watchlist (
                code TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                added_date TEXT NOT NULL
            )
            ''')
            
            # 거래 내역 테이블 생성
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_no TEXT,
                code TEXT NOT NULL,
                name TEXT NOT NULL,
                trade_type TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                price REAL NOT NULL,
                amount REAL NOT NULL,
                trade_time TEXT NOT NULL,
                trade_reason TEXT,
                fees REAL DEFAULT 0,
                tax REAL DEFAULT 0,
                net_profit REAL DEFAULT 0,
                slippage REAL DEFAULT 0
            )
            ''')

            # 매매 결정 근거 테이블 생성
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                stock_code TEXT NOT NULL,
                decision_type TEXT NOT NULL,
                reason TEXT,
                related_data TEXT
            )
            ''')

            # 일별 계좌 스냅샷 테이블 생성
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS daily_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT UNIQUE NOT NULL,
                deposit REAL,
                total_purchase_amount REAL,
                total_evaluation_amount REAL,
                total_profit_loss_amount REAL,
                total_return_rate REAL,
                portfolio_details TEXT,
                total_asset_value REAL
            )
            ''')
            
            # 시계열 데이터(OHLCV) 테이블 생성
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS ohlcv_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL,
                timeframe TEXT NOT NULL, -- 'D', 'W', 'M'
                date TEXT NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume INTEGER NOT NULL,
                timestamp TEXT NOT NULL, -- DB 기록 시간
                UNIQUE(code, timeframe, date) -- 중복 방지
            )
            ''')

            self.conn.commit()
            if self.logger:
                self.logger.info(f"데이터베이스 ({self.db_file}) 초기화 성공")
            else:
                print(f"INFO: 데이터베이스 ({self.db_file}) 초기화 성공")
            return True
        except sqlite3.Error as e:
            if self.logger:
                self.logger.error(f"데이터베이스 초기화 오류 ({self.db_file}): {e}")
            else:
                print(f"ERROR: 데이터베이스 초기화 오류 ({self.db_file}): {e}")
            return False
            
    def close(self):
        """
        데이터베이스 연결 종료
        """
        if self.conn:
            self.conn.close()
            
    def add_watchlist_item(self, code, name):
        """
        관심종목 추가
        
        Args:
            code (str): 종목 코드
            name (str): 종목명
            
        Returns:
            bool: 추가 성공 여부
        """
        try:
            cursor = self.conn.cursor()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            cursor.execute(
                "INSERT OR REPLACE INTO watchlist (code, name, added_date) VALUES (?, ?, ?)",
                (code, name, now)
            )
            
            self.conn.commit()
            if self.logger:
                self.logger.info(f"관심종목 추가 성공: {code} ({name})")
            else:
                print(f"INFO: 관심종목 추가 성공: {code} ({name})")
            return True
        except sqlite3.Error as e:
            if self.logger:
                self.logger.error(f"관심종목 추가 오류 ({code}, {name}): {e}")
            else:
                print(f"ERROR: 관심종목 추가 오류 ({code}, {name}): {e}")
            return False
            
    def remove_watchlist_item(self, code):
        """
        관심종목 삭제
        
        Args:
            code (str): 종목 코드
            
        Returns:
            bool: 삭제 성공 여부
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM watchlist WHERE code = ?", (code,))
            self.conn.commit()
            if self.logger:
                self.logger.info(f"관심종목 삭제 성공: {code}")
            else:
                print(f"INFO: 관심종목 삭제 성공: {code}")
            return True
        except sqlite3.Error as e:
            if self.logger:
                self.logger.error(f"관심종목 삭제 오류 ({code}): {e}")
            else:
                print(f"ERROR: 관심종목 삭제 오류 ({code}): {e}")
            return False
            
    def get_watchlist(self):
        """
        관심종목 목록 조회
        
        Returns:
            list: 관심종목 목록
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT code, name, added_date FROM watchlist ORDER BY added_date")
            
            result = []
            for row in cursor.fetchall():
                result.append({
                    "code": row[0],
                    "name": row[1],
                    "added_date": row[2]
                })
            
            return result
        except sqlite3.Error as e:
            if self.logger:
                self.logger.error(f"관심종목 조회 오류: {e}")
            else:
                print(f"ERROR: 관심종목 조회 오류: {e}")
            return []

    def add_decision_record(self, timestamp, stock_code, decision_type, reason, related_data_dict):
        """
        매매 결정 근거 기록

        Args:
            timestamp (str): 결정 시간 (YYYY-MM-DD HH:MM:SS)
            stock_code (str): 종목 코드
            decision_type (str): 결정 유형 (매수, 매도)
            reason (str): 판단 근거 요약
            related_data_dict (dict): 관련 데이터 (JSON으로 변환하여 저장)

        Returns:
            bool: 추가 성공 여부
        """
        try:
            cursor = self.conn.cursor()
            related_data_json = json.dumps(related_data_dict) # dict를 JSON 문자열로 변환
            
            cursor.execute(
                "INSERT INTO decisions (timestamp, stock_code, decision_type, reason, related_data) VALUES (?, ?, ?, ?, ?)",
                (timestamp, stock_code, decision_type, reason, related_data_json)
            )
            self.conn.commit()
            if self.logger:
                self.logger.info(f"매매 결정 기록 추가 성공: {decision_type} - {stock_code}, 이유: {reason}")
            else:
                print(f"INFO: 매매 결정 기록 추가 성공: {decision_type} - {stock_code}, 이유: {reason}")
            return True
        except sqlite3.Error as e:
            if self.logger:
                self.logger.error(f"매매 결정 기록 추가 오류 ({stock_code}): {e}")
            else:
                print(f"ERROR: 매매 결정 기록 추가 오류 ({stock_code}): {e}")
            return False

    def add_daily_snapshot(self, date, deposit, total_purchase_amount, total_evaluation_amount, total_profit_loss_amount, total_return_rate, portfolio_details_dict, total_asset_value=None):
        """
        일별 계좌 스냅샷 기록

        Args:
            date (str): 날짜 (YYYY-MM-DD)
            deposit (float): 예수금
            total_purchase_amount (float): 총 매입 금액
            total_evaluation_amount (float): 총 평가 금액
            total_profit_loss_amount (float): 총 평가 손익 금액
            total_return_rate (float): 총 수익률
            portfolio_details_dict (dict): 포트폴리오 상세 (JSON으로 변환되어 저장됨)
            total_asset_value (float, optional): 총 자산 평가액 (추정예탁자산). Defaults to None. 
                                               None이면 total_evaluation_amount + deposit으로 계산 시도.

        Returns:
            bool: 추가 성공 여부 (이미 해당 날짜 데이터 있으면 False)
        """
        try:
            cursor = self.conn.cursor()
            portfolio_details_json = json.dumps(portfolio_details_dict) if isinstance(portfolio_details_dict, dict) else portfolio_details_dict

            calculated_asset_value = total_asset_value
            if calculated_asset_value is None:
                if total_evaluation_amount is not None and deposit is not None:
                    calculated_asset_value = total_evaluation_amount + deposit
                else:
                    calculated_asset_value = None 
            
            cursor.execute(
                "INSERT INTO daily_snapshots (date, deposit, total_purchase_amount, total_evaluation_amount, total_profit_loss_amount, total_return_rate, portfolio_details, total_asset_value) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (date, deposit, total_purchase_amount, total_evaluation_amount, total_profit_loss_amount, total_return_rate, portfolio_details_json, calculated_asset_value)
            )
            self.conn.commit()
            log_msg = f"일별 계좌 스냅샷 추가 성공: {date}, 예수금({deposit}), 총매입({total_purchase_amount}), 총평가({total_evaluation_amount}), 손익({total_profit_loss_amount}), 수익률({total_return_rate}%), 자산({calculated_asset_value})"
            if self.logger:
                self.logger.info(log_msg)
            else:
                print(f"INFO: {log_msg}")
            return True
        except sqlite3.IntegrityError: # UNIQUE 제약 조건 위반 (이미 해당 날짜 데이터 존재)
            if self.logger:
                self.logger.warning(f"일별 계좌 스냅샷 추가 실패: {date} 데이터 이미 존재함")
            else:
                print(f"WARNING: 일별 계좌 스냅샷 추가 실패: {date} 데이터 이미 존재함")
            return False
        except sqlite3.Error as e:
            if self.logger:
                self.logger.error(f"일별 계좌 스냅샷 추가 오류 ({date}): {e}")
            else:
                print(f"ERROR: 일별 계좌 스냅샷 추가 오류 ({date}): {e}")
            return False
            
    def add_trade(self, order_no, code, name, trade_type, quantity, price, trade_reason=None, fees=0, tax=0, net_profit=0, slippage=0):
        """
        거래 내역 추가
        
        Args:
            code (str): 종목 코드
            name (str): 종목명
            trade_type (str): 거래 유형 (매수, 매도)
            quantity (int): 수량
            price (float): 가격
            trade_reason (str, optional): 거래 사유
            
        Returns:
            bool: 추가 성공 여부
        """
        try:
            cursor = self.conn.cursor()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            amount = quantity * price
            
            cursor.execute(
                "INSERT INTO trades (order_no, code, name, trade_type, quantity, price, amount, trade_time, trade_reason, fees, tax, net_profit, slippage) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", # 물음표 개수 확인
                (order_no, code, name, trade_type, quantity, price, amount, now, trade_reason, fees, tax, net_profit, slippage) # 전달 변수 추가
            )
            
            self.conn.commit()
            if self.logger:
                self.logger.info(f"거래 내역 추가 성공: {trade_type} - {name}({code}), {quantity}주 @ {price}")
            else:
                print(f"INFO: 거래 내역 추가 성공: {trade_type} - {name}({code}), {quantity}주 @ {price}")
            return True
        except sqlite3.Error as e:
            if self.logger:
                self.logger.error(f"거래 내역 추가 오류 ({code}, {name}): {e}")
            else:
                print(f"ERROR: 거래 내역 추가 오류 ({code}, {name}): {e}")
            return False
            

    def add_ohlcv_data(self, code, timeframe, date_str, open_price, high_price, low_price, close_price, volume):
        """
        OHLCV (일/주/월봉) 데이터를 추가합니다.

        Args:
            code (str): 종목 코드
            timeframe (str): 데이터 주기 ('D', 'W', 'M')
            date_str (str): 날짜 (YYYYMMDD 형식)
            open_price (float): 시가
            high_price (float): 고가
            low_price (float): 저가
            close_price (float): 종가
            volume (int): 거래량

        Returns:
            bool: 추가 성공 여부 (이미 해당 데이터 존재 시 False 반환)
        """
        try:
            cursor = self.conn.cursor()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # YYYYMMDD 형식의 date_str을 YYYY-MM-DD 형식으로 변환 (DB 저장용)
            # API에서 오는 날짜 형식이 YYYYMMDD이므로 그대로 사용하거나, 필요시 변환
            # 여기서는 UNIQUE 제약조건을 위해 date_str 그대로 사용

            cursor.execute(
                "INSERT INTO ohlcv_data (code, timeframe, date, open, high, low, close, volume, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (code, timeframe, date_str, open_price, high_price, low_price, close_price, volume, now)
            )
            self.conn.commit()
            if self.logger:
                self.logger.debug(f"OHLCV 데이터 추가 성공: {code}, {timeframe}, {date_str}")
            else:
                print(f"DEBUG: OHLCV 데이터 추가 성공: {code}, {timeframe}, {date_str}")
            return True
        except sqlite3.IntegrityError: # UNIQUE 제약 조건 위반 (code, timeframe, date 중복)
            if self.logger:
                self.logger.debug(f"OHLCV 데이터 이미 존재: {code}, {timeframe}, {date_str}")
            else:
                print(f"DEBUG: OHLCV 데이터 이미 존재: {code}, {timeframe}, {date_str}")
            return False # 이미 존재하므로 추가하지 않음
        except sqlite3.Error as e:
            if self.logger:
                self.logger.error(f"OHLCV 데이터 추가 오류 ({code}, {timeframe}, {date_str}): {e}")
            else:
                print(f"ERROR: OHLCV 데이터 추가 오류 ({code}, {timeframe}, {date_str}): {e}")
            return False

    def get_trades(self, code=None, trade_type=None, start_date=None, end_date=None, trade_reason=None):
        """
        거래 내역 조회
        
        Args:
            code (str, optional): 종목 코드
            trade_type (str, optional): 거래 유형 (매수, 매도)
            start_date (str, optional): 시작 날짜 (YYYY-MM-DD)
            end_date (str, optional): 종료 날짜 (YYYY-MM-DD)
            trade_reason (str, optional): 거래 사유
            
        Returns:
            list: 거래 내역 목록
        """
        try:
            cursor = self.conn.cursor()
            
            query = "SELECT * FROM trades"
            conditions = []
            params = []
            
            if code:
                conditions.append("code = ?")
                params.append(code)
                
            if trade_type:
                conditions.append("trade_type = ?")
                params.append(trade_type)

            if trade_reason:
                conditions.append("trade_reason = ?")
                params.append(trade_reason)
                
            if start_date:
                conditions.append("trade_time >= ?")
                params.append(f"{start_date} 00:00:00")
                
            if end_date:
                conditions.append("trade_time <= ?")
                params.append(f"{end_date} 23:59:59")
                
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
                
            query += " ORDER BY trade_time DESC"
            
            cursor.execute(query, params)
            
            result = []
            for row in cursor.fetchall():
                result.append({
                    "id": row[0],
                    "order_no": row[1],
                    "code": row[2],
                    "name": row[3],
                    "trade_type": row[4],
                    "quantity": row[5],
                    "price": row[6],
                    "amount": row[7],
                    "trade_time": row[8],
                    "trade_reason": row[9],
                    "fees": row[10],
                    "tax": row[11],
                    "net_profit": row[12] if len(row) > 12 else 0, # Handle older rows that might not have these columns
                    "slippage": row[13] if len(row) > 13 else 0   # Handle older rows
                })
            
            return result
        except sqlite3.Error as e:
            if self.logger:
                self.logger.error(f"거래 내역 조회 오류: {e}")
            else:
                print(f"ERROR: 거래 내역 조회 오류: {e}")
            return [] 

    def get_trades_by_date(self, date_str):
        """지정된 날짜의 모든 거래 기록을 가져옵니다."""
        try:
            self._ensure_trades_table_exists()
            
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT * FROM trades 
                WHERE date(trade_time) = date(?)
                ORDER BY trade_time DESC
            """, (date_str,))
            
            trades = []
            columns = [col[0] for col in cursor.description]
            for row in cursor.fetchall():
                trades.append(dict(zip(columns, row)))
            
            self.logger.info(f"{date_str} 날짜의 거래 {len(trades)}건을 DB에서 로드했습니다.")
            return trades
        except Exception as e:
            self.logger.error(f"날짜별 거래 기록 조회 중 오류: {e}")
            return []
    
    def get_recent_trades_by_code(self, code, limit=10):
        """특정 종목의 최근 거래 기록을 가져옵니다."""
        try:
            self._ensure_trades_table_exists()
            
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT * FROM trades 
                WHERE code = ?
                ORDER BY trade_time DESC
                LIMIT ?
            """, (code, limit))
            
            trades = []
            columns = [col[0] for col in cursor.description]
            for row in cursor.fetchall():
                trades.append(dict(zip(columns, row)))
            
            self.logger.info(f"{code} 종목의 최근 거래 {len(trades)}건을 DB에서 로드했습니다.")
            return trades
        except Exception as e:
            self.logger.error(f"종목별 거래 기록 조회 중 오류: {e}")
            return [] 

    def _ensure_trades_table_exists(self):
        """trades 테이블이 존재하는지 확인하고, 없으면 생성합니다."""
        try:
            cursor = self.conn.cursor()
            
            # 테이블 존재 여부 확인
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='trades'")
            if not cursor.fetchone():
                # 테이블이 없으면 생성
                cursor.execute('''
                CREATE TABLE trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_no TEXT,
                    code TEXT NOT NULL,
                    name TEXT NOT NULL,
                    trade_type TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    price REAL NOT NULL,
                    amount REAL NOT NULL,
                    trade_time TEXT NOT NULL,
                    trade_reason TEXT,
                    fees REAL DEFAULT 0,
                    tax REAL DEFAULT 0,
                    net_profit REAL DEFAULT 0,
                    slippage REAL DEFAULT 0
                )
                ''')
                self.conn.commit()
                if self.logger:
                    self.logger.info("trades 테이블이 생성되었습니다.")
                else:
                    print("INFO: trades 테이블이 생성되었습니다.")
            return True
        except sqlite3.Error as e:
            if self.logger:
                self.logger.error(f"trades 테이블 확인/생성 중 오류: {e}")
            else:
                print(f"ERROR: trades 테이블 확인/생성 중 오류: {e}")
            return False 