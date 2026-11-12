-- New MySQL baseline created by SQLAlchemy metadata: datasets, specs, scenarios, runs, reviews, reports, users, audits.
-- All six physical quality bounds are DOUBLE. Dataset attributes and widths use JSON number values.
-- Existing deployments need reviewed migrations; no destructive automatic upgrades.

-- 中断恢复增量（应用启动时 src.config.database._upgrade_runs_table 也会幂等执行同等补列）：
-- 为 runs 增加输入快照、尝试次数与租约字段。只加列不改历史行，已完成试算及报告归档保持原样。
ALTER TABLE runs
  ADD COLUMN input_snapshot JSON,
  ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN locked_by VARCHAR(64) NOT NULL DEFAULT '',
  ADD COLUMN locked_at DATETIME NULL,
  ADD COLUMN started_at DATETIME NULL,
  ADD COLUMN finished_at DATETIME NULL;
