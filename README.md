# Trading Profit Calculator

一个用于从交易所获取成交记录与资金流水，并计算账户利润与本金变化的工具。

---

## 项目简介

本项目主要用于：

* 从交易所获取 **成交记录（trades）**
* 获取 **出入金记录（deposit / withdrawal）**
* 统一数据结构进行处理
* 计算：
  * 持仓
  * 利润
  * 未实现盈亏
  * 净值曲线
  * 本金变化

适用于账户对账。

---

## 项目结构

```
.
├── binance                   #  bianance
|   |── binance_unified.py    #  交易所接口封装
|   |── check.py              #  主程序：数据获取 + 利润计算
├── utils.py                  #  通用方法
├── requirements.txt          #  依赖列表
└── README.md
```

---

## 核心逻辑

### 数据来源

* 成交记录（Trades）
* 出入金记录（Deposit / Withdraw）

---

### 计算内容

* 当前持仓（pos）
* 累计收益（pnl）
* 未实现盈亏 （unrealizedPnl）
* 本金变化（含出入金）
* 净值曲线（nav）
---

## 安装依赖

```bash
pip install -r requirements.txt
```

---

## requirements.txt 示例

```
ccxt
matplotlib
```

## 使用方法

如果需要对账binance，需要在主目录下运行
```bash
python3 -m binance.check
```

---

## 配置说明

请在代码中配置交易所 API Key：

```python
onlyReadApiKey = "your_api_key"
onlyReadApiSecret = "your_secret_key"
startTime = "2026-02-08 21:00:00.000000"  # 对账开始的时间点UTC+8
endTime = "2026-04-14 17:00:00.000000"  # 对账结束的时间点UTC+8
interval = 1800000  # 对账的时间颗粒度, 单位为ms
```

建议：

* 使用只读权限 API Key
* 不要提交到代码仓库

---

## 交易所接口说明

`binance_unified.py` 负责：

* 封装 Binance API
* 签名请求（HMAC）
* 统一返回数据格式

支持扩展：

* 其他交易所（Gate / OKX 等）
* 多账户管理

---

## 注意事项

* 时间统一使用 UTC 或 UTC+8（避免误差）
* API 有频率限制，请做好限速处理

---
