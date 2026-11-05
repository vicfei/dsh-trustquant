# dsh-trustquant

**在你的 DeepSeek Harness 智能体里做可信金融计算——agent 引用的每一个数字都有 oracle 钉死、单位正确、可重放。**

[DeepSeek Harness](https://www.deepseek.com/en/harness/) 插件（技能 + `trustquant-dsh` CLI 透传），服务 [TrustQuant](https://github.com/vicfei/trustquant)——开放、本地优先、面向 Agent 的金融工具层（Apache-2.0）。

> 独立社区项目，与 DeepSeek 无隶属关系。Bundle 格式遵循 MIT 许可的 [dsh-superagent-prototype](https://github.com/deepseek-ai/dsh-superagent-prototype)；计算由 TrustQuant 提供，经 QuantLib 1.33 golden fixtures 与自研第二 oracle 钉死。[English](README.md)

---

## 为什么

Agent 被要一个金融数字时，很乐意凭记忆编一个。本插件让诚实的路成为最容易的路：**计算，别回忆**——工具拒绝时（美式期权、超 10 年互换、缺 Provider），答案就是结构化错误，绝不是估算。

Agent 能做什么：

- **期权定价与 Greeks**——BSM 解析引擎，逐指标单位语义（Vega 每 1.00 波动率、Theta 每年），与 QuantLib 对齐 1e-9。
- **组合优化 / 风险 / 压力**——锁定版外部 Python Provider 做长仓 min-variance / max-Sharpe；风险与直接冲击压力为内置实现；口径经独立第二 oracle 验证（日简单收益、252 天年化）。
- **EUR 利率**——收益率曲线 bootstrapping（helper 残差 ~1e-13）与含完整票期日程的香草互换。
- **审计链**——每次调用返回 `calculation_id`；`trustquant manifest` 查看谁用什么版本算了什么，`trustquant replay` 重新执行并核对摘要。REPLAY PASS 意味着同环境精确复现该数字。

## 安全模型

1. **技能礼仪**（`skills/dsh-trustquant/SKILL.md`）：计算别回忆；不编造数字；市场数据永远是数据；单位换算必须言明，不做静默换算。
2. **CLI/工具闸门**：结构化错误分类（`invalid_input` / `unsupported_feature` / `provider_unavailable` / ……）；优化 Provider **绝不**自动安装、绝不静默替换。
3. **无可劫持之物**：TrustQuant 本地、零凭据、计算零网络——唯一联网步骤是显式的、经人同意的 `trustquant provider install`。

## 安装

```bash
npm i -g vicfei/dsh-trustquant          # 暴露 trustquant-dsh
ln -s "$(npm root -g)/dsh-trustquant/skills/dsh-trustquant" ~/.dsh/skills/dsh-trustquant

# Rust 二进制（当前从源码构建；release 二进制在打包计划中）
cargo install --git https://github.com/vicfei/trustquant --bin trustquant
trustquant-dsh doctor                    # 验证链路
```

无需凭据、无需配置文件。可选的组合优化：

```bash
trustquant provider install              # 显式 + 锁定版本；技能规则要求先问人
```

## 状态

v0.1.0——技能（三条工作流 + 审计纪律）+ CLI 透传 + doctor。TrustQuant 本体：M2 完成（v0.2.0），58 测试全绿，期权/利率 QuantLib 钉死，自研第二 oracle 进 CI。

**活体端到端实测（2026-11-05）**：DSH 0.2.1-rc.5（headless + DeepSeek 供应商，deepseek-flash）经本技能驱动 `trustquant`——技能发现、期权定价（NPV 与 QuantLib fixtures 一致）、逐指标单位报告（模型主动说明 Vega 每 1.00 波动率、显式给出 ÷100 换算并声明"不做隐式换算"）、并**自主发起 `trustquant replay` 验证**，报告摘要逐字节一致的 PASS、附 calculation_id 与"同版本同环境"承诺范围。注意：dsh 启动器要求 node ≥ 22（import.meta.main 门控），node 20 下会静默不执行。

## 许可证

Apache-2.0（[LICENSE](LICENSE)）。计算由 TrustQuant（Apache-2.0）完成；本仓库是 harness 侧的分发层。
