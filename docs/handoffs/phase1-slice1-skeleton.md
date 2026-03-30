# AI 切片交接单 — Phase 1 Slice 1: 项目骨架 + 数据模型

## 任务目标

- 本次只完成：搭建 Python 项目结构，实现 3 个数据模型、配置加载、SQLite 存储层、产品文件管理
- 交付完成的判断标准：所有模块可被 import，Storage 能建表，product_store 能创建/读取/更新产品

## 背景上下文

- 当前阶段：Phase 1（后端骨架），切片 1/N
- 与本切片直接相关的已有文件或模块：
  - `E:\即梦内容工厂\docs\ARCHITECTURE.md` — 架构设计（核心模型、状态机、目录结构）
  - `E:\即梦内容工厂\config.example.yaml` — 配置模板
  - `E:\自动AI视频工厂\src\auto_video_workflow\runtime\product_store.py` — 旧仓参考实现
  - `E:\自动AI视频工厂\src\auto_video_workflow\runtime\storage.py` — 旧仓参考实现
  - `E:\自动AI视频工厂\src\auto_video_workflow\models\task.py` — 旧仓参考实现
  - `E:\自动AI视频工厂\src\auto_video_workflow\models\account.py` — 旧仓参考实现
  - `E:\自动AI视频工厂\src\auto_video_workflow\config.py` — 旧仓参考实现
- 本次不解决的问题：Web 层、Provider 迁移、前端、调度器、收割器

## 允许修改文件

- `E:\即梦内容工厂\src\__init__.py` （新建）
- `E:\即梦内容工厂\src\models\__init__.py` （新建）
- `E:\即梦内容工厂\src\models\product.py` （新建）
- `E:\即梦内容工厂\src\models\task.py` （新建）
- `E:\即梦内容工厂\src\models\account.py` （新建）
- `E:\即梦内容工厂\src\runtime\__init__.py` （新建）
- `E:\即梦内容工厂\src\runtime\storage.py` （新建）
- `E:\即梦内容工厂\src\runtime\product_store.py` （新建）
- `E:\即梦内容工厂\src\config.py` （新建）
- `E:\即梦内容工厂\requirements.txt` （新建）

## 禁止修改文件

- `E:\即梦内容工厂\docs\ARCHITECTURE.md`
- `E:\即梦内容工厂\docs\STATUS.md`
- `E:\即梦内容工厂\config.example.yaml`
- `E:\即梦内容工厂\.gitignore`
- `E:\自动AI视频工厂\` 下任何文件（只读参考）

## 实现要求

### 必须保留的现有行为

无（全部新建）

### 必须新增的行为

**1. models/product.py**
```python
class PromptVariant(BaseModel):
    id: str          # 8位短码
    title: str
    prompt: str

class Product(BaseModel):
    name: str
    images: list[str]                    # 文件名列表
    prompt_variants: list[PromptVariant]
```
- 无 base_prompt 字段
- `ensure_variant_ids(variants)`: 缺少 id 时自动生成
- `compute_product_revision(data)`: SHA-256 前16位，参考旧仓实现

**2. models/task.py**
```python
class TaskStatus(StrEnum):
    PENDING = "pending"
    SUBMITTING = "submitting"
    GENERATING = "generating"      # 注意：旧仓叫 waiting_asset，新仓改为 generating
    DOWNLOADING = "downloading"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
```
Task 模型字段参照 ARCHITECTURE.md 第2节，精简为：
- task_id, product_name, variant_id, prompt, account_name
- status, result_video_path, error_message
- retry_count, max_retries
- created_at, updated_at
- duration_seconds (可选，默认从 config 读取，运营提交时可覆盖)

**3. models/account.py**
```python
class AccountStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"
    ERROR = "error"

class Account(BaseModel):
    name: str
    space_id: str
    cdp_url: str
    web_port: int
    status: AccountStatus = AccountStatus.ACTIVE
    generating_count: int = 0
    max_concurrent: int = 10
```

**4. config.py**
- 加载 config.yaml（Pydantic 模型）
- 所有路径可配置，不硬编码
- 包含 jimeng_defaults（mode, model, reference_type, aspect_ratio）
- duration_seconds 可选 5 或 15，默认 10

**5. runtime/storage.py**
- SQLite 连接管理
- `init_db()`: 建 tasks 表 + accounts 表
- `create_task()`, `get_task()`, `list_tasks()`, `update_task_status()`
- `sync_accounts()`, `get_accounts()`, `update_generating_count()`
- 参考旧仓但精简字段

**6. runtime/product_store.py**
- `list_products(data_dir)`: 扫描产品目录
- `get_product(data_dir, name)`: 读取 product.json
- `create_product(data_dir, name, variants, images)`: 创建产品目录 + product.json
- `update_product(data_dir, name, variants)`: 更新变体
- `compute_product_revision()`: 从旧仓迁移

**7. requirements.txt**
```
fastapi>=0.115.0
uvicorn>=0.34.0
pydantic>=2.11.0
PyYAML>=6.0.0
playwright>=1.52.0
python-multipart>=0.0.20
```

### 明确禁止的实现方式

- 不允许出现 base_prompt 字段
- 不允许出现 trace_token / JMID 相关逻辑
- 不允许出现 catalog.yaml 加载逻辑
- 不允许硬编码本地路径
- 不允许引入 requirements.txt 以外的依赖

## 验收标准

- [ ] 成功路径：`cd E:\即梦内容工厂 && python -c "from src.models.product import Product, PromptVariant, compute_product_revision; print('OK')"` 输出 OK
- [ ] 成功路径：`python -c "from src.models.task import Task, TaskStatus; print(TaskStatus.GENERATING)"` 输出 generating
- [ ] 成功路径：`python -c "from src.models.account import Account, AccountStatus; print('OK')"` 输出 OK
- [ ] 成功路径：`python -c "from src.config import load_config; print('OK')"` 输出 OK
- [ ] 成功路径：`python -c "from src.runtime.storage import Storage; s = Storage(':memory:'); s.init_db(); print('tables created')"` 能初始化内存数据库并建表
- [ ] 成功路径：product_store 能在临时目录中创建产品、读取产品、更新变体
- [ ] 失败路径：product_store 创建同名产品时应报错或返回错误
- [ ] 边界情况：空 prompt_variants 列表应被模型接受（允许先建产品后加变体）

## 验证命令

```bash
cd E:\即梦内容工厂
python -c "from src.models.product import Product, PromptVariant, compute_product_revision; print('product OK')"
python -c "from src.models.task import Task, TaskStatus; print('task OK')"
python -c "from src.models.account import Account, AccountStatus; print('account OK')"
python -c "from src.config import load_config; print('config OK')"
python -c "
from src.runtime.storage import Storage
s = Storage(':memory:')
s.init_db()
print('storage OK')
"
python -c "
import tempfile, os
from src.runtime.product_store import create_product, get_product, list_products
d = tempfile.mkdtemp()
create_product(d, 'test_product', [{'id':'var1','title':'v1','prompt':'hello'}], [])
p = get_product(d, 'test_product')
assert p['name'] == 'test_product'
assert len(p['prompt_variants']) == 1
print('product_store OK')
"
```

## 停止条件

- 需要新增依赖时停止
- 需要修改未授权文件时停止
- 需要改架构或数据模型时停止
- 连续两次尝试无新证据时停止
- 发现验收标准本身不足以判断完成时停止

## 回传格式

执行完成后，严格按以下结构回传：

```markdown
## 已完成内容
-

## 实际修改文件
-

## 验证结果
- 命令：
- 结果：

## 风险与阻塞
-

## 建议下一步
-
```

## 规划者自检

- [x] 这是单个端到端最小切片
- [x] 执行者不需要自己决定范围
- [x] 验收标准可由审核者逐条判断
- [x] 允许修改文件足够清楚
- [x] 停止条件明确
