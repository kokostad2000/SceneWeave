#!/usr/bin/env bash
#
# 把本仓库推送到 GitHub（自检 + 创建仓库 + 推送）。
#
# 设计目标：**先证明不会泄漏，再推送**。任何一项检查不通过就中止，不做危险操作。
#
# 用法：
#   scripts/push_to_github.sh --dry-run          # 只做检查，不推送
#   scripts/push_to_github.sh                    # 创建私有仓库并推送（默认）
#   scripts/push_to_github.sh --public           # 创建公开仓库并推送
#   scripts/push_to_github.sh --repo owner/name  # 指定仓库（默认取 gh 当前账号）
#   scripts/push_to_github.sh --name MyRepo      # 只改仓库名
#
# 前置条件：`gh auth status` 必须已登录且有 repo 权限。
# 密钥只从 .env／环境变量读取，本脚本**不读取也不打印**任何密钥内容。
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

DRY_RUN=0
VISIBILITY="--private"
REPO_FULL=""
REPO_NAME=""
BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --public) VISIBILITY="--public"; shift ;;
    --private) VISIBILITY="--private"; shift ;;
    --repo) REPO_FULL="${2:-}"; shift 2 ;;
    --name) REPO_NAME="${2:-}"; shift 2 ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "未知参数：$1" >&2; exit 2 ;;
  esac
done

fail() { echo "✗ $1" >&2; exit 1; }
ok()   { echo "✓ $1"; }
info() { echo "  $1"; }

echo "=== 1) 仓库状态 ==="
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || fail "当前目录不是 git 仓库"
ok "git 仓库：$ROOT_DIR"
info "分支：$BRANCH"
info "提交：$(git rev-parse --short HEAD) $(git log -1 --pretty=%s | cut -c1-60)"

if [[ -n "$(git status --porcelain)" ]]; then
  fail "工作区不干净，请先提交或 stash：
$(git status --porcelain | head -10)"
fi
ok "工作区干净"

echo
echo "=== 2) 敏感文件检查（最关键）==="
TRACKED_SENSITIVE="$(git ls-files | grep -E '(^|/)\.env$|(^|/)\.env\.[^e]|\.db$|\.sqlite3$|(^|/)node_modules/|(^|/)\.venv/|(^|/)\.cache/|(^|/)dist/|\.pyc$' || true)"
if [[ -n "$TRACKED_SENSITIVE" ]]; then
  fail "以下敏感文件已被 git 跟踪，**必须先从索引移除**：
$(echo "$TRACKED_SENSITIVE" | sed 's/^/    /')"
fi
ok "无 .env／数据库／依赖目录／构建产物被跟踪"

if git check-ignore -q .env; then ok ".env 已被 .gitignore 忽略"; else fail ".env 未被忽略，危险"; fi
if git check-ignore -q .env.example; then fail ".env.example 被忽略了，模板应当入库"; else ok ".env.example 正常入库"; fi

echo
echo "=== 3) 密钥模式扫描（只报文件名，不输出内容）==="
HITS="$(git grep -lE 'sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----' -- . 2>/dev/null || true)"
if [[ -n "$HITS" ]]; then
  fail "以下已提交文件中出现密钥模式，**先撤销并轮换**：
$(echo "$HITS" | sed 's/^/    /')"
fi
ok "已跟踪文件中未发现密钥模式"

echo
echo "=== 4) gh 登录状态 ==="
if ! command -v gh >/dev/null 2>&1; then
  fail "未安装 gh。请安装后运行 gh auth login，或改用 SSH 推送"
fi
if ! gh auth status >/dev/null 2>&1; then
  cat >&2 <<'EOF'
✗ gh 未登录（或 token 失效）。请先在你的终端执行：

    gh auth login -h github.com

走完浏览器授权后重新运行本脚本。也可以用 SSH：
把公钥加到 GitHub → Settings → SSH and GPG keys，然后自行 git push。
EOF
  exit 1
fi
ACCOUNT="$(gh api user --jq .login 2>/dev/null || echo '')"
[[ -n "$ACCOUNT" ]] || fail "无法读取 gh 账号（token 可能缺 repo 权限）"
ok "已登录账号：$ACCOUNT"

if [[ -z "$REPO_FULL" ]]; then
  [[ -n "$REPO_NAME" ]] || REPO_NAME="$(basename "$ROOT_DIR")"
  REPO_FULL="$ACCOUNT/$REPO_NAME"
fi
info "目标仓库：$REPO_FULL（${VISIBILITY#--}）"

echo
echo "=== 5) 待推送内容概览 ==="
info "文件数：$(git ls-files | wc -l | tr -d ' ')"
info "提交数：$(git rev-list --count HEAD)"
info "体积：$(git count-objects -vH | awk -F': ' '/size-pack/{print $2}')"

if [[ "$DRY_RUN" == "1" ]]; then
  echo
  ok "dry-run：所有检查通过，未做任何推送。去掉 --dry-run 即会创建仓库并推送。"
  exit 0
fi

echo
echo "=== 6) 创建仓库并推送 ==="
if gh repo view "$REPO_FULL" >/dev/null 2>&1; then
  info "仓库已存在，直接推送"
  git remote get-url origin >/dev/null 2>&1 || git remote add origin "https://github.com/$REPO_FULL.git"
  git push -u origin "$BRANCH"
else
  gh repo create "$REPO_FULL" "$VISIBILITY" --source=. --remote=origin --push
fi

echo
echo "=== 7) 核对远端 ==="
LOCAL_SHA="$(git rev-parse HEAD)"
REMOTE_SHA="$(git ls-remote origin "refs/heads/$BRANCH" | awk '{print $1}')"
info "本地 HEAD：$LOCAL_SHA"
info "远端 $BRANCH：$REMOTE_SHA"
[[ "$LOCAL_SHA" == "$REMOTE_SHA" ]] || fail "远端提交与本地不一致，请检查推送结果"
ok "推送完成且远端与本地一致"
echo
ok "仓库地址：https://github.com/$REPO_FULL"
