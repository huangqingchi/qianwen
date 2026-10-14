# 百炼模型评测

这是一个独立的 Python 项目，按七个项目分别测试阿里云百炼的 OpenAI 兼容接口。每项测试的请求、判定方法和边界都直接写在对应的 `评测/<项目>/test.py` 中文注释中。

当前默认模型为 `glm-5.3`。项目目录名是 `qianwen`，但实际测试哪个模型由 `eval_config.json` 或 `--model` 决定。

## 准备

需要 Python 3.10 或更新版本。脚本只用 Python 标准库；运行本地自动测试需要 `pytest`。

在项目根目录新建 `本地密钥.txt`，文件内容只写你的百炼 API Key（一行即可）。此文件已加入 `.gitignore`，不会上传到 GitHub。也可以设置 `DASHSCOPE_API_KEY` 环境变量来覆盖文件中的密钥。

密钥不会保存在源码或报告中。如果密钥所在地域不同，可额外设置 `DASHSCOPE_BASE_URL`。

## 运行

先进入项目根目录。项目可以放在任意位置；脚本按自身位置查找配置、题集和本地密钥。

Windows PowerShell：

```powershell
cd Z:\qianwen
python -m 评测.run --list
python -m 评测.run --item 固定题集精度 --profile smoke
python -m 评测.run --profile smoke
```

Ubuntu Bash（将路径换成实际项目位置）：

```bash
cd /path/to/qianwen
python3 -m 评测.run --list
python3 -m 评测.run --item 固定题集精度 --profile smoke
python3 -m 评测.run --profile smoke
```

如果用环境变量覆盖密钥，PowerShell 用 `$env:DASHSCOPE_API_KEY = '...'`，Bash 用 `export DASHSCOPE_API_KEY='...'`。

详细参数、独立计分和结果目录见 [评测说明](评测/README.md)。单独手工聊天可在项目根目录运行 `python -m qwen_chat "你好"`（Ubuntu 通常用 `python3`）。

结果写入项目内的 `评测/结果/<运行时间>/`，该目录不会提交到 Git。相对的 `--output-dir` 也以项目根目录为基准。现有分数是本地用例通过率，并不等于照片中的正式等级。
