# Novel Writer - 多智能体小说写作系统

一个基于 LangGraph 的多智能体系统，用于生成逻辑自洽的长篇小说。

## ✨ 特性

- **多智能体协作**: Director、Writer、Reviewer、Archivist 四个 Agent 各司其职
- **基于文件**: 使用 Markdown 文件管理角色、大纲、风格，简单直观
- **长期记忆**: 自动提取角色关系、伏笔、事件等信息，保持全文一致性
- **质量把控**: Reviewer 自动审核，不合格自动修改

---

## 🚀 快速开始

### 1. 安装

```bash
# 克隆项目
git clone <repo-url>
cd novel-writer

# 安装依赖（建议使用虚拟环境）
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -e .
```

### 2. 配置 API 密钥

```bash
# 复制配置模板
cp .env.example .env

# 编辑 .env 文件，填写你的 API 密钥
# 支持 OpenAI、DeepSeek、Anthropic 等
```

**.env 示例**:
```ini
# 选择一个填写即可
OPENAI_API_KEY=sk-xxx
DEEPSEEK_API_KEY=sk-xxx

# 可选：指定模型
LLM_MODEL=deepseek-chat
```

### 3. 创建小说项目

```bash
# 创建项目目录
mkdir 我的奇幻小说
cd 我的奇幻小说

# 添加模板文件
novel-writer add
```

这会生成三个文件：
- `roles.md` - 角色设定
- `outline.md` - 章节大纲
- `style.md` - 写作风格

### 4. 编辑设定文件

**编辑 `roles.md`** - 定义你的角色：
```markdown
## 李云飞

一位年轻的剑客，性格沉稳内敛。背负着家族的秘密，踏上寻找真相的道路。
身高七尺，面容俊朗，常着一袭青衫，腰佩长剑"破晓"。
```

**编辑 `outline.md`** - 写好每章大纲：
```markdown
## 第一章：离别

本章目标：介绍主角李云飞，展示他的家乡和日常，通过一封神秘来信引出冒险的开始。
主要场景：青云镇，李家宅院。
关键事件：收到亡父旧友的来信，决定离开家乡。
```

### 5. 开始生成

```bash
# 生成下一章（自动检测进度）
novel-writer write

# 或指定章节号
novel-writer write-c 1

# 批量生成
novel-writer write-n 10    # 生成接下来 10 章
novel-writer write-all     # 生成所有剩余章节
```

生成的章节保存在 `chapters/` 目录下。

---

## 📖 命令参考

| 命令 | 说明 | 示例 |
|------|------|------|
| `add` | 添加项目模板文件 | `novel-writer add` |
| `write` | 生成下一章 | `novel-writer write` |
| `write -c N` | 生成第 N 章 | `novel-writer write -c 5` |
| `write-c N` | 生成第 N 章（简写） | `novel-writer write-c 5` |
| `write-n N` | 生成接下来 N 章 | `novel-writer write-n 10` |
| `write-all` | 生成所有剩余章节 | `novel-writer write-all` |
| `status` | 查看项目进度 | `novel-writer status` |
| `read N` | 阅读第 N 章 | `novel-writer read 3` |
| `delete-c N` | 删除第 N 章 | `novel-writer delete-c 5` |

**通用选项**:
- `-p, --path` 指定项目目录（默认当前目录）
- `-r, --retries` 最大修改次数（默认 3）

---

## 🏗️ 项目结构

```
我的奇幻小说/
├── roles.md          # 角色设定
├── outline.md        # 章节大纲  
├── style.md          # 写作风格
├── chapters/         # 生成的章节
│   ├── 001.md
│   ├── 002.md
│   └── ...
└── .memory/          # 长期记忆（自动管理）
```

---

## 🤖 智能体架构

```
                     ┌─────────────┐
                     │  Director   │ ← 规划章节目标
                     └──────┬──────┘
                            ↓
                     ┌─────────────┐
                     │   Writer    │ ← 撰写正文
                     └──────┬──────┘
                            ↓
                     ┌─────────────┐
              retry ←│  Reviewer   │ ← 审核质量
                     └──────┬──────┘
                            ↓ pass
                     ┌─────────────┐
                     │  Archivist  │ ← 提取记忆
                     └─────────────┘
```

- **Director**: 根据大纲规划本章的具体目标和要点
- **Writer**: 结合角色设定、前文、记忆撰写正文
- **Reviewer**: 检查逻辑一致性、角色行为、情节连贯
- **Archivist**: 提取关键信息（人物关系、伏笔等）存入长期记忆

---

## 🔧 高级配置

### 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `LLM_MODEL` | 使用的模型 | `deepseek-chat` |
| `LLM_TEMPERATURE` | 生成温度 | `0.7` |
| `OPENAI_API_KEY` | OpenAI API 密钥 | - |
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥 | - |
| `ANTHROPIC_API_KEY` | Anthropic API 密钥 | - |

### 自定义服务端点

```ini
# .env
OPENAI_BASE_URL=https://your-proxy.com/v1
```

---

## 📝 常见问题

**Q: 生成的章节质量不好怎么办？**

A: 尝试以下方法：
1. 丰富 `roles.md` 中的角色描述
2. 在 `outline.md` 中写更详细的章节大纲
3. 在 `style.md` 中明确写作风格要求

**Q: 如何重新生成某一章？**

A: 先删除再重写：
```bash
novel-writer delete-c 5
novel-writer write-c 5
```

**Q: 支持哪些 LLM？**

A: 支持所有兼容 OpenAI API 的模型，包括：
- OpenAI (GPT-4, GPT-4o)
- DeepSeek
- Anthropic Claude
- 本地模型（通过 ollama 等）

---

## License

MIT
