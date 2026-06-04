# L-Agent

一个基于 LLM 的交互式 AI Coding Agent，采用 ReAct 循环架构，支持流式输出、工具调用、会话持久化和时间线回溯。

## 快速开始

### 安装

```bash
pip install -e .
```

### 配置

编辑 `workspace/config.yaml`（或 `~/.l-agent/config.yaml`）：

```yaml
llm:
  api_base: "https://api.deepseek.com"
  api_key: "your-api-key"
  model: "deepseek-chat"
  temperature: 0.7
  max_tokens: 4096

budget:
  max_iterations: 25
  max_tokens: 200000

agent:
  guidance_file: "knowledge/guidance.md"
```

### 启动

```bash
l-agent                        # 新建会话
l-agent --session <id>         # 恢复历史会话
l-agent --config path.yaml     # 指定配置文件
l-agent --db path/to/db        # 指定 SQLite 路径
```

## 内置工具

| 工具 | 说明 | 审批策略 |
|------|------|---------|
| `think` | 思考推理 | 自动 |
| `read_file` | 读取文件 | 自动 |
| `write_file` | 写入文件 | 需确认 |
| `list_directory` | 列出目录 | 自动 |
| `search_file` | 搜索文件内容 | 自动 |
| `terminal` | 执行终端命令 | 需确认 |
| `web_search` | 网络搜索 | 自动 |
| `web_fetch` | 获取网页内容 | 自动 |

## 交互命令

在 `❯` 提示符下输入斜杠命令：

| 命令 | 说明 |
|------|------|
| `/new` | 创建新会话 |
| `/list` | 列出并选择历史会话 |
| `/resume <id>` | 恢复指定会话 |
| `/rewind` | 回溯到历史检查点 |
| `/status` | 查看当前会话状态 |

## 架构概览

```
agent/
├── cli/             # CLI 入口、渲染、审批交互、斜杠命令
├── config/          # YAML 配置加载
├── core/            # AgentRunner（ReAct 循环）、Factory、Context
├── actions/         # model_call / tool_call 具体执行逻辑
├── steps/           # 生命周期各阶段的 Step（before/after model/tool/agent）
├── middleware/      # 横切关注点（预算、审计、审批、结果截断）
├── llm/             # OpenAI 兼容的 LLM 客户端
├── tools/           # 工具定义、注册、分发
├── timeline/        # 会话时间线、Resume、Rewind
├── storage/         # SQLite 持久化
├── memory/          # 记忆接口
└── events.py        # 事件类型定义
```

### 运行流程

1. CLI 启动 → 加载配置 → Factory 组装 Runner
2. 用户输入 → 构建 RunContext → 进入 ReAct 循环
3. `before_model` → LLM 流式调用 → `after_model`
4. 若有 tool_call → `before_tool` → 审批 → 执行工具 → `after_tool` → 回到 3
5. 若为最终答案 → 退出循环，渲染结果

## 开发

```bash
# 运行测试
pip install pytest pytest-asyncio
pytest

# 项目结构要求 Python >= 3.11
```

## License

MIT
