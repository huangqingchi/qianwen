# 模型评测：一项一个文件夹

七个项目文件夹各有自己的 `test.py` 和 `README.md`。测试时可只运行指定项目，报告也只保存这个项目的结果。

## 最简单的运行方法

在项目根目录的 PowerShell 里：

```powershell
python .\评测\run.py --list
python .\评测\run.py --item 固定题集精度 --profile smoke
python .\评测\run.py --item 长上下文 --profile smoke
```

不写 `--item` 才会依次运行全部七项：

```powershell
python .\评测\run.py --profile smoke
```

结果保存在 `评测/结果/<运行时间>/`。其中 `总览.md` 只列各项分数；每个项目都有独立的 `报告.md` 和 `结果.json`。每次运行都会新建目录，旧结果不会被覆盖。`--output-dir` 可指定结果位置。

默认沿用项目根目录 `eval_config.json` 中的模型和档位；可以用 `--model`、`--base-url` 和环境变量 `DASHSCOPE_BASE_URL` 覆盖。运行前必须设置 `DASHSCOPE_API_KEY`。当前默认档位 `smoke` 的题数和请求次数较少；`standard`、`extended` 会增加测试量。长上下文可单测一个指定长度：

```powershell
python .\评测\run.py --item 长上下文 --only-long-context --context-words 7000
```

## 怎么看分数

- 有明确对错的用例按 `通过数 / (通过数 + 失败数) × 100` 得到**本地用例分数**。每项单独计算，不合并成一个总分。
- “待确认”表示服务端数据不足以确认，例如隐式缓存未命中；不计入分数。
- “已测量”表示只拿到了性能数值，尚无判级阈值；不计入分数。请求失败仍记为“失败”。
- 这些是本地测试分数，不是三张照片中可能列出的 A 级或其他官方等级。收到具体评分标准后再逐项对齐阈值。
