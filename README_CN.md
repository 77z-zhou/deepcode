# DeepCode 🐽 - 基于 LangChain 的 AI 编码助手

[English](README.md) | [中文](README_CN.md)

一款智能 AI 驱动的编码命令行工具，帮助您使用自然语言命令编写、分析和理解代码。

![Python](https://img.shields.io/badge/python-3.11+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

## 特性

- **AI 驱动的代码助手**：使用自然语言与代码库交互
- **人工审核批准**：在工具执行前审查并批准操作
- **标签式问题界面**：用于多步骤用户交互的精美 TUI：
  - 问题之间的标签导航
  - 进度指示器（"步骤 X / Y"）
  - 方向键导航（←→ 切换标签，↑↓ 选择选项）
  - 支持富 Markdown/代码预览的预览面板
  - 深色模式主题配蓝色高亮
  - 提交验证（必须回答所有问题）
  - "其他"选项的内联自定义输入（支持英文/中文）
- **丰富的终端 UI**：支持 Markdown 渲染和语法高亮的精美输出
- **多模型支持**：兼容 OpenAI API（OpenAI、DeepSeek 等）
- **可扩展的中间件系统**：通过中间件添加自定义行为
- **异步架构**：基于 asyncio 构建响应式交互

## 安装

### 前置要求

- Python 3.11 或更高版本
- [uv](https://github.com/astral-sh/uv)（推荐的包管理器）

### 使用 uv 安装

```bash
# 克隆仓库
git clone <your-repo-url>
cd deepcode

# 安装依赖
uv sync

# 或以开发模式安装
uv pip install -e .
```

### 使用 pip 安装

```bash
pip install -e .
```

## 快速开始

```bash
# 运行 deepcode
deepcode

# 或使用 Python
python -m deepcode
```

首次运行会提示您配置：
- API 提供商（OpenAI、DeepSeek 等）
- API 密钥
- 模型名称
- 工作区目录

## 使用方法

### 交互模式

启动 CLI 并与 Agent 对话：

```bash
deepcode
```

示例交互：

```
You: 读取 main.py 文件并总结它的功能

You: 为 parse_config 函数添加错误处理

You: 为 User 类创建测试

You: 哪些文件使用了 Database 连接？
```

### 内置命令

- `/help` - 显示帮助信息
- `/clear` - 清屏
- `/model` - 更换 AI 模型
- `/compact` - 压缩对话上下文
- `/cost` - 显示 API 使用成本
- `/exit` - 退出程序
- `/init` - 重新初始化配置

## 配置

配置存储在项目目录中。首次运行将引导您完成设置：

```python
# 示例配置结构
{
    "model": "gpt-4",           # 模型标识符
    "api_key": "sk-...",        # API 密钥
    "base_url": null,           # 自定义 API 基础 URL（可选）
    "workspace": ".",           # 工作目录
    "recursion_limit": 50,      # Agent 递归限制
    "skills_dir": ".claude/skills"  # 自定义技能目录
}
```

## 项目结构

```
deepcode/
├── deepcode/
│   ├── __init__.py
│   ├── __main__.py           # 入口点
│   ├── cli/                  # CLI 接口
│   │   ├── app.py            # 主 CLI 应用程序
│   │   ├── commands/         # 内置命令
│   │   └── utils.py          # TUI 组件（标签式界面）
│   ├── core/
│   │   ├── agent.py          # 主要 Agent 逻辑
│   │   ├── model.py          # 模型工厂
│   │   └── middleware/       # Agent 中间件
│   ├── config/               # 配置管理
│   └── bus/                  # 异步通信的消息总线
├── tests/                    # 测试套件
├── pyproject.toml           # 项目元数据
└── README.md
```

## 开发

### 运行测试

```bash
# 运行所有测试
pytest

# 运行测试并生成覆盖率报告
pytest --cov=deepcode
```

### 代码风格

本项目遵循标准 Python 约定并使用类型提示。

### 核心组件

- **标签式问题界面**（`deepcode/cli/utils.py`）：
  - `_present_user_questions()` - 主要 TUI 入口
  - 完整的 prompt_toolkit 实现，带自定义键绑定
  - 语法高亮的富 Markdown 预览

- **Agent**（`deepcode/core/agent.py`）：
  - 基于 LangGraph 的 Agent，集成 LangChain
  - 带进度回调的流式响应
  - HITL（人工审核）支持

- **消息总线**（`deepcode/bus/`）：
  - 入站/出站消息的异步发布/订阅
  - 协调 CLI 和 Agent 之间的通信

## 依赖

- **langchain** - Agent 框架
- **langgraph** - Agent 编排
- **prompt_toolkit** - 终端 UI 框架
- **rich** - 富文本和格式化
- **typer** - CLI 框架
- **pydantic** - 数据验证
- **loguru** - 日志记录
- **questionary** - 交互式提示

## 许可证

MIT License - 详见 LICENSE 文件

## 贡献

欢迎贡献！请随时提交 Pull Request。

## 致谢

构建于：
- [LangChain](https://github.com/langchain-ai/langchain) - AI Agent 框架
- [prompt_toolkit](https://github.com/prompt-toolkit/python-prompt-toolkit) - 终端 UI
- [Rich](https://github.com/Textualize/rich) - 终端格式化
