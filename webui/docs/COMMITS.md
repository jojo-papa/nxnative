# Commit titles

Every commit in this fork uses the same shape:

    [方向][简要概括]

The first bracket says what kind of change the commit is; the second says
what the change does, in one line.  The subject is one line; the body says
why the change was made and what was checked.

## The directions

The vocabulary is closed, so the history can be read at a glance:

| 方向 | 用途 |
|---|---|
| `[同步]` | 跟上上游：重建基线、重贴补丁、把 webui 树搬到新的上游树上 |
| `[功能]` | 玩家能感到的能力：新的开关、新的打包目标、新的界面 |
| `[修复]` | 修错：崩溃、构建失败、画面不对 |
| `[规则]` | 规则与治理：`RULES.md`、规则注册表、检查、测试门 |
| `[工具]` | 工具与脚本：`webui/tools`、`webui/build`、打包流程 |
| `[清理]` | 删掉不再需要的东西：死补丁、死代码、死引用 |
| `[文档]` | 只改文档 |

## Examples

    [同步][以 ac9598a 为基线重整 fork：8 个补丁、Windows 打包层与规则门]
    [功能][启动页设置面板接入功能开关，不重装即可回退]
    [修复][MetalFX 放大在内存警告时释放 scaler]
    [规则][新增 R-16：构建产物不进仓库、不进 stage 树]
    [清理][删掉上游已有的 MetalFX Makefile 补丁]

## What a body owes the reader

The upstream's own commits explain the fix in the body: what was wrong, what
the change does, and what was tried.  A fork commit owes the same, plus one
extra thing: **whether the upstream already had it**.  When the answer is
"the upstream now does this too", the body says so and the fork's own copy
is dropped (rule R-02, R-15).
