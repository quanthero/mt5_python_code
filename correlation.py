import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import math
import time
import logging

# 初始化日志记录
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

# 初始化MetaTrader 5终端
if not mt5.initialize():
    logging.error("initialize() failed, error code = %s", mt5.last_error())
    quit()

# 登录到你的账户
# account = 1469182  # 替换为你的账户号码
# password = "4p-tBgLr"  # 替换为你的密码
# server = "AMPGlobalUSA-Demo"  # 替换为你的服务器


#Thinkmarkets demo 账户 

account = 25121570  # 替换为你的账户号码
password = "9&SF6lV}Vt@D"  # 替换为你的密码
server = "Tickmill-Demo"  # 替换为你的服务器

if not mt5.login(account, password=password, server=server):
    logging.error("login() failed, error code = %s", mt5.last_error())
    mt5.shutdown()
    quit()

logging.info("Logged in to account %s", account)

# 定义交易参数
# symbol = "NAS100"
# symbol = "EPM24"
symbol = "BTCUSD"
FastLength = 20
SlowLength = 40
OverBought = 0.5
OverSold = 0.2
start = datetime(2024, 6, 19)
finish = datetime(9999, 1, 1)

# 检查交易品种的信息
symbol_info = mt5.symbol_info(symbol)
if symbol_info is None:
    logging.error("Failed to get symbol info for %s", symbol)
    mt5.shutdown()
    quit()

# 获取交易量要求
min_volume = symbol_info.volume_min
max_volume = symbol_info.volume_max
volume_step = symbol_info.volume_step

# 确保交易量符合要求
def adjust_volume(volume):
    if volume < min_volume:
        volume = min_volume
    elif volume > max_volume:
        volume = max_volume
    else:
        volume = round(volume / volume_step) * volume_step
    return volume

# 定义窗口函数
def window(time):
    return start <= time <= finish

# 计算相关性
def calculate_correlation(length, close_prices):
    Sx, Sy, Sxx, Sxy, Syy = 0, 0, 0, 0, 0
    for count in range(length):
        X = close_prices.iloc[-(count + 1)]
        Y = -count
        Sx += X
        Sy += Y
        Sxx += X * X
        Sxy += X * Y
        Syy += Y * Y
    if length * Sxx - Sx * Sx > 0 and length * Syy - Sy * Sy > 0:
        correlation = (length * Sxy - Sx * Sy) / math.sqrt((length * Sxx - Sx * Sx) * (length * Syy - Sy * Sy))
        return correlation
    else:
        return np.nan

# 获取市场数据
def fetch_market_data():
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M10, 0, 100)  # 获取最近1000条5分钟数据
    data = pd.DataFrame(rates)
    data['time'] = pd.to_datetime(data['time'], unit='s')
    return data

# 记录账户信息
def log_account_info():
    account_info = mt5.account_info()
    if account_info:
        logging.info("Account Info: Balance: %s, Equity: %s, Margin: %s, Free Margin: %s",
                     account_info.balance, account_info.equity, account_info.margin, account_info.margin_free)
    else:
        logging.error("Failed to get account info, error code = %s", mt5.last_error())

# 检查当前持仓
def check_positions():
    positions = mt5.positions_get(symbol=symbol)
    for pos in positions:
        if pos.type == mt5.ORDER_TYPE_BUY:
            return True
    return False

# 发送订单请求并处理结果
def send_order(request):
    result = mt5.order_send(request)
    if result is None:
        logging.error("Order send failed, error code = %s", mt5.last_error())
    else:
        logging.info("Order result: %s", result)
    return result

# 执行策略
def execute_strategy():
    data = fetch_market_data()

    # 初始化变量
    data['CorrF'] = np.nan
    data['CorrS'] = np.nan

    # 应用策略
    for i in range(SlowLength, len(data)):
        if window(data['time'].iloc[i]):
            data.at[i, 'CorrF'] = calculate_correlation(FastLength, data['close'][:i + 1])
            data.at[i, 'CorrS'] = calculate_correlation(SlowLength, data['close'][:i + 1])

    # 打印前两个K线的相关性值
    if len(data) > 3:
        prev_corrf = data['CorrF'].iloc[-2]
        prev_corrs = data['CorrS'].iloc[-2]
        prev_prev_corrf = data['CorrF'].iloc[-3]
        prev_prev_corrs = data['CorrS'].iloc[-3]
        prev_close = data['close'].iloc[-2]
        prev_prev_close = data['close'].iloc[-3]
        logging.info("Prev close: %s, Prev-Prev close: %s", prev_close, prev_prev_close)             
        logging.info("Prev CorrF: %s, Prev CorrS: %s", prev_corrf, prev_corrs)
        logging.info("Prev-Prev CorrF: %s, Prev-Prev CorrS: %s", prev_prev_corrf, prev_prev_corrs)

    # 生成交易信号
    buy_signal = (prev_prev_corrf < OverBought) and (prev_corrf > OverBought)
    sell_signal = (prev_prev_corrs > OverSold) and (prev_corrs < OverSold)

    # 检查当前是否有持仓
    has_position = check_positions()

    # 执行交易（每次循环只执行一次交易）
    executed_trade = False
    if buy_signal and not has_position and not executed_trade:
        price = data['close'].iloc[-1]
        volume = adjust_volume(0.1)  # 调整交易量，确保符合要求
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": mt5.ORDER_TYPE_BUY,
            "price": price,
            "deviation": 5,
            "magic": 123456,
            "comment": "Python script open",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        result = send_order(request)
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            has_position = True  # 更新持仓状态
            executed_trade = True

    if sell_signal and has_position and not executed_trade:
        positions = mt5.positions_get(symbol=symbol)
        if positions:
            for pos in positions:
                request = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": symbol,
                    "volume": pos.volume,
                    "type": mt5.ORDER_TYPE_SELL,
                    "position": pos.ticket,
                    "price": data['close'].iloc[-1],
                    "deviation": 5,
                    "magic": 123456,
                    "comment": "Python script close",
                    "type_time": mt5.ORDER_TIME_GTC,
                    "type_filling": mt5.ORDER_FILLING_IOC,
                }
                result = send_order(request)
                if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                    has_position = False  # 更新持仓状态
                    executed_trade = True
current_time = 0
previous_time = 0
# 主循环
while True:
    # 获取当前时间
    time_candle = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M10, 0, 1)

    if time_candle is not None and len(time_candle) > 0:
        # 提取时间
        current_time = time_candle['time'][0]

        # 比较当前时间与前一个时间
        if current_time != previous_time:
            # 有新的K线出现，执行策略
            logging.info("New Candle! Let's trade.")
            # 更新前一个时间
            previous_time = current_time
            # 执行策略
            execute_strategy()
        else:
            # 没有新的K线
            # logging.info("No new candle. Sleeping.")
            time.sleep(1)
    else:
        logging.error("Failed to fetch the latest candle data.")

# 关闭MetaTrader 5连接
mt5.shutdown()
