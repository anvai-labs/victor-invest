# Architecture

**System design & components**

---

## 🏗️ Overall Flow

```
┌─────────────────────────────────────────────────────────────┐
│  YAML Workflows → Handlers → Tools → Domain Services        │
│                                                      ↓        │
│                                              Cache → Web UI   │
└─────────────────────────────────────────────────────────────┘
```

---

## 🧩 Components

### YAML Workflows

```
victor_invest/workflows/
├── quick.yaml           # Technical only
├── standard.yaml        # Technical + Fundamental
└── comprehensive.yaml   # All + LLM synthesis
```

### Handlers

```python
@handler_decorator("handler_name", vertical="investment")
@dataclass
class MyHandler(BaseHandler):
    async def execute(self, node, context, tool_registry):
        # Implementation
        return {"data": result}, 0
```

### Tools

```python
class MyTool(BaseTool):
    name = "my_tool"
    description = "What this tool does"

    async def execute(self, _exec_ctx=None, **kwargs) -> ToolResult:
        return ToolResult.create_success(data)
```

---

## 🗄️ Cache System

```
┌─────────────────────────────────────────────────────────────┐
│  L1: In-Memory (Python dict)   │  TTL: 5 minutes            │
│  L2: Disk (Parquet)            │  TTL: 24 hours            │
│  L3: Database (PostgreSQL)     │  Persistent               │
└─────────────────────────────────────────────────────────────┘
```

---

## 📊 Data Flow

```
User Input → YAML → Handlers → Tools → Domain Services
                                           ↓
                                   SEC Data + Market Data
                                           ↓
                                   Valuation Models
                                           ↓
                                   Results → Cache → UI
```

---

## 🔗 Related

- [Development](development.md) - Dev workflow
- [System Diagram](system-diagram.md) - Visual diagrams
