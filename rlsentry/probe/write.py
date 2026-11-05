"""probe/write.py (FR-09; dev/ci only; ADR-029 + 補記). Contract: rlsentry/contracts/probe.py.

Every write carries `Prefer: return=minimal`; the end state is checked with a HEAD count, so no
row is ever downloaded. The scanner only writes rows it created itself (canaries)."""
import re
import uuid
from collections.abc import Mapping

import httpx

from rlsentry.contracts.models import Op, Role, Target
from rlsentry.contracts.policy import ExpectedAccess
from rlsentry.contracts.probe import (
    CANARY_PREFIX,
    CONTENT_RANGE_TOTAL_RE,
    PROBE_ROLES,
    USER_ROLES,
    WRITE_OPS,
    ReadBack,
    SeededRow,
    Sessions,
    WriteAttempt,
    WritePlan,
)
from rlsentry.contracts.safety import SafeClientContract
from rlsentry.probe.evidence import curl_command
from rlsentry.probe.fill import fill_required
from rlsentry.probe.paths import rest_url
from rlsentry.probe.verdict import forbidden_write
from rlsentry.rules.severity import write_rule


def _other_user(actor: Role, user_ids: Mapping[Role, str], tokens: Mapping[Role, str]) -> Role | None:
    """First user role other than `actor` that has both an id and a token."""
    for role in USER_ROLES:
        if role is not actor and role in user_ids and role in tokens:
            return role
    return None


def plan_writes(expected_by_op: Mapping[tuple[Op, Role], ExpectedAccess],
                user_ids: Mapping[Role, str], tokens: Mapping[Role, str],
                text_column: str | None) -> list[WritePlan]:
    """Enumerate the forbidden writes worth attempting, from the EXPECTED policy only.

    Why: a write is attempted only when the policy forbids its end state, so a confirmed
    effect is always a vulnerability; review scopes (unknown owner) are never probed.
    """
    plans: list[WritePlan] = []
    for op in WRITE_OPS:
        for actor in PROBE_ROLES:
            exp = expected_by_op.get((op, actor))
            if exp is None or exp.is_review:
                continue
            actor_id = None if actor is Role.ANON else user_ids.get(actor)
            if actor is not Role.ANON and actor_id is None:
                continue
            rule = write_rule(actor, op)
            other = _other_user(actor, user_ids, tokens)
            if other is None or not forbidden_write(exp.scope, actor_id, user_ids[other], False):
                continue
            if op is Op.INSERT:
                plans.append(WritePlan(op=op, actor=actor, rule=rule, reader=other,
                                       new_owner=other))
            elif op is Op.DELETE:
                plans.append(WritePlan(op=op, actor=actor, rule=rule, reader=other,
                                       work_owner=other))
            else:
                if text_column is not None:
                    plans.append(WritePlan(op=op, actor=actor, rule=rule, reader=other,
                                           work_owner=other, text_column=text_column))
                if actor is not Role.ANON and actor in tokens:
                    plans.append(WritePlan(op=op, actor=actor, rule=rule, reader=other,
                                           work_owner=actor, new_owner=other, transfer=True))
    return plans


def _headers(anon_key: str, token: str, json_body: bool = False) -> dict[str, str]:
    h = {"apikey": anon_key, "Authorization": f"Bearer {token}", "Prefer": "return=minimal"}
    if json_body:
        h["Content-Type"] = "application/json"
    return h


async def seed_work_row(client: SafeClientContract, supabase_url: str, anon_key: str,
                        target: Target, owner: Role, text_column: str | None,
                        owner_column: str, sessions: Sessions) -> SeededRow | None:
    """Create one fresh private canary owned by `owner`, so each destructive probe is isolated.

    Why: None (never a guess) when the row could not be created, so the cell is NOT_TESTED.
    """
    token = sessions.tokens.get(owner)
    uid = sessions.user_ids.get(owner)
    if not token or not uid or len(target.primary_key) != 1 or target.kind != "table":
        return None
    pk = str(uuid.uuid4())
    marker = CANARY_PREFIX + uuid.uuid4().hex
    body: dict[str, object] = {target.primary_key[0]: pk, owner_column: uid}
    if text_column is not None:
        body[text_column] = marker
    extra = fill_required(target, uid, body.keys())
    if extra is None:
        return None
    body.update(extra)
    try:
        resp = await client.request("POST", rest_url(supabase_url, target),
                                    headers=_headers(anon_key, token, True), json=body)
    except httpx.HTTPError:
        return None
    if not 200 <= resp.status_code < 300:
        return None
    return SeededRow(target=target.name, pk=pk, owner=owner, marker=marker,
                     text_column=text_column)


async def send_write(client: SafeClientContract, supabase_url: str, anon_key: str,
                     target: Target, plan: WritePlan, work: SeededRow | None,
                     owner_column: str, sessions: Sessions) -> WriteAttempt:
    """Send the plan's single write as the actor, with `Prefer: return=minimal`.

    Why: a returned representation would re-run the SELECT policy and hide a real write.
    """
    pk_col = target.primary_key[0]
    url = rest_url(supabase_url, target)
    token = sessions.tokens.get(plan.actor, "")
    headers = _headers(anon_key, token, plan.op is not Op.DELETE)
    params: dict[str, str] | None = None
    body: dict[str, object] | None = None
    new_pk: str | None = None
    new_value: str | None = None
    if plan.op is Op.INSERT:
        method = "POST"
        new_pk = str(uuid.uuid4())
        body = {pk_col: new_pk}
        if plan.new_owner is not None:
            body[owner_column] = sessions.user_ids.get(plan.new_owner, "")
        if plan.text_column is not None:
            body[plan.text_column] = CANARY_PREFIX + uuid.uuid4().hex
        owner_id = sessions.user_ids.get(plan.new_owner, "") if plan.new_owner else ""
        extra = fill_required(target, owner_id, body.keys())
        if extra is None:
            return WriteAttempt(status=None, curl="")
        body.update(extra)
    else:
        if work is None:
            return WriteAttempt(status=None, curl="")
        params = {pk_col: f"eq.{work.pk}"}
        if plan.op is Op.DELETE:
            method = "DELETE"
        else:
            method = "PATCH"
            if plan.transfer:
                body = {owner_column: sessions.user_ids.get(plan.new_owner or plan.actor, "")}
            else:
                new_value = CANARY_PREFIX + uuid.uuid4().hex
                body = {plan.text_column or "": new_value}
    final_url = str(httpx.URL(url).copy_merge_params(params)) if params else url
    curl = curl_command(method, final_url, headers)
    try:
        resp = await client.request(method, url, headers=headers, params=params, json=body)
    except httpx.HTTPError:
        return WriteAttempt(status=None, curl=curl, new_pk=new_pk, new_value=new_value)
    return WriteAttempt(status=resp.status_code, curl=curl, new_pk=new_pk, new_value=new_value)


async def read_back(client: SafeClientContract, supabase_url: str, anon_key: str,
                    target: Target, reader_token: str, filters: Mapping[str, str]) -> ReadBack:
    """HEAD-count the forbidden end state as its reader; never downloads a row.

    Why: present stays None unless the count is trustworthy, so a bad read-back is never "denied".
    """
    url = rest_url(supabase_url, target)
    params = {"select": target.primary_key[0], **filters}
    headers = {"apikey": anon_key, "Authorization": f"Bearer {reader_token}",
               "Prefer": "count=exact"}
    curl = curl_command("HEAD", str(httpx.URL(url).copy_merge_params(params)), headers)
    try:
        resp = await client.request("HEAD", url, headers=headers, params=params)
    except httpx.HTTPError:
        return ReadBack(present=None, status=None, curl=curl)
    match = re.match(CONTENT_RANGE_TOTAL_RE, resp.headers.get("Content-Range", ""))
    present = int(match.group(1)) > 0 if match and resp.status_code in (200, 206) else None
    return ReadBack(present=present, status=resp.status_code, curl=curl)


def after_filter(plan: WritePlan, attempt: WriteAttempt, work: SeededRow | None, pk_col: str,
                 owner_col: str | None, user_ids: Mapping[Role, str]) -> dict[str, str]:
    """PostgREST filters describing the forbidden end state after the write.

    Why: the read-back must match exactly the canary and value/owner the write tried to set.
    """
    if plan.op is Op.INSERT:
        return {pk_col: f"eq.{attempt.new_pk}"}
    if work is None:
        raise ValueError("UPDATE/DELETE need the work row")
    filters = {pk_col: f"eq.{work.pk}"}
    if plan.op is Op.UPDATE:
        if plan.transfer:
            if owner_col is None or plan.new_owner is None:
                raise ValueError("transfer needs an owner column and a new owner")
            filters[owner_col] = f"eq.{user_ids[plan.new_owner]}"
        else:
            if plan.text_column is None:
                raise ValueError("value-change needs a text column")
            filters[plan.text_column] = f"eq.{attempt.new_value}"
    return filters
