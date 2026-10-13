# 阅笺 · 小说 RAG 问答

> 仓库：[github.com/zhichenou90-web/yuejian](https://github.com/zhichenou90-web/yuejian)

基于 **FastAPI + LangChain + DeepSeek + 智谱 Embedding** 的长篇小说问答系统。

上传网文 TXT → 按章切分 → 向量库 + BM25 → 混合检索 → Rerank → DeepSeek 流式回答。  
前端产品名 **阅笺**：阅读器 + 侧栏问答，答案附原文出处。

**请勿提交** `.env`、向量库、上传小说与简历等个人文件；配置请复制 `.env.example`。

## 技术栈

| 层 | 选型 |
|----|------|
| 对话 | DeepSeek（`deepseek-chat`） |
| Embedding / Rerank | 智谱 `embedding-3` / `rerank` |
| 向量库 | Chroma |
| 关键词 | jieba + rank-bm25（RRF） |
| 前端 | Vue 3 + Vite + TypeScript（阅读器布局） |

## 快速开始

### 1. 安装依赖

在 conda 环境中：

```bash
pip install -r requirements.txt
```

### 2. 配置密钥

复制 `.env.example` 为 `.env`：

```ini
LLM_API_KEY=你的DeepSeekKey
LLM_API_BASE=https://api.deepseek.com/v1
LLM_CHAT_MODEL=deepseek-chat

EMBEDDING_API_KEY=你的智谱Key
EMBEDDING_API_BASE=https://open.bigmodel.cn/api/paas/v4
EMBEDDING_MODEL=embedding-3
```

### 3. 启动后端

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

文档：http://127.0.0.1:8000/docs

### 4. 启动前端（Vite + Vue 3）

```bash
cd frontend
npm install
npm run dev
```

浏览器打开 http://127.0.0.1:5173（已代理 `/api` 到后端 `8000`）。

### 5. 离线入库（可选）

```bash
python scripts/ingest_book.py "D:\新建文件夹\我的26岁女房客 (1).txt"
```

长篇小说首次向量化可能需要数分钟。

## 切分策略

- 优先识别 `第N章：标题`、`第N回 标题` 等章节（网文与古典章回体）
- 章内 `chunk_size=1200`，`overlap=180`
- 命中章节过少时降级为固定窗口切分

同格式网文 / 章回体 TXT 可直接上传；无清晰章节的纯长文会降级切分。

## 首期范围

- 已做：上传、按章阅读、混合检索、Rerank、DeepSeek 流式问答
- 未做：溯源卡片、多用户鉴权、EPUB/PDF、Agent
