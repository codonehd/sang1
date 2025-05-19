#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler
# from PyQt5.QtCore import QObject, pyqtSignal # 제거

class Logger: # QObject 상속 제거
    """
    로깅 기능을 제공하는 클래스 (콘솔 및 파일)
    """
    # log_message_received = pyqtSignal(str) # 제거
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(Logger, cls).__new__(cls)
        return cls._instance

    def __init__(self, log_file="logs/app.log", log_level=logging.DEBUG, max_bytes=10*1024*1024, backup_count=5):
        # super().__init__() # QObject 상속 제거로 인해 super() 호출 불필요

        if hasattr(self, '_initialized') and self._initialized:
            return
        
        self.log_file = log_file
        self.log_level = log_level
        self.logger = logging.getLogger("AppLogger")
        self.logger.setLevel(self.log_level)

        if self.logger.hasHandlers():
            self.logger.handlers.clear()

        log_dir = os.path.dirname(self.log_file)
        if not os.path.exists(log_dir):
            try:
                os.makedirs(log_dir)
            except OSError as e:
                print(f"Error creating log directory {log_dir}: {e}")
                return

        self.formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(lineno)d - %(message)s'
        )

        try:
            fh = RotatingFileHandler(
                self.log_file, maxBytes=max_bytes, backupCount=backup_count, encoding='utf-8'
            )
            fh.setLevel(self.log_level)
            fh.setFormatter(self.formatter)
            self.logger.addHandler(fh)
        except Exception as e:
            print(f"Error setting up file handler for {self.log_file}: {e}")

        ch = logging.StreamHandler()
        ch.setLevel(self.log_level)
        ch.setFormatter(self.formatter)
        self.logger.addHandler(ch)
        
        # signal_handler = QTextEditLogHandler(self.log_message_received) # 제거
        # signal_handler.setLevel(self.log_level) # 제거
        # signal_handler.setFormatter(self.formatter) # 제거
        # self.logger.addHandler(signal_handler) # 제거
        
        self._initialized = True
        self.info("로깅 시스템 초기화 완료 (콘솔 및 파일 핸들러)") # 메시지 수정

    # def _emit_log_message(self, level, message, exc_info=False): # 제거
    #     log_record = self.logger.makeRecord( # 제거
    #         self.logger.name, level, fn=inspect.stack()[1].filename, # 제거
    #         lno=inspect.stack()[1].lineno, msg=message, args=(), # 제거
    #         exc_info=exc_info if exc_info else None, func=inspect.stack()[1].function # 제거
    #     ) # 제거
    #     formatted_message = self.formatter.format(log_record) # 제거
    #     self.log_message_received.emit(formatted_message) # 제거

    def debug(self, message):
        self.logger.debug(message)

    def info(self, message):
        self.logger.info(message)

    def warning(self, message):
        self.logger.warning(message)

    def error(self, message, exc_info=False):
        self.logger.error(message, exc_info=exc_info)

    def critical(self, message, exc_info=False):
        self.logger.critical(message, exc_info=exc_info)

# QTextEdit에 로그를 추가하는 핸들러 # 제거
# class QTextEditLogHandler(logging.Handler): # 제거
#     def __init__(self, text_widget_signal): # 제거
#         super().__init__() # 제거
#         self.text_widget_signal = text_widget_signal # 제거
# # 제거
#     def emit(self, record): # 제거
#         msg = self.format(record) # 제거
#         self.text_widget_signal.emit(msg) # 제거

# 전역 로거 인스턴스 (필요시 사용)
# logger_instance = Logger() 