# CharClamp-01 · 炭窑焖烧志

窑场炭窑与焖烧班次台账基线项目（Litestar + SQLAlchemy 2 + Jinja2 + HTMX）。

## 技术栈

| 层 | 技术 |
| --- | --- |
| Web | Litestar · Jinja2 · HTMX CDN · Session 认证 |
| 数据 | SQLAlchemy 2（async） · PostgreSQL 15 |
| 部署 | Docker Compose · Uvicorn |
| 结构 | `domain/` · `infra/` · `web/` 分层（非 Django apps） |

## 路径与端口

- **项目路径**：`d:\work\document\bytecode\claudeCodePro\CharClamp\CharClamp-01`
- **Web**：http://localhost:4750
- **PostgreSQL**：localhost:6150

## 演示账号

| 用户名 | 密码 | 角色 |
| --- | --- | --- |
| `admin` | `123456` | 管理员 |
| `worker` | `123456` | 操作工 |

登录页已预填 `admin` / `123456`。entrypoint 会建表并写入种子数据（窑场 **乌石岗焖烧坞**，两座窑 **坞东-甲（焖烧中，炭品 A）/ 坞东-乙（已码窑，炭品 B）**，两种炭品字母分属两窑）。

## 主界面：焖烧时间轴

登录后进入全宽 **焖烧时间轴**（不再使用侧栏 + 双 CRUD 列表）：

1. **顶部窑剪影行**：每座炭窑以 SVG 剪影展示；点击某窑用 HTMX 局部刷新下方时间轴，并更新地址栏 `?clamp_id=`；「全部窑」取消筛选。
2. **炭品字母精确筛**：筛选条按炭品字母做**精确相等**匹配（`charcoal_grade = ?`，非 LIKE/包含）。筛后给出三组互相可对账的数：**命中班次张数 = 筛后卡片数**、**这些班次所属窑去重座数 = 剪影点亮数**、**其中窑态仍为焖烧中的座数 = 点亮剪影里的焖烧中子集**；筛不到时三组数均为 0。未命中的剪影压暗熄火。
3. **纵向时间轴**：按开始时间倒序列出 `BurnShift`；每条卡片带窑号徽章（再点可开抽屉）、峰值温度、炭品与当前窑态；炭品字母可在卡片上直接改（单行原子 UPDATE，多人同时改不同班次互不覆盖）。
4. **侧抽屉（非独立编辑页）**：「登记班次」写入新班次；点窑徽章打开操作抽屉，可标记「已出炭」（受峰值规则约束）。

## 业务规则

炭窑状态不可设为「已出炭」（`drawn`），除非该窑**最近一条** `BurnShift` 的 `peakTempC` 已记录且 **≥ 400℃**。

规则实现：`src/charclamp/domain/rules.py`

## 快速启动

```bash
cd d:\work\document\bytecode\claudeCodePro\CharClamp\CharClamp-01
docker compose up --build
```

浏览器打开 http://localhost:4750

## 目录结构

```
CharClamp-01/
├── docker-compose.yml
├── Dockerfile
├── entrypoint.sh
└── src/charclamp/
    ├── main.py
    ├── domain/          # models + rules
    ├── infra/           # db + seed + security
    └── web/             # controllers + templates + static
```
