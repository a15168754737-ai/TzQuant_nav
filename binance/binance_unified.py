import re
import time
import hmac
import urllib
import hashlib
import requests
from datetime import datetime


class BinanceUnifiedClient:
    def __init__(self, api_key, api_secret):
        self.base_url = 'https://papi.binance.com'
        self.api_key = api_key
        self.api_secret = api_secret
        self._chinese_pattern = re.compile(r'[\u4e00-\u9fff]')

    def sign_request(self, params):
        def needs_encoding(value):
            return self._chinese_pattern.search(str(value)) is not None
        query_string = '&'.join([f"{k}={urllib.parse.quote(str(v), safe='') if k == 'symbol' and needs_encoding(v) else str(v)}" for k, v in params.items()])
        signature = hmac.new(self.api_secret.encode(), query_string.encode(), hashlib.sha256).hexdigest()
        params['signature'] = signature
        return params

    def get_headers(self):
        return {
            'X-MBX-APIKEY': self.api_key
        }

    def sleep_until_next_minute(self):
        """
        防止触发封禁
        """
        now = datetime.now()
        # 计算当前秒和微秒
        current_second = now.second
        current_microsecond = now.microsecond
        # 计算到下一分钟开始的剩余时间
        remaining_time = 60 - current_second - current_microsecond / 1000000.0
        time.sleep(remaining_time)

    def get_response(self, url, params):
        response = requests.get(url, headers=self.get_headers(), params=self.sign_request(params))
        if response.headers.get('x-mbx-used-weight-1m'):
            if int(response.headers['x-mbx-used-weight-1m']) >= 2300:
                self.sleep_until_next_minute()
        if response.headers.get('X-SAPI-USED-IP-WEIGHT-1M'):
            if int(response.headers['X-SAPI-USED-IP-WEIGHT-1M']) >= 2300:
                self.sleep_until_next_minute()
        return response
    
    def get_spot_margin_transfer(self, asset, endTime):
        """获取统一账户杠杆转入转出"""
        url = 'https://api4.binance.com' + '/sapi/v1/margin/transfer'
        params = {
            'asset': asset,
            "endTime": endTime,
            "size": 100,
            'timestamp': int(time.time() * 1000)
        }
        return self.get_response(url, params)

    def get_um_trades(self, endTime, limit):
        """查询U本位合约成交记录"""
        url = self.base_url + '/papi/v1/um/userTrades'
        params = {
            'endTime': endTime,
            "limit": limit,
            'timestamp': int(time.time() * 1000)
        }
        return self.get_response(url, params)

    def get_um_income(self, endTime, incomeType, limit=1000):
        """查询U本位转入转出记录"""
        url = self.base_url + '/papi/v1/um/income'
        params = {
            'endTime': endTime,
            'incomeType': incomeType,
            "limit": limit,
            'timestamp': int(time.time() * 1000)
        }
        return self.get_response(url, params)

    def get_margin_trades(self, symbol, endTime, limit):
        """查询现货成交记录"""
        url = self.base_url + '/papi/v1/margin/myTrades'
        params = {
            'symbol': symbol,
            'endTime': endTime,
            "limit": limit,
            'timestamp': int(time.time() * 1000)
        }
        return self.get_response(url, params)