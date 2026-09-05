# 交付止损与快速迭代规则

> 最初的 48 小时规则形成于 2026-09-03。B10 于 2026-09-05 更新了机器职责：开发机现在承担可达
> API 部署、baseline、调优和镜像构建；主办方评审机只加载镜像并运行。本文件保留时间盒原则并以
> B10 工作流为当前规则。

## 1. 优先级

1. 可评分 Add/Search/Health 闭环和凭据/隔离安全；
2. 开发机真实 API smoke 与首个可复现 baseline；
3. 少量高收益单变量调优及 holdout；
4. 源码/配置冻结后一次最终镜像构建和交付验证；
5. 不影响评分的容器美化或扩展证据。

没有 baseline 前不做广泛调优，低优先级工程不得阻塞真实评测。

## 2. 开发机迭代路径

```text
确定性测试
  -> 原生进程或源码挂载的开发服务
  -> 开发机可达 API smoke/baseline
  -> 单变量调优
  -> 源码和非秘密配置冻结
  -> 一次最终项目镜像构建
  -> 四镜像 bundle/ZIP/manifest/checksum
```

模型、URL、Key、prompt 和阈值变化不重建镜像。Docker/网络问题单阶段排障不超过 30 分钟；开发期
可以使用原生或复用容器路径，但最终候选必须在开发机完成 release 镜像验证。

Python 包构建一次只使用一个明确、credential-free 的 HTTPS index，不设置多源 fallback 或
trusted-host 绕过。基础镜像和第三方镜像保持 digest 锁；主办方不接触任何构建源。

## 3. 主办方运行边界

主办方只执行 hash 校验、解包、私有配置、`docker load`、image ID/revision 核对、Compose
`--no-build --pull never` 启动、Smoke 和官方评测。不提供 native/Python 构建兜底，因为该机器被
定义为评审机而不是开发机。评审机失败返回证据，修复回到开发机。

## 4. 立即停止条件

- Add 达到 120 秒或 Search 达到 60 秒；
- 跨用户泄漏、错误成功、数据损坏或凭据风险；
- Git commit、artifact hash、image ID 或 revision label 不一致；
- 必须修改公共 Schema、Embedding 维度/存量索引或新增服务；
- 主办方流程企图 build、pull、安装依赖、修改源码或删除卷；
- 官方评测器缺失却准备自行发明替代评分。

## 5. 最小记录

每次实验只强制记录候选、唯一主变量、非秘密配置、数据切片、得分、P95/max、失败数、结论和回退
点。最终还记录四个 artifact hash、四张 image ID、custom revision label 和主办方评测器身份。

成功标准是一个契约正确、可启动、可回退、有真实 baseline/调优收益、且主办方无需构建即可运行的
候选；未完成的语义或运维加分项如实登记，不冒充已通过。
