from datetime import datetime, timezone, timedelta

def generate_time_points(start_ts, end_ts, interval):
    """
    预处理快照时间线长度
    """
    start_dt = datetime.fromtimestamp(start_ts / 1000)
    end_dt = datetime.fromtimestamp(end_ts / 1000)

    minute = 30 if start_dt.minute <= 30 else 60
    start_dt = start_dt.replace(minute=minute, second=0, microsecond=0)

    minute = 30 if end_dt.minute <= 30 else 60
    end_dt = end_dt.replace(minute=minute, second=0, microsecond=0)

    startTimeDt = int(start_dt.timestamp() * 1000)
    endTimeDt = int(end_dt.timestamp() * 1000)
    startTimeDtLen = (endTimeDt - startTimeDt + interval - 1) // interval
    return startTimeDt, startTimeDtLen


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