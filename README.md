# Novel Writer - 多智能体小说写作系统

一个基于 LangGraph 的多智能体系统，用于生成逻辑自洽的长篇小说。

## 特性

- **Director Agent**: 控制整体剧情走向
- **Plotter Agent**: 生成章节大纲
- **Writer Agent**: 撰写正文内容
- **Reviewer Agent**: 检查连贯性和一致性
- **Archivist Agent**: 管理记忆和状态

## 安装

```bash
cd novel-writer
pip install -e .
```

## 配置

复制 `.env.example` 到 `.env` 并填写 API 密钥：

```bash
cp .env.example .env
```

## 使用

```bash
# 创建新小说
novel-writer init "我的奇幻小说" --genre fantasy

# 生成章节
novel-writer write-chapter 1 --goal "主角发现古老的预言"

# 查看状态
novel-writer status
```

## 架构

```
Director -> Plotter -> ContextBuilder -> Writer -> Reviewer
                                           ↑         ↓
                                           └─ retry ─┘
                                                  ↓ pass
                                             Archivist
```

## License

MIT
