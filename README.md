# Skill Harvester

自动从 GitHub 搜索公开的 Agent Skills，下载 `SKILL.md`，执行格式校验、静态安全扫描、质量评分、完全重复检测，并生成 Markdown、CSV、JSONL 报告。

**安全边界：本项目不会执行候选 Skill 中的命令或脚本，也不会自动安装 Skill。**

## 目录

```text
.
├── .github/workflows/skills_search.yml
├── config/config.yml
├── skill_harvester/
├── tests/
├── data/
├── reports/
├── pyproject.toml
└── requirements.txt
```

## 一、本地运行

### 1. 安装

Windows PowerShell：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

macOS / Linux：

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

`requirements.txt` 中包含 `-e .`，因此会安装当前项目，不会再出现：

```text
No module named skill_harvester
```

### 2. 配置 GitHub Token

推荐创建一个仅用于读取公开仓库的 GitHub Token，不要授予写入其他仓库、组织管理或密钥相关权限。

PowerShell：

```powershell
$env:GH_SEARCH_TOKEN="github_pat_xxx"
```

macOS / Linux：

```bash
export GH_SEARCH_TOKEN="github_pat_xxx"
```

不要把 Token 写进代码、YAML 或提交到仓库。

### 3. 执行

完整运行：

```bash
python -m skill_harvester --config config/config.yml run
```

分步运行：

```bash
python -m skill_harvester --config config/config.yml discover
python -m skill_harvester --config config/config.yml generate-report
python -m skill_harvester --config config/config.yml stats
```

安装后也可以使用：

```bash
skill-harvester --config config/config.yml run
```

## 二、GitHub Actions 配置

### 1. 添加 Token

仓库页面：

```text
Settings
→ Secrets and variables
→ Actions
→ New repository secret
```

名称：

```text
GH_SEARCH_TOKEN
```

值填写 GitHub Token。工作流在该 Secret 缺失时会退回 `${{ github.token }}`，但为了稳定地搜索全站公开代码，建议使用独立的只读搜索 Token。

### 2. 允许工作流提交报告

仓库页面：

```text
Settings
→ Actions
→ General
→ Workflow permissions
→ Read and write permissions
→ Save
```

如果默认分支受保护并禁止机器人直接推送，请删掉工作流最后的提交步骤，或者改成由工作流创建 Pull Request。

### 3. 手动运行

```text
Actions
→ Discover Skills
→ Run workflow
```

定时规则：

```yaml
cron: "0 1 * * 1"
```

表示每周一 01:00 UTC；台湾时间为周一 09:00。GitHub 定时任务可能因平台负载略有延迟。

## 三、输出

```text
data/
├── skills.db       # 增量 SQLite 数据库
└── skills.jsonl    # 便于程序读取与版本比较

reports/
├── latest.md       # 最新人工阅读报告
├── latest.csv      # 可在 Excel 中筛选
└── YYYY-MM-DD.md   # 每次运行的日期快照
```

每条记录包含：

- 来源仓库、路径、链接和 Blob SHA
- Skill 名称、描述、正文和 Frontmatter
- 仓库 Stars、许可证、更新时间
- 格式错误与警告
- 静态安全风险和匹配片段
- 分项质量评分
- 搜索词命中来源
- 完全重复内容的主记录

## 四、修改搜索范围

编辑 `config/config.yml`：

```yaml
search:
  queries:
    - 'filename:SKILL.md path:skills'
    - 'matlab filename:SKILL.md'
    - '"scientific computing" filename:SKILL.md'
    - 'optics filename:SKILL.md'
```

建议使用多条窄查询，而不是只使用一条极宽的 `filename:SKILL.md`。GitHub Code Search 对单个查询可返回的结果有限，窄查询也更容易覆盖不同领域。

常用参数：

```yaml
github:
  request_interval_seconds: 0.15
  max_pages_per_query: 1
  max_candidates_total: 500
  max_candidates_per_query: 100
  search_interval_seconds: 7

search:
  skip_archived_repositories: true
  minimum_repository_stars: 0
```

增加页数和候选数量会显著增加 API 请求与工作流时间。

## 五、评分含义

总分 100，由四部分组成：

- Agent Skills 格式规范：30
- 指令的程序性和可验证性：30
- 仓库可信度、活跃度、Stars、许可证：20
- 静态安全：20

默认等级：

- `recommended`：70 分以上、格式有效、无高/严重风险
- `review`：50 分以上，需要人工复核
- `low`：低质量、格式无效或风险较高

评分只是候选排序工具。最终是否有用，仍应通过真实任务的 A/B 测试判断。

## 六、安全注意事项

1. 本项目只静态读取 `SKILL.md`，不运行其中命令。
2. 报告中的高分 Skill 也不能直接自动安装。
3. 安装前检查整个 Skill 目录，包括 `scripts/`、`references/` 和依赖文件。
4. 未知脚本只在无密钥、无私人项目文件的容器中运行。
5. 上游内容会变化；采用 Skill 时固定仓库 Commit 或 Blob SHA。

## 七、测试

```bash
pytest
```

测试覆盖 Frontmatter 解析、危险命令识别和基础质量评分。
