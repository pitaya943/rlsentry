"""report/html.py: the static, self-contained HTML report (FR-12; NFR-03; ADR-044)."""
from __future__ import annotations

from jinja2 import Environment

from rlsentry.contracts.models import Evidence, ScanReport, Severity
from rlsentry.recon.links import report_url
from rlsentry.safety.mask import mask_text

_SECTIONS: tuple[tuple[Evidence, str], ...] = (
    (Evidence.CONFIRMED, "Confirmed"),
    (Evidence.SUSPECTED, "Suspected"),
    (Evidence.CONFIG_WARNING, "Configuration warning"),
)

_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<title>RLSentry report</title>
<style>
body{font-family:sans-serif;margin:2em;max-width:70em}
table{border-collapse:collapse}td,th{border:1px solid #999;padding:2px 8px;text-align:left}
pre{background:#f4f4f4;padding:.5em;overflow:auto}
.f{border:1px solid #bbb;padding:.5em 1em;margin:1em 0}
</style>
</head>
<body>
<h1>RLSentry report</h1>
<p>Target: {{ target }}<br>Profile: {{ r.profile.value }}<br>Tool version: {{ r.tool_version }}<br>
Started: {{ r.started_at.isoformat() }}<br>Finished: {{ r.finished_at.isoformat() }}</p>

<h2>Authorization</h2>
<ul>
<li>confirmed_by: {{ a.confirmed_by }}</li>
<li>method: {{ a.method }}</li>
<li>confirmed_at: {{ a.confirmed_at.isoformat() }}</li>
<li>supabase_url: {{ a.supabase_url or "-" }} ({{ a.supabase_url_method or "-" }})</li>
<li>write_hosts: {{ a.write_hosts | join(", ") or "-" }}</li>
</ul>

<h2>Modules</h2>
<p>{{ r.modules | join(", ") or "-" }}</p>
<h3>notes</h3>
<ul>{% for n in r.notes %}<li>{{ n }}</li>{% else %}<li>-</li>{% endfor %}</ul>

<h2>Summary</h2>
<table>
<tr><th>Evidence</th>{% for s in severities %}<th>{{ s }}</th>{% endfor %}</tr>
{% for sec in sections %}<tr><td>{{ sec.title }}</td>{% for c in sec.counts %}<td>{{ c }}</td>{% endfor %}</tr>
{% endfor %}</table>

<h2>Findings</h2>
{% for sec in sections %}
<h3>{{ sec.title }}</h3>
{% for f in sec.findings %}
<div class="f">
<h4>{{ f.title or f.rule }}</h4>
<ul>
<li>rule: {{ f.rule }}</li>
<li>severity: {{ f.severity.value }}</li>
<li>target: {{ f.target or "-" }}</li>
<li>role: {{ f.role.value if f.role else "-" }}</li>
<li>op: {{ f.op.value if f.op else "-" }}</li>
<li>correlation: {{ f.correlation or "-" }}</li>
<li>lint: {{ f.lint or "-" }}</li>
</ul>
{% if f.probes %}<table>
<tr><th>outcome</th><th>known_rows_checked</th><th>http_status</th><th>reason</th></tr>
{% for p in f.probes %}<tr><td>{{ p.outcome.value }}</td><td>{{ p.known_rows_checked }}</td>
<td>{{ p.http_status if p.http_status is not none else "-" }}</td><td>{{ p.reason }}</td></tr>
{% endfor %}</table>{% endif %}
{% if f.repro %}<p>Repro</p><pre>{{ f.repro }}</pre>{% endif %}
{% if f.fix_sql %}<p>Fix SQL</p><pre>{{ f.fix_sql }}</pre>{% endif %}
{% if f.references %}<p>References</p><ul>{% for u in f.references %}<li><a href="{{ u }}">{{ u }}</a></li>{% endfor %}</ul>{% endif %}
</div>
{% else %}<p>-</p>
{% endfor %}
{% endfor %}

{% if r.policies %}<h2>pg_policies</h2>
<table>
<tr><th>schema</th><th>table</th><th>name</th><th>command</th><th>roles</th><th>permissive</th><th>using</th><th>with_check</th></tr>
{% for p in r.policies %}<tr><td>{{ p.schema_ }}</td><td>{{ p.table }}</td><td>{{ p.name }}</td><td>{{ p.command }}</td>
<td>{{ p.roles | join(", ") }}</td><td>{{ p.permissive }}</td><td>{{ p.using or "-" }}</td><td>{{ p.with_check or "-" }}</td></tr>
{% endfor %}</table>{% endif %}

<h2>Access matrix</h2>
<table>
<tr><th>target</th><th>role</th><th>op</th><th>outcome</th><th>known_rows_checked</th><th>http_status</th><th>reason</th></tr>
{% for c in r.matrix.cells %}<tr><td>{{ c.target }}</td><td>{{ c.role.value }}</td><td>{{ c.op.value }}</td>
<td>{{ c.outcome.value }}</td><td>{{ c.known_rows_checked }}</td>
<td>{{ c.http_status if c.http_status is not none else "-" }}</td><td>{{ c.reason }}</td></tr>
{% endfor %}</table>

{% if r.recon %}<h2>Recon scope</h2>
<p>supabase_url: {{ r.recon.supabase_url or "-" }}</p>
<h3>chunks_scanned</h3>
<ul>{% for u in r.recon.chunks_scanned %}<li>{{ u }}</li>{% else %}<li>-</li>{% endfor %}</ul>
<h3>chunks_skipped</h3>
<ul>{% for u in r.recon.chunks_skipped %}<li>{{ u }}</li>{% else %}<li>-</li>{% endfor %}</ul>
<h3>keys</h3>
<table>
<tr><th>label</th><th>kind</th><th>masked</th><th>source_file</th></tr>
{% for k in r.recon.keys %}<tr><td>{{ k.label }}</td><td>{{ k.kind }}</td><td>{{ k.masked }}</td><td>{{ k.source_file }}</td></tr>
{% endfor %}</table>{% endif %}
</body>
</html>
"""

_ENV = Environment(autoescape=True)
_COMPILED = _ENV.from_string(_TEMPLATE)
_SEVERITIES = (Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.REVIEW)


def render_html(report: ScanReport) -> str:
    """Render one self-contained HTML5 page (no script, no external resource).

    Why: a report must be safe to open anywhere and must not call out; autoescape handles
    attacker-controlled names from the target's OpenAPI, and mask_text is the last defence
    against a key reaching the file (NFR-03).
    """
    sections = []
    for ev, title in _SECTIONS:
        items = [f for f in report.findings if f.evidence == ev]
        counts = [sum(1 for f in items if f.severity == s) for s in _SEVERITIES]
        sections.append({"title": title, "findings": items, "counts": counts})
    text = _COMPILED.render(
        r=report, a=report.authorization, target=report_url(report.target),
        sections=sections, severities=[s.value for s in _SEVERITIES],
    )
    return mask_text(text)
