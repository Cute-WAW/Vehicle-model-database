import pandas as pd
import numpy as np

df = pd.read_csv("D:\software\cheyipai_data.csv",encoding='gbk')

# print(df.head())
# 删除无用列 df.drop(columns="Unnamed: 0",inplace=True)

# print(df.info())

# 删除重复行
# print(df[df.duplicated(keep=False)])
df.drop_duplicates(keep="first",inplace=True)



# 缺失值处理

df["成交价格"] = df["成交价格"].replace("-",np.nan).replace('',np.nan)

# 删除 '成交价格' 为空 (NaN) 的行
df.dropna(subset=['成交价格'], inplace=True)
df["成交价格"] = df["成交价格"].str.replace('万','')
df["成交价格"] = df["成交价格"].astype(float)

# 处理车况
df['车况'] = df['车况'].replace("-",np.nan).replace(' ',np.nan)
df.dropna(subset=['车况'], inplace=True)



# 重置索引
df.reset_index(drop=True, inplace=True)

# 处理城市
df["城市"] = df["城市"].replace("-",np.nan).replace(' ',np.nan)
df["城市"] = df["城市"].ffill()

# 处理行驶里程
df['行驶里程'] = df['行驶里程'].str.replace('万公里','')
df['行驶里程'] = df['行驶里程'].replace('-',np.nan).replace(' ',np.nan).replace('n',np.nan)
df.dropna(subset=['行驶里程'], inplace=True)
df["行驶里程"] = df["行驶里程"].astype(float)


# 处理颜色
df["颜色"] = df["颜色"].replace("-",np.nan).replace(' ',np.nan)
df["颜色"] = df["颜色"].ffill()

# 处理是否营运
df['是否营运'] = df['是否营运'].replace("-",np.nan).replace(' ',np.nan)
df['是否营运'] = df['是否营运'].fillna('非营运')

#成交时间
df['成交时间'] = df['成交时间'].replace('-',np.nan).replace(' ',np.nan)
df['成交时间'] = df['成交时间'].fillna('6月30日')

# 车型
df['车型'] = df['车型'].replace("-",np.nan).replace(' ',np.nan)
df.dropna(subset=['车型'], inplace=True)

# 上牌时间
df['上牌时间'] = df['上牌时间'].replace('-',np.nan).replace(' ',np.nan)
df.dropna(subset=['上牌时间'], inplace=True)

# 完成清洗并保存
df.to_csv("cheyipai_data_clean.csv",index=False,encoding='gbk')
