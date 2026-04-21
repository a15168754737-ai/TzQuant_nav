import csv
import ccxt
import logging
import binance.binance_unified as binance_unified
from copy import deepcopy
import matplotlib.pyplot as plt
from datetime import datetime, timezone, timedelta

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    filename=f"./binance/binance.log",
    filemode="a"  # a=追加，w=覆盖
)


from utils import (
    cal_balance_now,
    to_timestamp_ms,
    generate_time_points
)

onlyReadApiKey = "xxx"
onlyReadApiSecret = 'xxx'

startTime = "2026-02-08 21:00:00.000000"  # 对账开始的时间点UTC+8
endTime = "2026-04-14 17:00:00.000000"  # 对账结束的时间点UTC+8
interval = 1800000  # 对账的颗粒度, 单位为ms

binanceApi = binance_unified.BinanceUnifiedClient(onlyReadApiKey, onlyReadApiSecret)

# # 初始化ccxt用于获取k线
exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': {'defaultType': 'future'}
})


def get_full_ohlcv(symbol, start_ts, end_ts, timeframe='30m'):
    """
    拉取完整 3个月k线
    """
    all_data = []
    since = start_ts
    end_ts = ((end_ts + interval - 1) // interval) * interval

    while since < end_ts:

        ohlcv = exchange.fetch_ohlcv(
            symbol.replace('USDT', '/USDT'),
            timeframe=timeframe,
            since=since,
            limit=1000
        )

        if not ohlcv:
            break

        all_data.extend(ohlcv)

        since = ohlcv[-1][0] + 1

    price_map = {}

    for k in all_data:
        ts = k[0]
        close = k[4]

        if start_ts <= ts <= end_ts:
            price_map[ts] = close
    
    return price_map

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

    startTimeStamp = to_timestamp_ms(startTime)
    endTimeStamp = to_timestamp_ms(endTime)

    (startTimeDt, startTimeDtLen) = generate_time_points(startTimeStamp, endTimeStamp, interval)

    # 从binance获取成交记录并且记录快照
    binanceTrades = []
    existSymbols = set()
    snapshotPositions = {}

    logging.info(f"开始获取成交记录")
    while True:
        response = binanceApi.get_um_trades(endTime=endTimeStamp, limit=1000)
        if response.status_code == 200:
            tmpTrades = response.json()
            sortedTrades = sorted(
                tmpTrades, key=lambda x: x["time"], reverse=True
            )
            if len(sortedTrades) == 0:
                endTimeStamp -= 604800000
            for trade in sortedTrades:
                symbol = trade['symbol']
                if symbol not in existSymbols:
                    existSymbols.add(symbol)
                    snapshotPositions[symbol] = [{
                        'pos': 0,
                        'ave_price': 0,
                        'pnl': 0
                    } for i in range(startTimeDtLen)]
                endTimeStamp = int(trade['time']) - 1
                binanceTrades.append(trade)
        else:
            logging.error(f"获取成交记录接口出错: {response.json()}")
        if endTimeStamp <= startTimeStamp:
            break

    kline_cache = {}
    startTimeStamp = to_timestamp_ms(startTime)
    endTimeStamp = to_timestamp_ms(endTime)

    for symbol in snapshotPositions:
        logging.info(f"开始获取 {symbol} k线数据")
        kline_cache[symbol] = get_full_ohlcv(symbol, startTimeStamp, endTimeStamp)
    
    binanceTrades.reverse()

    logging.info(f"开始生成持仓快照")

    for trade in binanceTrades:
        symbol = trade['symbol']
        if symbol not in posData:
            posData[symbol] = {
                'pos': 0,
                'ave_price': 0,
                'pnl': 0
            }
        cal_trade(symbol, posData, trade)
        if int(trade['time']) <= startTimeDt:
            snapshotIndex = 0
        else:
            snapshotIndex = (int(trade['time']) - startTimeDt + interval - 1) // interval
        snapshotPositions[symbol][snapshotIndex] = deepcopy(posData[symbol])

    pnl = {}
    
    logging.info(f"开始计算未实现盈亏和开平仓利润")

    for symbol in snapshotPositions:
        nowPos = {
            'pos': 0,
            'ave_price': 0,
            'pnl': 0
        }
        for index in range(len(snapshotPositions[symbol])):
            nowTimestamp = startTimeDt + interval * index
            if pnl.get(nowTimestamp) is None:
                pnl[nowTimestamp] = {
                    'pnl': 0,
                    'unrealizedPnl': 0
                }
            if snapshotPositions[symbol][index]['pos'] != 0:
                nowPos = deepcopy(snapshotPositions[symbol][index])
            else:
                snapshotPositions[symbol][index] = deepcopy(nowPos)
            # continue
            if kline_cache[symbol].get(nowTimestamp) is None:
                continue
            else:
                close = kline_cache[symbol].get(nowTimestamp)
            pnl[nowTimestamp]['pnl'] += snapshotPositions[symbol][index]['pnl']
            pnl[nowTimestamp]['unrealizedPnl'] += snapshotPositions[symbol][index]['pos'] * (close - snapshotPositions[symbol][index]['ave_price'])

    
    logging.info(f"保存持仓快照到文件中")

    with open(f'./binance/positionSnapshot.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        csv_head = ['datetime']
        for symbol in snapshotPositions:
            csv_head.append(symbol)
        writer.writerow(csv_head)
        for index in range(startTimeDtLen):
            nowTimestamp = startTimeDt + interval * index
            newRow = [""f"{datetime.fromtimestamp(nowTimestamp / 1000, timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S.%f')}"""]
            for symbol in snapshotPositions:
                newRow.append(snapshotPositions[symbol][index]['pos'])
            writer.writerow(newRow)

    allPnl = 0

    for symbol in posData:
        allPnl += posData[symbol]['pnl']
    logging.info(f"所有交易对开平仓利润为: {allPnl}")

    return pnl


def get_trans():
    """
    获取出入金记录计算账户本金
    """

    logging.info(f"开始获取账户出入金记录")

    startTimeStamp = to_timestamp_ms(startTime)
    endTimeStamp = to_timestamp_ms(endTime)

    (startTimeDt, startTimeDtLen) = generate_time_points(startTimeStamp, endTimeStamp, interval)

    allTransStream = []

    # 获取u本位账户的出入金流水记录
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
                tmpTrnas = {
                    "time": trans['time'],
                    "amount": trans['income']
                }
                allTransStream.append(tmpTrnas)
        else:
            logging.error(f"获取u本位账户的出入金接口出错: {response.json()}")
        if endTimeStamp <= startTimeStamp:
            break

    swapTransList.reverse()

    swapUsdt = 0
    for trans in swapTransList:
        swapUsdt += float(trans['income'])

    logging.info(f"u本位账户出入金总和为: {swapUsdt}")

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
                tmpTrnas = {
                    "time": trans['timestamp'],
                    "amount": float(trans['amount']) if trans['type'] == 'ROLL_IN' else -float(trans['amount'])
                }
                allTransStream.append(tmpTrnas)
        else:
            logging.error(f"获取杠杆账户的出入金接口出错: {response.json()}")
        if endTimeStamp <= startTimeStamp:
            break

    spotTransList.reverse()

    spotUsdt = 0
    for trans in spotTransList:
        if trans['type'] == 'ROLL_IN':
            spotUsdt += float(trans['amount'])
        else:
            spotUsdt -= float(trans['amount'])
    
    logging.info(f"全仓杠杆账户出入金总和为: {spotUsdt}")

    sortedTransStream = sorted(
        allTransStream, key=lambda x: x["time"], reverse=False
    )

    principal = [0] * startTimeDtLen
    
    nowPrincipal = 0

    logging.info(f"开始生成账户本金快照")

    for trans in sortedTransStream:
        nowPrincipal += float(trans['amount'])
        nowTime = int(trans['time'])
        if nowTime <= startTimeDt:
            snapshotIndex = 0
        else:
            snapshotIndex = (nowTime - startTimeDt + interval - 1) // interval
        principal[snapshotIndex] = nowPrincipal

    prePrincipal = 0

    for index in range(startTimeDtLen):
        if principal[index] != 0:
            prePrincipal = principal[index]
        else:
            principal[index] = prePrincipal
    
    principalSnapshot = {}

    for index in range(startTimeDtLen):
        nowTimestamp = startTimeDt + interval * index
        principalSnapshot[nowTimestamp] = principal[index]
    
    return principalSnapshot

if __name__ == '__main__':
    pnlSnapshot = get_trades()
    principalSnapshot = get_trans()

    logging.info(f"开始计算nav曲线")
    nav = {}
    nav_csv = {}
    shares = 0
    assets = 0
    preCapital = 0
    preAssets = 0

    for timeStamp in principalSnapshot:
        capital = principalSnapshot[timeStamp]
        if len(nav) > 0 and abs(capital - preCapital) >= 1000:
            deltaCapital = capital - preCapital
            preNav = preAssets / shares if shares > 0 else 1.0
            deltaShares = deltaCapital / preNav if preNav > 0 else 0
            shares += deltaShares
        preCapital = capital
        preAssets = pnlSnapshot[timeStamp]['pnl'] + pnlSnapshot[timeStamp]['unrealizedPnl'] + capital
        nav[timeStamp] = preAssets / shares if shares > 0 else 1.0
        nav_csv[timeStamp] = {
            'nav': round(nav[timeStamp], 6),
            'assets': round(preAssets, 2)
        }
    
    logging.info(f"保存净值和资产快照到文件中")
    with open(f'./binance/navSnapshot.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        csv_head = ['datetime', 'nav', 'assets']
        writer.writerow(csv_head)
        for timeStamp in nav_csv:
            newRow = [
                ""f"{datetime.fromtimestamp(timeStamp / 1000, timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S.%f')}""",
                nav_csv[timeStamp]['nav'],
                nav_csv[timeStamp]['assets']
            ]
            writer.writerow(newRow)
    
    logging.info(f"开始生成nav的图表")
    sorted_items = sorted(nav.items())

    times = [datetime.fromtimestamp(ts / 1000) for ts, _ in sorted_items]
    values = [v for _, v in sorted_items]

    plt.figure(figsize=(12, 6))
    plt.plot(times, values)

    plt.title("NAV Curve")
    plt.xlabel("Time")
    plt.ylabel("NAV")
    plt.grid(True)

    plt.gcf().autofmt_xdate()

    plt.savefig("./binance/nav_curve.png", dpi=150)
