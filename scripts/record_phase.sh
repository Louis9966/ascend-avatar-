#!/bin/bash
# 用法：bash scripts/record_phase.sh <Phase号> <Phase名称> <结果> <耗时> <验证人>
cat >> /ascend-avatar/loop-state.md << EEOF

## Phase $1: $2 $3
- 日期: $(date '+%Y-%m-%d %H:%M:%S')
- 结果: $3
- 耗时: $4
- 验证人: $5
- 关键信息: $6

EEOF
