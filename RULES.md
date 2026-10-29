# 项目规则

这个项目的规矩。每条规则有编号、说法、**谁在检查它**，以及违反了怎么办。

规矩不是写给人看的，是写给机器执行的：`webui/tools/rules.py` 是规则与检查的唯一事实来源，
`RULES.md` 是它的人类可读副本，`webui/tests/test_rules.py` 断言这两边一致 ——
**改了规矩却没改这份文档，或者改了这份文档却没改注册表，测试会红。**

跑一遍全部门：

```sh
python webui/tools/gate.py            # 四项检查 + 全部规则检查
python webui/tools/rules.py           # 只跑规则检查
python webui/tools/rules.py --rule R-11 --json
```

规矩的两种状态：

| 状态 | 含义 |
|---|---|
| `active` | 有可执行的检查，就在 gate 里，不绿就不许合入 main |
| `planned` | 规矩已经生效，但负责检查它的工具还没建；表里写明了是哪个工具 |

---

## 一、基线与主分支

**R-01** 每日重建 daily 分支
> 定时任务把上游 seedds/nxnative 的 main 抓到 daily 分支，并把本仓库的 fork 提交 rebase 到它上面。

- 检查：`webui/tools/daily_sync.py --plan`
- 状态：`active`
- 违反时：跑 `python webui/tools/daily_sync.py --run`：它负责抓取、rebase、补丁重放与跑门，绿了才提升 main。

**R-02** 冲突时基线优先
> 补丁重放到新基线时，若基线已经包含我们的等价改动，就丢弃我们的补丁、用基线的版本；只有基线没覆盖的部分才重做。

- 检查：`webui/tools/patch_rebase.py`
- 状态：`active`
- 违反时：它要对每条补丁给出 `KEEP` / `DROP_BASELINE_HAS_IT` / `PARTIAL` / `NEEDS_MANUAL` 之一；出现 `NEEDS_MANUAL` 就不许提升 main。

**R-03** 测试门
> 任何要进主分支的改动，必须四项检查全绿：补丁队列、stage 树、sync_check、单元测试。

- 检查：`webui/tools/gate.py`
- 状态：`active`
- 违反时：跑 `python webui/tools/gate.py --json` 看哪一项红。

**R-04** 主分支只进不退
> main 只能由一次绿灯的 daily 得到；任何失败、任何红灯都不许动 main。

- 检查：被测分支（主工作树是 main，daily 工作树是 daily）包含 webui/patches/UPSTREAM_BASE 记录的上游提交
- 状态：`active`
- 违反时：main 被改动了。回退到最近一次绿灯的提交，或重新跑一次 daily 让它绿灯。

**R-05** 主分支随时可构建
> main 的 stage 树必须能重建并通过 verify。

- 检查：webui/tools/gate.py 里的 stage_ensure 与 stage_verify
- 状态：`active`
- 违反时：跑 `python webui/tools/stage.py ensure --rebuild` 看报错。

---

## 二、补丁开发与合入

**R-06** 补丁开发走功能分支
> 每一条补丁的开发都在一个 `feature/<名字>` 分支上做，分支从 main 拉，不在 main 上直接改。

- 检查：.github/workflows/daily-sync.yml 里的 feature-branch 检查
- 状态：`planned`（分支流的工作流待建）
- 违反时：分支流的工作流还没建。

**R-07** 合入主分支必须测绿
> 功能分支合入 main 之前，必须跑过与 R-03 相同的四项检查。

- 检查：.github/workflows/daily-sync.yml 里的 pull_request 检查
- 状态：`planned`（分支流的工作流待建）
- 违反时：分支流的工作流还没建。

**R-08** 按功能拆分
> 一条补丁只属于一个功能；同一个功能的补丁在 series 里必须连成一段，不许和别的功能交错。

- 检查：webui/tools/rules.py --rule R-08
- 状态：`active`
- 违反时：把交错的补丁在 `webui/patches/series` 里挪到一起，或把它拆到别的功能下。

**R-11** 基础修改在前、定制修改在后
> series 里定制补丁之后不该再出现基础补丁，除非那个基础补丁是前面某个定制补丁的前置（needs）。

- 检查：webui/tools/rules.py --rule R-11
- 状态：`active`
- 违反时：在 `webui/patches/series` 里把基础补丁挪到定制补丁前面，或在 needs 里写明依赖关系。

**R-12** 补丁元数据齐全
> 每条入队补丁在 `webui/patches/features.tsv` 里都要有一行，写明 kind、feature、needs 与理由。

- 检查：webui/tools/rules.py --rule R-12
- 状态：`active`
- 违反时：给缺的补丁补一行。

---

## 三、功能开关

**R-09** 独立功能有独立开关
> 每一条定制补丁（`kind=custom`）必须挂在 `webui/features.tsv` 里的一个功能上；每个功能必须有 scope 与说明。

- 检查：webui/tools/rules.py --rule R-09
- 状态：`active`
- 违反时：在 `webui/patches/features.tsv` 给这条补丁填 feature，或在 `webui/features.tsv` 补上这个功能。

**R-10** 开关能在启动页切换且不用重装
> `scope=runtime` 的功能，它的 env 变量必须真的出现在该功能关联的补丁或 overlay 源文件里（开关是真接上的，不是表里的一个名字）；`scope=build` 的功能必须写明为什么运行时改不了。

- 检查：webui/tools/rules.py --rule R-10
- 状态：`active`
- 违反时：要么给补丁加上这个 env 的运行时判断，要么把 scope 改成 build 并在 note 里说明。

### 三张表的关系

| 表 | 放什么 | 谁读它 |
|---|---|---|
| `webui/features.tsv` | 功能开关：id、显示名、分组、scope、env、取值、默认、说明 | 启动页按它生成开关；R-09/R-10 按它检查 |
| `webui/patches/features.tsv` | 补丁元数据：补丁、kind、feature、needs、理由 | R-08/R-09/R-11/R-12 按它检查 |
| `webui/patches/series` | 入队顺序 | 构建与 R-08/R-11 按它走 |

`kind` 的两种取值：

- `base` —— 基础修改：工具链、移植性、正确性与安全。除非它是某个定制补丁的前置，否则应当排在定制补丁前面。
- `custom` —— 定制修改：玩家看得见的行为（画面、音频、手感、界面）。每一条都必须挂一个功能开关。

---

## 四、一致性

**R-13** 规则文档与实现同步
> RULES.md 必须有本注册表里的每一条规则，且每条的编号、标题、检查写法一致；反过来 RULES.md 里出现的每个编号也必须在注册表里。

- 检查：webui/tests/test_rules.py
- 状态：`active`
- 违反时：改 RULES.md 或改 `webui/tools/rules.py`，两边一起改。

**R-14** 上游文件保持干净
> 除 `dm/ios/project.yml` 外，不得直接改动上游拥有的文件；我们的改动只能以补丁或 overlay 的形式存在。

- 检查：webui/tools/sync_check.py
- 状态：`active`
- 违反时：把改动改成 `webui/patches/` 里的补丁或 `webui/overlays/` 里的 overlay。

**R-16** 构建产物不进仓库、不进 stage 树
> 仓库根目录的 `out/`（打包好的 IPA、截图、研究笔记）是构建产物：既不被 git 跟踪，也不被拷进 stage 树。stage 树必须是源码树，不是构建产物的副本。

- 检查：`webui/tools/rules.py --rule R-16`
- 状态：`active`
- 违反时：把 `'out/'` 加进 `webui/repo.py` 的 `DATA_EXCLUDES`（它写进 `.git/info/exclude`，不动上游的 `.gitignore`），并把它加进 `webui/staging.py` 的 `SKIP_REL_PREFIXES`。

### 为什么有这条

`out/` 里现在是 71 GB 的 IPA。stage 树是仓库的一份完整拷贝，
所以只要 `out/` 还在仓库里，**每建一次 stage 就要把这 71 GB 再拷一遍**，
而且 stage 的 key 会随 `out/` 的任何变化而变 —— 构建产物一动，stage 就得重建。
这条规矩第一次被写下来，是因为它真的把磁盘写满了（`WinError 112`）：
`test_stage_is_isolated_and_reused` 和 `test_extract_installs_dotnet_first` 两个测试同时红，
而它们在干净 worktree 上都是绿的。

---

## 五、不重复开发

**R-15** 先查上游，不重复开发
> 要给某个游戏加补丁之前，先在 `webui/games/upstream_status.tsv` 里登记这个游戏查过上游的结果：上游有没有 profile、上游为它加了哪些专属补丁、上游在它上面先发现了哪些通用修复、上游还有什么没解决。

- 检查：webui/tools/rules.py --rule R-15
- 状态：`active`
- 违反时：在 `webui/games/upstream_status.tsv` 里补上这个 title id 的一行。表格里的 upstream_general_fixes 与 our_gap 两列不许留空：写「—」也要写出来，说明确实没有。

### 为什么有这条

上游 `seedds/nxnative` 的作者已经把这些游戏做过了（奥德赛、王国之泪、梦境岛在上游都写着「Plays on the iPhone」）。
所以我们遇到问题时，**先问「上游有没有遇到同样的问题、他们怎么修的」，而不是自己从头修一遍**。

上游把答案放在三个地方：

| 资料 | 位置 | 用途 |
|---|---|---|
| 症状索引 | `docs/agents/symptoms.md` | 一行一个症状：你看到的现象、`[RED]` 文本、崩溃点 → 对应的机制条目 |
| 逐游戏补丁索引 | `docs/agents/game-patches.md` | 每个游戏上游加了哪些专属 cut / 帧步站点 / profile key |
| 游戏笔记 | `dm/games/<id>/README.md` | 实测到哪一步、哪里没验证、哪些修复只验过 Mac、还剩什么没解决 |

`webui/games/upstream_status.tsv` 是我们自己的对照表，把这三处里跟我们要做的游戏有关的部分摘出来。
表里的 `our_gap` 一列写的是「我们相对上游缺什么」，`our_plan` 一列写「我们打算怎么办」。

高优目标（2026-10-29 用户定）：

| 游戏 | title id | 上游状态 |
|---|---|---|
| 奥德赛 | `0100000000010000` | 上游支持，iPhone 可玩，IPA 约 6 GB；12 条通用修复我们一条都没有 |
| 王国之泪 | `0100F2C0115B6000` | 上游支持，iPhone 可玩 60 fps；我们的 `patches.py` 与它逐字一致，但通用修复与四个 profile key 没有 |
| 织梦岛（梦境岛） | `01006BB00C6F0000` | 上游支持，iPhone 可玩 60 fps；10 条通用修复里有 4 条正是画面问题的直接原因 |
| 恶魔城 Demo | `0100D1D027E96000` | 上游没有这个游戏，全新移植对象 |

目标顺序：**先让游戏能玩、好玩**（闪退 / 内存 / 画面这类基本问题），**再叠加全屏**。
