# 百炼模型评测

这是一个独立的 Python 项目，按七个项目分别测试阿里云百炼的 OpenAI 兼容接口。每项测试的请求、判定方法和边界都直接写在对应的 `评测/<项目>/test.py` 中文注释中。

当前默认模型为 `glm-5.3`。项目目录名是 `qianwen`，但实际测试哪个模型由 `eval_config.json` 或 `--model` 决定。

## 准备

需要 Python 3.10 或更新版本。脚本只用 Python 标准库；运行本地自动测试需要 `pytest`。

在 PowerShell 中设置百炼 API Key：

```powershell
$env:DASHSCOPE_API_KEY = '你的 API Key'
```

密钥不会保存在源码或报告中。如果密钥所在地域不同，可额外设置 `DASHSCOPE_BASE_URL`。

## 运行

进入本项目根目录 `Z:\qianwen`，然后运行：

```powershell
python .\评测\run.py --list
python .\评测\run.py --item 固定题集精度 --profile smoke
python .\评测\run.py --profile smoke
```

详细参数、独立计分和结果目录见 [评测说明](评测/README.md)。单独手工聊天可运行 `python .\qwen_chat.py "你好"`。

结果写入 `评测/结果/<运行时间>/`，该目录不会提交到 Git。现有分数是本地用例通过率，并不等于照片中的正式等级。
