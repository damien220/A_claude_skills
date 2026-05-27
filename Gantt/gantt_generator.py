#!/usr/bin/env python3
"""
Gantt Timeline & Pricing HTML Generator

Reads a YAML or JSON config file and produces a ready-to-use HTML file by
injecting the config data into the timeline_and_pricing.html template.

Usage:
    python gantt_generator.py <config.yaml|config.json> [--template path] [--output path]

Output defaults to <config_stem>_gantt.html in the same directory as the config.
"""

import argparse
import json
import re
import sys
from pathlib import Path

THIS_DIR = Path(__file__).parent

# Palette applied in order when a phase has no colour defined
DEFAULT_COLORS = [
    "#534AB7", "#1D9E75", "#378ADD", "#D85A30", "#D4537E",
    "#639922", "#BA7517", "#E24B4A", "#888780", "#4A90D9",
    "#B44DB7", "#22A0B8",
]

# ── JavaScript render function (time-unit-aware) ───────────────────────────────
# Embedded verbatim — Python must NOT interpret the ${} template literals.
# The JS field name 'weeks' is kept for all time units (it is an internal key).
RENDER_FUNCTION = """\
  function render() {
    const tier = tiers[activeTier];
    const totalCost = totalHours * tier.rate;

    const unitConfig = {
      weeks: { label: "weeks", markerPrefix: "W", markerStep: 2, perLabel: "week",  monthlyDiv: 4.33 },
      days:  { label: "days",  markerPrefix: "D", markerStep: 5, perLabel: "day",   monthlyDiv: 22   },
      hours: { label: "hours", markerPrefix: "H", markerStep: 8, perLabel: null,    monthlyDiv: null  },
    };
    const uc = unitConfig[timeUnit] || unitConfig.weeks;

    const monthly = uc.monthlyDiv !== null
      ? Math.round(totalCost / (totalDuration / uc.monthlyDiv))
      : null;

    let html = "";

    // Summary cards
    html += `<div class="stat-grid">
      <div class="stat-card"><div class="stat-label">Duration</div><div class="stat-value">~${totalDuration} ${uc.label}</div><div class="stat-sub">&#x2248; ${totalDuration} ${uc.label}</div></div>
      <div class="stat-card"><div class="stat-label">Total hours</div><div class="stat-value">${totalHours}h</div><div class="stat-sub">${uc.perLabel ? `~${Math.round(totalHours / totalDuration)}h/${uc.perLabel} avg` : "billable effort"}</div></div>
      <div class="stat-card"><div class="stat-label">Project cost</div><div class="stat-value">$${totalCost.toLocaleString()}</div><div class="stat-sub">at $${tier.rate}/hr (${tier.label})</div></div>
      ${monthly !== null ? `<div class="stat-card"><div class="stat-label">Monthly avg</div><div class="stat-value">$${monthly.toLocaleString()}</div><div class="stat-sub">over ${totalDuration} ${uc.label}</div></div>` : ""}
    </div>`;

    // Tier tabs
    html += `<div class="section-label">Rate tier</div><div class="tabs">`;
    for (const [key, t] of Object.entries(tiers)) {
      html += `<div class="tab ${key === activeTier ? "active" : ""}" onclick="activeTier='${key}'; render();">${t.label}<br><span style="font-size:11px;color:var(--color-text-tertiary)">${t.desc}</span></div>`;
    }
    html += `</div>`;

    // Gantt
    html += `<div class="section-label">Timeline (Gantt)</div>`;
    html += `<div class="week-markers">`;
    for (let w = 1; w <= totalDuration; w += uc.markerStep) html += `<span>${uc.markerPrefix}${w}</span>`;
    html += `</div>`;

    for (const p of phases) {
      const left  = (((p.weeks[0] - 1) / totalDuration) * 100).toFixed(1);
      const width = (((p.weeks[1] - p.weeks[0] + 1) / totalDuration) * 100).toFixed(1);
      const cost  = p.hours * tier.rate;
      html += `<div class="phase-row">
        <div class="phase-num">P${p.id}</div>
        <div class="bar-wrap"><div class="bar" style="margin-left:${left}%;width:${width}%;background:${p.color}22;color:${p.color};border:0.5px solid ${p.color}44;">${p.name}</div></div>
        <div class="hours-col">${p.hours}h</div>
        <div class="cost-col">$${cost.toLocaleString()}</div>
      </div>`;
    }

    document.getElementById("app").innerHTML = html;
  }\
"""


# ── Config loading ─────────────────────────────────────────────────────────────

def load_config(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if path.suffix in (".yml", ".yaml"):
        try:
            import yaml  # type: ignore
            return yaml.safe_load(text)
        except ImportError:
            sys.exit("PyYAML is required for .yaml files. Install with: pip install pyyaml")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        sys.exit(f"Invalid JSON in {path}: {exc}")


def validate_config(config: dict) -> None:
    if "phases" not in config or not config["phases"]:
        sys.exit("Config must include at least one phase under the 'phases' key.")
    valid_units = {"weeks", "days", "hours"}
    unit = config.get("time_unit", "weeks")
    if unit not in valid_units:
        sys.exit(f"'time_unit' must be one of {sorted(valid_units)}, got: {unit!r}")
    for i, phase in enumerate(config["phases"]):
        if "name" not in phase:
            sys.exit(f"Phase at index {i} is missing required field 'name'.")
        start = phase.get("start", 1)
        end = phase.get("end", start)
        if end < start:
            sys.exit(f"Phase '{phase['name']}': 'end' ({end}) must be >= 'start' ({start}).")


# ── JavaScript block builders ──────────────────────────────────────────────────

def _auto_desc(rate: float) -> str:
    return f"${int(rate)}/hr range"


def build_phases_js(phases: list) -> str:
    lines = ["  const phases = ["]
    for i, p in enumerate(phases):
        pid   = p.get("id", i + 1)
        name  = p.get("name", f"Phase {pid}")
        start = p.get("start", 1)
        end   = p.get("end", start)
        hours = p.get("hours", 0)
        color = p.get("color", DEFAULT_COLORS[i % len(DEFAULT_COLORS)])
        # 'weeks' is the internal JS key regardless of time_unit
        lines += [
            "    {",
            f'      id: {pid},',
            f'      name: "{name}",',
            f'      weeks: [{start}, {end}],',
            f'      hours: {hours},',
            f'      color: "{color}",',
            "    },",
        ]
    lines.append("  ];")
    return "\n".join(lines)


def build_tiers_js(tiers: dict) -> str:
    lines = ["  const tiers = {"]
    for key, t in tiers.items():
        rate  = t["rate"]
        label = t.get("label", key.capitalize())
        desc  = t.get("desc") or _auto_desc(rate)
        lines.append(
            f'    {key}: {{ label: "{label}", rate: {rate}, desc: "{desc}" }},'
        )
    lines.append("  };")
    return "\n".join(lines)


def build_script_block(config: dict) -> str:
    phases    = config["phases"]
    time_unit = config.get("time_unit", "weeks")
    tiers_cfg = config.get("tiers", {
        "mid":        {"label": "Mid-level",      "rate": 20},
        "senior":     {"label": "Senior",         "rate": 25},
        "specialist": {"label": "LLM specialist", "rate": 30},
    })

    # Validate active_tier falls back to first key if missing/invalid
    active_tier = config.get("active_tier", next(iter(tiers_cfg)))
    if active_tier not in tiers_cfg:
        active_tier = next(iter(tiers_cfg))

    # totalDuration = max end across all phases
    total_duration = max(p.get("end", p.get("start", 1)) for p in phases)

    parts = [
        build_phases_js(phases),
        "",
        f"  const totalDuration = {total_duration};",
        f'  const timeUnit = "{time_unit}";',
        "  const totalHours = phases.reduce((s, p) => s + p.hours, 0);",
        "",
        build_tiers_js(tiers_cfg),
        "",
        f'  let activeTier = "{active_tier}";',
        "",
        RENDER_FUNCTION,
        "",
        "  render();",
    ]
    return "\n".join(parts)


# ── HTML assembly ──────────────────────────────────────────────────────────────

def generate(config_path: str, template_path: str | None, output_path: str | None) -> Path:
    cfg_path = Path(config_path)
    if not cfg_path.exists():
        sys.exit(f"Config file not found: {cfg_path}")

    tmpl_path = Path(template_path) if template_path else THIS_DIR / "timeline_and_pricing.html"
    if not tmpl_path.exists():
        sys.exit(f"Template not found: {tmpl_path}")

    out_path = (
        Path(output_path) if output_path
        else cfg_path.parent / f"{cfg_path.stem}_gantt.html"
    )

    config = load_config(cfg_path)
    validate_config(config)

    template = tmpl_path.read_text(encoding="utf-8")
    new_script = build_script_block(config)

    # Replace the entire <script>…</script> block
    new_html = re.sub(
        r"<script>[\s\S]*?</script>",
        lambda _: f"<script>\n{new_script}\n</script>",
        template,
        count=1,
    )

    # Update the <h2> title if provided in config
    title = config.get("project_title")
    if title:
        new_html = re.sub(
            r"(<h2[^>]*>)[\s\S]*?(</h2>)",
            lambda m: f"{m.group(1)}\n  {title}\n{m.group(2)}",
            new_html,
            count=1,
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(new_html, encoding="utf-8")
    return out_path


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate Gantt timeline HTML from a YAML or JSON config file.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python gantt_generator.py sample_config.yaml
  python gantt_generator.py my_project.json --output report.html
  python gantt_generator.py config.yaml --template custom_template.html --output out.html
        """,
    )
    parser.add_argument("config",     help="Path to YAML or JSON config file")
    parser.add_argument("--template", help="HTML template path (default: timeline_and_pricing.html)")
    parser.add_argument("--output",   help="Output HTML path (default: <config_stem>_gantt.html)")
    args = parser.parse_args()

    out = generate(args.config, args.template, args.output)
    print(f"Generated: {out}")


if __name__ == "__main__":
    main()
