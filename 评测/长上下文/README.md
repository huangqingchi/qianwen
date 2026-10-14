# 长上下文

在合成文本的前、中、后放三个标记；按顺序找回全部标记才通过。每个测试长度各占一个本地用例。报告记录服务端返回的真实输入 token 数；填充词数不等于 token 数。

运行：`python .\评测\run.py --item 长上下文 --profile smoke`

指定单个长度：`python .\评测\run.py --item 长上下文 --only-long-context --context-words 7000`
