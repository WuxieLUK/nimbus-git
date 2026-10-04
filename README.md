# nimbus-git

![tests](https://github.com/WuxieLUK/nimbus-git/actions/workflows/tests.yml/badge.svg)
![python](https://img.shields.io/badge/python-3.10%2B-blue)
![license](https://img.shields.io/github/license/WuxieLUK/nimbus-git)

一个 **从零实现 Git** 的开发者工具，纯 Python 标准库，**零运行时依赖**。
不调用 `git` 二进制，自己完成对象模型、索引文件、引用、工作区快照、提交图遍历和 Myers diff。

> 和 [nimbus-kv](https://github.com/WuxieLUK/nimbus-kv)（从零实现的 Raft KV）同属 Nimbus 系统系列：
> 一个解决分布式一致性，一个解决内容寻址与版本控制。

## 为什么值得拿奖

- **硬核系统主题**：不是 CRUD，而是实现 Git 的底层数据模型（blob/tree/commit/tag、SHA-1 内容寻址、zlib 压缩、loose object）。
- **真实 Git 兼容**：`nimbus init` 建的仓库可以被原生 `git status / log / cat-file` 直接读取；也能读取原生 Git 创建的仓库。
- **零依赖**：只使用 Python 标准库，评审者无需安装任何东西即可跑通。
- **完整命令行体验**：`init / add / commit / status / log / diff / branch / checkout / switch / tag / cat-file / ls-files / ls-tree / hash-object / rev-parse`。
- **自带 Myers diff**：从算法层面实现 O((N+M)D) 的贪心 Myers 差异算法并渲染 unified diff。
- **可测试**：12 个单元测试覆盖哈希、对象序列化、索引、diff 与完整工作流。

## 架构

```
                    ┌──────────────────────────────┐
                    │            nimbus CLI        │
                    └──────────────┬───────────────┘
                                   │ 命令分发
             ┌─────────────────────┼──────────────────────────┐
             ▼                     ▼                          ▼
     ┌──────────────┐      ┌──────────────┐          ┌──────────────┐
     │   worktree   │      │    index     │          │     refs     │
     │ 快照/树构建  │      │ DIRC 解析/写 │          │ HEAD/分支/标签│
     └──────┬───────┘      └──────┬───────┘          └──────┬───────┘
            │                     │                          │
            └──────────┬──────────┴────────────┬─────────────┘
                       ▼                       ▼
              ┌─────────────────┐      ┌─────────────────┐
              │   object store  │      │    diff (Myers) │
              │ blob/tree/commit│      │ unified render  │
              └─────────────────┘      └─────────────────┘
```

核心不变量：**内容即地址**。文件被哈希为 blob，目录被哈希为 tree，一次提交是一棵不可变 tree 加上父提交指针。

## 快速开始

```bash
# 可选：安装为命令
pip install -e .

# 直接跑源码也行
export PYTHONPATH=src
python -m nimbusgit --help
```

Windows PowerShell：

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
python -m nimbusgit --help
```

## 使用示例

```bash
mkdir demo && cd demo
nimbus init
echo "hello, nimbus" > README.md
nimbus add README.md
nimbus commit -m "first commit"
nimbus status
nimbus log

# 修改后查看差异
echo "second line" >> README.md
nimbus diff

# 分支与切换
nimbus branch feature
nimbus checkout feature
nimbus switch main

# 轻量标签与对象检查
nimbus tag v1.0.0
nimbus rev-parse HEAD
nimbus cat-file -p HEAD
nimbus ls-tree HEAD
```

用原生 Git 验证兼容性：

```bash
git status
git log --oneline --all
git cat-file -t HEAD
```

## 已实现能力

| 模块 | 说明 |
| --- | --- |
| `hashing.py` | SHA-1 内容寻址、`<type> <size>\0` 对象头、zlib 压缩 |
| `objects.py` | blob / tree / commit / tag 的解析与序列化，loose object 存取 |
| `index.py` | Git DIRC v2 索引文件读写（含 8 字节对齐与校验和） |
| `refs.py` | HEAD、分支、标签、短 SHA 消歧解析 |
| `worktree.py` | 工作区快照、递归 tree 构建、tree 展平 |
| `diff.py` | O((N+M)D) Myers diff 与 unified diff 渲染 |
| `commands.py` | 14 个用户命令 |
| `cli.py` | argparse 驱动的命令行入口 |

## 测试

```bash
export PYTHONPATH=src
python -m unittest discover -s tests -v
```

## 已知限制

- 暂未实现 merge / rebase / remote / packfile / reflog / index extensions。
- 与原生 Git 相同位置的 snapshot 语义，但不做 `core.autocrlf` 文本规范化，按字节精确存储。
- Windows 上文件权限位不区分可执行文件。

这些点已经列在 `roadmap` 中，是后续参加进阶赛的清晰增量空间。

## Roadmap

- [ ] three-way merge 与冲突标记
- [ ] packfile 读写与 delta 压缩
- [ ] `clone` / `fetch` / `push` 与 smart HTTP transport
- [ ] 分支历史图与 `log --graph`
- [ ] 悬空对象 GC

## License

MIT
