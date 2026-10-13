# 阅笺 · 小说 RAG 问答

> 仓库：[github.com/zhichenou90-web/yuejian](https://github.com/zhichenou90-web/yuejian)

基于 **FastAPI + LangChain + DeepSeek + 智谱 Embedding** 的长篇小说问答系统。

上传网文 TXT → 按章切分 → 向量库 + BM25 → 混合检索 → Rerank → DeepSeek 流式回答。  
前端产品名 **阅笺**：阅读器 + 侧栏问答，答案附原文出处。

### 入库格式说明（重要）

| 格式 | 状态 |
|------|------|
| **TXT** | 已支持（当前**唯一**知识库入库格式） |
| PDF / Word / EPUB / 图片等 | **未支持** |

请使用 `.txt` 上传；其它格式需自行转换为文本后再导入。  
仓库内已附四本公版示例小说，见 [`samples/`](./samples/)。

**请勿提交** `.env`、本地向量库 `chroma_db/`、运行时 `data/` 与简历等个人文件；配置请复制 `.env.example`。

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

### 5. 导入示例小说（可选）

```bash
python scripts/ingest_book.py samples/novels/西游记.txt
# 或：红楼梦.txt / 三国演义.txt / 水浒传.txt
```

也可在前端「导入 TXT 小说」。长篇首次向量化可能需要数分钟。

## 切分策略

- 优先识别 `第N章：标题`、`第N回 标题` 等章节（网文与古典章回体）
- 章内 `chunk_size=1200`，`overlap=180`
- 命中章节过少时降级为固定窗口切分

同格式网文 / 章回体 TXT 可直接上传；无清晰章节的纯长文会降级切分。

## 首期范围

- 已做：TXT 上传入库、按章阅读、混合检索、Rerank、LLM 质检二次检索、DeepSeek 流式问答与出处跳转
- 未做：PDF / 图片等非 TXT 入库、多用户鉴权、EPUB、独立 Agent 编排
