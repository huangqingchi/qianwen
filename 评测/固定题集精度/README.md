# 固定题集精度

`smoke` 运行项目根目录 `eval_cases.json` 的 8 道本地题。`standard` 增加 12 道 GSM8K 固定样本，`extended` 增加 20 道。逐题判对错，分数为答对题数占已测题数的百分比。GSM8K 抽样分数不等于完整数据集成绩。

运行：`python .\评测\run.py --item 固定题集精度 --profile smoke`
