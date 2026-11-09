"""F1 generated-hook subprocess with macOS deny rules and JSON-only ask IPC.

The AST restrictions are language capabilities, not an OS sandbox. The macOS
sandbox-exec profile independently denies network, writes and child execution.
Failure to establish that boundary fails closed; there is no in-process fallback.
"""
from __future__ import annotations
import ast
import json
import os
from pathlib import Path
import selectors
import subprocess
import sys
import time

MAX_FRAME = 2_000_000


def _encoded(value):
    data = json.dumps(value, allow_nan=False, separators=(",", ":")).encode()
    if len(data) > MAX_FRAME:
        raise ValueError("HOOK_IPC_FRAME_LIMIT")
    return data + b"\n"


def sandbox_profile(executable, worker, base_prefix):
    # The interpreter needs its stdlib/dyld, never the project or user home.
    literal = lambda p: json.dumps(str(p))
    reads = [str(Path(base_prefix).resolve()), "/System/Library", "/usr/lib", "/dev/null",
             "/dev/urandom", str(Path(worker).resolve())]
    # Framework Python's small launcher reexecutes this exact same interpreter.
    app = Path(base_prefix) / "Resources/Python.app/Contents/MacOS/Python"
    executables = [Path(executable).resolve()]
    if app.is_file() and app.resolve() not in executables:
        executables.append(app.resolve())
    # realpath traverses these directories; metadata only grants no file data.
    ancestors = sorted({str(parent) for value in [*executables, Path(worker).resolve()]
                        for parent in value.parents})
    return ("(version 1)(deny default)"
            "(allow process-exec " + " ".join("(literal " + literal(p) + ")" for p in executables) + ")"
            # dyld ignition opens the root directory itself; this is NOT subpath /.
            '(allow file-read* (literal "/"))'
            "(allow file-read-metadata " + " ".join("(literal " + literal(p) + ")" for p in ancestors) + ")"
            "(allow file-read* " + " ".join("(subpath " + literal(p) + ")" for p in reads) + ")"
            "(allow sysctl-read)(allow mach-lookup)"
            "(allow signal (target self))")


def run_isolated_hook(site, source, context, ask):
    if sys.platform != "darwin" or not Path("/usr/bin/sandbox-exec").is_file():
        raise ValueError("ISOLATED_HOST_UNAVAILABLE")
    worker = Path(__file__).resolve()
    executable = Path(sys.executable).resolve()
    app = Path(sys.base_prefix) / "Resources/Python.app/Contents/MacOS/Python"
    if app.is_file():
        executable = app.resolve()  # Avoid launcher child PID; monitor actual worker.
    command = ["/usr/bin/sandbox-exec", "-p", sandbox_profile(executable, worker, sys.base_prefix),
               str(executable), "-I", "-S", "-B", str(worker), "--worker"]
    # No inherited credentials, token, HOME, PATH, Python path or user site.
    proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, cwd="/", env={}, bufsize=0)
    deadline = time.monotonic() + min(900, max(1, context.get("quota", {}).get("wall_s_left", 900)))
    calls = 0
    selector = selectors.DefaultSelector()
    selector.register(proc.stdout, selectors.EVENT_READ)
    buffer = b""
    try:
        proc.stdin.write(_encoded({"site": site, "source": source, "context": context}))
        while time.monotonic() < deadline:
            rss = subprocess.run(["/bin/ps", "-o", "rss=", "-p", str(proc.pid)],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, env={}, cwd="/", timeout=1)
            if rss.returncode == 0 and rss.stdout.strip():
                if int(rss.stdout.strip()) * 1024 > 256 * 1024 * 1024:
                    raise ValueError("HOOK_RSS_MONITOR_LIMIT")
            if not selector.select(min(.05, max(.001, deadline-time.monotonic()))):
                if proc.poll() is not None:
                    raise ValueError("ISOLATED_WORKER_EXIT:" + str(proc.returncode))
                continue
            chunk = os.read(proc.stdout.fileno(), 65536)
            if not chunk:
                raise ValueError("ISOLATED_WORKER_EOF:" + str(proc.poll()))
            buffer += chunk
            if len(buffer) > MAX_FRAME:
                raise ValueError("HOOK_IPC_FRAME_LIMIT")
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                message = json.loads(line)
                if message.get("type") == "ask":
                    calls += 1
                    if (calls > 24 or message.get("site") != site or
                            not isinstance(message.get("payload"), dict)):
                        raise ValueError("HOOK_ASK_CAPABILITY")
                    response = ask(site, message["payload"])
                    proc.stdin.write(_encoded({"response": response}))
                elif message.get("type") == "result":
                    result = message.get("value")
                    if not isinstance(result, dict):
                        raise ValueError("HOOK_RESULT_NOT_OBJECT")
                    return result
                else:
                    raise ValueError("HOOK_WORKER_ERROR:" + str(message.get("error", "IPC")))
        raise ValueError("HOOK_WALL_LIMIT")
    finally:
        selector.close()
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=5)
        proc.stdin.close()
        proc.stdout.close()


def _worker():
    import resource
    resource.setrlimit(resource.RLIMIT_CPU, (2, 2))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    resource.setrlimit(resource.RLIMIT_NOFILE, (16, 16))
    # No file/network/process builtins are exposed; sandbox rules are independent.
    # macOS maps a huge shared virtual region and rejects small RLIMIT_AS
    # (aliased to RSS on this runtime). This is a virtual ceiling, not RAM quota;
    # the trusted parent additionally monitors this exact PID's RSS at 256 MiB.
    resource.setrlimit(resource.RLIMIT_AS, (1024 ** 4, 1024 ** 4))
    data = json.loads(sys.stdin.buffer.readline(MAX_FRAME + 1))
    site, source, context = data["site"], data["source"], data["context"]
    expected = site.lower().replace("-", "_")
    tree = ast.parse(source)
    if len(source.encode()) > 65536 or len(list(ast.walk(tree))) > 5000:
        raise ValueError("HOOK_SOURCE_LIMIT")
    safe_attrs = {"get", "items", "keys", "values", "copy", "append", "extend", "update", "pop",
                  "sort", "count", "index", "startswith", "endswith"}
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or (node.name != expected and not node.name.startswith("helper_")):
            raise ValueError("HOOK_TOP_LEVEL")
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.Global, ast.Nonlocal, ast.ClassDef,
                ast.AsyncFunctionDef, ast.While, ast.With, ast.Try, ast.Raise, ast.Delete, ast.Yield, ast.YieldFrom)):
            raise ValueError("HOOK_CAPABILITY")
        if isinstance(node, ast.Name) and node.id.startswith("_"):
            raise ValueError("HOOK_PRIVATE_NAME")
        if isinstance(node, ast.Attribute) and node.attr not in safe_attrs:
            raise ValueError("HOOK_ATTRIBUTE")
        if isinstance(node, ast.FunctionDef) and (node.decorator_list or node.args.defaults or node.args.kw_defaults or node.returns):
            raise ValueError("HOOK_DEFINITION_EFFECT")
        if isinstance(node, ast.arg) and node.annotation:
            raise ValueError("HOOK_ANNOTATION")
    def bounded_range(*args):
        value = range(*args)
        if len(value) > 1000:
            raise ValueError("HOOK_RANGE_LIMIT")
        return value
    names = {"len": len, "min": min, "max": max, "sum": sum, "abs": abs, "all": all,
             "any": any, "sorted": sorted, "enumerate": enumerate, "zip": zip, "range": bounded_range,
             "dict": dict, "list": list, "tuple": tuple, "set": set, "str": str, "int": int,
             "float": float, "bool": bool, "isinstance": isinstance}
    namespace = {"__builtins__": names}
    exec(compile(tree, "<pqe:" + site + ">", "exec"), namespace)
    fn = namespace[expected]
    if fn.__code__.co_argcount != 2:
        raise ValueError("HOOK_SIGNATURE_REQUIRES_CTX_ASK")
    steps = 0
    def trace(frame, event, arg):
        nonlocal steps
        if frame.f_code.co_filename.startswith("<pqe:") and event in {"line", "call"}:
            steps += 1
            if steps > 10000:
                raise ValueError("HOOK_STEP_LIMIT")
        return trace
    def ask(site_name, payload):
        if site_name != site or not isinstance(payload, dict):
            raise ValueError("HOOK_ASK_CAPABILITY")
        sys.stdout.buffer.write(_encoded({"type": "ask", "site": site_name, "payload": payload}))
        sys.stdout.buffer.flush()
        return json.loads(sys.stdin.buffer.readline(MAX_FRAME + 1))["response"]
    sys.settrace(trace)
    try:
        result = fn(context, ask)
    finally:
        sys.settrace(None)
    sys.stdout.buffer.write(_encoded({"type": "result", "value": result}))
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    try:
        if sys.argv[1:] != ["--worker"]:
            raise ValueError("WORKER_ENTRY_ONLY")
        _worker()
    except BaseException as error:
        sys.stdout.buffer.write(_encoded({"type": "error", "error": type(error).__name__ + ":" + str(error)}))
        sys.stdout.buffer.flush()
        sys.exit(1)
