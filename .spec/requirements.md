需求：
1.csv的车型库文件
"D:\antigravity\price_evaluation\车型库映射\data\力洋车型库精简5.csv"

2.2个成交数据，文件分别如下
"D:\antigravity\price_evaluation\车型库映射\data\youxinpai_vehicles.csv"
"D:\antigravity\price_evaluation\车型库映射\data\有辆成交价格.csv"

现在是将 成交记录，映射到车型库

车型库中，映射用到的字段
brand,series,models,sales_name,year,level_id
例如
大众,帕萨特,帕萨特,1.4TSI 双离合 280TSI 星空精英版(改款),2023,CSV0214D0115
通过brand,series,models,sales_name,year，将成交数据的车，映射到车型库中对应的level_id

2个成交数据,映射用到的字段
"D:\antigravity\price_evaluation\车型库映射\data\有辆成交价格.csv"
通过 车型
例如 福克斯,福特 福克斯 2014款1.8 手自一体 酷白典藏版

"D:\antigravity\price_evaluation\车型库映射\data\youxinpai_vehicles.csv"
通过 车辆名称
例如 中升车源
宝马/X1/2016款 2.0T 自动 20Li豪华型前驱

映射的逻辑
1）去除噪音 中升车源，**车源
2) 车型库中sales_name，例如
燃油车和电动车有些不一样
燃油车：
1.4TSI 双离合 280TSI 星空精英版(改款) 
2.0T 自动 柴油版长风
1.6THP 手自一体 30THP 尊贵型
2.0TFSI 双离合 40TFSI 时尚型Plus
1.5 手动 标准型5座
1.5 手动 标准型5座
1.5 手动 标准型6-7座


电动车
增程Ultra版52kWh6座版
纯电Max版100kWh
Max四驱版5座
300 Lite探索版
400 Extra创新版
400 Extra创新版
400 Lite探索版
420KM 冠军版 超越型
420KM 冠军版 领先型
420KM 荣耀版 超越型
420KM 荣耀版 领先型



通常可以分解为 
排量：例如：2.0T，1.4TSI，1.5L 2,0 1.5
自动手动挡位：例如：自动，手动，手自一体，单离合，双离合
驱动：例如：四驱，后驱，两驱
款式： 例如：京彩款，**款
版式：例如：智尚版，智风版，豪华版，尊贵型，标准型5座，运动型，精英版，时尚型Plus，**版，**型，**型Plus
续航里程：400,420km


3）匹配逻辑：
车型库中brand > 车型库中的series > 驱动(如果有) > 自动手动档位 > 排量(续航里程) > 款式 > 版式 

要求：
1）车型库建索引，给一个车辆的名称，能快速匹配到车型库对应的level_id，速度一定要快
2）匹配精度的阈值可以配置，可以通过设置不同的阈值来调整返回的精度
3）后面可能接入更多的数据源，车辆名称的描述的语言风格，会有不同，实体类型不会差太多，对于实体识别的类型和匹配规则做到可以配置
4）要有测试，做一个测试集合，保证程序版本更新整体的稳定性
5）开发一个web界面，我可以输入一个车辆的名称，将实体识别，匹配，排序打分的过程输出，方便我调试
6）python环境安装在 "D:\antigravity\price_evaluation\venv_car_price_20251216"




