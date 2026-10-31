"""Compare the caps two generators produced for one CAM-SIMA suite.

The reference is original capgen (CAM-SIMA's bundled ccpp_framework); the
other is xdsl-ccpp. The two lay their code out differently, so the
comparison is of what the code does: for each phase (register, init,
timestep_init, run per group, timestep_final, final), the scheme calls in
execution order with their subcycle-loop depth, and for each call the
expression each argument finally receives. An argument is resolved through
the suite routine's dummy arguments, the host cap's calls into it and pointer
associations, back to what the host cap passes.

Both inputs are generated code, whose Fortran is regular: one call per
statement, keyword arguments, no nested routines. ``read_caps`` reads only
that subset.

Where the generators hold the same data in different containers, the
correspondence is stated in ``EQUIVALENT_EXPRESSIONS`` (e.g. capgen's
``cam_constituents_obj%vars_layer`` is xdsl-ccpp's ``lc_constituent_array``).
Variables the generated caps own themselves (suite variables, interstitials)
may be named differently; a consistent one-to-one renaming is accepted and
reported, any other mismatch is a difference.
"""

from __future__ import annotations

import collections
import glob
import os
import re
from dataclasses import dataclass, field

PHASES = ("register", "init", "timestep_init", "run", "timestep_final", "final")

_SUB = re.compile(r"^(?:\w+\s+)*subroutine\s+(\w+)\s*(?:\((.*)\))?", re.I)
_ENDSUB = re.compile(r"^end\s+subroutine", re.I)
_CALL = re.compile(r"^(?:if\s*\(.*\)\s*)?call\s+(\w+)\s*(?:\((.*)\))?\s*$", re.I)
_DO = re.compile(r"^(?:\w+\s*:\s*)?do\b(?!\s*while\b.*\bnot\b)", re.I)
_ENDDO = re.compile(r"^end\s*do\b", re.I)
_POINTER = re.compile(r"^(\w+)\s*=>\s*(.+)$")
_ASSIGN = re.compile(r"^(\w+)(?:\([^=]*\))?\s*=(?![=>])\s*(.+)$")
_CONST_INDEX = re.compile(r"const_index\(\s*(\w+)\s*,\s*'(\w+)'", re.I)
_CAPGEN_INDEX_NAMES = re.compile(r"(\w+)_const_stdnames\(\d+\)\s*=\s*\(/(.*?)/\)", re.S)
# A section covering a whole dimension: (:), (col_start:col_end), (1:n), ...
_WHOLE_SECTION = re.compile(
    r"\((?:\s*(?::|col_start\s*:\s*col_end|1\s*:\s*\$?\w+|1:size\(\w+,\d\))\s*,?)+\)$", re.I)

# The same data in each generator's containers, mapped to one name. capgen's
# host cap passes CAM's cam_constituents_obj components; xdsl-ccpp's host cap
# keeps its own lc_* pointers to the same object.
EQUIVALENT_EXPRESSIONS = [
    (r"cam_constituents_obj%vars_layer_tend\b", "$const_tend"),
    (r"(?<![$\w])lc_const_tend\b", "$const_tend"),
    (r"cam_constituents_obj%vars_layer\b", "$const"),
    (r"cam_constituents_obj%field_data_ptr\(\)", "$const"),
    (r"cam_constituents_obj%num_layer_vars\b", "$nconst"),
    (r"size\(lc_all_constituents\)", "$nconst"),
    (r"cam_constituents_obj%const_metadata\b", "$cprops"),
    (r"(?<![$\w])lc_const_props\b", "$cprops"),
    (r"cam_constituents_obj%vars_minvalue\b", "$qmin"),
    (r"(?<![$\w])(errcode|errflg)\b", "$errflg"),
    # the register phase's dynamic-constituent arrays
    (r"^lc_(\w*(constituents|consts))$", r"\1"),
    # outside the run phase both pass the whole task: col_start = 1 and
    # col_end = columns_on_task
    (r"^\(?col_end-col_start\+1\)?$", "columns_on_task"),
]


def logical_lines(path: str) -> list[str]:
    """Free-form Fortran statements: comments removed, continuations joined."""
    out, buf = [], ""
    for raw in open(path):
        s = _strip_comment(raw.rstrip("\n")).strip()
        if not s:
            continue
        if s.startswith("&"):
            s = s[1:].lstrip()
        if s.endswith("&"):
            buf += s[:-1] + " "
            continue
        out.append(buf + s)
        buf = ""
    return out


def _strip_comment(line: str) -> str:
    quote = None
    for i, c in enumerate(line):
        if quote:
            if c == quote:
                quote = None
        elif c in "'\"":
            quote = c
        elif c == "!":
            return line[:i]
    return line


def split_args(text: str) -> list[str]:
    """Split an argument list at top-level commas."""
    parts, depth, cur, quote = [], 0, "", None
    for c in text:
        if quote:
            cur += c
            if c == quote:
                quote = None
            continue
        if c in "'\"":
            quote = c
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        elif c == "," and depth == 0:
            parts.append(cur.strip())
            cur = ""
            continue
        cur += c
    if cur.strip():
        parts.append(cur.strip())
    return parts


def bind(dummies: list[str], args: list[str]) -> dict[str, str]:
    """Dummy name -> actual expression, for keyword or positional arguments."""
    out = {}
    for i, a in enumerate(args):
        m = re.match(r"^(\w+)\s*=(?!=)\s*(.*)$", a, re.S)
        if m:
            out[m.group(1).lower()] = m.group(2).strip()
        elif i < len(dummies):
            out[dummies[i]] = a
    return out


def phase_of(entry: str) -> tuple[str | None, str]:
    """(phase, scheme) of a scheme entry point name."""
    for p in ("timestep_init", "timestep_final", "register", "init", "run", "final"):
        if entry.endswith("_" + p):
            return p, entry[: -len(p) - 1]
    return None, entry


def _normalize(expr: str) -> str:
    e = re.sub(r"\s+", "", expr).lower()
    prev = None
    while prev != e:
        prev = e
        e = _WHOLE_SECTION.sub("", e)
    return e


def _parenthesize(v: str) -> str:
    return v if re.match(r"^[\w%@$]+$", v) or _enclosed(v) else "(" + v + ")"


def _enclosed(v: str) -> bool:
    """True if v is a single parenthesized expression."""
    if not (v.startswith("(") and v.endswith(")")):
        return False
    depth = 0
    for i, c in enumerate(v):
        depth += c == "("
        depth -= c == ")"
        if depth == 0 and i < len(v) - 1:
            return False
    return True


def _conversion(rhs: str) -> str:
    """A unit conversion's right-hand side, so that x*c and c*x agree and so
    do 1.0E-2_kind_phys and 0.01_kind_phys."""
    e = re.sub(r"(?<![\w.])(\d+\.?\d*(?:[ed][-+]?\d+)?)_\w+",
               lambda m: repr(float(m.group(1).replace("d", "e"))), rhs)
    parts = e.split("*")
    return "*".join(sorted(parts)) if len(parts) == 2 else e


@dataclass
class Call:
    scheme: str
    entry: str
    depth: int                      # enclosing loop depth in the suite routine
    args: dict[str, str]            # scheme dummy -> resolved expression


@dataclass
class Caps:
    """One generator's caps: the routines of the suite and host caps."""
    groups: tuple[str, ...]
    dummies: dict[str, list[str]] = field(default_factory=dict)
    calls_in: dict[str, list[tuple[str, list[str], int]]] = field(default_factory=dict)
    pointers: dict[str, tuple[str, str]] = field(default_factory=dict)
    index_names: dict = field(default_factory=dict)       # (array, k) -> standard name
    assigns: dict = field(default_factory=dict)            # (routine, local) -> [rhs]
    suite_routines: set = field(default_factory=set)
    owned: set = field(default_factory=set)               # variables the caps declare
    callers: dict = field(default_factory=lambda: collections.defaultdict(list))

    def calls(self) -> dict[tuple[str, str | None], list[Call]]:
        """{(phase, group or None): [Call]} in execution order; groups only
        distinguish the run phase."""
        out: dict = {}
        for routine, events in self.calls_in.items():
            if routine not in self.suite_routines:
                continue
            group = max((g for g in self.groups if g in routine), key=len, default=None)
            for name, args, depth in events:
                phase, scheme = phase_of(name)
                if phase is None:
                    continue
                key = (phase, group if phase == "run" else None)
                out.setdefault(key, []).append(Call(
                    scheme, name, depth,
                    {k: self.resolve(routine, v) for k, v in bind([], args).items()}))
        return out

    def resolve(self, routine: str, expr: str, seen: tuple = ()) -> str:
        """The expression <expr> in <routine> finally stands for."""
        dummies = set(self.dummies.get(routine, []))

        def substitute(m):
            w = m.group(0).lower()
            if w in dummies:
                values = {self.resolve(c, b[w], seen) for c, b in self.callers.get(routine, []) if w in b}
                return _parenthesize(values.pop()) if len(values) == 1 else w
            if w in self.pointers and w not in seen:
                r, e = self.pointers[w]
                return _parenthesize(self.resolve(r, e, seen + (w,)))
            rhs = self.assigns.get((routine, w), [])
            if len(rhs) == 1 and re.search(r"[*/]|col_end", rhs[0]) and w not in seen:
                v = self.resolve(routine, rhs[0], seen + (w,))
                return ("conv(" + _conversion(v) + ")" if re.search(r"[*/]", rhs[0])
                        else _parenthesize(v))
            return w

        e = re.sub(r"(?<![%@$\w.])[A-Za-z_]\w*", substitute, expr)
        e = re.sub(r"(\w+)\((\d+)\)",
                   lambda m: "@" + self.index_names[(m.group(1).lower(), int(m.group(2)))]
                   if (m.group(1).lower(), int(m.group(2))) in self.index_names else m.group(0), e)
        e = _normalize(e)
        for pattern, replacement in EQUIVALENT_EXPRESSIONS:
            e = re.sub(pattern, replacement, e)
        return e


def read_caps(cap_dir: str, groups) -> Caps:
    """Read a generator's output directory: the host cap cam_ccpp_cap.F90 and
    the suite caps (the other *_cap.F90 files)."""
    caps = Caps(tuple(groups))
    host = os.path.join(cap_dir, "cam_ccpp_cap.F90")
    suite_files = [f for f in glob.glob(os.path.join(cap_dir, "*_cap.F90")) if f != host]
    for path in suite_files + [host]:
        routines = _scan(caps, path)
        if path != host:
            caps.suite_routines |= routines
        for line in logical_lines(path):
            m = re.match(r"^[^!]*::\s*(.+)$", line)
            if m and not line.lower().startswith("use") and "intent" not in line.lower():
                for v in split_args(m.group(1)):
                    n = re.match(r"\s*(\w+)", v)
                    if n:
                        caps.owned.add(n.group(1).lower())
    for routine, events in caps.calls_in.items():
        for callee, args, _ in events:
            if callee in caps.dummies:
                caps.callers[callee].append((routine, bind(caps.dummies[callee], args)))
    return caps


def _scan(caps: Caps, path: str) -> set:
    """Record one file's routines, calls, pointers and assignments; returns
    the routine names."""
    lines = logical_lines(path)
    # capgen: <host>_const_stdnames(n) = (/ 'a', 'b' /) names <host>_const_indices
    for m in _CAPGEN_INDEX_NAMES.finditer("\n".join(lines)):
        for k, s in enumerate(re.findall(r"['\"]\s*(\w+)\s*['\"]", m.group(2)), 1):
            caps.index_names[(m.group(1) + "_const_indices", k)] = s
    routines, cur, depth, local_index = set(), None, 0, {}
    for line in lines:
        m = _SUB.match(line)
        if m and not line.lower().startswith("end"):
            cur = m.group(1).lower()
            routines.add(cur)
            caps.dummies[cur] = [x.strip().lower() for x in (m.group(2) or "").split(",") if x.strip()]
            caps.calls_in[cur] = []
            local_index, depth = {}, 0
            continue
        if cur is None:
            continue
        if _ENDSUB.match(line):
            cur = None
            continue
        a = _ASSIGN.match(line)
        if a and a.group(1).lower() not in caps.dummies[cur]:
            caps.assigns.setdefault((cur, a.group(1).lower()), []).append(a.group(2))
        for var, std in _CONST_INDEX.findall(line):
            local_index[var.lower()] = std
        statement = line.split(" then ")[-1].strip()
        if _DO.match(line):
            depth += 1
        elif _ENDDO.match(line):
            depth -= 1
        elif _POINTER.match(statement):
            p = _POINTER.match(statement)
            # an index just set by const_index names the constituent
            rhs = re.sub(r"\b\w+\b", lambda w: "@" + local_index[w.group(0).lower()]
                         if w.group(0).lower() in local_index else w.group(0), p.group(2))
            caps.pointers[p.group(1).lower()] = (cur, rhs)
        else:
            c = _CALL.match(line)
            if c:
                caps.calls_in[cur].append((c.group(1).lower(), split_args(c.group(2) or ""), depth))
    return routines


def compare(reference_dir: str, other_dir: str, groups) -> tuple[list[str], list[tuple[str, str]]]:
    """Differences between the reference (capgen) and the other (xdsl-ccpp)
    caps, and the accepted renamings of cap-owned variables."""
    a, b = read_caps(reference_dir, groups), read_caps(other_dir, groups)
    ca, cb = a.calls(), b.calls()
    diffs, pairs = [], []
    for key in sorted(set(ca) | set(cb), key=lambda k: (PHASES.index(k[0]), k[1] or "")):
        la, lb = ca.get(key, []), cb.get(key, [])
        where = key[0] + ("/" + key[1] if key[1] else "")
        sa, sb = [(c.scheme, c.depth) for c in la], [(c.scheme, c.depth) for c in lb]
        if sa != sb:
            diffs.append(f"{where}: call sequence differs\n    capgen: {_sequence(sa)}\n"
                         f"    xdsl:   {_sequence(sb)}")
        pa, pb = _by_occurrence(la), _by_occurrence(lb)
        for k in [k for k in pa if k in pb]:
            ba, bb = pa[k].args, pb[k].args
            for dummy in sorted(set(ba) | set(bb)):
                va, vb = ba.get(dummy), bb.get(dummy)
                msg = f"{where}: {k[0]}#{k[1]} {dummy}: capgen {va} | xdsl {vb}"
                if va != vb and va and vb and va in a.owned and vb in b.owned:
                    pairs.append((va, vb, msg))
                elif va != vb:
                    diffs.append(msg)
    # Cap-owned variables may be named differently: accept a consistent
    # one-to-one renaming, report a name that maps two ways.
    fwd, back = collections.defaultdict(set), collections.defaultdict(set)
    for va, vb, _ in pairs:
        fwd[va].add(vb)
        back[vb].add(va)
    renames = set()
    for va, vb, msg in pairs:
        if len(fwd[va]) == 1 and len(back[vb]) == 1:
            renames.add((va, vb))
        else:
            diffs.append(msg + "  (inconsistent naming)")
    return diffs, sorted(renames)


def _by_occurrence(calls: list[Call]) -> dict:
    n, out = collections.Counter(), {}
    for c in calls:
        n[c.entry] += 1
        out[(c.entry, n[c.entry])] = c
    return out


def _sequence(seq) -> str:
    return " ".join(("[" * d) + s + ("]" * d) for s, d in seq)
