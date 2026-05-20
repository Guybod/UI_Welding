# chinese-hershey-font 黑体单线数据（本地放置）

来源：[LingDong-/chinese-hershey-font](https://github.com/LingDong-/chinese-hershey-font)

## 推荐文件

| 文件 | 说明 |
|------|------|
| `STRK-Heiti.json` | 从 **思源黑体 / Source Han Sans** 派生的单线折线（约 2 万汉字） |

下载地址（约 9.8MB）：

```text
https://raw.githubusercontent.com/LingDong-/chinese-hershey-font/master/dist/json/STRK-Heiti.json
```

放置为：

```text
third_party/chinese-hershey-font/STRK-Heiti.json
```

## 授权说明

- **STRK-Heiti** 由开源 **Source Han Sans（思源黑体）** 经算法提取单线，**不是**微软雅黑。
- **请勿**将微软雅黑（`msyh.ttc` 等）随仓库分发。
- 项目 POC 仅读取已生成的 JSON 折线，**运行时不对 TTF 做轮廓渲染**。
- 正式商用前请自行核对：Source Han Sans（SIL Open Font License）及 chinese-hershey-font 仓库许可。

## 坐标系

JSON 内点为 **0.0~1.0 归一化坐标**，**左上角为原点**，Y 轴向下（与 PIL 一致）。
