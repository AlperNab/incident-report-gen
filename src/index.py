#!/usr/bin/env python3
"""
incident-report-gen — security incident data → structured incident report
Generates: executive summary, technical timeline, root cause analysis,
impact assessment, remediation steps, lessons learned, action items
"""
import anthropic, json, re, sys
from datetime import datetime, timezone
from pathlib import Path

SYSTEM = """You are a CISO and incident response lead who has managed hundreds of security incidents.
Generate a professional, complete incident report that serves both technical and executive audiences.

Return ONLY valid JSON — no markdown, no explanation.

{
  "incident_id": "INC-YYYY-NNNN",
  "title": "concise incident title",
  "severity": "P1_critical|P2_high|P3_medium|P4_low",
  "incident_type": "data_breach|ransomware|ddos|phishing|insider_threat|system_outage|unauthorized_access|malware|other",
  "status": "ongoing|contained|resolved|closed",
  "executive_summary": "3-4 sentence non-technical summary for C-suite and board",
  "timeline": [
    {
      "timestamp": "YYYY-MM-DD HH:MM UTC or relative",
      "event": "what happened",
      "actor": "attacker|system|staff|automated|unknown",
      "significance": "critical|high|medium|informational"
    }
  ],
  "detection": {
    "detected_by": "SIEM|EDR|user_report|external|monitoring|null",
    "detection_timestamp": "string or null",
    "time_to_detect_hours": number_or_null,
    "detection_gap": "any window where activity went undetected"
  },
  "scope": {
    "systems_affected": ["list"],
    "data_affected": {
      "pii_involved": true_or_false,
      "pii_records_estimate": number_or_null,
      "data_types": ["email","SSN","payment_card","health","other"],
      "data_exfiltrated": true_or_false,
      "volume_estimate": "string or null"
    },
    "users_affected": number_or_null,
    "services_impacted": ["list"],
    "geographic_scope": ["list of regions/countries"]
  },
  "root_cause": {
    "primary_cause": "string",
    "contributing_factors": ["list"],
    "attack_vector": "string",
    "initial_access": "phishing|exposed_credentials|vulnerability|insider|supply_chain|other"
  },
  "attacker_profile": {
    "likely_motivation": "financial|espionage|hacktivism|disruption|unknown",
    "sophistication": "script_kiddie|opportunistic|advanced|nation_state|unknown",
    "ttps": ["MITRE ATT&CK techniques if identifiable"]
  },
  "containment_actions": [
    {"action":"string","timestamp":"string or null","effective":true_or_false}
  ],
  "eradication_actions": ["list of steps to remove threat"],
  "recovery_actions": ["list of steps to restore normal operations"],
  "impact_assessment": {
    "operational_impact": "description",
    "financial_impact_estimate": "string or null",
    "reputational_impact": "low|medium|high|critical",
    "regulatory_implications": ["GDPR notification required","HIPAA breach","SEC disclosure","none"]
  },
  "notification_requirements": {
    "regulator_notification_required": true_or_false,
    "regulator_deadline": "72 hours|30 days|other|null",
    "customer_notification_required": true_or_false,
    "law_enforcement_involved": true_or_false
  },
  "lessons_learned": ["specific process or technology gaps revealed"],
  "action_items": [
    {
      "action": "specific remediation task",
      "owner": "team or role",
      "priority": "immediate|7_days|30_days|90_days",
      "estimated_effort": "hours|days|weeks"
    }
  ],
  "technical_indicators": {
    "iocs": ["IPs","domains","hashes","emails"],
    "detection_rules": ["YARA rules or SIEM queries to detect recurrence"]
  },
  "metrics": {
    "time_to_detect_hours": number_or_null,
    "time_to_contain_hours": number_or_null,
    "time_to_recover_hours": number_or_null,
    "total_downtime_hours": number_or_null
  },
  "confidence": 0.0
}"""

def generate(incident_notes: str, incident_type: str = "auto", severity: str = "auto") -> dict:
    client = anthropic.Anthropic()
    context = f"Incident type: {incident_type}\nSeverity: {severity}\n\nIncident data:\n{incident_notes[:30000]}"
    resp = client.messages.create(
        model="claude-sonnet-4-20250514", max_tokens=4096, system=SYSTEM,
        messages=[{"role":"user","content":f"Generate incident report:\n\n{context}"}]
    )
    raw = re.sub(r'^```(?:json)?\s*','',resp.content[0].text.strip(),flags=re.MULTILINE)
    raw = re.sub(r'\s*```$','',raw,flags=re.MULTILINE)
    return json.loads(raw)

def to_markdown(r: dict) -> str:
    lines = [
        f"# Incident Report: {r.get('incident_id','')} — {r.get('title','')}",
        f"**Severity:** {r.get('severity','')} | **Status:** {r.get('status','')} | **Type:** {r.get('incident_type','')}",
        "", "---", "", "## Executive Summary", "", r.get("executive_summary",""), "",
        "---", "", "## Timeline", "",
        "| Time | Event | Significance |", "|------|-------|--------------|",
    ]
    for ev in r.get("timeline",[]): lines.append(f"| {ev.get('timestamp','')} | {ev.get('event','')} | {ev.get('significance','')} |")
    scope = r.get("scope",{})
    data = scope.get("data_affected",{})
    lines += ["", "---", "", "## Scope", "",
        f"**PII involved:** {'Yes ⚠' if data.get('pii_involved') else 'No'} | "
        f"**Records:** {data.get('pii_records_estimate','unknown')} | "
        f"**Exfiltrated:** {'Yes' if data.get('data_exfiltrated') else 'No'}",
    ]
    rc = r.get("root_cause",{})
    lines += ["", "---", "", "## Root Cause", "", rc.get("primary_cause",""), ""]
    for f in rc.get("contributing_factors",[]): lines.append(f"- {f}")
    lines += ["", "---", "", "## Action Items", "", "| Action | Owner | Priority | Effort |", "|--------|-------|----------|--------|"]
    for ai in r.get("action_items",[]): lines.append(f"| {ai.get('action','')} | {ai.get('owner','')} | {ai.get('priority','')} | {ai.get('estimated_effort','')} |")
    lines += ["", "---", "", "## Lessons Learned", ""]
    for ll in r.get("lessons_learned",[]): lines.append(f"- {ll}")
    return "\n".join(lines)

SEV_C = {"P1_critical":"\033[91m","P2_high":"\033[91m","P3_medium":"\033[93m","P4_low":"\033[92m"}
SIG_ICON = {"critical":"🔴","high":"🟠","medium":"🟡","informational":"⚪"}
R = "\033[0m"

def print_report(r: dict):
    sev = r.get("severity","P3_medium")
    print(f"\n{'═'*60}")
    print(f"  INCIDENT REPORT — {r.get('incident_id','?')}")
    print(f"  {SEV_C.get(sev,'')}{sev}{R} | {r.get('incident_type','?').replace('_',' ').upper()} | {r.get('status','?').upper()}")
    print(f"  {r.get('title','')}")
    print(f"{'═'*60}")
    print(f"\n  EXECUTIVE SUMMARY\n  {r.get('executive_summary','')}")

    timeline = r.get("timeline",[])
    if timeline:
        print(f"\n  TIMELINE ({len(timeline)} events)")
        for ev in timeline:
            print(f"  {SIG_ICON.get(ev.get('significance','informational'),'')} {ev.get('timestamp','?'):>22}  {ev.get('event','')[:60]}")

    scope = r.get("scope",{})
    data = scope.get("data_affected",{})
    print(f"\n  SCOPE")
    if data.get("pii_involved"): print(f"  ⚠ PII involved: ~{data.get('pii_records_estimate','?')} records")
    if data.get("data_exfiltrated"): print(f"  🚨 Data exfiltrated")
    if scope.get("systems_affected"): print(f"  Systems: {', '.join(scope['systems_affected'][:4])}")
    m = r.get("metrics",{})
    if m.get("time_to_detect_hours"): print(f"\n  TTD: {m['time_to_detect_hours']}h | TTC: {m.get('time_to_contain_hours','?')}h | TTR: {m.get('time_to_recover_hours','?')}h")

    rc = r.get("root_cause",{})
    print(f"\n  ROOT CAUSE\n  {rc.get('primary_cause','')}")

    notif = r.get("notification_requirements",{})
    if notif.get("regulator_notification_required"):
        print(f"\n  ⚠ REGULATORY NOTIFICATION REQUIRED — deadline: {notif.get('regulator_deadline','?')}")

    actions = r.get("action_items",[])
    immediate = [a for a in actions if a.get("priority")=="immediate"]
    if immediate:
        print(f"\n  IMMEDIATE ACTIONS")
        for a in immediate: print(f"  ⚡ [{a.get('owner','?')}] {a.get('action','')}")

    ll = r.get("lessons_learned",[])
    if ll:
        print(f"\n  LESSONS LEARNED")
        for l in ll[:4]: print(f"  → {l}")

    print(f"\n  Confidence: {int(r.get('confidence',0)*100)}%")
    print(f"{'═'*60}\n")

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Generate security incident report")
    p.add_argument("notes", help="Incident notes file or '-' for stdin")
    p.add_argument("--type","-t",default="auto")
    p.add_argument("--severity","-s",default="auto")
    p.add_argument("--markdown","-m",help="Save as markdown")
    p.add_argument("--json",action="store_true")
    a = p.parse_args()
    src = sys.stdin.read() if a.notes=="-" else (Path(a.notes).read_text(encoding="utf-8",errors="replace") if Path(a.notes).exists() else a.notes)
    r = generate(src, a.type, a.severity)
    if a.markdown: Path(a.markdown).write_text(to_markdown(r),encoding="utf-8"); print(f"Report saved to {a.markdown}")
    if a.json: print(json.dumps(r,indent=2,ensure_ascii=False))
    else: print_report(r)
