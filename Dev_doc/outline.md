
# 키움 OpenAPI+ 자동매매 프로그램 최종 아웃라인

## 1. 프로그램 구조
```
- main.py: 프로그램 진입점
- kiwoom_api.py: 키움 API 연결 및 이벤트 처리 클래스
- strategy.py: 매매 전략 구현 클래스
- ui.py: 사용자 인터페이스 구현
- config.py: 설정 및 상수 정의
- util.py: 유틸리티 함수
- database.py: 거래 기록 및 관심종목 저장
- logger.py: 로깅 및 오류 알림 기능
```

## 2. 주요 기능 구현

### 2.1 설정 관리 (config.py)
```python
# 기본 설정
DEFAULT_SETTINGS = {
    "매수금액": 1000000,  # 종목당 100만원
    "익절_수익률": 5.0,   # 5% 수익 시 부분 매도
    "익절_매도비율": 50,  # 익절 시 50% 매도
    "트레일링_하락률": 2.0,  # 고점에서 2% 하락 시 매도
    "손절_손실률": 3.0    # 3% 손실 시 전량 매도
}

class ConfigManager:
    def __init__(self):
        self.settings = DEFAULT_SETTINGS.copy()
    
    def save_settings(self):
        # 설정 저장
        
    def load_settings(self):
        # 설정 불러오기
```

### 2.2 키움 API 연결 (kiwoom_api.py)
```python
class KiwoomAPI:
    def __init__(self, event_handler=None):
        self.ocx = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")
        self.event_handler = event_handler
        self.connect_events()
        self.account_number = ""
        
    def connect_events(self):
        self.ocx.OnEventConnect.connect(self.on_event_connect)
        self.ocx.OnReceiveTrData.connect(self.on_receive_tr_data)
        self.ocx.OnReceiveRealData.connect(self.on_receive_real_data)
        self.ocx.OnReceiveChejanData.connect(self.on_receive_chejan_data)
        self.ocx.OnReceiveMsg.connect(self.on_receive_msg)
        
    def login(self):
        return self.ocx.dynamicCall("CommConnect()")
        
    def get_login_info(self, tag):
        return self.ocx.dynamicCall("GetLoginInfo(QString)", tag)
        
    def get_stock_info(self, code):
        # 종목 정보 조회
        # TR: opt10001 (주식기본정보)
        
    def get_daily_chart(self, code):
        # 일봉 데이터 조회
        # TR: opt10081 (주식일봉차트조회)
```

### 2.3 관심종목 관리
```python
class WatchlistManager:
    def __init__(self, api):
        self.api = api
        self.watchlist = []  # 관심종목 목록 (3~7개)
        
    def add_stock(self, code, name):
        if len(self.watchlist) < 7:
            self.watchlist.append({"code": code, "name": name})
            return True
        return False
        
    def remove_stock(self, code):
        self.watchlist = [item for item in self.watchlist if item["code"] != code]
        
    def get_watchlist(self):
        return self.watchlist
        
    def save_watchlist(self):
        # 관심종목 저장
        
    def load_watchlist(self):
        # 관심종목 불러오기
```

### 2.4 매매 전략 (strategy.py)
```python
class TradingStrategy:
    def __init__(self, api, config):
        self.api = api
        self.config = config
        self.position = {}  # 보유 포지션 정보
        self.high_prices = {}  # 종목별 고가 정보 (트레일링 스탑용)
        self.prev_close = {}  # 전일 종가
        self.today_open = {}  # 당일 시가
        self.price_crossed_down = {}  # 전일 종가 밑으로 내려갔는지 여부
        
    def initialize_stock_data(self, code):
        # 전일 종가, 당일 시가 정보 초기화
        daily_data = self.api.get_daily_chart(code)
        if len(daily_data) >= 2:
            self.prev_close[code] = daily_data[1]['종가']
            self.today_open[code] = daily_data[0]['시가']
            self.price_crossed_down[code] = False
        
    def process_real_data(self, code, current_price):
        # 실시간 데이터 처리
        
        # 매수 조건 체크
        if code not in self.position:
            if self.check_buy_condition(code, current_price):
                self.execute_buy(code, current_price)
        
        # 매도 조건 체크
        else:
            if self.check_sell_condition(code, current_price):
                self.execute_sell(code, current_price)
    
    def check_buy_condition(self, code, current_price):
        # 조건1: 당일 시가 > 전일 종가
        condition1 = self.today_open[code] > self.prev_close[code]
        
        # 조건2: 현재가가 전일 종가 하회 후 돌파
        if current_price < self.prev_close[code]:
            self.price_crossed_down[code] = True
            return False
        
        condition2 = self.price_crossed_down[code] and current_price >= self.prev_close[code]
        
        return condition1 and condition2
    
    def execute_buy(self, code, current_price):
        # 매수 수량 계산 (고정 금액으로 매수)
        quantity = int(self.config.settings["매수금액"] / current_price)
        
        # 매수 주문 요청
        if quantity > 0:
            order_result = self.api.send_order("매수", code, quantity, 0, "03")
            
            if order_result:
                self.position[code] = {
                    "quantity": quantity,
                    "bought_price": current_price,
                    "bought_time": datetime.now(),
                    "high_price": current_price,
                    "partial_sold": False
                }
    
    def check_sell_condition(self, code, current_price):
        if code not in self.position:
            return False
            
        position = self.position[code]
        profit_percent = (current_price - position["bought_price"]) / position["bought_price"] * 100
        
        # 손절: 3% 손실 시 전량 매도
        if profit_percent <= -self.config.settings["손절_손실률"]:
            return {"type": "손절", "quantity": position["quantity"]}
        
        # 고점 갱신
        if current_price > position["high_price"]:
            position["high_price"] = current_price
        
        # 익절1: 5% 수익 시 50% 매도
        if not position["partial_sold"] and profit_percent >= self.config.settings["익절_수익률"]:
            position["partial_sold"] = True
            sell_quantity = int(position["quantity"] * self.config.settings["익절_매도비율"] / 100)
            return {"type": "부분익절", "quantity": sell_quantity}
        
        # 익절2: 고점 대비 2% 하락 시 전량 매도 (부분 매도 이후)
        if position["partial_sold"]:
            decline_from_high = (position["high_price"] - current_price) / position["high_price"] * 100
            if decline_from_high >= self.config.settings["트레일링_하락률"]:
                return {"type": "트레일링스탑", "quantity": position["quantity"] - int(position["quantity"] * self.config.settings["익절_매도비율"] / 100)}
        
        return False
    
    def execute_sell(self, code, sell_info):
        # 매도 주문 요청
        order_result = self.api.send_order("매도", code, sell_info["quantity"], 0, "03")
        
        if order_result:
            if sell_info["type"] in ["손절", "트레일링스탑"] or sell_info["quantity"] == self.position[code]["quantity"]:
                del self.position[code]
            else:
                self.position[code]["quantity"] -= sell_info["quantity"]
```

### 2.5 사용자 인터페이스 (ui.py)
```python
class MainWindow(QMainWindow):
    def __init__(self, api, config, strategy):
        super().__init__()
        self.api = api
        self.config = config
        self.strategy = strategy
        self.watchlist_manager = WatchlistManager(api)
        self.init_ui()
        
    def init_ui(self):
        # 메인 윈도우 설정
        self.setWindowTitle("키움 자동매매 시스템")
        self.setGeometry(100, 100, 800, 600)
        
        # 탭 위젯 설정
        self.tab_widget = QTabWidget()
        self.setCentralWidget(self.tab_widget)
        
        # 탭 추가
        self.init_dashboard_tab()
        self.init_watchlist_tab()
        self.init_settings_tab()
        self.init_log_tab()
        
    def init_dashboard_tab(self):
        # 대시보드 탭 (매매 현황)
        dashboard_tab = QWidget()
        # 계좌 정보, 보유종목, 매매내역 등 표시
        
        self.tab_widget.addTab(dashboard_tab, "대시보드")
        
    def init_watchlist_tab(self):
        # 관심종목 관리 탭
        watchlist_tab = QWidget()
        
        # 관심종목 목록 테이블
        self.watchlist_table = QTableWidget()
        self.watchlist_table.setColumnCount(5)
        self.watchlist_table.setHorizontalHeaderLabels(["종목코드", "종목명", "현재가", "전일대비", "등록/삭제"])
        
        # 종목 추가 입력 필드
        code_label = QLabel("종목코드:")
        self.code_input = QLineEdit()
        name_label = QLabel("종목명:")
        self.name_input = QLineEdit()
        add_button = QPushButton("추가")
        add_button.clicked.connect(self.add_stock_to_watchlist)
        
        # 레이아웃 설정
        
        self.tab_widget.addTab(watchlist_tab, "관심종목")
        
    def init_settings_tab(self):
        # 설정 탭
        settings_tab = QWidget()
        
        # 매매 설정 입력 필드들
        amount_label = QLabel("종목당 매수금액:")
        self.amount_input = QSpinBox()
        self.amount_input.setRange(100000, 10000000)
        self.amount_input.setSingleStep(100000)
        self.amount_input.setValue(self.config.settings["매수금액"])
        
        profit_label = QLabel("익절 수익률(%):")
        self.profit_input = QDoubleSpinBox()
        self.profit_input.setRange(1.0, 20.0)
        self.profit_input.setSingleStep(0.5)
        self.profit_input.setValue(self.config.settings["익절_수익률"])
        
        # 다른 설정 필드들...
        
        save_button = QPushButton("설정 저장")
        save_button.clicked.connect(self.save_settings)
        
        # 레이아웃 설정
        
        self.tab_widget.addTab(settings_tab, "설정")
        
    def init_log_tab(self):
        # 로그 탭
        log_tab = QWidget()
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        
        # 레이아웃 설정
        
        self.tab_widget.addTab(log_tab, "로그")
        
    def add_stock_to_watchlist(self):
        code = self.code_input.text().strip()
        name = self.name_input.text().strip()
        
        if code and name:
            result = self.watchlist_manager.add_stock(code, name)
            if result:
                self.refresh_watchlist_table()
                self.code_input.clear()
                self.name_input.clear()
            else:
                QMessageBox.warning(self, "관심종목 추가 실패", "관심종목은 최대 7개까지 추가할 수 있습니다.")
        
    def refresh_watchlist_table(self):
        # 관심종목 테이블 갱신
        
    def save_settings(self):
        # 설정 값 저장
        self.config.settings["매수금액"] = self.amount_input.value()
        self.config.settings["익절_수익률"] = self.profit_input.value()
        # 다른 설정 값들...
        
        self.config.save_settings()
        QMessageBox.information(self, "설정 저장", "설정이 성공적으로 저장되었습니다.")
```

### 2.6 오류 알림 기능 (logger.py)
```python
class Logger:
    def __init__(self, log_widget=None):
        self.log_widget = log_widget
        self.log_file = "trading_log.txt"
        
    def log(self, message, level="INFO"):
        log_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_message = f"[{level}] {log_time} - {message}"
        
        # 로그 파일에 기록
        with open(self.log_file, "a") as f:
            f.write(log_message + "\n")
        
        # UI 로그 위젯에 출력
        if self.log_widget:
            self.log_widget.append(log_message)
            
    def error(self, message):
        self.log(message, "ERROR")
        # 메시지 알림 (우선순위가 낮으므로 기본 구현만)
        # 추후 SMS, 이메일 등으로 확장 가능
```

## 3. 메인 진입점 (main.py)
```python
def main():
    app = QApplication(sys.argv)
    
    # 설정 관리자 초기화
    config = ConfigManager()
    config.load_settings()
    
    # 키움 API 초기화
    kiwoom = KiwoomAPI()
    
    # 로그인
    login_result = kiwoom.login()
    if not login_result:
        QMessageBox.critical(None, "로그인 실패", "키움 API 로그인에 실패했습니다.")
        return
    
    # 계좌 정보 가져오기
    account_number = kiwoom.get_login_info("ACCNO").split(';')[0]
    
    # 매매 전략 초기화
    strategy = TradingStrategy(kiwoom, config)
    
    # 메인 윈도우 생성
    main_window = MainWindow(kiwoom, config, strategy)
    main_window.show()
    
    # 이벤트 루프 실행
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
```

## 4. 구현 단계

1. 개발 환경 설정 (Python 설치, PyQt 설치, 키움 OpenAPI+ 설치)
2. 기본 UI 및 설정 관리 기능 구현
3. 키움 API 연결 및 이벤트 처리 구현
4. 관심종목 관리 기능 구현
5. 매매 전략 로직 구현
6. 실시간 데이터 처리 및 주문 실행 기능 구현
7. 로깅 및 오류 처리 기능 구현
8. 테스트 및 디버깅
9. 시스템 안정화
10. 대체거래소 대응 확장 (추후)

이 아웃라인을 바탕으로 단계적으로 개발을 진행하실 수 있습니다. 추가 질문이 있으시면 언제든지 물어봐 주세요!
