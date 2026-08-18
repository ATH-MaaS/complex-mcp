from client.agent import OpenAIBackend, HumanAnnotator, AgentClient, Toolbox
from client.rag import ChromaRAG
from benchmark.rubric_pytest_judge import make_openai_rubric_judge, make_anthropic_rubric_judge
from benchmark.rubric_judge import evaluate_rubric, find_rubric_for_task, load_rubric
from benchmark.classify_failure import classify as _classify_failure, parse_expected_tools as _parse_expected_tools
from benchmark.passk import estimate as _passk_estimate
from benchmark.harbor_layout import slug_of as _hslug
from scripts.task_writer import write_task_dir, write_mcp_stump_run, write_trials_aggregate, parse_trajectory as _parse_traj_for_layout, parse_trajectory
from software.utils import fixtures
from software.utils.seed_content_registry import seed_rolls_content
from dotenv import load_dotenv
from argparse import ArgumentParser
from prompt_toolkit import prompt
from typing import Dict, Any
from pathlib import Path
import random
import json

import sys
import os
import hashlib
import re
import uuid as _stdlib_uuid
import subprocess
import yaml
import asyncio
from collections import Counter
from datetime import datetime, timezone

import pandas as pd
from shortuuid import uuid

# A4 reconciliation (seed_content_registry.py): dedup so the seed/content
# advisory below prints once per offending app-set per process, not once
# per task -- a full benchmark run is thousands of tasks.
_WARNED_STATIC_SEED_APPS = set()

def _aggregate_trials_on_disk(run_dir: Path, model: str) -> dict:
    """Corpus roll-up over EVERY ``trials_*/summary.json`` present on disk.

    The per-invocation summary only knows about the episodes THIS run touched, so
    running tasks piecemeal (or re-running one) leaves the top-level accuracy as
    last-writer-wins -- one episode instead of the whole corpus (defect A1). This
    re-reads every trials dir so the headline number is always correct.
    """
    tasks: list[dict] = []
    # mcp-stump layout puts trials dirs directly under run_dir; the harbor layout
    # nests them at <task-slug>/.raw/trials_*. Globbing only the flat form
    # reported "0 tasks, accuracy 0.0" for every harbor run -- the roll-up found
    # nothing and said so as though it were a result.
    # Three shapes: mcp-stump (flat), harbor pointed at the output root, and
    # harbor pointed at a single task dir (the per-task roll-up).
    trial_dirs = sorted(run_dir.glob("trials_*")) + \
        sorted(run_dir.glob("*/.raw/trials_*")) + \
        sorted(run_dir.glob(".raw/trials_*"))
    for sd in trial_dirs:
        sp = sd / "summary.json"
        if not sp.is_file():
            continue
        try:
            s = json.loads(sp.read_text())
        except json.JSONDecodeError:
            continue
        m = s.get("metrics", {}) or {}
        attempts = s.get("attempts", []) or []
        n = m.get("n") or len(attempts) or 0
        c = m.get("c")
        if c is None:
            c = sum(1 for a in attempts if a.get("passed"))
        rewards = [a.get("reward") for a in attempts if a.get("reward") is not None]
        mean_reward = round(sum(rewards) / len(rewards), 6) if rewards else None
        tasks.append({
            "task": s.get("task", sd.name),
            "n": n, "c": c,
            "pass@1": round(c / n, 6) if n else 0.0,
            "pass@k": m.get("pass@k", {}) or {},
            "pass^k": m.get("pass^k", {}) or {},
            "mean_reward_per_trial": mean_reward,
            "failure_breakdown": m.get("failure_breakdown", {}) or {},
        })
    total = len(tasks)
    passed = sum(1 for t in tasks if (t["c"] or 0) >= 1)
    hist: Counter = Counter()
    for t in tasks:
        for k, v in t["failure_breakdown"].items():
            hist[k] += v
    all_ks = sorted({int(k) for t in tasks for k in t["pass@k"]})

    def _mean(field: str, k: int) -> float | None:
        vals = [t[field].get(str(k)) for t in tasks if str(k) in t[field]]
        return round(sum(vals) / len(vals), 6) if vals else None

    task_rewards = [t["mean_reward_per_trial"] for t in tasks
                    if t.get("mean_reward_per_trial") is not None]
    corpus_mean_reward = (round(sum(task_rewards) / len(task_rewards), 6)
                          if task_rewards else None)
    return {
        "model": model,
        "tasks": total,
        "passed": passed,
        "accuracy": round(passed / total, 6) if total else 0.0,
        "mean_reward_per_trial": corpus_mean_reward,
        "mean_pass@k": {str(k): _mean("pass@k", k) for k in all_ks},
        "mean_pass^k": {str(k): _mean("pass^k", k) for k in all_ks},
        "failure_mode_histogram": dict(hist.most_common()),
        "per_task": tasks,
    }


def _scoped_summary(summary: dict, task_name: str) -> dict:
    """`summary` narrowed to one task, with its headline metrics recomputed.

    The invocation-level summary aggregates every task in the run, so dropping a
    copy of it into each task directory would report other tasks' numbers under
    this task's name. Filtering the episodes and re-deriving the averages from
    them keeps each task directory self-describing.
    """
    eps = [e for e in summary.get("episodes", []) if e.get("name") == task_name]
    out = {**summary, "episodes": eps, "scope": "task", "task": task_name}
    if not eps:
        return out

    def _avg(fn):
        vals = [v for v in (fn(e) for e in eps) if v is not None]
        return round(sum(vals) / len(vals), 6) if vals else 0.0

    def _rate(e, num, den):
        j = e.get("judge") or {}
        t = j.get(den) or 0
        return (j.get(num) or 0) / t if t else None

    out["metrics"] = {
        "accuracy": round(sum(1 for e in eps if e.get("passed")) / len(eps), 6),
        "avg_completion_rate": _avg(lambda e: _rate(e, "recall", "total")),
        "avg_misbehave_rate": _avg(lambda e: _rate(e, "misbehave", "total")),
        "avg_valid_tool_calls": _avg(lambda e: e.get("valid_tool_calls")),
        "avg_invalid_tool_calls": _avg(lambda e: e.get("invalid_tool_calls")),
        "avg_error_tool_calls": _avg(lambda e: e.get("error_tool_calls")),
        "avg_prompt_tokens": _avg(lambda e: (e.get("tokens") or {}).get("prompt")),
        "avg_llm_tokens": _avg(lambda e: (e.get("tokens") or {}).get("llm")),
        "avg_tool_tokens": _avg(lambda e: (e.get("tokens") or {}).get("tool")),
    }
    out["config"] = {**summary.get("config", {}), "episodes": len(eps)}
    return out


def _iso_z(dt) -> str | None:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z" if dt else None


def _phase_timings(trial_start, agent_start, agent_end) -> dict:
    """The four phase spans result.json carries.

    Only the spans this process actually measures are filled. `environment_setup`
    and `agent_setup` happen once per process (the sandbox is brought up outside
    the attempt loop, or by scripts/run_task.sh), so attributing them to a
    particular attempt would invent a measurement -- they stay null.
    """
    now = datetime.now(timezone.utc)
    return {
        "started_at": _iso_z(trial_start),
        "finished_at": _iso_z(now),
        "environment_setup": None,
        "agent_setup": None,
        "agent_execution": {"started_at": _iso_z(agent_start),
                            "finished_at": _iso_z(agent_end)},
        # Everything between the rollout ending and the record being written is
        # grading.
        "verifier": {"started_at": _iso_z(agent_end), "finished_at": _iso_z(now)},
    }


def parse_toolbox(tool_config_path: str | Path, method: str, rag_conf: Dict = {}):
    config = {}
    with open(tool_config_path) as f:
        data = yaml.safe_load(f)
        config["servers"] = data["servers"]

    toolbox = Toolbox(method=method) if method not in ["rag", "fetch"] else Toolbox(method=method, rag_cls=ChromaRAG, default_k=rag_conf["topk"])
    skipped = []
    for server in config["servers"]:
        if not server["use"]: continue
        server_args = {
            "server_name": server["name"],
            "server_url": server["url"],
            "desc_path": server.get("desc"),
            "use_sandbox": server.get("use_sandbox", False)
        }
        try:
            toolbox.register_server(**server_args)
        except Exception as exc:
            skipped.append((server["name"], type(exc).__name__))
    if skipped:
        print(f"[toolbox] skipped {len(skipped)} unreachable server(s): " + ", ".join(f"{n}({e})" for n, e in skipped[:5]) + (" ..." if len(skipped) > 5 else ""))
    return toolbox

def add_data(query_result: Dict[str, Any]):
    dataset_path = Path("benchmark") / "data" / "data.parquet"
    if os.path.exists(dataset_path):
        df = pd.read_parquet(dataset_path)
    else:
        df = pd.DataFrame()
    new_df = pd.DataFrame(query_result)
    df = pd.concat([df, new_df])

    df.to_parquet(dataset_path)

def gen_instruct_by_human(agent: AgentClient, generate: bool):
    toolbox = agent.toolbox
    method = toolbox.method

    assert method != "provide"
    apps = [app for app in toolbox.servers if app in {"LightTalk", "LightShop", "LightWeather", "LightFlight", "LightStock", "LightNews"}]
    level = int(prompt("> level: "))
    query = f"{prompt('> instruct: ')}\nOnce you've completed the task—or if you believe it's unsolvable—output [END] at the end."

    task = agent.process_query(
        query=query,
        max_turns=10000,
        verbose=True,
        stop_tag="[END]",
        env={
            "apps": apps
        }
    )

    result = asyncio.run(task)
    print(result["tool_cnt"])

    if generate:
        query_result = {
            "query": [query],
            "apps": [json.dumps(apps)],
            "level": [level],
            "output": [json.dumps(result["output"])],
            "tool_cnt": [json.dumps(result["tool_cnt"])],
            "gt_env": [json.dumps(result["apps"])]
        }
        ok = prompt(">>> Pass this query? [Y/n] ")
        if ok.strip().lower() == "y":
            add_data(query_result)

def _load_parquet_tasks(path: Path, task_name: str | None, limit: int) -> list[dict]:
    df = pd.read_parquet(path)
    # Seedless: legacy parquet datasets may still carry a "seed" column; it is a
    # dead row label now (worlds are static fixtures) and is neither required nor used.
    if task_name and "seed" in df.columns:
        df = df[df["seed"].astype(str) == task_name].reset_index(drop=True)
    if limit > 0:
        df = df.head(limit).reset_index(drop=True)
    out: list[dict] = []
    for i in range(len(df)):
        row = df.iloc[i]
        apps = json.loads(row["apps"])
        gt_env = json.loads(row["gt_env"])
        gt_tool_cnt = json.loads(row["tool_cnt"])
        level = row.get("level")
        try:
            level = int(level) if level is not None else None
        except (TypeError, ValueError):
            pass
        name = f"parquet-ep{i + 1:03d}"
        if level is not None:
            name = f"parquet-l{level}-ep{i + 1:03d}"
        out.append({
            "name": name,
            "query": row["query"],
            "apps": apps,
            "level": level,
            "gt_env": gt_env,
            "gt_tool_cnt": gt_tool_cnt,
            "provide_tools": list(gt_tool_cnt.keys()),
        })
    return out


def _extract_task_query(instr: str) -> str:
    """Extract the full agent-facing task text from an instruction.md, format-agnostic.

    Takes everything under the "# Task" heading (or the whole file if there is no
    such heading) and drops the metadata footer at the first horizontal rule
    (---, ***, or ___ on its own line). Multi-paragraph aware: unlike the old
    regex it does NOT stop at the first blank line, and it relies on no specific
    sentinel phrase (e.g. "Once ...").
    """
    m = re.search(r"(?im)^\s*#\s*task\s*$", instr)
    body = instr[m.end():] if m else instr
    # Cut the footer (Environment/Level/Success block) at the first thematic break.
    body = re.split(r"(?m)^[ \t]*(?:-{3,}|\*{3,}|_{3,})[ \t]*$", body, maxsplit=1)[0]
    # Strip HTML comments (e.g. the `<!-- harbor-canary GUID ... -->` corpus
    # canary) so they never reach the model -- they stay in instruction.md for
    # training-corpus leak detection but must not appear in the agent prompt.
    body = re.sub(r"<!--.*?-->", "", body, flags=re.DOTALL)
    return body.strip()


def _load_harbor_tasks(dir_path: Path, task_name: str | None, limit: int) -> list[dict]:
    import tomllib
    task_dirs = sorted([d for d in dir_path.iterdir()
                        if d.is_dir() and (d / "task.toml").exists()])
    if task_name:
        task_dirs = [d for d in task_dirs
                     if d.name == task_name or d.name.startswith(task_name)]
    if limit > 0:
        task_dirs = task_dirs[:limit]
    out: list[dict] = []
    for td in task_dirs:
        with open(td / "task.toml", "rb") as f:
            info = tomllib.load(f)
        meta = info.get("task", {}).get("metadata", {}) or info.get("metadata", {})
        apps = meta.get("apps", [])
        if isinstance(apps, str):
            apps = json.loads(apps)
        # Harbor task.toml often declares no apps. Without them the client logs
        # into / seeds nothing, so every tool call returns "<App> has not been
        # logged into yet" and the world snapshot is empty. Derive the apps from
        # the gold plan's server_names (LightSystem is the implicit login server
        # and must NOT be listed -- it crashes __login).
        if not apps:
            gp_path = td / "tests" / "gold_plan.json"
            if gp_path.exists():
                try:
                    gp = json.loads(gp_path.read_text())
                    seen: list[str] = []
                    for step in gp:
                        for alt in (step if isinstance(step, list) else [step]):
                            sv = alt.get("server_name") or alt.get("server")
                            if sv and sv != "LightSystem" and sv not in seen:
                                seen.append(sv)
                    apps = seen
                except (json.JSONDecodeError, AttributeError, TypeError):
                    pass
        with open(td / "instruction.md") as f:
            instr = f.read()
        query = _extract_task_query(instr) or info["task"].get("description", "")
        gt_env = None
        gt_env_path = td / "tests" / "gt_env.json"
        if gt_env_path.exists():
            gt_env = json.loads(gt_env_path.read_text())
        gt_tool_cnt = None
        etc = meta.get("expected_tool_calls")
        if isinstance(etc, str):
            try:
                gt_tool_cnt = json.loads(etc)
            except json.JSONDecodeError:
                gt_tool_cnt = None
        # Implicit tool selection (ETOM-style): do NOT hand the agent the ground-truth tools.
        # expected_tool_calls stays diagnostic-only; the agent must select tools from the query.
        provide_tools = None
        # The user authors the pytest + rubric that live in the task's tests/ (Skoll manual-kit style).
        grading_dir = td / "tests"
        has_rubric_pytest = (grading_dir / "test_outputs.py").exists() and \
            (grading_dir / "test_weights.json").exists()
        # Seedless: worlds are static fixtures (software/<App>/world.pkl); no seed
        # is derived, consumed, or needed. The user provides only the query + apps.
        # Task metadata for failure classification (commit c171043 / 9990708).
        stump_levers = meta.get("stump_levers") or []
        if isinstance(stump_levers, str):
            try:
                stump_levers = json.loads(stump_levers)
            except json.JSONDecodeError:
                stump_levers = [stump_levers]
        out.append({
            "name": info["task"]["name"],
            "query": query,
            "apps": apps,
            "seed": meta.get("seed"),
            "fixture": meta.get("fixture"),
            "world_data": meta.get("world_data"),
            "level": meta.get("level"),
            "gt_env": gt_env,
            "gt_tool_cnt": gt_tool_cnt,
            "provide_tools": provide_tools,
            "grading_dir": str(grading_dir) if has_rubric_pytest else None,
            "stump_levers": list(stump_levers),
            "capability_level": meta.get("capability_level"),
            "expected_tool_calls": meta.get("expected_tool_calls"),
            "task_dir": str(td),
            "grader": meta.get("grader"),
        })
    return out


def load_tasks(source: str, path: Path, task_name: str | None, limit: int) -> list[dict]:
    if source == "auto":
        source = "harbor" if path.is_dir() else "parquet"
    if source == "parquet":
        return _load_parquet_tasks(path, task_name, limit)
    if source == "harbor":
        return _load_harbor_tasks(path, task_name, limit)
    raise ValueError(f"unknown source: {source}")


def main(args):
    model = args.__getattribute__("model")
    tool_config_path = args.__getattribute__("tool_config")
    custom = args.__getattribute__("custom")
    generate = args.__getattribute__("generate")
    distraction = args.__getattribute__("distraction")
    topk = args.__getattribute__("topk")
    rag_conf = {
        "topk": topk
    }

    method = args.__getattribute__("method") if distraction == -1 else "provide"

    toolbox = parse_toolbox(tool_config_path, method, rag_conf) if tool_config_path else None
    native_tools = getattr(args, "native_tools", False)
    # Enable extended thinking by default on the Anthropic/ccbridge path so the
    # trajectory captures reasoning text + signatures and usage carries thinking
    # tokens. setdefault => an explicit MAX_THINKING_TOKENS (incl. "0" to disable)
    # always wins. Ignored by non-thinking backends (OpenAIBackend uses
    # reasoning_effort instead).
    os.environ.setdefault("MAX_THINKING_TOKENS", "4000")
    if model == "human":
        llm = HumanAnnotator()
    elif native_tools:
        # Native function-calling needs an OpenAI-compatible endpoint (the proxy),
        # so force OpenAIBackend even for claude* models.
        llm = OpenAIBackend(model=model)
    elif model.startswith("claude") or model in ("sonnet", "opus", "haiku"):
        # If a ccbridge (or any Anthropic endpoint) is wired via ANTHROPIC_BASE_URL,
        # call /v1/messages directly -- this returns full extended-thinking (text +
        # signature) and the cache breakdown inline, unlike `claude -p` which
        # redacts thinking and trips a connectors conflict against a custom endpoint.
        if os.environ.get("ANTHROPIC_BASE_URL") or os.environ.get("ANTHROPIC_API_BASE"):
            from client.agent import AnthropicBridgeBackend
            llm = AnthropicBridgeBackend(model=model)
        else:
            from client.agent import ClaudeCodeBackend
            llm = ClaudeCodeBackend(model=model)
    else:
        llm = OpenAIBackend(model=model)
    if toolbox and native_tools:
        agent_system_prompt = toolbox.get_native_system_prompt()
    elif toolbox:
        agent_system_prompt = toolbox.get_system_prompt()
    else:
        agent_system_prompt = ""
    agent = AgentClient(
        llm=llm,
        toolbox=toolbox,
        system_prompt=agent_system_prompt
    )

    if custom:
        gen_instruct_by_human(
            agent=agent,
            generate=generate
        )
        return

    source = getattr(args, "source", "auto")
    task_name = getattr(args, "task", None) or None
    limit = getattr(args, "limit", 0) or 0
    tasks_dir_arg = getattr(args, "tasks_dir", None)
    if tasks_dir_arg:
        data_path = Path(tasks_dir_arg)
    else:
        data_path = Path("benchmark") / "data" / "data.parquet"
    tasks_list = load_tasks(source, data_path, task_name, limit)
    if not tasks_list:
        raise SystemExit(f"no tasks selected from {data_path} (source={source}, task={task_name!r})")
    print(f"[input] loaded {len(tasks_list)} task(s) from {data_path}")

    avg_recall_rate = 0
    avg_misbehave_rate = 0
    acc_cnt = 0
    avg_valid_tc = 0
    avg_error_tc = 0
    avg_invalid_tc = 0

    prompt_tokens = 0
    llm_tokens = 0
    tool_tokens = 0

    layout = getattr(args, "layout", "legacy") or "legacy"
    default_output = "output" if layout in ("mcp-stump", "harbor") else "runs"
    output_dir = getattr(args, "output_dir", None) or default_output
    run_dir = None
    tasks_dir = None
    per_episode: list = []
    controls_by_task: dict = {}
    trials_runs: dict[str, list[dict]] = {}
    # Channel-B rubric judge (Skoll-style). Built once. Prefer OpenAI creds; fall
    # back to the Anthropic ccbridge (ANTHROPIC_BASE_URL/API_KEY) so the rubric
    # still runs without an OpenAI key. None only if neither backend is available,
    # in which case rubric+pytest tasks grade on Channel A (pytest) alone.
    rubric_judge = make_openai_rubric_judge() or make_anthropic_rubric_judge()
    if output_dir:
        safe_model = re.sub(r"[^A-Za-z0-9._-]+", "_", model).strip("_") or "model"
        if layout in ("mcp-stump", "harbor"):
            run_dir = Path(output_dir)
            tasks_dir = run_dir
            tasks_dir.mkdir(parents=True, exist_ok=True)
        else:
            run_id = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}__{safe_model}__{method}"
            run_dir = Path(output_dir) / run_id
            tasks_dir = run_dir / "tasks"
            tasks_dir.mkdir(parents=True, exist_ok=True)
        print(f"[output] writing results to {run_dir} (layout={layout})")

    n_attempts = max(1, getattr(args, "n_attempts", 1) or 1)
    at_ks = getattr(args, "at_ks", None) or [1]

    # Harbor layout: one job per task (D8). The id and timestamp are fixed once
    # per invocation so every trial of every task agrees on them.
    _harbor_job_id = str(_stdlib_uuid.uuid4())
    _harbor_stamp = datetime.now().strftime("%H%M%S")
    _harbor_started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"
    _harbor_trials: dict[str, list] = {}
    _harbor_job_labels: dict[str, str] = {}
    _harbor_task_dirs: dict[str, str] = {}

    for i in range(len(tasks_list)):
        print(f"Completion: [{i + 1} / {len(tasks_list)}]")
        task_info = tasks_list[i]
        query = task_info["query"]
        apps = task_info["apps"]
        gt_env = task_info.get("gt_env")
        gt_tool_cnt = task_info.get("gt_tool_cnt") or {}
        episode_name = task_info["name"]
        # Seed architecture: the task's declared seed drives the world. Apps read
        # $COMPLEXMCP_SEED at login (software.utils.world_snapshot.resolve_seed),
        # so set it here before any world boots. The task's baked old_env/gt_env
        # must be baked at this same seed (benchmark/bake_state.py).
        if task_info.get("seed") is not None:
            os.environ["COMPLEXMCP_SEED"] = str(task_info["seed"])
        # Task-specific world overlay (software.utils.fixtures): apps whose world
        # is rolled randomly (LightShop/Wallet/Budget/Talk) read this at login to
        # inject fixed story entities. Must match the fixture the task's gt_env
        # was baked with; cleared when absent so it never leaks across tasks.
        if task_info.get("fixture"):
            os.environ["COMPLEXMCP_FIXTURE"] = str(task_info["fixture"])
        else:
            os.environ.pop("COMPLEXMCP_FIXTURE", None)
        # Bring-your-own world data (software.utils.world_data): a task's own
        # "world_data" meta (e.g. a Harbor bundle's bundle-relative world_data/)
        # wins per-task; otherwise fall back to the run-wide --world-data dir;
        # cleared when neither is set so it never leaks across tasks.
        if task_info.get("world_data"):
            os.environ["COMPLEXMCP_WORLD_DATA"] = str(task_info["world_data"])
        elif getattr(args, "world_data", None):
            os.environ["COMPLEXMCP_WORLD_DATA"] = str(Path(args.world_data).resolve())
        else:
            os.environ.pop("COMPLEXMCP_WORLD_DATA", None)
        # A4 reconciliation: task.toml's seed and world_data/fixture are two
        # independent content mechanisms (see seed_content_registry.py). If a
        # task declares a seed but no world_data/fixture is active, any app
        # whose content the registry says is seed-static won't actually vary
        # -- warn once per offending app-set so this doesn't get discovered by
        # staring at a state-diff instead.
        if task_info.get("seed") is not None and not os.environ.get("COMPLEXMCP_WORLD_DATA"):
            _fixture_apps = {app for (_, app) in fixtures._REGISTRY} if os.environ.get("COMPLEXMCP_FIXTURE") else set()
            _static_apps = sorted(
                a for a in apps
                if a not in _fixture_apps and not seed_rolls_content(a)
            )
            if _static_apps and tuple(_static_apps) not in _WARNED_STATIC_SEED_APPS:
                _WARNED_STATIC_SEED_APPS.add(tuple(_static_apps))
                print(
                    f"[seed/content] task {episode_name!r} declares seed="
                    f"{task_info['seed']} but {_static_apps} load static "
                    "per-app content that doesn't vary by seed (see "
                    "seed_content_registry.py) -- supply world_data or a "
                    "fixture if per-task content variation is expected."
                )
        # Compute the presented toolset ONCE per task so every attempt in the
        # pass@k loop sees the same distractor sample (the knob is a property of
        # the measurement, not of the individual rollout).
        provide_tools = list(task_info.get("provide_tools") or gt_tool_cnt.keys() or [])
        if distraction > 0:
            distra_tools = list(set(toolbox.tools.keys()) - set(provide_tools))
            provide_tools += random.sample(distra_tools, k=min(len(distra_tools), distraction))
            # random.shuffle(provide_tools)

        # --- ADMISSIBILITY GATE: fires BEFORE the model runs. A task is only
        # worth a model run if its Pytest suite is non-trivial (nop -> 0.0) and
        # satisfiable by the oracle (oracle -> 1.0). A 0/k from a broken task is
        # indistinguishable from difficulty, so skip it rather than poison the run.
        _gd = task_info.get("grading_dir")
        if _gd and not getattr(args, "skip_controls", False):
            from benchmark.pytest_judge import run_controls
            _ctrl = run_controls(_gd, task_dir=task_info.get("task_dir"))
            controls_by_task[episode_name] = _ctrl
            if _ctrl.get("mode") == "world-full":
                _st = _ctrl.get("state", {})
                print(f"[controls] mode=world-full  "
                      f"oracle Rc={_st.get('oracle_Rc')} (want 1.0) Rb={_st.get('oracle_Rb')} (want 0)  "
                      f"nop Rc={_st.get('nop_Rc')} (want <1.0)  keys={_st.get('keys_required')}  "
                      f"-> admissible={_ctrl['admissible']}")
            else:
                _orc = _ctrl.get("oracle_reward")
                print(f"[controls] mode=world-free  nop={_ctrl['nop_reward']} (want 0.0)  "
                      f"oracle={_orc if _orc is not None else 'n/a'} (want 1.0)  "
                      f"-> admissible={_ctrl['admissible']}")
            if not _ctrl["admissible"]:
                print(f"[controls] INADMISSIBLE -> SKIP {episode_name} "
                      f"(not running the model)")
                per_episode.append({
                    "index": i + 1, "name": episode_name,
                    "passed": False, "gradeable": False,
                    "admissible": False, "controls": _ctrl,
                })
                continue

      # --- attempts loop (pass@k). n_attempts==1 reproduces the single-shot run
      # exactly: only attempt 0 feeds the run-wide aggregates and the legacy
      # per-task dir; every attempt is collected into trials_runs for pass@k.
      # (indentation of the body is preserved below via `if True:` blocks)
        for attempt in range(n_attempts):
            first_attempt = (attempt == 0)
            if n_attempts > 1:
                print(f"  attempt {attempt + 1} / {n_attempts}")

            # Phase timings for result.json. Recorded around the real work
            # rather than reconstructed afterwards; `agent_execution` brackets
            # the rollout, and the remaining span up to the grade is the
            # verifier. Environment/agent setup happen once per process (the
            # sandbox is already up), so those are left null rather than
            # attributed to an arbitrary attempt.
            _t_trial_start = datetime.now(timezone.utc)

            task = agent.process_query(
                query=query,
                max_turns=100,
                verbose=True,
                stop_tag="[END]",
                env={
                    "apps": apps
                },
                provide_tools=provide_tools if toolbox.method == "provide" else None,
                native=native_tools
            )

            _t_agent_start = datetime.now(timezone.utc)
            result = asyncio.run(task)
            _t_agent_end = datetime.now(timezone.utc)

            old_env = result["old_apps"]
            new_env = result["apps"]
            tool_cnt = result["tool_cnt"]
            tokens = result["tokens"]
            usage = result.get("usage")  # real API usage incl. prompt-cache

            grading_dir = task_info.get("grading_dir")
            _traj = parse_trajectory(result.get("output", ""))
            # Prefer the task's own task.toml [task.metadata].grader when it
            # declares one (e.g. "weighted") -- args.grader is a single global
            # CLI flag (default "graph") applied uniformly to every task, so a
            # task that opts into weighted grading was silently graded "graph"
            # instead whenever the CLI wasn't invoked with --grader weighted
            # (e.g. docker/docker-compose.yml's runner never passes it). Falls
            # back to the CLI flag/default for tasks that declare none.
            _grader = task_info.get("grader") or getattr(args, "grader", "graph")
            _task_dir = task_info.get("task_dir")
            # World-full 'before' snapshot: the login dump (result["old_apps"]) is
            # the session handshake, NOT a full world capture (~empty output), so
            # diffing `new`/`gt` against it makes the WHOLE pre-existing world look
            # "changed" and inflates Rc (e.g. a real 0.67 shows as 0.99). Prefer the
            # task's baked tests/old_env.json — a FULL snapshot at this same seed.
            # Keep the live dump only when there is no baked one (world-free tasks,
            # which never touch the state channel anyway).
            if _task_dir:
                _bp = os.path.join(str(_task_dir), "tests", "old_env.json")
                if os.path.exists(_bp):
                    try:
                        _baked_old = json.load(open(_bp, encoding="utf-8"))
                        if _baked_old:
                            old_env = _baked_old
                    except (OSError, json.JSONDecodeError):
                        pass
            from benchmark.graph_judge import load_gold as _load_gold, load_efs as _load_efs
            _gold = _load_gold(_task_dir) if _task_dir else None

            _rpath = None
            for _p in (os.path.join(str(_task_dir), "tests", "rubric.json"),
                       os.path.join(str(_task_dir), "rubric.json")):
                if _task_dir and os.path.exists(_p):
                    _rpath = _p; break

            if _grader == "weighted":
                # HYBRID grading: state-diff (Rc/Rb), plan-shape (graph_f1) and an
                # optional rubric are combined as a weighted ledger with penalties
                # (tests/test_weights.json). State components drop out and the score
                # renormalizes when gt_env is unavailable, so seedless tasks still grade.
                from benchmark.weighted_judge import judge_weighted
                # Layer-1 repair: if the Docker facade dumped empty for the state
                # apps, rebuild new_env in-process by replaying the trajectory so
                # the state channel can grade instead of dropping to inadmissible.
                # Fully guarded: no-op on a healthy dump / missing gt, and any
                # error is swallowed so grading proceeds exactly as before.
                if _task_dir and old_env and gt_env and new_env is not None:
                    try:
                        from benchmark.bake_state_mcp import repair_new_env
                        new_env, _rep = repair_new_env(
                            str(_task_dir), new_env, old_env, gt_env, _traj)
                        if _rep.get("repaired"):
                            print(f"[state] repaired empty facade dump via "
                                  f"in-process replay ({_rep.get('calls_applied')} "
                                  f"calls) — was {_rep.get('reason')}")
                        elif _rep.get("reason", "").startswith("empty_dump+"):
                            print(f"[state] replay REFUSED ({_rep.get('reason')}) — "
                                  f"state channel will be marked inadmissible "
                                  f"rather than graded against an unverified world")
                        # Carried so report.json can say the state channel was
                        # reconstructed, not natively captured.
                        _state_repair = _rep
                    except Exception as _exc:
                        print(f"[state] repair skipped: {type(_exc).__name__}: {_exc}")
                judge_result = judge_weighted(
                    old_env=old_env, new_env=new_env, gt_env=gt_env,
                    trajectory=_traj, gold_plan=_gold, efs=_load_efs(_task_dir),
                    grading_dir=grading_dir,
                    final_message=_traj.get("final_message"),
                    rubric_judge=rubric_judge, rubric_path=_rpath)
                print(f"[judge] weighted reward={judge_result['reward']} "
                      f"({judge_result['quadrant']}) earned={judge_result['earned']} "
                      f"penalty={judge_result['penalty']} -> passed={judge_result['passed']}")
                passed = int(judge_result["passed"])
                gradeable = True
            elif _grader == "graph" and _gold:
                # ETOM-style WORLD-INDEPENDENT grading: score the agent's tool-call
                # DAG against the oracle's tool sequence (solution/trajectory.json)
                # with equal-function-sets. No world state, no world-specific values
                # (uids/tickers/IDs) -- so frozen-fixture / seed mismatches can't bite.
                from benchmark.graph_judge import judge_trajectory_graph
                judge_result = judge_trajectory_graph(
                    _traj, _gold, efs=_load_efs(_task_dir),
                    final_message=_traj.get("final_message"),
                    rubric_judge=rubric_judge, rubric_path=_rpath)
                print(f"[judge] graph_f1={judge_result['graph_f1']} "
                      f"(precision={judge_result['graph_precision']} recall={judge_result['graph_recall']}) "
                      f"rubric={judge_result.get('rubric_score')} -> passed={judge_result['passed']}")
                passed = int(judge_result["passed"])
                gradeable = True
            elif grading_dir:
                # Fallback: trajectory Pytest+Rubric (tool-call assertions).
                from benchmark.pytest_judge import judge_trajectory_pytest
                judge_result = judge_trajectory_pytest(
                    _traj, grading_dir,
                    final_message=_traj.get("final_message"),
                    rubric_judge=rubric_judge, verbose=True)
                passed = int(judge_result["passed"])
                gradeable = True
            else:
                judge_result = {"recall": 0, "total": 0, "misbehave": 0}
                passed = 0
                gradeable = False
                print("[judge] SKIP: no solution/trajectory.json (graph gold) and no "
                      "tests/test_outputs.py (pytest) -- add one to grade this task.")

            ep_valid = ep_invalid = ep_error = 0
            for tool_cnt_info in tool_cnt.values():
                ep_valid += tool_cnt_info.get("ok", 0)
                ep_error += tool_cnt_info.get("error", 0)
                ep_invalid += tool_cnt_info.get("failed", 0)

            # Run-wide aggregates are attempt-0 only, so n_attempts==1 reproduces
            # the single-shot metrics exactly. Extra attempts feed pass@k alone.
            if first_attempt:
                acc_cnt += passed
                if gradeable:
                    avg_recall_rate += judge_result["recall"] / judge_result["total"] if judge_result["total"] else (judge_result["recall"] == 0)
                    avg_misbehave_rate += min(judge_result["misbehave"] / judge_result["total"] if judge_result["total"] else judge_result["misbehave"], 3)
                avg_valid_tc += ep_valid
                avg_error_tc += ep_error
                avg_invalid_tc += ep_invalid
                prompt_tokens += tokens["prompt"]
                llm_tokens += tokens["llm"]
                tool_tokens += tokens["tool"]

            if tasks_dir is not None:
                level = task_info.get("level")
                recall = judge_result.get("recall", 0)
                total = judge_result.get("total", 0)
                reward = judge_result.get("reward")
                if reward is None:
                    reward = float(recall) / total if total else (1.0 if recall == 0 else None)
                if gradeable:
                    # Per-test outcomes for report.json / detail.json / ctrf.json.
                    # The weighted grader keeps them under `traj_tests`, NOT under
                    # `detail` -- reading only `detail` reported every weighted run
                    # as "no tests ran" (test_weights_percentage=null,
                    # passed_tests=null) while verifier/ctrf.json listed them all.
                    _pt = (judge_result.get("traj_tests") or {}).get("passed_tests") \
                        or (judge_result.get("detail") or {}).get("passed_tests")
                    _checks = None
                    if judge_result.get("traj_tests"):
                        from benchmark.weighted_judge import traj_test_rows
                        _rows, _wscore = traj_test_rows(judge_result, grading_dir)
                        if _rows:
                            # weighted_score is the ledger's own traj_tests value,
                            # not a recomputation, so report.json cannot drift from
                            # the reward that was actually awarded.
                            _checks = {"weighted_score": _wscore if _wscore is not None else 0.0,
                                       "tests": _rows}
                    score = {
                        "gradeable": True,
                        "reward": reward,
                        "recall": recall,
                        "misbehave": judge_result.get("misbehave", 0),
                        "total": total,
                        "passed": bool(passed),
                        "pytest_score": judge_result.get("pytest_score"),
                        "rubric_score": judge_result.get("rubric_score"),
                        "passed_tests": _pt,
                        "pytest_checks": _checks,
                        # Per-key-path detail (judge_spec allowlist) so the CTRF
                        # writer can emit one row per scored path instead of a
                        # single #reward aggregate.
                        "failed_positive": judge_result.get("failed_positive"),
                        "passed_positive": judge_result.get("passed_positive"),
                        "damaged_negative": judge_result.get("damaged_negative"),
                        "held_negative": judge_result.get("held_negative"),
                        "gt_env": gt_env,
                        "old_env": old_env,
                        "new_env": new_env,
                        "gt_tool_cnt": gt_tool_cnt,
                    }
                else:
                    score = {
                        "gradeable": False,
                        "reason": "not gradeable: task has no tests/test_outputs.py (Pytest+Rubric grading).",
                        "reward": None,
                        "recall": None,
                        "misbehave": None,
                        "total": None,
                        "old_env": old_env,
                        "new_env": new_env,
                        "gt_tool_cnt": gt_tool_cnt,
                    }
                rubric_result = None
                # Standalone rubric.json scorer (commit 9990708). Only runs if the pytest
                # grader didn't already produce a rubric_score, so the two rubric systems
                # don't clobber each other.
                rubric_path = find_rubric_for_task(task_info.get("task_dir"))
                if rubric_path is not None and score.get("rubric_score") is None:
                    try:
                        rubric = load_rubric(rubric_path)
                        parsed_traj = parse_trajectory(result.get("output", ""))
                        rubric_result = evaluate_rubric(
                            rubric, parsed_traj, score,
                            final_message=parsed_traj.get("final_message", ""),
                        )
                        score["rubric_score"] = rubric_result["rubric_score"]
                        score["rubric_format"] = rubric_result.get("format")
                        if "per_check" in rubric_result:
                            score["rubric_per_check"] = rubric_result["per_check"]
                        if "per_criterion" in rubric_result:
                            score["rubric_per_criterion"] = rubric_result["per_criterion"]
                            score["rubric_rc"] = rubric_result.get("rc")
                            score["rubric_rb"] = rubric_result.get("rb")
                        score["rubric_path"] = str(rubric_path)
                        print(f"[rubric] {rubric_path.name}: {rubric_result['rubric_score']:.2f}")
                    except (ValueError, KeyError) as exc:
                        score["rubric_error"] = f"{type(exc).__name__}: {exc}"
                        print(f"[rubric] SKIP {rubric_path.name}: {exc}")
                        rubric_result = None
                # If the pytest judge already scored a criteria-style tests/rubric.json
                # (Channel B), surface it as a rubric_result so the mcp-stump writer emits
                # it — the evaluate_rubric path above is skipped in that case.
                if rubric_result is None and judge_result.get("rubric_score") is not None:
                    rubric_result = {
                        "format": "criteria",
                        "rubric_score": judge_result.get("rubric_score"),
                        "per_criterion": judge_result.get("rubric_per_criterion"),
                    }
                record = {
                    "index": i + 1,
                    "name": episode_name,
                    "query": query,
                    "apps": apps,
                    "level": level,
                    # Seed drives the world (COMPLEXMCP_SEED, set above); it was
                    # missing from the record so report.json/summary.json/pairs
                    # all logged seed=null despite a seeded world. Carry it here.
                    "seed": task_info.get("seed"),
                    "tool_cnt": tool_cnt,
                    "tokens": tokens,
                    "usage": usage,
                    "valid_tool_calls": ep_valid,
                    "invalid_tool_calls": ep_invalid,
                    "error_tool_calls": ep_error,
                    "output": result.get("output", ""),
                    "expected_tool_calls": task_info.get("expected_tool_calls"),
                    "reasoning_signatures": result.get("reasoning_signatures") or [],
                    "termination_reason": result.get("termination_reason"),
                    # Per-turn timestamps + token slices + tool-call counts. The
                    # trajectory is reconstructed from a flat text stream with no
                    # turn boundaries, so ATIF cannot group calls into turns (or
                    # stamp them) without this.
                    "turns": result.get("turns") or [],
                    "session_id": str(_stdlib_uuid.uuid4()),
                    # Verifier span closes here: grading has run by this point.
                    "timings": _phase_timings(_t_trial_start, _t_agent_start,
                                              _t_agent_end),
                }
                # Context for the failure classifier (commit 9990708).
                task_context = {
                    "expected_tools": list(gt_tool_cnt.keys()) if gt_tool_cnt else None,
                    "stump_levers": task_info.get("stump_levers") or [],
                    "capability_level": task_info.get("capability_level"),
                    "apps": apps,
                }
                record["old_env"] = old_env
                record["new_env"] = new_env
                traj_for_pair = _parse_traj_for_layout(record.get("output", ""))
                if layout == "harbor":
                    # `.raw` holds the mcp-stump tree verbatim; the Harbor-shaped
                    # trial is written BESIDE it. The reshape has no slot for
                    # diagnosis/trace/world-snapshots, and those are what the
                    # training pipeline reads -- so nothing is relocated, only added.
                    from benchmark.harbor_layout import (
                        write_harbor_trial, job_name as _job_name, slug_of as _slug_of)
                    _job_dir = run_dir / _slug_of(episode_name)
                    task_dir, final_score = write_mcp_stump_run(
                        _job_dir / ".raw", record, model=model, score=score,
                        task_context=task_context,
                        rubric_result=rubric_result,
                        task_dir_source=task_info.get("task_dir"),
                    )
                    _run_no = int(task_dir.name.split("_", 1)[1]) \
                        if task_dir.name.startswith("run_") else attempt + 1
                    _atif = None
                    _ap = task_dir / "agent" / "trajectory.json"
                    if _ap.exists():
                        _atif = json.loads(_ap.read_text())
                    _label = _harbor_job_labels.setdefault(
                        episode_name, _job_name(episode_name, _harbor_stamp))
                    _row = write_harbor_trial(
                        _job_dir, _run_no, record=record, model=model,
                        judge_result=judge_result,
                        task_dir=task_info.get("task_dir"),
                        grading_dir=grading_dir,
                        rubric_result=rubric_result,
                        atif_doc=_atif,
                        job_id=_harbor_job_id, job_label=_label,
                        timings=record.get("timings"),
                        judge_response=(rubric_result or {}).get("judge_response"),
                    )
                    _harbor_trials.setdefault(episode_name, []).append(_row)
                    _harbor_task_dirs[episode_name] = task_info.get("task_dir")
                elif layout == "mcp-stump":
                    # Every attempt writes its own run_N under trials_<task>/.
                    task_dir, final_score = write_mcp_stump_run(
                        run_dir, record, model=model, score=score,
                        task_context=task_context,
                        rubric_result=rubric_result,
                        task_dir_source=task_info.get("task_dir"),
                    )
                elif first_attempt:
                    # Legacy layout writes one dir per task (attempt 0).
                    task_dir, final_score = write_task_dir(
                        tasks_dir, record, score=score, task_context=task_context
                    )
                else:
                    # Legacy, extra attempt: classify without writing a second dir.
                    task_dir = None
                    ctx = dict(task_context)
                    if "expected_tools" not in ctx and record.get("expected_tool_calls"):
                        ctx["expected_tools"] = _parse_expected_tools(record.get("expected_tool_calls"))
                    if not bool(score.get("passed")):
                        verdict = _classify_failure(
                            trajectory=traj_for_pair,
                            tool_summary={"valid_tool_calls": ep_valid,
                                          "invalid_tool_calls": ep_invalid,
                                          "error_tool_calls": ep_error},
                            score=score, task_context=ctx,
                            final_message=traj_for_pair.get("final_message"),
                        )
                        final_score = {**score, **verdict.to_dict()}
                    else:
                        final_score = dict(score)

                # (snapshot test_state.py verifier removed — grading is trajectory
                # Pytest+Rubric only; the verifier/ folder is written below.)

                # When the trajectory Pytest+Rubric grader ran, emit the same
                # verifier/{reward,ctrf,detail}.json folder the snapshot verifier
                # produced -- so downstream tooling reading verifier/ gets the
                # pytest results (overwrites any snapshot verifier written above).
                _grd = str(judge_result.get("grader", ""))
                if task_dir is not None and _grd.startswith("pytest+rubric"):
                    from benchmark.pytest_judge import write_verifier as _write_pytest_verifier
                    _vdir = _write_pytest_verifier(task_dir, judge_result)
                    print(f"[verifier] wrote {_vdir} from Pytest+Rubric grader")
                elif task_dir is not None and _grd.startswith("graph_f1"):
                    _vd = task_dir / "verifier"
                    _vd.mkdir(parents=True, exist_ok=True)
                    (_vd / "reward.json").write_text(json.dumps({
                        "reward": judge_result.get("reward"),
                        "graph_f1": judge_result.get("graph_f1"),
                        "graph_precision": judge_result.get("graph_precision"),
                        "graph_recall": judge_result.get("graph_recall"),
                        "matched_nodes": judge_result.get("matched_nodes"),
                        "missing_nodes": judge_result.get("missing_nodes"),
                        "rubric_score": judge_result.get("rubric_score"),
                        "grader": _grd,
                    }, indent=2, default=str))
                    (_vd / "detail.json").write_text(json.dumps(judge_result, indent=2, default=str))
                    (_vd / "reward.txt").write_text(str(judge_result.get("reward")))
                    _gf1 = judge_result.get("graph_f1")
                    (_vd / "ctrf.json").write_text(json.dumps({"results": {
                        "tool": {"name": "complexmcp-graph"},
                        "summary": {"tests": 1, "passed": 1 if judge_result.get("passed") else 0,
                                    "failed": 0 if judge_result.get("passed") else 1,
                                    "pending": 0, "skipped": 0, "other": 0, "start": 0, "stop": 0},
                        "tests": [{"name": "graph_f1", "status": "passed" if judge_result.get("passed") else "failed",
                                   "extra": {"graph_f1": _gf1, "graph_precision": judge_result.get("graph_precision"),
                                             "graph_recall": judge_result.get("graph_recall")}}],
                    }}, indent=2, default=str))
                    print(f"[verifier] wrote {_vd} from graph grader (f1={judge_result.get('graph_f1')})")
                elif task_dir is not None and _grd.startswith("weighted"):
                    # Write the FULL verifier folder (reward.json, reward.txt,
                    # ctrf.json, detail.json) — same 4-file set the pytest+rubric
                    # and legacy snapshot verifiers produced. Previously this
                    # branch dropped reward.txt + ctrf.json.
                    from benchmark.weighted_judge import write_weighted_verifier
                    _vd = write_weighted_verifier(task_dir, judge_result, grading_dir)
                    print(f"[verifier] wrote {_vd} from weighted grader "
                          f"(reward={judge_result.get('reward')} {judge_result.get('quadrant')})")

                # The physical run_N slot is the single source of truth for the
                # attempt number (report.json/ctrf use it). Carry it so the trials
                # aggregate reports the same number instead of a list index, which
                # drifts whenever run_N dirs already exist on disk (re-runs/merges).
                run_attempt = None
                if task_dir is not None and task_dir.name.startswith("run_"):
                    try:
                        run_attempt = int(task_dir.name.split("_", 1)[1])
                    except (IndexError, ValueError):
                        run_attempt = None

                # Collect EVERY attempt for the pass@k aggregate.
                trials_runs.setdefault(episode_name, []).append({
                    "attempt": run_attempt,
                    "passed": bool(passed),
                    "reward": final_score.get("reward"),
                    "completion_rate": (final_score.get("recall") / final_score.get("total"))
                        if final_score.get("total") else (1.0 if passed else 0.0),
                    # Clamped to [0,1]; see task_writer for why.
                    "misbehaving_rate": min(
                        (final_score.get("misbehave") / final_score.get("total"))
                        if final_score.get("total") else 0.0, 1.0),
                    # `misbehave_kind` says what the two rates above MEAN (state
                    # corruption vs plan false-positives); `state_admissible`
                    # flags a run whose state channel was inadmissible, so the
                    # rates aren't read as a real completion/misbehave score.
                    "misbehave_kind": final_score.get("misbehave_kind"),
                    "state_admissible": final_score.get("state_admissible"),
                    "state_reason": final_score.get("state_reason"),
                    "failure_class": final_score.get("failure_class"),
                    "reason": final_score.get("reason"),
                    "query": query,
                    "final_message": traj_for_pair.get("final_message", ""),
                    "judge_detail": final_score,
                })

                if first_attempt:
                    per_episode.append({
                        "index": i + 1,
                        "name": episode_name,
                        "passed": bool(passed),
                        "gradeable": gradeable,
                        "judge": judge_result,
                        "valid_tool_calls": ep_valid,
                        "invalid_tool_calls": ep_invalid,
                        "error_tool_calls": ep_error,
                        "tokens": tokens,
                        "usage": usage,
                        "dir": str(task_dir.relative_to(run_dir)) if task_dir is not None else None,
                        "failure_class": final_score.get("failure_class"),
                        "failure_reason": final_score.get("reason"),
                    })

    avg_recall_rate /= len(tasks_list)
    avg_misbehave_rate /= len(tasks_list)
    avg_valid_tc /= len(tasks_list)
    avg_error_tc /= len(tasks_list)
    avg_invalid_tc /= len(tasks_list)

    prompt_tokens /= len(tasks_list)
    llm_tokens /= len(tasks_list)
    tool_tokens /= len(tasks_list)

    accuracy = acc_cnt / len(tasks_list)

    print(f"Model: {model}")
    print(f"\t\taccuracy:\t{accuracy}")
    print(f"\t\tavg. completion rate:\t{avg_recall_rate}")
    print(f"\t\tavg. misbehave rate:\t{avg_misbehave_rate}")
    print("+" * 50)
    print(f"\t\tvalid tool calling count:\t{avg_valid_tc}")
    print(f"\t\tinvalid tool calling count:\t{avg_invalid_tc}")
    print(f"\t\terror tool calling count:\t{avg_error_tc}")
    print("+" * 50)
    print(f"\t\tavg. prompt tokens:\t{prompt_tokens}")
    print(f"\t\tavg. llm tokens:\t{llm_tokens}")
    print(f"\t\tavg. tool tokens:\t{tool_tokens}")

    if run_dir is not None:
        summary = {
            "run_id": run_dir.name,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "config": {
                "model": model,
                "method": method,
                "tool_config": str(tool_config_path) if tool_config_path else None,
                "distraction": distraction,
                "topk": topk,
                "limit": limit,
                "episodes": len(tasks_list),
            },
            "metrics": {
                "accuracy": accuracy,
                "avg_completion_rate": avg_recall_rate,
                "avg_misbehave_rate": avg_misbehave_rate,
                "avg_valid_tool_calls": avg_valid_tc,
                "avg_invalid_tool_calls": avg_invalid_tc,
                "avg_error_tool_calls": avg_error_tc,
                "avg_prompt_tokens": prompt_tokens,
                "avg_llm_tokens": llm_tokens,
                "avg_tool_tokens": tool_tokens,
            },
            "episodes": per_episode,
        }
        # Harbor layout: these live INSIDE the task directory, so running several
        # tasks (or the same task again) never overwrites another task's summary
        # at the output root. Each copy is narrowed to its own task.
        _names = [e.get("name") for e in per_episode if e.get("name")]
        _dests = ([(run_dir / _hslug(n), _scoped_summary(summary, n)) for n in dict.fromkeys(_names)]
                  if layout == "harbor" and _names else [(run_dir, summary)])
        summary_path = None
        for _d, _s in _dests:
            _d.mkdir(parents=True, exist_ok=True)
            summary_path = _d / "summary.json"
            with open(summary_path, "w") as f:
                json.dump(_s, f, indent=2, default=str)

        report_lines = [
            f"# Benchmark Report — {run_dir.name}",
            "",
            f"- Timestamp: {summary['timestamp']}",
            f"- Model: `{model}`",
            f"- Method: `{method}`",
            f"- Tool config: `{tool_config_path}`",
            f"- Episodes: {len(tasks_list)}" + (f" (limit={limit})" if limit else ""),
            "",
            "## Aggregate metrics",
            "",
            "| Metric | Value |",
            "|---|---|",
            f"| Accuracy | {accuracy:.4f} |",
            f"| Avg completion rate | {avg_recall_rate:.4f} |",
            f"| Avg misbehave rate | {avg_misbehave_rate:.4f} |",
            f"| Avg valid tool calls / episode | {avg_valid_tc:.4f} |",
            f"| Avg invalid tool calls / episode | {avg_invalid_tc:.4f} |",
            f"| Avg error tool calls / episode | {avg_error_tc:.4f} |",
            f"| Avg prompt tokens | {prompt_tokens:.2f} |",
            f"| Avg llm tokens | {llm_tokens:.2f} |",
            f"| Avg tool tokens | {tool_tokens:.2f} |",
            "",
            "## Per-episode",
            "",
            "| # | Passed | Recall / Total | Misbehave | Valid TC | Invalid TC | Failure | Dir |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for ep in per_episode:
            # Inadmissible/skipped episodes (see the admissibility gate) carry no
            # judge/tool-call fields -- render a SKIP row instead of crashing the
            # whole report on a missing key.
            if ep.get("admissible") is False or "judge" not in ep:
                fc = ep.get("failure_class") or "inadmissible"
                report_lines.append(
                    f"| {ep.get('index', '?')} | ⊘ SKIP "
                    f"| - / - | - "
                    f"| - | - "
                    f"| `{fc}` | `{ep.get('dir', '')}` |"
                )
                continue
            j = ep["judge"]
            fc = ep.get("failure_class") or ""
            report_lines.append(
                f"| {ep['index']} | {'✓' if ep['passed'] else '✗'} "
                f"| {j['recall']} / {j['total']} | {j['misbehave']} "
                f"| {ep['valid_tool_calls']} | {ep['invalid_tool_calls']} "
                f"| `{fc}` | `{ep['dir']}` |"
            )

        failure_counts = Counter(
            ep.get("failure_class") for ep in per_episode
            if ep.get("failure_class") and ep.get("failure_class") != "unknown"
        )
        if failure_counts:
            report_lines += [
                "",
                "## Failure breakdown",
                "",
                "| Failure class | Count |",
                "|---|---|",
            ]
            for fc, count in failure_counts.most_common():
                report_lines.append(f"| `{fc}` | {count} |")
        report_path = (summary_path.parent if summary_path else run_dir) / "report.md"
        with open(report_path, "w") as f:
            f.write("\n".join(report_lines) + "\n")

        print(f"[output] wrote {summary_path}")
        print(f"[output] wrote {report_path}")
        print(f"[output] per-task subdirs in {tasks_dir}")

        if trials_runs:
            per_task_passk: list[dict] = []
            for task_name, runs in trials_runs.items():
                # Harbor layout keeps the mcp-stump aggregate under .raw/ beside
                # the Harbor job files, so nothing the training pipeline reads
                # (pairs.jsonl, failure_analysis.json) is lost in the reshape.
                _agg_root = run_dir
                if layout == "harbor":
                    from benchmark.harbor_layout import slug_of as _slug_of
                    _agg_root = run_dir / _slug_of(task_name) / ".raw"
                trials_dir = write_trials_aggregate(
                    _agg_root, task_name, model, runs,
                    instruction=runs[0].get("query") if runs else None,
                    at=at_ks,
                )
                n = len(runs)
                c = sum(1 for r in runs if r.get("passed"))
                est = _passk_estimate(n, c, at_ks)
                if layout == "harbor" and _harbor_trials.get(task_name):
                    from benchmark.harbor_layout import (
                        write_harbor_job as _wjob, slug_of as _slugx)
                    _jd = _wjob(
                        run_dir / _slugx(task_name),
                        task_name=task_name,
                        task_dir=_harbor_task_dirs.get(task_name),
                        model=model,
                        trials=_harbor_trials[task_name],
                        job_id=_harbor_job_id,
                        job_label=_harbor_job_labels.get(task_name, ""),
                        started_at=_harbor_started,
                        finished_at=datetime.now(timezone.utc).strftime(
                            "%Y-%m-%dT%H:%M:%S.%f") + "Z",
                        pass_at_k={str(k): v for k, v in est["pass@k"].items()},
                    )
                    print(f"[output] wrote harbor job {_jd}")
                per_task_passk.append({
                    "task": task_name,
                    "n": n, "c": c,
                    "p_hat": est["p_hat"], "ci95": est["ci95"],
                    "pass@k": est["pass@k"], "pass^k": est["pass^k"],
                })
                print(f"[output] wrote {trials_dir}/summary.json + pairs.jsonl + failure_analysis.json")

            # Per-model roll-up: mean pass@k across tasks + failure-mode histogram.
            mode_hist = Counter(
                r.get("failure_class") for runs in trials_runs.values()
                for r in runs if not r.get("passed") and r.get("failure_class"))
            all_ks = sorted({int(k) for t in per_task_passk for k in t["pass@k"].keys()})
            def _mean_over(field_key: str, k: int) -> float | None:
                vals = [t[field_key].get(str(k)) for t in per_task_passk
                        if str(k) in t[field_key]]
                return round(sum(vals) / len(vals), 6) if vals else None
            pass_summary = {
                "model": model,
                "tasks": len(per_task_passk),
                "attempts_per_task": n_attempts,
                "at": at_ks,
                "mean_pass@k": {str(k): _mean_over("pass@k", k) for k in all_ks},
                "mean_pass^k": {str(k): _mean_over("pass^k", k) for k in all_ks},
                "failure_mode_histogram": dict(mode_hist.most_common()),
                "per_task": per_task_passk,
            }
            # D4: `pass_summary.json` is claimed by the percentage-shaped
            # per-model roll-up (benchmark.harbor_layout). This pass@k-shaped
            # corpus roll-up is a different artifact answering a different
            # question, so it gets its own name rather than racing for one.
            ps_path = run_dir / "passk_summary.json"
            if layout == "harbor" and trials_runs:
                # One roll-up per task dir; the corpus view is recoverable by
                # reading them together, and nothing collides at the root.
                for _tn in trials_runs:
                    _td = run_dir / _hslug(_tn)
                    _td.mkdir(parents=True, exist_ok=True)
                    _c = _aggregate_trials_on_disk(_td, model)
                    _c["attempts_per_task"] = n_attempts
                    _c["at"] = at_ks
                    (_td / "passk_summary.json").write_text(
                        json.dumps(_c, indent=2, default=str))
                ps_path = None
            # A1 fix: the headline roll-up aggregates EVERY trials_*/ on disk, not
            # just this invocation's episodes -- so piecemeal runs and re-runs
            # report the true corpus accuracy instead of last-writer-wins.
            corpus = _aggregate_trials_on_disk(run_dir, model)
            corpus["attempts_per_task"] = n_attempts
            corpus["at"] = at_ks
            if ps_path is not None:
                ps_path.write_text(json.dumps(corpus, indent=2, default=str))
            print(f"[output] corpus roll-up: {corpus['passed']}/{corpus['tasks']} "
                  f"tasks passed (accuracy {corpus['accuracy']})"
                  + (f" -> {ps_path}" if ps_path else " -> per-task passk_summary.json"))


def load_dotenv_if_not_exist():
    if "OPENAI_API_KEY" not in os.environ:
        load_dotenv()


def _sandbox_up(sandbox_timeout: int = 240) -> None:
    """Bring the full sandbox (20 servers + 142 apps) up in one Docker container.

    Idempotent: `docker start` an existing `complexmcp-sandbox`, else `docker run`
    a fresh one from the `complexmcp:latest` image (whose CMD is
    docker/start_benchmark_sandbox.sh, launching all 168 processes). Blocks until
    the sandbox is responsive. This is the one-command sibling of the tmux path in
    scripts/run_task.sh and the 3-container docker/docker-compose.yml stack.
    """
    import time
    import urllib.request
    import urllib.error

    def _run(cmd, timeout=120):
        try:
            return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            print(f"[startup] {' '.join(cmd)}: {e}")
            return None

    # Sandbox: try `docker start`; if the container was removed, `docker run` it.
    r = _run(["docker", "start", "complexmcp-sandbox"])
    if r is not None and r.returncode == 0:
        print("[startup] started complexmcp-sandbox")
    else:
        msg = ((r.stderr or r.stdout).strip() if r is not None else "") or "unknown"
        if "no such container" in msg.lower():
            img = _run(["docker", "images", "-q", "complexmcp:latest"])
            if img is None or not (img.stdout or "").strip():
                print("[startup] complexmcp-sandbox missing AND image complexmcp:latest not found "
                      "— run `docker build -t complexmcp:latest .` first")
                return
            print("[startup] complexmcp-sandbox not found — creating from complexmcp:latest")
            run_r = _run([
                "docker", "run", "-d", "--name", "complexmcp-sandbox",
                "-p", "8000-8007:8000-8007",
                "-p", "8013-8024:8013-8024",
                "-p", "9000-9008:9000-9008",
                "-p", "9014-9144:9014-9144",
                "complexmcp:latest",
            ], timeout=180)
            if run_r is None or run_r.returncode != 0:
                err = ((run_r.stderr or run_r.stdout).strip() if run_r is not None else "unknown")
                print(f"[startup] complexmcp-sandbox: recreate failed: {err}")
                return
            print("[startup] recreated complexmcp-sandbox from image")
        elif any(kw in msg.lower() for kw in ("already", "running")):
            print("[startup] complexmcp-sandbox: already running")
        else:
            print(f"[startup] complexmcp-sandbox: {msg}")

    # Poll first and LAST port. The sandbox binds sequentially low -> high, so port
    # 9144 (LightZoom, last app in start_benchmark_sandbox.sh) being up means all 168 are up.
    for port in (8000, 9144):
        deadline = time.time() + sandbox_timeout
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=3) as resp:
                    print(f"[startup] sandbox port {port} responsive (HTTP {resp.status})")
                    break
            except urllib.error.HTTPError as e:
                print(f"[startup] sandbox port {port} responsive (HTTP {e.code})")
                break
            except (urllib.error.URLError, OSError):
                pass
            time.sleep(2)
        else:
            print(f"[startup] WARNING: sandbox port {port} not responsive within {sandbox_timeout}s")


def _sandbox_down() -> None:
    """Stop the sandbox container. `docker stop` fires the in-container trap, which
    kills all 168 child processes."""
    try:
        r = subprocess.run(["docker", "stop", "complexmcp-sandbox"],
                           capture_output=True, text=True, timeout=60)
        if r.returncode == 0:
            print("[cleanup] stopped complexmcp-sandbox")
        else:
            print(f"[cleanup] complexmcp-sandbox: {(r.stderr or r.stdout).strip() or 'not running'}")
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"[cleanup] complexmcp-sandbox: {e}")


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("-m", "--model", default="gpt-4o", type=str)
    parser.add_argument("--method", default="list_all", type=str)
    parser.add_argument("--native-tools", dest="native_tools", action="store_true", default=False,
                        help="Use native OpenAI function-calling instead of the <tool> text protocol. "
                             "Forces OpenAIBackend (routes through the proxy at OPENAI_BASE_URL).")
    parser.add_argument("-t", "--tool-config", type=str, required=False)
    parser.add_argument("-c", "--custom", action="store_true", default=False)
    parser.add_argument("-g", "--generate", action="store_true", default=False)
    parser.add_argument("-d", "--distraction", type=int, default=-1, help="0: no other tools; -1: all tools' description will be put in system prompt; n: n tools' description will be put in system prompt")
    parser.add_argument("--topk", type=int, default=30)
    parser.add_argument("--limit", type=int, default=0, help="Max episodes to run (0 = all)")
    parser.add_argument("--output-dir", type=str, default=None, help="Directory to write per-run results. Default depends on --layout: 'runs' (legacy) or 'output' (mcp-stump). Set to '' to disable.")
    parser.add_argument("--layout", type=str, default="legacy", choices=["legacy", "mcp-stump", "harbor"], help="Output layout. 'legacy' writes runs/<ts>__model__method/tasks/task_NNN__slug/*.json. 'mcp-stump' writes output/trials_<task>/trajectories/<model>/run_N/*.json matching mcp-stump/out/ format. 'harbor' writes output/<task>/ with .raw/ (the mcp-stump tree, verbatim) beside trajectory/Run N/ in the Harbor-native shape.")
    parser.add_argument("--source", type=str, default="auto", choices=["auto", "parquet", "harbor"], help="Task source. 'auto' picks 'harbor' if --tasks-dir is a directory, else 'parquet'.")
    parser.add_argument("--tasks-dir", type=str, default=None, help="Path to task source. For harbor: directory of complexmcp-* task packages. For parquet: path to .parquet file. Defaults to benchmark/data/data.parquet.")
    parser.add_argument("--task", type=str, default=None, help="Run only tasks whose name equals or starts with this string.")
    parser.add_argument("--n-attempts", dest="n_attempts", type=int, default=1,
                        help="Rollouts per task for pass@k / pass^k. Default 1 (single-shot; "
                             "run-wide metrics are computed from attempt 1 only).")
    parser.add_argument("--grader", dest="grader", type=str, default="graph",
                        choices=["graph", "pytest", "weighted"],
                        help="Grading mode. 'graph' (default): ETOM-style world-independent "
                             "tool-DAG match vs the oracle plan + equivalence sets. 'pytest': "
                             "trajectory tests/test_outputs.py assertions. 'weighted': hybrid "
                             "ledger combining state-diff (Rc/Rb), plan-shape (graph_f1) and an "
                             "optional rubric with per-component weights and penalties "
                             "(tests/test_weights.json).")
    parser.add_argument("--skip-controls", dest="skip_controls", action="store_true",
                        default=False,
                        help="Skip the pre-launch admissibility gate (oracle=1.0 / nop=0.0). "
                             "The gate runs by default and skips inadmissible tasks.")
    parser.add_argument("--at", dest="at", type=str, default="1",
                        help="Comma-separated k values to report for pass@k and pass^k "
                             "(e.g. '1,2,8'). Values > --n-attempts are clamped.")
    parser.add_argument("--manage-sandbox", dest="manage_sandbox", action="store_true",
                        default=False,
                        help="One-command lifecycle: auto-start the complexmcp-sandbox Docker "
                             "container (all 20 servers + 142 apps) before the run and stop it "
                             "after. Requires a built complexmcp:latest image. Omit this if you "
                             "bring the sandbox up yourself via scripts/run_task.sh (tmux) or "
                             "docker/docker-compose.yml.")
    parser.add_argument("--world-data", dest="world_data", type=str, default=None,
                        help="Directory of <AppName>.json files (software.utils.world_data) to "
                             "replace the seed-rolled world with user-authored state, for every "
                             "app that has a JSON file there. Applies to every task in this run "
                             "unless a task's own meta declares 'world_data' (e.g. a Harbor "
                             "bundle's task.toml, bundle-relative), which wins per-task.")

    args = parser.parse_args()
    # Parse --at into a sorted unique int list; clamp to n_attempts.
    try:
        _ks = sorted({int(x) for x in str(args.at).split(",") if x.strip()})
    except ValueError:
        _ks = [1]
    args.at_ks = [k for k in _ks if 1 <= k <= max(1, args.n_attempts)] or [1]
    load_dotenv_if_not_exist()

    if args.world_data:
        # Run-wide default; a per-task "world_data" meta key (below) overrides
        # this for that task only (Harbor bundles ship their own bundle-relative
        # world_data/, distinct from a locally-authored --world-data dir).
        os.environ["COMPLEXMCP_WORLD_DATA"] = str(Path(args.world_data).resolve())

    if args.manage_sandbox:
        exit_code = 0
        try:
            _sandbox_up()
            exit_code = main(args) or 0
        finally:
            _sandbox_down()
        sys.exit(exit_code)

    sys.exit(main(args))