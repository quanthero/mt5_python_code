import MetaTrader5 as mt5
import pandas as pd
import pandas_ta as ta
from datetime import datetime, timedelta
import time
import logging

# Initialize logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

# Initialize MetaTrader 5 terminal
if not mt5.initialize():
    logging.error("initialize() failed, error code = %s", mt5.last_error())
    quit()

# Log in to your account
account = 155767  # Replace with your account number
password = "9FBCAvmR!"  # Replace with your password
server = "ThinkMarkets-Demo"  # Replace with your server

if not mt5.login(account, password=password, server=server):
    logging.error("login() failed, error code = %s", mt5.last_error())
    mt5.shutdown()
    quit()

logging.info("Logged in to account %s", account)

# Define trading parameters
symbol = "NAS100"
start_date = datetime(2024, 6, 20)
finish_date = datetime(9999, 1, 1)

# Check symbol info
symbol_info = mt5.symbol_info(symbol)
if symbol_info is None:
    logging.error("Failed to get symbol info for %s", symbol)
    mt5.shutdown()
    quit()

# Get volume requirements
min_volume = symbol_info.volume_min
max_volume = symbol_info.volume_max
volume_step = symbol_info.volume_step

# Ensure volume meets requirements
def adjust_volume(volume):
    if volume < min_volume:
        volume = min_volume
    elif volume > max_volume:
        volume = max_volume
    else:
        volume = round(volume / volume_step) * volume_step
    return volume

# Define window function
def window(time):
    return start_date <= time <= finish_date

# Fetch market data
def fetch_market_data():
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M10, 0, 100)  # Get recent 1000 1-minute data
    data = pd.DataFrame(rates)
    data['time'] = pd.to_datetime(data['time'], unit='s')
    return data

# Log account info
def log_account_info():
    account_info = mt5.account_info()
    if account_info:
        logging.info("Account Info: Balance: %s, Equity: %s, Margin: %s, Free Margin: %s",
                     account_info.balance, account_info.equity, account_info.margin, account_info.margin_free)
    else:
        logging.error("Failed to get account info, error code = %s", mt5.last_error())

# Check current positions
def check_positions():
    positions = mt5.positions_get(symbol=symbol)
    for pos in positions:
        if pos.type == mt5.ORDER_TYPE_BUY:
            return True
    return False

# Send order request and handle result
def send_order(request):
    result = mt5.order_send(request)
    if result is None:
        logging.error("Order send failed, error code = %s", mt5.last_error())
    else:
        logging.info("Order result: %s", result)
    return result

# Execute strategy
def execute_strategy():
    data = fetch_market_data()
    #logging.info("Data sample before applying psar: %s", data.head())

    # Apply PSAR
    data.ta.psar(high='high', low='low', append=True)
    #logging.info("Data sample after applying psar: %s", data[['time', 'high', 'low', 'close', 'PSARl_0.02_0.2', 'PSARs_0.02_0.2']].head())

    # Verify column names after applying psar
    #logging.info("Columns after applying psar: %s", data.columns)

    # Log the last three SAR values
    #if len(data) >= 3:
       # logging.info("SAR values for the last 3 bars: %s, %s, %s",
                   #  data['PSARl_0.02_0.2'].iloc[-3],
                  #   data['PSARl_0.02_0.2'].iloc[-2],
                  #   data['PSARl_0.02_0.2'].iloc[-1])

    # Generate trading signals
    data['signal'] = 0
    data.loc[(data['close'] > data['PSARl_0.02_0.2']), 'signal'] = 1  # Buy signal
    data.loc[(data['close'] < data['PSARs_0.02_0.2']), 'signal'] = -1  # Sell signal

    # Log the signals
    #logging.info("Generated signals: %s", data[['time', 'signal']].tail())

    # Check current positions
    has_position = check_positions()

    # Execute trades
    executed_trade = False
    if data['signal'].iloc[-1] == 1 and not has_position and not executed_trade:
        price = data['close'].iloc[-1]
        volume = adjust_volume(1)  # Adjust volume to meet requirements
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
            "type_filling": mt5.ORDER_FILLING_FOK,  # Change to Fill or Kill
        }
        result = send_order(request)
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            has_position = True  # Update position status
            executed_trade = True
            logging.info("Buy order executed at price %s", price)
        else:
            logging.error("Buy order failed with retcode %s", result.retcode)

    if data['signal'].iloc[-1] == -1 and has_position and not executed_trade:
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
                    "type_filling": mt5.ORDER_FILLING_FOK,  # Change to Fill or Kill
                }
                result = send_order(request)
                if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                    has_position = False  # Update position status
                    executed_trade = True
                    logging.info("Sell order executed at price %s", data['close'].iloc[-1])
                else:
                    logging.error("Sell order failed with retcode %s", result.retcode)

current_time = 0
previous_time = 0
# Main loop
while True:
    # Get current time
    time_candle = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M10, 0, 1)

    if time_candle is not None and len(time_candle) > 0:
        # Extract time
        current_time = time_candle['time'][0]

        # Compare current time with previous time
        if current_time != previous_time:
            # New candle appeared, execute strategy
            logging.info("New Candle! Let's trade.")
            # Update previous time
            previous_time = current_time
            # Execute strategy
            execute_strategy()
        else:
            # No new candle
            # logging.info("No new candle. Sleeping.")
            time.sleep(1)
    else:
        logging.error("Failed to fetch the latest candle data.")

# Shutdown MetaTrader 5 connection
mt5.shutdown()
