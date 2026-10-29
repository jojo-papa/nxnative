#!/usr/bin/env python3
"""The project's rules, and the checks that enforce them.

Every rule has an id, a one-line statement, the check that enforces it, and
what to do when it fails.  `RULES.md` is the human-readable copy of this
registry; `webui/tests/test_rules.py` fails when the two drift apart, so a rule
change cannot land without the document changing with it.

    python webui/tools/rules.py            # run every active check
    python webui/tools/rules.py --json
    python webui/tools/rules.py --rule R-11
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from webui import staging  # noqa: E402

RULES_DOC = ROOT / 'RULES.md'
FEATURES_TSV = ROOT / 'webui' / 'features.tsv'
PATCH_META_TSV = ROOT / 'webui' / 'patches' / 'features.tsv'
GAME_STATUS_TSV = ROOT / 'webui' / 'games' / 'upstream_status.tsv'
OVERLAY_ROOT = ROOT / 'webui' / 'overlays'

FEATURE_COLUMNS = ('id', 'label', 'group', 'scope', 'env', 'values', 'default', 'note')
PATCH_META_COLUMNS = ('patch', 'kind', 'feature', 'needs', 'reason')
GAME_STATUS_COLUMNS = ('title_id', 'name', 'priority', 'upstream_profile', 'upstream_game_patches',
                        'upstream_general_fixes', 'upstream_open', 'our_profile', 'our_gap',
                        'our_plan', 'checked')

ACTIVE = 'active'      # a runnable check enforces it
PLANNED = 'planned'    # the rule is in force; its check arrives with the named tool

# id, section, title, statement, status, check id, what to do when it fails
RULES = [
    {
        'id': 'R-01', 'section': 'baseline', 'status': ACTIVE,
        'title': '每日重建 daily 分支',
        'rule': '定时任务把上游 seedds/nxnative 的 main 抓到 daily 分支，并把本仓库的 fork 提交 rebase 到它上面。',
        'check': 'webui/tools/daily_sync.py --plan',
        'fix': '跑 python webui/tools/daily_sync.py --run：它负责抓取、rebase、补丁重放与跑门，绿了才提升 main。',
    },
    {
        'id': 'R-02', 'section': 'baseline', 'status': ACTIVE,
        'title': '冲突时基线优先',
        'rule': '补丁重放到新基线时，若基线已经包含我们的等价改动，就丢弃我们的补丁、用基线的版本；只有基线没覆盖的部分才重做。',
        'check': 'webui/tools/patch_rebase.py',
        'fix': '它要对每条补丁给出 KEEP / DROP_BASELINE_HAS_IT / PARTIAL / NEEDS_MANUAL 之一；出现 NEEDS_MANUAL 就不许提升 main。',
    },
    {
        'id': 'R-03', 'section': 'baseline', 'status': ACTIVE,
        'title': '测试门',
        'rule': '任何要进主分支的改动，必须四项检查全绿：补丁队列、stage 树、sync_check、单元测试。',
        'check': 'webui/tools/gate.py',
        'fix': '跑 python webui/tools/gate.py --json 看哪一项红。',
    },
    {
        'id': 'R-04', 'section': 'baseline', 'status': ACTIVE,
        'title': '主分支只进不退',
        'rule': 'main 只能由一次绿灯的 daily 得到；任何失败、任何红灯都不许动 main。',
        'check': 'main 包含 webui/patches/UPSTREAM_BASE 记录的上游提交',
        'fix': 'main 被改动了。回退到最近一次绿灯的提交，或重新跑一次 daily 让它绿灯。',
    },
    {
        'id': 'R-05', 'section': 'baseline', 'status': ACTIVE,
        'title': '主分支随时可构建',
        'rule': 'main 的 stage 树必须能重建并通过 verify。',
        'check': 'webui/tools/gate.py 里的 stage_ensure 与 stage_verify',
        'fix': '跑 python webui/tools/stage.py ensure --rebuild 看报错。',
    },
    {
        'id': 'R-06', 'section': 'development', 'status': PLANNED,
        'title': '补丁开发走功能分支',
        'rule': '每一条补丁的开发都在一个 feature/<名字> 分支上做，分支从 main 拉，不在 main 上直接改。',
        'check': '.github/workflows/daily-sync.yml 里的 feature-branch 检查',
        'fix': '分支流的工作流还没建。',
    },
    {
        'id': 'R-07', 'section': 'development', 'status': PLANNED,
        'title': '合入主分支必须测绿',
        'rule': '功能分支合入 main 之前，必须跑过与 R-03 相同的四项检查。',
        'check': '.github/workflows/daily-sync.yml 里的 pull_request 检查',
        'fix': '分支流的工作流还没建。',
    },
    {
        'id': 'R-08', 'section': 'development', 'status': ACTIVE,
        'title': '按功能拆分',
        'rule': '一条补丁只属于一个功能；同一个功能的补丁在 series 里必须连成一段，不许和别的功能交错。',
        'check': 'webui/tools/rules.py --rule R-08',
        'fix': '把交错的补丁在 series 里挪到一起，或把它拆到别的功能下。',
    },
    {
        'id': 'R-09', 'section': 'features', 'status': ACTIVE,
        'title': '独立功能有独立开关',
        'rule': '每一条定制补丁（kind=custom）必须挂在 webui/features.tsv 里的一个功能上；每个功能必须有 scope 与说明。',
        'check': 'webui/tools/rules.py --rule R-09',
        'fix': '在 webui/patches/features.tsv 给这条补丁填 feature，或在 webui/features.tsv 补上这个功能。',
    },
    {
        'id': 'R-10', 'section': 'features', 'status': ACTIVE,
        'title': '开关能在启动页切换且不用重装',
        'rule': 'scope=runtime 的功能，它的 env 变量必须真的出现在该功能关联的补丁或 overlay 源文件里（开关是真接上的，不是表里的一个名字）；scope=build 的功能必须写明为什么运行时改不了。',
        'check': 'webui/tools/rules.py --rule R-10',
        'fix': '要么给补丁加上这个 env 的运行时判断，要么把 scope 改成 build 并在 note 里说明。',
    },
    {
        'id': 'R-11', 'section': 'development', 'status': ACTIVE,
        'title': '基础修改在前、定制修改在后',
        'rule': 'series 里定制补丁之后不该再出现基础补丁，除非那个基础补丁是前面某个定制补丁的前置（needs）。',
        'check': 'webui/tools/rules.py --rule R-11',
        'fix': '在 webui/patches/series 里把基础补丁挪到定制补丁前面，或在 needs 里写明依赖关系。',
    },
    {
        'id': 'R-12', 'section': 'development', 'status': ACTIVE,
        'title': '补丁元数据齐全',
        'rule': '每条入队补丁在 webui/patches/features.tsv 里都要有一行，写明 kind、feature、needs 与理由。',
        'check': 'webui/tools/rules.py --rule R-12',
        'fix': '给缺的补丁补一行。',
    },
    {
        'id': 'R-13', 'section': 'consistency', 'status': ACTIVE,
        'title': '规则文档与实现同步',
        'rule': 'RULES.md 必须有本注册表里的每一条规则，且每条的编号、标题、检查写法一致；反过来 RULES.md 里出现的每个编号也必须在注册表里。',
        'check': 'webui/tests/test_rules.py',
        'fix': '改 RULES.md 或改 webui/tools/rules.py，两边一起改。',
    },
    {
        'id': 'R-14', 'section': 'consistency', 'status': ACTIVE,
        'title': '上游文件保持干净',
        'rule': '除 dm/ios/project.yml 外，不得直接改动上游拥有的文件；我们的改动只能以补丁或 overlay 的形式存在。',
        'check': 'webui/tools/sync_check.py',
        'fix': '把改动改成 webui/patches/ 里的补丁或 webui/overlays/ 里的 overlay。',
    },
    {
        'id': 'R-15', 'section': 'upstream', 'status': ACTIVE,
        'title': '先查上游，不重复开发',
        'rule': '要给某个游戏加补丁之前，先在 webui/games/upstream_status.tsv 里登记这个游戏查过上游的结果：上游有没有 profile、上游为它加了哪些专属补丁、上游在它上面先发现了哪些通用修复、上游还有什么没解决。',
        'check': 'webui/tools/rules.py --rule R-15',
        'fix': '在 webui/games/upstream_status.tsv 里补上这个 title id 的一行。表格里的 upstream_general_fixes 与 our_gap 两列不许留空：写「—」也要写出来，说明确实没有。',
    },
    {
        'id': 'R-16', 'section': 'consistency', 'status': ACTIVE,
        'title': '构建产物不进仓库、不进 stage 树',
        'rule': '仓库根目录的 out/（打包好的 IPA、截图、研究笔记）是构建产物：既不被 git 跟踪，也不被拷进 stage 树。stage 树必须是源码树，不是构建产物的副本。',
        'check': 'webui/tools/rules.py --rule R-16',
        'fix': "把 'out/' 加进 webui/repo.py 的 DATA_EXCLUDES（它写进 .git/info/exclude，不动上游的 .gitignore），并把它加进 webui/staging.py 的 SKIP_REL_PREFIXES。",
    },
]

SECTIONS = [
    ('baseline', '一、基线与主分支'),
    ('development', '二、补丁开发与合入'),
    ('features', '三、功能开关'),
    ('consistency', '四、一致性'),
    ('upstream', '五、不重复开发'),
]


# ---------- reading the tables ----------

def read_tsv(path: Path, columns):
    """A tab-separated table with a header line: list of (line number, row dict).

    `columns` is the column order the table must have.  A header line that
    disagrees with it, or a row with the wrong number of columns, is an
    error — not something to paper over.
    """
    if not path.is_file():
        return []
    rows = []
    header = None
    for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        fields = line.split('\t')
        if header is None:
            header = fields
            if header != list(columns):
                raise ValueError(f'{path.name}:{number}: 表头必须是 {list(columns)}，拿到 {header}')
            continue
        if len(fields) != len(header):
            raise ValueError(f'{path.name}:{number}: expected {len(header)} columns, got {len(fields)}')
        rows.append((number, dict(zip(header, fields))))
    return rows


def load_features():
    """id -> feature dict."""
    out = {}
    for number, row in read_tsv(FEATURES_TSV, FEATURE_COLUMNS):
        out[row['id']] = {'id': row['id'], 'label': row['label'], 'group': row['group'],
                          'scope': row['scope'], 'env': row['env'], 'values': row['values'],
                          'default': row['default'], 'note': row['note'], 'line': number}
    return out


def load_patch_meta():
    """patch file name -> metadata dict."""
    out = {}
    for number, row in read_tsv(PATCH_META_TSV, PATCH_META_COLUMNS):
        needs = row['needs']
        out[row['patch']] = {'patch': row['patch'], 'kind': row['kind'], 'feature': row['feature'],
                             'needs': [item for item in needs.split(',') if item and item != '-'],
                             'reason': row['reason'], 'line': number}
    return out


def series_order():
    """The patch file names in the order the queue applies them."""
    return [patch.name for patch, _target in staging.patch_queue()]


def overlay_text():
    """Every overlay source file, concatenated."""
    if not OVERLAY_ROOT.is_dir():
        return ''
    parts = []
    for path in sorted(OVERLAY_ROOT.rglob('*')):
        if path.is_file():
            try:
                parts.append(path.read_text(encoding='utf-8', errors='replace'))
            except OSError:
                pass
    return '\n'.join(parts)


def patch_text(name):
    path = ROOT / 'webui' / 'patches' / name
    if not path.is_file():
        return ''
    try:
        return path.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return ''


def git_out(*args):
    git = shutil.which('git')
    if not git:
        return ''
    process = subprocess.run([git, '-C', str(ROOT), *args], capture_output=True, text=True,
                             encoding='utf-8', errors='replace')
    return process.stdout.strip() if process.returncode == 0 else ''


def git_ok(*args):
    """True when the git command succeeds (for the commands that print nothing)."""
    git = shutil.which('git')
    if not git:
        return False
    process = subprocess.run([git, '-C', str(ROOT), *args], capture_output=True, text=True,
                             encoding='utf-8', errors='replace')
    return process.returncode == 0


# ---------- the checks ----------

def check_r04_main_never_goes_back():
    """main must still contain the upstream commit the fork recorded."""
    base = ROOT / 'webui' / 'patches' / 'UPSTREAM_BASE'
    upstream = ''
    if base.is_file():
        for line in base.read_text(encoding='utf-8').splitlines():
            if line.startswith('upstream '):
                upstream = line.split(None, 1)[1].strip()
    if not upstream:
        return [(False, 'webui/patches/UPSTREAM_BASE 里没有 upstream 行')]
    if not git_ok('cat-file', '-e', upstream + '^{commit}'):
        return [(False, f'上游提交 {upstream[:12]} 不在本仓库里')]
    if git_ok('merge-base', '--is-ancestor', upstream, 'main'):
        return [(True, f'main 包含上游 {upstream[:12]}')]
    return [(False, f'main 不包含上游 {upstream[:12]} —— main 被改回去了')]


def check_r05_stage_gate_is_in_the_gate():
    """The gate must rebuild and verify the staging tree."""
    gate = ROOT / 'webui' / 'tools' / 'gate.py'
    if not gate.is_file():
        return [(False, 'webui/tools/gate.py 不存在')]
    text = gate.read_text(encoding='utf-8')
    missing = [name for name in ('stage_ensure', 'stage_verify') if name not in text]
    return [(not missing, '; '.join(f'gate.py 里没有 {name}' for name in missing) or
             'gate.py 重建并校验了 stage 树')]


def check_r14_upstream_files_stay_clean():
    """sync_check must be part of the gate."""
    gate = ROOT / 'webui' / 'tools' / 'gate.py'
    checker = ROOT / 'webui' / 'tools' / 'sync_check.py'
    if not checker.is_file():
        return [(False, 'webui/tools/sync_check.py 不存在')]
    if not gate.is_file():
        return [(False, 'webui/tools/gate.py 不存在')]
    if 'sync_check' not in gate.read_text(encoding='utf-8'):
        return [(False, 'gate.py 没有跑 sync_check')]
    return [(True, 'gate.py 跑了 sync_check，上游文件的纯净由它看着')]


def check_r08_split_by_feature():
    """A feature's patches must be one run in the series.

    Only the features with a user-facing switch have to be in one piece: a
    runtime feature is the unit the player switches on and off, so its patches
    belong together.  A build-scope feature is documentation, not a switch, and
    is not bound by the order.
    """
    meta = load_patch_meta()
    features = load_features()
    order = series_order()
    problems = []
    runs = {}
    for name in order:
        feature = meta.get(name, {}).get('feature', '-')
        if feature in ('', '-'):
            continue
        if features.get(feature, {}).get('scope') != 'runtime':
            continue
        runs.setdefault(feature, []).append(name)
    for feature, names in sorted(runs.items()):
        positions = [order.index(name) for name in names]
        if positions[-1] - positions[0] + 1 != len(positions):
            problems.append(f'功能 {feature} 的补丁在 series 里被别的功能打断了：{", ".join(names)}')
    return [(not problems, '; '.join(problems) or f'{len(runs)} 个可开关功能的补丁各自连成一段')]


def check_r09_every_custom_has_a_switch():
    """A custom patch must hang on a known feature."""
    features = load_features()
    meta = load_patch_meta()
    problems = []
    for name in series_order():
        row = meta.get(name)
        if not row:
            continue
        if row['kind'] != 'custom':
            continue
        feature = row['feature']
        if feature in ('', '-'):
            problems.append(f'{name}: 定制补丁没有挂功能')
            continue
        if feature not in features:
            problems.append(f'{name}: 功能 {feature} 不在 webui/features.tsv 里')
    return [(not problems, '; '.join(problems) or f'{sum(1 for n in series_order() if meta.get(n, {}).get("kind") == "custom")} 条定制补丁都挂了功能')]


def check_r10_switch_is_really_wired():
    """A runtime feature's env var must really be read somewhere."""
    features = load_features()
    meta = load_patch_meta()
    overlays = overlay_text()
    problems = []
    order = series_order()
    checked = 0
    for fid, feature in sorted(features.items()):
        patches = [name for name in order if meta.get(name, {}).get('feature') == fid]
        if not patches:
            continue          # the feature is not in the queue yet: nothing to check yet
        checked += 1
        if feature['scope'] == 'build':
            if not feature['note'].strip():
                problems.append(f'{fid}: scope=build 但 note 是空的，必须写明为什么运行时改不了')
            continue
        if feature['scope'] != 'runtime':
            problems.append(f'{fid}: scope 必须是 runtime 或 build，拿到的是 {feature["scope"]!r}')
            continue
        env = feature['env'].strip()
        if not env or env == '-':
            problems.append(f'{fid}: scope=runtime 必须有 env 变量')
            continue
        text = '\n'.join(patch_text(name) for name in patches) + overlays
        if env not in text:
            problems.append(f'{fid}: 开关变量 {env} 在 {", ".join(patches)} 与 overlay 里都找不到 —— 这个开关没有真的接上')
    return [(not problems, '; '.join(problems) or f'{checked} 个已入队的 runtime 功能，开关变量都真的被读到了')]


def check_r11_base_before_custom():
    """A base patch must not come after a custom one, unless it is its prerequisite."""
    meta = load_patch_meta()
    order = series_order()

    def closure(name, seen=None):
        seen = seen or set()
        for need in meta.get(name, {}).get('needs', []):
            if need in seen:
                continue
            seen.add(need)
            closure(need, seen)
        return seen

    problems = []
    custom_positions = [(index, name) for index, name in enumerate(order)
                        if meta.get(name, {}).get('kind') == 'custom']
    for index, name in enumerate(order):
        if meta.get(name, {}).get('kind') != 'base':
            continue
        needed_by = set()
        for custom_index, custom in custom_positions:
            if custom_index < index:
                continue
            if name in closure(custom):
                needed_by.add(custom)
        if needed_by:
            continue
        earlier_custom = [custom for custom_index, custom in custom_positions if custom_index < index]
        if earlier_custom:
            problems.append(f'{name}（基础）排在定制补丁 {earlier_custom[0]} 之后')
    return [(not problems, '; '.join(problems) or '基础修改都在定制修改之前')]


def check_r12_patch_metadata():
    """Every queued patch has a metadata row with all its fields."""
    meta = load_patch_meta()
    problems = []
    for name in series_order():
        row = meta.get(name)
        if not row:
            problems.append(f'{name}: webui/patches/features.tsv 里没有这一行')
            continue
        if row['kind'] not in ('base', 'custom'):
            problems.append(f'{name}: kind 必须是 base 或 custom，拿到的是 {row["kind"]!r}')
        if not row['reason'].strip():
            problems.append(f'{name}: 理由是空的')
        for need in row['needs']:
            if need not in meta:
                problems.append(f'{name}: needs 指向不存在的补丁 {need}')
    return [(not problems, '; '.join(problems) or f'{len(series_order())} 条入队补丁的元数据都齐全')]


def check_r13_doc_matches_registry():
    """RULES.md and this registry must agree."""
    problems = []
    if not RULES_DOC.is_file():
        return [(False, 'RULES.md 不存在')]
    text = RULES_DOC.read_text(encoding='utf-8')
    for rule in RULES:
        if f"**{rule['id']}**" not in text:
            problems.append(f'RULES.md 里没有 {rule["id"]}')
            continue
        if rule['title'] not in text:
            problems.append(f'RULES.md 里 {rule["id"]} 的标题与注册表不一致（应为 {rule["title"]}）')
        if rule['check'] not in text:
            problems.append(f'RULES.md 里 {rule["id"]} 的检查写法与注册表不一致（应为 {rule["check"]}）')
    for match in re.finditer(r'\*\*(R-\d+)\*\*', text):
        if match.group(1) not in {rule['id'] for rule in RULES}:
            problems.append(f'RULES.md 里的 {match.group(1)} 不在注册表里')
    for name, title in SECTIONS:
        if title not in text:
            problems.append(f'RULES.md 里没有分区「{title}」（注册表里的 {name} 分区）')
    return [(not problems, '; '.join(problems) or f'{len(RULES)} 条规则，文档与注册表一致')]


def check_r03_gate_covers_four():
    """The gate must run the four checks the rule names."""
    gate = ROOT / 'webui' / 'tools' / 'gate.py'
    if not gate.is_file():
        return [(False, 'webui/tools/gate.py 不存在')]
    text = gate.read_text(encoding='utf-8')
    wanted = ['patch_queue', 'stage', 'sync_check', 'unittest']
    missing = [name for name in wanted if name not in text]
    return [(not missing, '; '.join(f'gate.py 里没有 {name}' for name in missing) or
             f'gate.py 覆盖了 {", ".join(wanted)}')]


def check_r15_looked_upstream_first():
    """Every game we patch must have a row in the upstream comparison table."""
    if not GAME_STATUS_TSV.is_file():
        return [(False, 'webui/games/upstream_status.tsv 不存在')]
    rows = {}
    for number, row in read_tsv(GAME_STATUS_TSV, GAME_STATUS_COLUMNS):
        rows[row['title_id']] = {'line': number, 'name': row['name'], 'priority': row['priority'],
                                 'upstream_profile': row['upstream_profile'],
                                 'general': row['upstream_general_fixes'],
                                 'gap': row['our_gap'], 'plan': row['our_plan'],
                                 'checked': row['checked']}
    problems = []
    for gid, row in sorted(rows.items()):
        for field, value in (('upstream_profile', row['upstream_profile']),
                             ('upstream_general_fixes', row['general']),
                             ('our_gap', row['gap']), ('our_plan', row['plan']),
                             ('checked', row['checked'])):
            if not value.strip():
                problems.append(f'{gid}: {field} 是空的（哪怕确实没有，也要写出来）')
    # every patch that touches one game's own files needs that game in the table
    for name, target in staging.patch_queue():
        if not target.startswith('dm/games/'):
            continue
        gid = target.split('/')[2]
        if gid not in rows:
            problems.append(f'{name}: 改的是 {gid}，但 webui/games/upstream_status.tsv 里没有这个游戏')
    return [(not problems, '; '.join(problems) or
             f'{len(rows)} 个游戏查过上游，{sum(1 for n, t in staging.patch_queue() if t.startswith("dm/games/"))} 条 per-game 补丁都有登记')]


def check_r16_build_outputs_stay_out():
    """The build products must stay out of the repository and out of the stage."""
    problems = []
    repo_text = (ROOT / 'webui' / 'repo.py').read_text(encoding='utf-8')
    if "'out/'" not in repo_text:
        problems.append("webui/repo.py 的 DATA_EXCLUDES 里没有 'out/' —— git 会把构建产物收进去")
    tracked = git_out('ls-files', '--', 'out')
    if tracked:
        problems.append(f'git 已经跟踪了 out/ 下的文件：{tracked.splitlines()[0]}')
    leaked = []
    for path in staging.iter_files(staging.REPO):
        try:
            relative = path.relative_to(staging.REPO)
        except ValueError:
            continue
        if relative.parts and relative.parts[0] == 'out':
            leaked.append(relative.as_posix())
    if leaked:
        problems.append(f'webui/staging.py 仍会把 {len(leaked)} 个 out/ 下的文件拷进 stage 树（例如 {leaked[0]}）')
    return [(not problems, '; '.join(problems) or '构建产物 out/ 既不进 git，也不进 stage 树')]


def check_r01_daily_branch_follows_upstream():
    """The daily branch has to carry the upstream's latest commit."""
    if not git_ok('rev-parse', '--verify', 'refs/heads/daily'):
        return [(True, '还没有 daily 分支 —— 第一次每日重建之前不算违规')]
    if git_ok('merge-base', '--is-ancestor', 'upstream/main', 'daily'):
        return [(True, 'daily 包含上游的最新提交')]
    return [(False, 'daily 不包含上游的最新提交 —— 每日重建没有跟上')]


def check_r02_rebase_engine_exists():
    """The patch rebase engine must give every patch a verdict."""
    tool = ROOT / 'webui' / 'tools' / 'patch_rebase.py'
    if not tool.is_file():
        return [(False, 'webui/tools/patch_rebase.py 不存在')]
    text = tool.read_text(encoding='utf-8')
    missing = [name for name in ('KEEP', 'DROP_BASELINE_HAS_IT', 'PARTIAL', 'NEEDS_MANUAL')
               if name not in text]
    if missing:
        return [(False, f'patch_rebase.py 里没有这些判定：{", ".join(missing)}')]
    return [(True, '补丁重放决策引擎在位，每条补丁都会得到四种判定之一')]


CHECKS = {
    'R-01': check_r01_daily_branch_follows_upstream,
    'R-02': check_r02_rebase_engine_exists,
    'R-03': check_r03_gate_covers_four,
    'R-04': check_r04_main_never_goes_back,
    'R-05': check_r05_stage_gate_is_in_the_gate,
    'R-08': check_r08_split_by_feature,
    'R-09': check_r09_every_custom_has_a_switch,
    'R-10': check_r10_switch_is_really_wired,
    'R-11': check_r11_base_before_custom,
    'R-12': check_r12_patch_metadata,
    'R-13': check_r13_doc_matches_registry,
    'R-14': check_r14_upstream_files_stay_clean,
    'R-15': check_r15_looked_upstream_first,
    'R-16': check_r16_build_outputs_stay_out,
}


def run(selected=None):
    report = []
    for rule in RULES:
        if selected and rule['id'] not in selected:
            continue
        entry = {'id': rule['id'], 'title': rule['title'], 'status': rule['status'],
                 'check': rule['check'], 'ok': None, 'detail': ''}
        function = CHECKS.get(rule['id'])
        if function is None:
            entry['detail'] = f'（{rule["status"]}）检查由 {rule["check"]} 负责'
            report.append(entry)
            continue
        try:
            results = function()
            entry['ok'] = all(ok for ok, _ in results)
            entry['detail'] = '；'.join(detail for _ok, detail in results)
        except Exception as error:  # noqa: BLE001
            entry['ok'] = False
            entry['detail'] = f'检查自己坏了: {error}'
        report.append(entry)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rule', action='append', help='only this rule id (repeatable)')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    report = run(args.rule)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        for entry in report:
            mark = {True: 'PASS', False: 'FAIL', None: 'SKIP'}[entry['ok']]
            print(f'{mark}  {entry["id"]}  {entry["title"]}  [{entry["status"]}]')
            if entry['detail']:
                print(f'      {entry["detail"]}')
    failed = [entry for entry in report if entry['ok'] is False]
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
