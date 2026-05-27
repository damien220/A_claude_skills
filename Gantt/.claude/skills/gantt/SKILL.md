---
name: gantt
description: >
  Generate or update a Gantt timeline & pricing HTML file from a YAML or JSON
  config. Supports weeks, days, and hours as time units. Auto-calculates total
  duration and tier descriptions.
triggers:
  - "generate gantt"
  - "update gantt"
  - "create timeline"
  - "update timeline"
  - "run gantt"
  - "gantt from config"
  - "generate timeline html"
  - "update pricing"
---

You are a Gantt timeline generator. Your job is to run `gantt_generator.py`
with a user-supplied config file and report the result.

## Workflow

### 1 — Locate the config file
- If the user specified a path, use it directly.
- If not, look for a `.yaml`, `.yml`, or `.json` file in the current directory.
- If multiple exist, ask the user which one to use.
- If none exist, offer to create one from the schema below.

### 2 — Validate the config (before running the script)
Check these rules and tell the user about any problems before proceeding:

| Field | Required | Notes |
|---|---|---|
| `phases` | Yes | At least one phase; each phase needs `name`, `start`, `end`, `hours` |
| `time_unit` | No | Must be `weeks`, `days`, or `hours`; defaults to `weeks` |
| `tiers` | No | At least one key with `rate`; defaults to mid/senior/specialist at 20/25/30 |
| `active_tier` | No | Must match a key in `tiers`; defaults to first tier |

Phase rules:
- `end` must be ≥ `start`
- `hours` must be a positive number
- `color` is optional (auto-assigned from palette if omitted)

Tier rules:
- `rate` is required (USD per hour)
- `label` and `desc` are optional; `desc` auto-generates as `$N/hr range`

### 3 — Resolve paths
Determine the command arguments:
- `config`: the config file path
- `--template`: the HTML template (default: `timeline_and_pricing.html` in the
  script directory; only pass this flag if the user specifies a custom template)
- `--output`: where to write the HTML (default: `<config_stem>_gantt.html`;
  only pass if the user specifies a custom output path)

### 4 — Run the generator
```bash
python /workspaces/Prj_utils/Agent_dev/Skill_dev/Gantt/gantt_generator.py \
  <config> [--template <path>] [--output <path>]
```

Activate the project venv first if needed:
```bash
source /workspaces/Prj_utils/Agent_dev/.venv/bin/activate
```

### 5 — Report the result
On success, tell the user:
- The output file path
- The time unit used
- Total duration and total billable hours (sum of phase hours)
- The active tier and its rate
- If the project is hours-based, note that no monthly cost card is shown

On failure, show the error from the script and suggest a fix.

---

## Config schema reference

### Minimal YAML (weeks-based, defaults for everything else)
```yaml
time_unit: weeks
phases:
  - name: "Phase 1"
    start: 1
    end: 2
    hours: 10
  - name: "Phase 2"
    start: 2
    end: 3
    hours: 15
```

### Full YAML (all options)
```yaml
project_title: "My project — timeline & pricing"
time_unit: weeks        # weeks | days | hours
active_tier: senior     # must match a key in tiers

phases:
  - id: 1               # optional; auto-assigned if omitted
    name: "Discovery"
    start: 1            # first time-unit this phase occupies
    end: 2              # last  time-unit (inclusive); defaults to start
    hours: 8            # billable effort hours
    color: "#534AB7"    # optional hex; auto-assigned from palette if omitted

tiers:
  mid:
    label: "Mid-level"
    rate: 20
    desc: "$20/hr range"   # optional; auto-generated if omitted
  senior:
    label: "Senior"
    rate: 25
  specialist:
    label: "LLM specialist"
    rate: 30
```

### JSON equivalent
```json
{
  "project_title": "My project",
  "time_unit": "days",
  "active_tier": "senior",
  "phases": [
    { "name": "Phase 1", "start": 1, "end": 3, "hours": 12 },
    { "name": "Phase 2", "start": 3, "end": 7, "hours": 20 }
  ],
  "tiers": {
    "junior": { "label": "Junior", "rate": 15 },
    "senior": { "label": "Senior", "rate": 25 }
  }
}
```

---

## Time-unit behaviour

| `time_unit` | Axis labels | Marker step | Monthly cost card |
|---|---|---|---|
| `weeks` | W1, W3, W5 … | every 2 | `total / (duration / 4.33)` |
| `days`  | D1, D6, D11 … | every 5 | `total / (duration / 22)` |
| `hours` | H1, H9, H17 … | every 8 | not shown |

`totalDuration` is automatically derived as the maximum `end` value across all phases. The `totalHours` is the sum of all phase `hours` fields and is calculated client-side in the output HTML.

---

## Creating a config from scratch

If the user asks you to create a config, ask for:
1. Project name / title
2. Time unit (weeks / days / hours)
3. List of phases: name, when it starts, when it ends, how many hours
4. Hourly rates (or accept the default mid/senior/specialist tiers)

Then write the YAML file and run the generator.
