from FinMind.data import DataLoader
import datetime
import requests
import pandas as pd

api = DataLoader()

# 抓取所有股票清單並篩選（排除ETF）
stock_info = api.taiwan_stock_info()
stock_info = stock_info[~stock_info["industry_category"].str.contains("ETF|基金", na=False)]
stock_info = stock_info[stock_info["stock_id"].str.match(r"^\d{4}$")]
valid_stocks = set(stock_info["stock_id"].tolist())

# 抓所有上市股票當日成交資料
url = "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY_ALL?response=json"
res = requests.get(url)
data = res.json()

# 整理成 DataFrame
df = pd.DataFrame(data["data"], columns=data["fields"])

# 只保留普通股（排除ETF）
df = df[df["證券代號"].isin(valid_stocks)]

# 成交金額轉成數字（原本是字串含逗號）
df["成交金額"] = df["成交金額"].str.replace(",", "").astype(float)

# 排序取前100
top100 = df.sort_values("成交金額", ascending=False).head(100)
top100 = top100.reset_index(drop=True)

top100["成交金額(億)"] = (top100["成交金額"] / 1e8).round(2)
print(top100[["證券代號", "證券名稱", "成交金額(億)", "收盤價"]].to_string())