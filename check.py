import requests
import binance_unified
from datetime import datetime, timezone, timedelta

onlyReadApiKey = "xxx"
onlyReadApiSecret = 'xxx'

startTime = "2026-02-08 21:00:00.000000"  # 对账开始的时间点UTC+8
endTime = "2026-04-14 17:00:00.000000"  # 对账结束的时间点UTC+8

binanceApi = binance_unified.BinanceUnifiedClient(onlyReadApiKey, onlyReadApiSecret)

def to_timestamp_ms(dt_str):
    """将时间转换为unix时间戳"""
    dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S.%f")
    
    # 指定 UTC+8
    tz_utc8 = timezone(timedelta(hours=8))
    dt = dt.replace(tzinfo=tz_utc8)

    # 转 UTC
    dt_utc = dt.astimezone(timezone.utc)

    return int(dt_utc.timestamp() * 1000)


def cal_balance_now(pos_size, pos_price, trade):
    """
    输入成交记录 持仓数量 持仓均价 手续费(/USD) 输出 本次利润和 新的持仓数量和持仓均价
    """
    fee = trade["fee"]
    # long position
    if pos_size > 0:
        # BUY OPEN
        if trade["side"] == "buy":
            old_volume = pos_price * pos_size
            pos_size += trade["size"]
            pos_price = (trade["size"] * trade["price"] + old_volume) / pos_size
            pnl = -fee
        # SELL CLOSE OR SELL CLOSE AND SELL OPEN
        else:
            # SELL CLOSE AND SELL OPEN
            if trade["size"] > pos_size:
                pnl = (trade["price"] - pos_price) * pos_size - fee
                pos_size -= trade["size"]
                pos_price = trade["price"]
            # SELL CLOSE
            else:
                pos_size -= trade["size"]
                pnl = (trade["price"] - pos_price) * trade["size"] - fee
    # short position or no position
    else:
        if trade["side"] == "buy":
            # BUY CLOSE AND BUY OPEN
            if trade["size"] > -pos_size:
                if pos_size:
                    pnl = (pos_price - trade["price"]) * -pos_size - fee
                else:
                    pnl = -fee
                pos_size += trade["size"]
                pos_price = trade["price"]
            # BUY CLOSE
            else:
                pos_size += trade["size"]
                pnl = (pos_price - trade["price"]) * trade["size"] - fee
        # SELL OPEN
        else:
            if pos_size:
                old_volume = pos_price * -pos_size
                pos_size -= trade["size"]
                pos_price = (trade["size"] * trade["price"] + old_volume) / -pos_size
            else:
                pos_size -= trade["size"]
                pos_price = trade["price"]
            pnl = -fee
    return pos_size, pos_price, pnl


def cal_trade(symbol, posData, tradeData):
    """
    将交易所的成交格式转换成计算利润的统一格式
    """

    price = float(tradeData['price'])
    size = abs(float(tradeData['qty']))
    commissionAsset = tradeData['commissionAsset'] 
    if commissionAsset == "USDT":
        fee = float(tradeData["commission"])
    else:
        fee = 0
    side = "buy" if tradeData["side"] == "BUY" else "sell"
    trade = {
        "size": size,
        "price": price,
        "fee": fee,
        "side": side
    }
    (
        posData[symbol]['pos'],
        posData[symbol]['ave_price'],
        pnl
    ) = cal_balance_now(
        pos_size = posData[symbol]['pos'],
        pos_price = posData[symbol]['ave_price'],
        trade = trade
    )
    posData[symbol]['pnl'] += pnl

def get_trades():
    """获取成交记录并且计算利润"""


    posData = {}

    # 由于binance获取成交记录的接口必须填交易对名称，无法获取所有交易对的成交，需要通过tzquant开放的精度接口获取所有的交易对名称
    symbols = []
    url = "https://api.tzquant.top/api/v2/precision"
    request_data = {"platform": 'binance_swap_u'}
    response = requests.get(url, params=request_data, timeout=15)
    if response.status_code == 200:
        for symbol in response.json()['data']:
            # 排除交割合约的交易对
            if '_' in symbol:
                continue
            symbols.append(symbol.upper())

    startTimeStamp = to_timestamp_ms(startTime)

    # 从binance获取成交记录
    binanceTrades = []
    for symbol in symbols:
        posData[symbol] = {
            'pos': 0,
            'ave_price': 0,
            'pnl': 0
        }
        endTimeStamp = to_timestamp_ms(endTime)
        allTrades = []
        while True:
            response = binanceApi.get_um_trades(symbol=symbol, endTime=endTimeStamp, limit=1000)
            if response.status_code == 200:
                tmpTrades = response.json()
                sortedTrades = sorted(
                    tmpTrades, key=lambda x: x["id"], reverse=True
                )
                if len(sortedTrades) == 0:
                    endTimeStamp -= 604800000
                for trade in sortedTrades:
                    allTrades.append(trade)
                    endTimeStamp = int(trade['time']) - 1
            else:
                print(f"获取{symbol}成交记录接口出错: {response.json()}")
            if endTimeStamp <= startTimeStamp:
                break
        allTrades.reverse()
        for trade in allTrades:
            cal_trade(symbol, posData, trade)

    allPnl = 0

    for symbol in posData:
        allPnl += posData[symbol]['pnl']
    print(f"所有交易对开平仓利润为: {allPnl}")


def get_trans():
    """
    获取出入金记录计算账户本金
    """

    startTimeStamp = to_timestamp_ms(startTime)

    # 获取u本位账户的出入金流水记录
    endTimeStamp = to_timestamp_ms(endTime)
    swapTransList = []
    while True:
        response = binanceApi.get_um_income(endTime=endTimeStamp, incomeType='TRANSFER')
        if response.status_code == 200:
            transList = response.json()
            sortedList = sorted(
                transList, key=lambda x: x["tranId"], reverse=True
            )
            if len(sortedList) == 0:
                endTimeStamp -= 604800000
            for trans in sortedList:
                endTimeStamp = trans['time'] - 1
                if trans['asset'] != 'USDT':
                    continue
                swapTransList.append(trans)
        else:
            print(f"获取u本位账户的出入金: {response.json()}")
        if endTimeStamp <= startTimeStamp:
            break

    swapTransList.reverse()

    swapUsdt = 0
    for trans in swapTransList:
        swapUsdt += float(trans['income'])

    print(f"u本位账户出入金总和为: {swapUsdt}")

    # 获取杠杆账户的出入金流水记录
    endTimeStamp = to_timestamp_ms(endTime)
    spotTransList = []
    while True:
        response = binanceApi.get_spot_margin_transfer(asset='USDT', endTime=endTimeStamp)
        if response.status_code == 200:
            transList = response.json()['rows']
            sortedList = sorted(
                transList, key=lambda x: int(x["txId"]), reverse=True
            )
            if len(sortedList) == 0:
                endTimeStamp -= 604800000
            for trans in sortedList:
                endTimeStamp = trans['timestamp'] - 1
                spotTransList.append(trans)
        else:
            print(f"获取杠杆账户的出入金: {response.json()}")
        if endTimeStamp <= startTimeStamp:
            break

    spotTransList.reverse()

    spotUsdt = 0
    for trans in spotTransList:
        if trans['type'] == 'ROLL_IN':
            spotUsdt += float(trans['amount'])
        else:
            spotUsdt -= float(trans['amount'])
    
    print(f"全仓杠杆账户出入金总和为: {spotUsdt}")

if __name__ == '__main__':
    get_trades()
    get_trans()
