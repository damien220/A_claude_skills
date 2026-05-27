# Gantt Timeline & Pricing Generator

Generates a self-contained HTML Gantt chart with interactive pricing tiers from a YAML or JSON config file.

## Requirements

- Python 3.9+
- PyYAML (only for `.yaml`/`.yml` configs) — already in the project venv:
  ```bash
  source /workspaces/Prj_utils/Agent_dev/.venv/bin/activate
  ```

## Quick start

```bash
python gantt_generator.py sample_config.yaml
# → writes sample_config_gantt.html next to the config
```

```bash
python gantt_generator.py my_project.json --output report.html
```

```bash
python gantt_generator.py config.yaml --template custom_template.html --output out.html
```

## CLI reference

```
gantt_generator.py <config> [--template PATH] [--output PATH]
```

| Argument | Default | Description |
|---|---|---|
| `config` | *(required)* | Path to YAML or JSON config file |
| `--template` | `timeline_and_pricing.html` (script directory) | HTML template to read |
| `--output` | `<config_stem>_gantt.html` beside the config | Where to write the generated HTML |

## Config file format

Both YAML and JSON are supported. Extension determines the parser (`.yaml`/`.yml` → PyYAML, everything else → JSON).

### Minimal example

```yaml
time_unit: weeks
phases:
  - name: "Discovery"
    start: 1
    end: 2
    hours: 8
  - name: "Build"
    start: 2
    end: 4
    hours: 24
```

### Full YAML (all options)

```yaml
project_title: "My project — timeline & pricing"  # updates the <h2> heading
time_unit: weeks        # weeks | days | hours  (default: weeks)
active_tier: senior     # which tab is selected on load (default: first tier key)

phases:
  - id: 1               # optional; auto-increments if omitted
    name: "Phase name"
    start: 1            # first time-unit this phase occupies (inclusive)
    end: 2              # last  time-unit (inclusive); defaults to start
    hours: 10           # billable effort hours — used for cost calculation
    color: "#534AB7"    # hex colour; auto-assigned from palette if omitted

tiers:
  mid:
    label: "Mid-level"
    rate: 20            # USD per hour (required)
    desc: "$20/hr range"  # tab sub-label; auto-generated as "$N/hr range" if omitted
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
  "project_title": "API Sprint",
  "time_unit": "days",
  "active_tier": "senior",
  "phases": [
    { "name": "Design",  "start": 1, "end": 3,  "hours": 12 },
    { "name": "Build",   "start": 3, "end": 8,  "hours": 30 },
    { "name": "QA",      "start": 8, "end": 10, "hours": 8  }
  ],
  "tiers": {
    "junior": { "label": "Junior", "rate": 15 },
    "senior": { "label": "Senior", "rate": 25 }
  }
}
```

## Time units

`time_unit` controls the Gantt axis labels and the monthly cost calculation.

| Value | Axis labels | Marker step | Monthly cost formula |
|---|---|---|---|
| `weeks` | W1, W3, W5 … | every 2 | `totalCost / (duration / 4.33)` |
| `days`  | D1, D6, D11 … | every 5 | `totalCost / (duration / 22)` |
| `hours` | H1, H9, H17 … | every 8 | not shown |

`totalDuration` is derived automatically as the highest `end` value across all phases.  
`totalHours` is the sum of all phase `hours` fields (computed client-side in the output HTML).

## Validation rules

The script exits with a clear message if any of these are violated:

- `phases` must contain at least one entry
- Each phase must have `name`
- `end` must be ≥ `start` within each phase
- `time_unit` must be `weeks`, `days`, or `hours`
- `active_tier` must match a key in `tiers` (falls back to first key if invalid)

## Claude Code skill

The `/gantt` skill wraps this workflow for use inside Claude Code. It triggers on phrases like:

> "generate gantt from config.yaml"  
> "create timeline"  
> "update pricing"

The skill guides Claude to locate the config, validate it, run the generator, and report the output path and summary stats.

## Files

```
Gantt/
├── timeline_and_pricing.html   ← HTML template (CSS + JS, do not edit the <script> block)
├── gantt_generator.py          ← generator script
├── sample_config.yaml          ← weeks-based reference config (9-phase LLM migration)
├── sample_config_days.json     ← days-based reference config  (5-phase API sprint)
└── .claude/skills/gantt/
    └── SKILL.md                ← Claude Code skill definition
```
