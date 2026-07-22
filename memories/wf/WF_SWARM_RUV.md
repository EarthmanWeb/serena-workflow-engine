---
name: WF_SWARM_RUV
description: Consolidated redirect — all Ruflo swarm coordination now lives in WF_SWARM_ORCHESTRATE.
metadata:
  type: workflow
---

# WF_SWARM_RUV — Consolidated

> **On step WF_SWARM_RUV**

- This workflow is CONSOLIDATED into `wf/WF_SWARM_ORCHESTRATE`. Read it now:

```
read_memory("wf/WF_SWARM_ORCHESTRATE")
```

- Ruflo coordination patterns B1, B2, B3 live in `wf/WF_SWARM_ORCHESTRATE`. Do NOT recreate them here.
