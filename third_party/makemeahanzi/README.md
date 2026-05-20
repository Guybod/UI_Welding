# MakeMeAHanzi 数据（本地放置，不入库大文件）

本目录供**绘图页 `hanzi_stroke`** 加载汉字 medians；`graphics.txt` 需本地放置，不入库大文件。

## 需要准备的文件

从 [MakeMeAHanzi](https://github.com/skishore/makemeahanzi) 获取：

- `graphics.txt` — JSONL，每行一个汉字，字段含 `character`、`medians`、`strokes`

将文件放到例如：

```text
third_party/makemeahanzi/graphics.txt
```

绘图页通过 `pipeline/hanzi/hanzi_data_loader.py` 读取；缺字时硬错误，无 TTF fallback。

## 说明

- **仅使用 `medians`**（笔画中线），不用 TTF，不对 strokes 做 skeletonize。
- `graphics.txt` 体积较大（约数十 MB），请勿在未确认仓库策略前提交到 Git。
