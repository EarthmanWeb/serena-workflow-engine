---
name: WF_SWARM_HIVE_MIND
description: Consolidated stub — Ruflo Hive-Mind consensus workflow now lives in WF_SWARM_ORCHESTRATE. Redirect on entry.
metadata:
  type: workflow
---

# WF_SWARM_HIVE_MIND — Consolidated

> **On step WF_SWARM_HIVE_MIND**

- This workflow is consolidated into `wf/WF_SWARM_ORCHESTRATE`. Do NOT execute swarm/hive-mind logic here.
- Read `wf/WF_SWARM_ORCHESTRATE` now:

```
read_memory("wf/WF_SWARM_ORCHESTRATE")
```

- All Ruflo Hive-Mind consensus documentation lives in `wf/WF_SWARM_ORCHESTRATE`.
