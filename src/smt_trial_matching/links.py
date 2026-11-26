"""Links between facts in different trials, so one answer fills every fact that means the same thing or follows.

Each trial is its own Z3 program, so "has asthma now" in one trial and "diagnosis of asthma now" in another are
separate variables. Two kinds of link, by variable name:
  same:     a and b mean the same thing (a variable name shared by several trials is always the same).
  implies:  if a is true then b is true (so if b is false, a is false), e.g. uncontrolled asthma now -> asthma now.
Links between two different time frames (now, in the history, in the past 12 months...) are left out: patients say
"past" to mean before now, while the trials' "in the history" includes now, so "no past conditions" would rule out
a condition the patient has now.
The table is built once with Gemini, one call per group of facts on the same topic, and saved to links.json.
During a conversation it is pure logic: `propagate` only ever fills facts that are still unknown.

  uv run python -m smt_trial_matching.links      # build links.json for the dev patients' trials
"""

from __future__ import annotations

import collections
import json
from concurrent.futures import ThreadPoolExecutor
from functools import cache
from pathlib import Path

from smt_trial_matching.answerability import parse
from smt_trial_matching.data import patients, variable
from smt_trial_matching.interview import describe, parse_json, topic
from smt_trial_matching.llm import ask_llm

TABLE = Path(__file__).with_name("links.json")
CHUNK = 40  # most facts sent in one call

LINK_PROMPT = """These facts about a patient come from different clinical trials' eligibility rules. Find the
ones that are logically linked.

Facts (id. type: description):
{facts}

Reply with JSON only: {{"same": [[a, b], ...], "implies": [[a, b], ...]}} using fact ids.
- "same": a and b mean exactly the same thing (same condition, same time frame, same detail).
- "implies": if a is true then b must be true, because a is narrower (a more specific form of the condition, or a
  time window inside b's, e.g. "taking steroids now" implies "took steroids in the past 12 months").
  Only yes/no facts go in "implies".
Leave out anything you are not sure about. Reply {{"same": [], "implies": []}} if nothing is linked."""


def build(split: str = "dev") -> dict:
    """Ask Gemini, topic group by topic group, which differently named facts are linked; save the table."""
    names = {}  # variable name -> (type, description), over the split's patients' trials
    for _, trials in patients(split):
        for nct in trials:
            for v in json.loads((Path(__file__).resolve().parents[2] / "data" / "variables" / f"{nct}.json")
                                .read_text()):
                names.setdefault(v["name"], (v["type"], describe(v)))
    groups = collections.defaultdict(list)
    for name in sorted(names):
        groups[topic(name)].append(name)
    chunks = [group[i:i + CHUNK] for group in groups.values() for i in range(0, len(group), CHUNK)]
    chunks = [c for c in chunks if len(c) >= 2]

    def ask(chunk):
        listed = "\n".join(f"{k}. {'yes/no' if names[n][0] == 'Bool' else 'number'}: {names[n][1]}"
                           for k, n in enumerate(chunk, 1))
        return parse_json(ask_llm(LINK_PROMPT.format(facts=listed)))

    same, implies = [], []
    with ThreadPoolExecutor(16) as pool:  # independent calls, so several at once
        answers = list(pool.map(ask, chunks))
    for chunk, found in zip(chunks, answers):
        for kind, out in (("same", same), ("implies", implies)):
            for pair in found.get(kind, []):
                if (isinstance(pair, list) and len(pair) == 2 and all(isinstance(k, int) for k in pair)
                        and all(1 <= k <= len(chunk) for k in pair) and pair[0] != pair[1]):
                    a, b = chunk[pair[0] - 1], chunk[pair[1] - 1]
                    if names[a][0] == names[b][0] and (kind == "same" or names[a][0] == "Bool") \
                            and _same_time_frame(a, b):
                        out.append([a, b])
    table = {"same": same, "implies": implies}
    TABLE.write_text(json.dumps(table, indent=0))
    return table


def _same_time_frame(a: str, b: str) -> bool:
    """False when both facts name a time frame and the two differ (e.g. now and in the history)."""
    ta, tb = parse(a)["timeframe"], parse(b)["timeframe"]
    return ta == tb or "none" in (ta, tb)


@cache
def _table() -> tuple[dict, dict]:
    """name -> names it is the same as; name -> names it implies (and the reverse, for false)."""
    raw = json.loads(TABLE.read_text()) if TABLE.exists() else {"same": [], "implies": []}
    same, down, up = collections.defaultdict(set), collections.defaultdict(set), collections.defaultdict(set)
    for a, b in raw["same"]:
        same[a].add(b)
        same[b].add(a)
    for a, b in raw["implies"]:
        down[a].add(b)  # a true -> b true
        up[b].add(a)  # b false -> a false
    return same, (down, up)


def propagate(states: dict, filled: dict) -> dict:
    """Facts that follow from `filled` ({(trial, name): value}) by the links, in every trial, that are still
    unknown. A name shared by several trials is the same fact in each."""
    same, (down, up) = _table()
    out, todo = {}, list(filled.items())
    while todo:
        (_, name), value = todo.pop()
        follows = {(n, value) for n in same[name] | {name}}
        if value is True:
            follows |= {(n, True) for n in down[name]}
        if value is False:
            follows |= {(n, False) for n in up[name]}
        for other, x in follows:
            for nct, s in states.items():
                key = (nct, other)
                if other in s.types and s.answers.get(other) is None and key not in filled and key not in out \
                        and variable(nct, other) and (s.types[other] == "Bool") == isinstance(x, bool):
                    out[key] = x
                    todo.append((key, x))
    return out


if __name__ == "__main__":
    t = build()
    print(f"{len(t['same'])} 'same' links and {len(t['implies'])} 'implies' links saved to {TABLE}")
