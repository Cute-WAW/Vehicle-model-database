import pandas as pd
import numpy as np

in_path = r"d:\BaiduNetdiskDownload\车型库映射\车型库映射\tests\cheyipai_more_car.csv"
df = pd.read_csv(in_path, encoding="gbk")

df.drop_duplicates(keep="first", inplace=True)

df["成交价格"] = df["成交价格"].replace("-", np.nan).replace("", np.nan)
df["成交价格"] = df["成交价格"].str.replace("万", "", regex=False)
df["成交价格"] = df["成交价格"].str.extract(r"([0-9]+(?:\.[0-9]+)?)")
df.dropna(subset=["成交价格"], inplace=True)
df["成交价格"] = df["成交价格"].astype(float)

df["车况"] = df["车况"].replace("-", np.nan).replace(" ", np.nan)
df.dropna(subset=["车况"], inplace=True)

df.reset_index(drop=True, inplace=True)

df["城市"] = df["城市"].replace("-", np.nan).replace(" ", np.nan)
df["城市"] = df["城市"].ffill()

df["行驶里程"] = df["行驶里程"].str.replace("万公里", "", regex=False)
df["行驶里程"] = df["行驶里程"].replace("-", np.nan).replace(" ", np.nan).replace("n", np.nan)
df["行驶里程"] = df["行驶里程"].str.extract(r"([0-9]+(?:\.[0-9]+)?)")
df.dropna(subset=["行驶里程"], inplace=True)
df["行驶里程"] = df["行驶里程"].astype(float)

df["颜色"] = df["颜色"].replace("-", np.nan).replace(" ", np.nan)
df["颜色"] = df["颜色"].ffill()

df["是否营运"] = df["是否营运"].replace("-", np.nan).replace(" ", np.nan)
df["是否营运"] = df["是否营运"].fillna("非营运")

df["成交时间"] = df["成交时间"].replace("-", np.nan).replace(" ", np.nan)
df["成交时间"] = df["成交时间"].fillna("6月30日")

df["车型"] = df["车型"].replace("-", np.nan).replace(" ", np.nan)
df.dropna(subset=["车型"], inplace=True)

df["上牌时间"] = df["上牌时间"].replace("-", np.nan).replace(" ", np.nan)
df.dropna(subset=["上牌时间"], inplace=True)

out_path = r"d:\BaiduNetdiskDownload\车型库映射\车型库映射\tests\cheyipai_more_data_clean.csv"
df.to_csv(out_path, index=False, encoding="gbk")
