"""Automation engine for SigmaOS-automate: rules, hooks and schedules.

Rules are declarative (trigger + condition + action) stored in a JSON file.
Evaluation against an injected event is pure and side-effect free; the run
verb only *reports* what would fire. Schedules are plans (cron/timer specs),
never installed by this module.
"""
import argparse, json, os, sys

ENGINE = {
    "name": "sigma-automate",
    "summary": "Declarative rules/hooks with pure evaluation and schedule plans",
    "language": "python",
    "verbs": ["add-rule", "list", "run", "schedule-plan"],
    "principles": ["Declarative over Imperative", "Plan Before Apply",
                   "Fail-Fast", "KISS", "Deterministic Testing"],
}

cli_doc = """\
$ sigma-automate add-rule --store rules.json --trigger battery-low \\
      --when percent lt 20 --then notify "Battery low"
$ sigma-automate list --store rules.json
$ sigma-automate run --store rules.json --event battery-low --payload percent=15
$ sigma-automate schedule-plan --store rules.json --rule nightly-clean --daily 02:30
"""

OPS = {"lt": lambda a, b: a < b, "le": lambda a, b: a <= b,
       "gt": lambda a, b: a > b, "ge": lambda a, b: a >= b,
       "eq": lambda a, b: a == b, "ne": lambda a, b: a != b,
       "in": lambda a, b: a in b, "contains": lambda a, b: b in a}


class AutomateError(Exception):
    pass


def make_rule(rule_id, trigger, field, op, value, action, args=()):
    """Pure constructor with full validation -> rule dict."""
    if not rule_id or not rule_id.replace("-", "").replace("_", "").isalnum():
        raise AutomateError(f"invalid rule id: {rule_id!r}")
    if op not in OPS:
        raise AutomateError(f"unknown operator {op!r}; choose from {sorted(OPS)}")
    if op in ("lt", "le", "gt", "ge") and not isinstance(value, (int, float)):
        raise AutomateError(f"operator {op!r} needs a numeric threshold, "
                            f"got {value!r}")
    return {"id": rule_id, "trigger": trigger, "when": {"field": field, "op": op,
                                                        "value": value},
            "then": {"action": action, "args": list(args)}}


def load_rules(path):
    """Read the rule store (JSON list); missing file -> empty."""
    if not os.path.exists(path):
        return []
    with open(path) as fh:
        rules = json.load(fh)
    if not isinstance(rules, list):
        raise AutomateError(f"rule store {path} must be a JSON list")
    seen = set()
    for r in rules:
        if r.get("id") in seen:
            raise AutomateError(f"duplicate rule id in store: {r.get('id')}")
        seen.add(r.get("id"))
    return rules


def save_rules(path, rules):
    """Atomic-ish write of the rule store."""
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(rules, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)


def add_rule(path, rule):
    """Idempotent add: same id -> replace in place; new id -> append."""
    rules = load_rules(path)
    for i, existing in enumerate(rules):
        if existing["id"] == rule["id"]:
            rules[i] = rule
            save_rules(path, rules)
            return rules, True
    rules.append(rule)
    save_rules(path, rules)
    return rules, False


def evaluate(rules, trigger, payload):
    """Pure: which rules fire for an event? Deterministic (store order)."""
    fired = []
    for rule in rules:
        if rule["trigger"] != trigger:
            continue
        cond = rule["when"]
        if cond["field"] not in payload:
            continue
        left = payload[cond["field"]]
        right = cond["value"]
        # payload values arrive as strings from the CLI; coerce when comparing
        if isinstance(right, (int, float)) and not isinstance(right, bool):
            try:
                left = type(right)(left)
            except (TypeError, ValueError):
                continue
        if OPS[cond["op"]](left, right):
            fired.append({"rule": rule["id"], "action": rule["then"]["action"],
                          "args": rule["then"]["args"],
                          "matched": {cond["field"]: left}})
    return fired


CRONISH = ("hourly", "daily", "weekly", "monthly")


def schedule_plan(rule_id, rules, daily=None, hourly=None, weekly=None,
                  monthly=None):
    """Pure: map a rule + cadence to cron + systemd-timer specs."""
    ids = {r["id"] for r in rules}
    if rule_id not in ids:
        raise AutomateError(f"unknown rule {rule_id!r}")
    chosen = [name for name, on in (("daily", daily), ("hourly", hourly),
                                    ("weekly", weekly), ("monthly", monthly))
              if on]
    if len(chosen) != 1:
        raise AutomateError("pick exactly one cadence: --hourly, --daily, "
                            "--weekly or --monthly")
    cadence = chosen[0]
    if cadence == "daily":
        try:
            hour, minute = (int(x) for x in daily.split(":"))
        except (AttributeError, ValueError):
            raise AutomateError(f"bad --daily time {daily!r}; expected HH:MM")
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise AutomateError(f"time out of range: {daily!r}")
        cron = f"{minute} {hour} * * *"
        on_calendar = f"*-*-* {hour:02d}:{minute:02d}:00"
    elif cadence == "hourly":
        cron = "0 * * * *"
        on_calendar = "hourly"
    elif cadence == "weekly":
        cron = "0 4 * * 0"
        on_calendar = "weekly *-*-* 04:00:00"
    else:
        cron = "0 5 1 * *"
        on_calendar = "monthly *-*-01 05:00:00"
    return {"rule": rule_id, "cadence": cadence, "cron": cron,
            "on_calendar": on_calendar,
            "timer_unit": f"sigma-auto-{rule_id}.timer",
            "commands": [f"systemctl enable --now sigma-auto-{rule_id}.timer"]}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=ENGINE["name"], description=ENGINE["summary"])
    p.add_argument("--store", default="rules.json", help="rule store path")
    sub = p.add_subparsers(dest="cmd", required=True)
    ar = sub.add_parser("add-rule", help="validate + store a rule")
    ar.add_argument("--id", required=True)
    ar.add_argument("--trigger", required=True)
    ar.add_argument("--when", nargs=3, required=True, metavar=("FIELD", "OP", "VALUE"))
    ar.add_argument("--then", nargs="+", required=True, metavar="ACTION_OR_ARG")
    ls = sub.add_parser("list", help="list stored rules")
    ls.add_argument("--trigger", default=None, help="filter by trigger")
    rn = sub.add_parser("run", help="evaluate rules against an event (pure)")
    rn.add_argument("--event", required=True)
    rn.add_argument("--payload", action="append", default=[],
                    help="key=value pairs (repeatable)")
    sp = sub.add_parser("schedule-plan", help="plan a timer for one rule")
    sp.add_argument("--rule", required=True)
    sp.add_argument("--hourly", action="store_true")
    sp.add_argument("--daily", default=None, metavar="HH:MM")
    sp.add_argument("--weekly", action="store_true")
    sp.add_argument("--monthly", action="store_true")
    return p


def _coerce_value(raw):
    """CLI values are strings; make numbers/bools/JSON lists when possible."""
    low = raw.lower()
    if low in ("true", "false"):
        return low == "true"
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    if raw.startswith("["):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
    return raw


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.cmd == "add-rule":
            field, op, raw_value = args.when
            rule = make_rule(args.id, args.trigger, field, op,
                             _coerce_value(raw_value),
                             args.then[0], args.then[1:])
            rules, replaced = add_rule(args.store, rule)
            verb = "updated" if replaced else "added"
            print(f"{verb} rule {rule['id']} ({len(rules)} total)")
        elif args.cmd == "list":
            rules = load_rules(args.store)
            for r in rules:
                if args.trigger and r["trigger"] != args.trigger:
                    continue
                cond = r["when"]
                print(f"{r['id']:24} on {r['trigger']:14} "
                      f"if {cond['field']} {cond['op']} {cond['value']!r} "
                      f"then {r['then']['action']}")
        elif args.cmd == "run":
            rules = load_rules(args.store)
            payload = {}
            for item in args.payload:
                key, _, value = item.partition("=")
                if not value:
                    raise AutomateError(f"bad --payload {item!r}; expected key=value")
                payload[key] = _coerce_value(value)
            fired = evaluate(rules, args.event, payload)
            if not fired:
                print("no rules fired")
            for hit in fired:
                args_str = " ".join(str(a) for a in hit["args"])
                print(f"WOULD RUN: {hit['action']} {args_str}  (rule {hit['rule']})")
        elif args.cmd == "schedule-plan":
            rules = load_rules(args.store)
            plan = schedule_plan(args.rule, rules, daily=args.daily,
                                 hourly=args.hourly, weekly=args.weekly,
                                 monthly=args.monthly)
            print(json.dumps(plan, indent=2))
        return 0
    except (AutomateError, OSError, json.JSONDecodeError, KeyError,
            TypeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


def self_test() -> None:
    import tempfile
    # rule construction + validation
    rule = make_rule("bat-low", "battery-low", "percent", "lt", 20,
                     "notify", ["Battery low!"])
    assert rule["when"] == {"field": "percent", "op": "lt", "value": 20}
    assert rule["then"]["args"] == ["Battery low!"]
    for bad_id in ("has space", "has/slash", ""):
        try:
            make_rule(bad_id, "t", "f", "eq", 1, "a")
        except AutomateError as e:
            assert "invalid rule id" in str(e)
        else:
            raise AssertionError(f"bad id not caught: {bad_id!r}")
    try:
        make_rule("r", "t", "f", "explodes", 1, "a")
    except AutomateError as e:
        assert "unknown operator" in str(e)
    else:
        raise AssertionError("bad op not caught")
    try:
        make_rule("r", "t", "f", "lt", "twenty", "a")
    except AutomateError as e:
        assert "numeric" in str(e)
    else:
        raise AssertionError("non-numeric threshold not caught")

    # evaluation is pure + order-stable
    rules = [
        rule,
        make_rule("bat-crit", "battery-low", "percent", "lt", 5, "suspend"),
        make_rule("ac-on", "battery-low", "percent", "ge", 20, "notify", ["full"]),
        make_rule("net-up", "network", "state", "eq", "up", "notify", ["online"]),
    ]
    fired = evaluate(rules, "battery-low", {"percent": 3})
    assert [f["rule"] for f in fired] == ["bat-low", "bat-crit"]  # store order
    assert fired[0]["action"] == "notify"
    fired_full = evaluate(rules, "battery-low", {"percent": 100})
    assert [f["rule"] for f in fired_full] == ["ac-on"]  # only the ge-20 rule
    assert evaluate(rules, "battery-low", {"percent": "7"})[0]["rule"] == "bat-low"
    assert evaluate(rules, "battery-low", {"other": 1}) == []  # missing field
    assert [f["rule"] for f in evaluate(rules, "network", {"state": "up"})] == ["net-up"]
    # 'in' operator with JSON list value
    r_in = make_rule("combo", "dock", "port", "in", ["hdmi", "dp"], "notify")
    assert evaluate([r_in], "dock", {"port": "dp"})[0]["rule"] == "combo"
    assert evaluate([r_in], "dock", {"port": "vga"}) == []

    # store round-trip, idempotent add, duplicate-id detection
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "rules.json")
        assert load_rules(path) == []  # missing file -> empty
        rules_list, replaced = add_rule(path, rule)
        assert replaced is False and len(rules_list) == 1
        rule2 = make_rule("bat-low", "battery-low", "percent", "lt", 15,
                          "notify", ["meh"])
        rules_list, replaced = add_rule(path, rule2)
        assert replaced is True and len(rules_list) == 1
        assert load_rules(path)[0]["when"]["value"] == 15  # updated in place
        add_rule(path, make_rule("net-up", "network", "state", "eq", "up", "beep"))
        assert len(load_rules(path)) == 2
        with open(path, "w") as fh:
            json.dump([{"id": "a"}, {"id": "a"}], fh)
        try:
            load_rules(path)
        except AutomateError as e:
            assert "duplicate" in str(e)
        else:
            raise AssertionError("duplicate store id not caught")
        with open(path, "w") as fh:
            fh.write('{"not": "a list"}')
        try:
            load_rules(path)
        except AutomateError as e:
            assert "JSON list" in str(e)
        else:
            raise AssertionError("non-list store not caught")
        store_rules = [rule2]
        # schedules
        plan = schedule_plan("bat-low", store_rules, daily="02:30")
        assert plan["cron"] == "30 2 * * *"
        assert plan["on_calendar"] == "*-*-* 02:30:00"
        assert plan["timer_unit"] == "sigma-auto-bat-low.timer"
        assert schedule_plan("bat-low", store_rules, hourly=True)["cron"] == "0 * * * *"
        assert schedule_plan("bat-low", store_rules, weekly=True)["cron"] == "0 4 * * 0"
        assert schedule_plan("bat-low", store_rules, monthly=True)["cron"] == "0 5 1 * *"
        for bad_kwargs in (dict(daily="25:00"), dict(daily="noon"), dict(),
                           dict(daily="02:30", hourly=True)):
            try:
                schedule_plan("bat-low", store_rules, **bad_kwargs)
            except AutomateError:
                pass
            else:
                raise AssertionError(f"bad schedule not caught: {bad_kwargs}")
        try:
            schedule_plan("ghost", store_rules, hourly=True)
        except AutomateError as e:
            assert "unknown rule" in str(e)
        else:
            raise AssertionError("unknown rule not caught")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
