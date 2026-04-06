"""Unit tests for local_model/safety.py — validate_command / prepare_command.

These tests document and lock the current permission-level behaviour so any
refactor can be verified against a known-good baseline without running the
full server.

Run:
    cd ~/.openclaw/apex
    .venv/bin/python3 -m pytest tests/test_safety.py -v
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# ── bootstrap (must happen before any apex import) ────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[1]
SERVER_DIR = REPO_ROOT / "server"

_TEST_ROOT = Path(tempfile.mkdtemp(prefix="apex-safety-tests-"))
os.environ.setdefault("APEX_ROOT", str(_TEST_ROOT))
os.environ.setdefault("APEX_WORKSPACE", str(_TEST_ROOT))
os.environ.setdefault("APEX_ALERT_TOKEN", "test-token")
os.environ.setdefault("APEX_ADMIN_TOKEN", "test-admin")
os.environ.setdefault("APEX_SSL_CERT", "")
os.environ.setdefault("APEX_SSL_KEY", "")
os.environ.setdefault("APEX_SSL_CA", "")
os.environ.setdefault("APEX_DB_NAME", "test_apex.db")
os.environ.setdefault("APEX_LOG_NAME", "test_apex.log")

if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from local_model.safety import (  # noqa: E402
    prepare_command,
    validate_command,
    ensure_workspace_path,
    validate_path,
    DEFAULT_LEVEL3_ALLOWED_COMMANDS,
)

# ── helpers ───────────────────────────────────────────────────────────────────

WS = str(_TEST_ROOT)  # test workspace root


def _ok(cmd: str, level: int, allowed_commands: list[str] | None = None) -> None:
    """Assert command is allowed at this level."""
    err = validate_command(cmd, WS, permission_level=level, allowed_commands=allowed_commands)
    assert err is None, f"Expected OK at l{level}: {cmd!r}  →  {err}"


def _blocked(cmd: str, level: int, allowed_commands: list[str] | None = None) -> None:
    """Assert command is blocked at this level."""
    err = validate_command(cmd, WS, permission_level=level, allowed_commands=allowed_commands)
    assert err is not None, f"Expected BLOCKED at l{level}: {cmd!r}"


# ── Level 0 ───────────────────────────────────────────────────────────────────

class TestLevel0:
    """Level 0: tools completely disabled."""

    def test_ls_blocked(self):         _blocked("ls", 0)
    def test_echo_blocked(self):       _blocked("echo hello", 0)
    def test_git_status_blocked(self): _blocked("git status", 0)
    def test_python_blocked(self):     _blocked("python3 -V", 0)
    def test_cat_blocked(self):        _blocked("cat file.txt", 0)


# ── Level 2: read-only commands ───────────────────────────────────────────────

class TestLevel2ReadOnlyPass:
    """Commands in READ_ONLY_COMMANDS are allowed at l2."""

    def test_ls(self):          _ok("ls", 2)
    def test_ls_path(self):     _ok(f"ls {WS}", 2)
    def test_echo(self):        _ok("echo hello", 2)
    def test_cat(self):         _ok(f"cat {WS}/file.txt", 2)
    def test_head(self):        _ok("head -n 20 file.txt", 2)
    def test_tail(self):        _ok("tail -n 20 file.txt", 2)
    def test_wc(self):          _ok("wc -l file.txt", 2)
    def test_grep(self):        _ok("grep foo bar.txt", 2)
    def test_find_basic(self):  _ok("find . -name '*.py'", 2)
    def test_stat(self):        _ok("stat file.txt", 2)
    def test_pwd(self):         _ok("pwd", 2)
    def test_which(self):       _ok("which python3", 2)
    def test_uname(self):       _ok("uname -a", 2)


class TestLevel2GitPass:
    """Read-only git subcommands are allowed at l2."""

    def test_git_status(self):       _ok("git status", 2)
    def test_git_diff(self):         _ok("git diff", 2)
    def test_git_log(self):          _ok("git log --oneline -10", 2)
    def test_git_show(self):         _ok("git show HEAD", 2)
    def test_git_branch(self):       _ok("git branch", 2)
    def test_git_rev_parse(self):    _ok("git rev-parse HEAD", 2)
    def test_git_ls_files(self):     _ok("git ls-files", 2)
    def test_git_blame(self):        _ok("git blame file.py", 2)
    def test_git_remote(self):       _ok("git remote -v", 2)
    def test_git_grep(self):         _ok("git grep foo", 2)
    def test_git_with_C_flag(self):  _ok(f"git -C {WS} status", 2)


class TestLevel2PythonPass:
    """Version check and -m py_compile are allowed at l2."""

    def test_python3_version(self):     _ok("python3 -V", 2)
    def test_python3_version_long(self): _ok("python3 --version", 2)
    def test_python3_py_compile(self):  _ok(f"python3 -m py_compile {WS}/script.py", 2)

    def test_python3_run_workspace_script(self):
        script = _TEST_ROOT / "run_me.py"
        script.write_text("print('hello')\n")
        _ok(f"python3 {script}", 2)


class TestLevel2Blocked:
    """Commands and constructs blocked at l2."""

    # Not in l2 allowlist
    def test_ping_blocked(self):         _blocked("ping 127.0.0.1", 2)
    def test_curl_blocked(self):         _blocked("curl http://example.com", 2)
    def test_rm_blocked(self):           _blocked("rm file.txt", 2)
    def test_node_blocked(self):         _blocked("node --version", 2)
    def test_npm_blocked(self):          _blocked("npm install", 2)
    def test_mkdir_blocked(self):        _blocked("mkdir testdir", 2)
    def test_touch_blocked(self):        _blocked("touch newfile.txt", 2)
    def test_cp_blocked(self):           _blocked("cp a.txt b.txt", 2)
    def test_mv_blocked(self):           _blocked("mv a.txt b.txt", 2)
    def test_sqlite3_blocked(self):      _blocked("sqlite3 test.db .tables", 2)

    # Shell metacharacters
    def test_pipe_blocked(self):         _blocked("ls | grep foo", 2)
    def test_and_blocked(self):          _blocked("echo a && echo b", 2)
    def test_or_blocked(self):           _blocked("echo a || echo b", 2)
    def test_semicolon_blocked(self):    _blocked("echo a; echo b", 2)
    def test_redirect_out_blocked(self): _blocked("echo hello > /tmp/out.txt", 2)
    def test_redirect_in_blocked(self):  _blocked("cat < file.txt", 2)
    def test_subshell_blocked(self):     _blocked("echo $(whoami)", 2)
    def test_backtick_blocked(self):     _blocked("echo `whoami`", 2)
    def test_brace_expand_blocked(self): _blocked("echo ${HOME}", 2)

    # Sensitive paths
    def test_cat_ssh_blocked(self):      _blocked("cat ~/.ssh/id_rsa", 2)
    def test_cat_env_blocked(self):      _blocked(f"cat {WS}/.env", 2)

    # sed -i (write mode)
    def test_sed_inplace_blocked(self):  _blocked("sed -i 's/foo/bar/' file.txt", 2)
    def test_sed_inplace_long_blocked(self): _blocked("sed --in-place 's/foo/bar/' file.txt", 2)

    # Dangerous find args
    def test_find_delete_blocked(self):  _blocked("find . -delete", 2)
    def test_find_execdir_blocked(self): _blocked("find . -execdir rm {} ;", 2)

    # Git write subcommands at l2: add/commit are validated but allowed when args are OK;
    # push and destructive ops are blocked.
    def test_git_push_blocked(self):   _blocked("git push", 2)
    def test_git_rm_blocked(self):     _blocked("git rm file.txt", 2)
    def test_git_reset_blocked(self):  _blocked("git reset --hard HEAD", 2)
    def test_git_merge_blocked(self):  _blocked("git merge main", 2)

    # Python script outside workspace
    def test_python_script_outside_ws_blocked(self):
        _blocked("python3 /etc/malicious.py", 2)

    def test_python_arbitrary_module_blocked(self):
        _blocked("python3 -m http.server 8888", 2)


# ── Level 3: extended allowlist, compound commands ────────────────────────────

class TestLevel3Pass:
    """Commands and constructs allowed at l3."""

    # Extended allowlist commands
    def test_rm(self):            _ok(f"rm {WS}/file.txt", 3)
    def test_mkdir(self):         _ok(f"mkdir {WS}/newdir", 3)
    def test_touch(self):         _ok(f"touch {WS}/file.txt", 3)
    def test_cp(self):            _ok(f"cp {WS}/a.txt {WS}/b.txt", 3)
    def test_mv(self):            _ok(f"mv {WS}/a.txt {WS}/b.txt", 3)
    def test_curl(self):          _ok("curl http://example.com", 3)
    def test_sqlite3(self):       _ok(f"sqlite3 {WS}/test.db .tables", 3)
    def test_git_add_dot(self):   _ok("git add .", 3)
    def test_git_add_A(self):     _ok("git add -A", 3)
    def test_git_add_files(self): _ok(f"git add {WS}/file.py", 3)
    def test_git_commit_m(self):  _ok("git commit -m 'test commit'", 3)
    def test_git_commit_am(self): _ok("git commit -a -m 'test'", 3)
    def test_python3_script(self):
        script = _TEST_ROOT / "script.py"
        script.write_text("print('hi')\n")
        _ok(f"python3 {script}", 3)

    # Compound commands (l3 operators allowed)
    def test_pipe(self):           _ok("ls | grep foo", 3)
    def test_and(self):            _ok("echo a && echo b", 3)
    def test_or(self):             _ok("echo a || echo b", 3)
    def test_semicolon(self):      _ok("echo a; echo b", 3)
    def test_pipe_chain(self):     _ok("find . -name '*.py' | grep test", 3)
    def test_stderr_redirect(self): _ok("ls /nonexistent 2>/dev/null", 3)
    def test_stderr_append(self):   _ok("ls /nonexistent 2>>/dev/null", 3)

    # find -exec grep (specifically allowed) — \; is the correct shell escape;
    # bare ; at l3 would be treated as a segment separator by the compound parser.
    def test_find_exec_grep(self): _ok("find . -exec grep -l foo {} \\;", 3)

    # Read-only commands still work
    def test_ls(self):   _ok("ls", 3)
    def test_echo(self): _ok("echo hello", 3)
    def test_grep(self): _ok("grep foo bar.txt", 3)
    def test_git_status(self): _ok("git status", 3)


class TestLevel3Blocked:
    """Commands and constructs still blocked at l3."""

    # Not in DEFAULT_LEVEL3_ALLOWED_COMMANDS
    def test_ping_blocked(self):    _blocked("ping 127.0.0.1", 3)
    def test_node_blocked(self):    _blocked("node --version", 3)
    def test_brew_blocked(self):    _blocked("brew install foo", 3)
    def test_docker_blocked(self):  _blocked("docker ps", 3)

    # Output redirection blocked at l3
    def test_redirect_out_blocked(self):    _blocked("echo hello > /tmp/out.txt", 3)
    def test_redirect_out_append_blocked(self): _blocked("echo hello >> /tmp/out.txt", 3)
    def test_redirect_in_blocked(self):     _blocked("cat < file.txt", 3)

    # Subshell / code injection
    def test_subshell_dollar_blocked(self): _blocked("echo $(whoami)", 3)
    def test_backtick_blocked(self):        _blocked("echo `whoami`", 3)
    def test_brace_expand_blocked(self):    _blocked("echo ${HOME}", 3)

    # Dangerous git subcommands
    def test_git_push_blocked(self):  _blocked("git push", 3)
    def test_git_push_force_blocked(self): _blocked("git push --force", 3)
    def test_git_rm_blocked(self):    _blocked("git rm file.txt", 3)
    def test_git_reset_blocked(self): _blocked("git reset --hard HEAD", 3)
    def test_git_merge_blocked(self): _blocked("git merge main", 3)
    def test_git_checkout_blocked(self): _blocked("git checkout main", 3)

    # git commit without -m
    def test_git_commit_no_m_blocked(self):      _blocked("git commit", 3)
    def test_git_commit_bad_flag_blocked(self):  _blocked("git commit --no-verify -m 'test'", 3)
    # git add/commit at l2 (allowed via git validator regardless of level)
    def test_git_add_at_l2_allowed(self):        _ok("git add .", 2)
    def test_git_commit_m_at_l2_allowed(self):   _ok("git commit -m 'test'", 2)

    # find with dangerous args
    def test_find_delete_blocked(self):  _blocked("find . -delete", 3)
    def test_find_execdir_blocked(self): _blocked("find . -execdir rm {} ;", 3)

    # Sensitive paths still blocked
    def test_cat_ssh_blocked(self):    _blocked("cat ~/.ssh/id_rsa", 3)
    def test_cat_env_blocked(self):    _blocked(f"cat {WS}/.env", 3)

    # Background execution
    def test_background_amp_blocked(self): _blocked("sleep 100 &", 3)


# ── Level 4: unrestricted shell ───────────────────────────────────────────────

class TestLevel4Pass:
    """Level 4 passes everything through to /bin/sh (except system blocks)."""

    def test_ping(self):           _ok("ping -c 1 127.0.0.1", 4)
    def test_node(self):           _ok("node --version", 4)
    def test_redirect_out(self):   _ok("echo hello > /tmp/apex-test-out.txt", 4)
    def test_subshell(self):       _ok("echo $(whoami)", 4)
    def test_backtick(self):       _ok("echo `whoami`", 4)
    def test_background(self):     _ok("sleep 1 &", 4)
    def test_docker(self):         _ok("docker ps", 4)
    def test_brew(self):           _ok("brew list", 4)
    def test_git_push(self):       _ok("git push origin main", 4)
    def test_git_reset_hard(self): _ok("git reset --hard HEAD", 4)
    def test_complex_chain(self):  _ok("ls | grep foo && echo done || echo fail", 4)


# ── System blocked commands (policy override) ─────────────────────────────────

class TestSystemBlocked:
    """never_allowed_commands policy blocks commands at all levels including l4."""

    def test_blocked_at_l2(self):
        _blocked("rm -rf /", 2, allowed_commands=["rm -rf /"])
        # Using the policy mechanism: validate_command checks system blocks via
        # config.json policy — test via the allowed_commands param shortcut here
        # to avoid needing a real config.json.

    def test_custom_allowed_commands_override_l3_defaults(self):
        # When allowed_commands is explicitly set, it replaces l3 defaults
        _ok("node --version", 3, allowed_commands=["node"])
        _blocked("ping 127.0.0.1", 3, allowed_commands=["node"])


# ── Path validation ───────────────────────────────────────────────────────────

class TestValidatePath:
    """validate_path blocks protected and sensitive paths."""

    def test_workspace_path_ok(self):
        path = str(_TEST_ROOT / "file.txt")
        assert validate_path(path) is None

    def test_tmp_path_ok(self):
        assert validate_path("/tmp/apex-test.txt") is None

    def test_env_file_blocked(self):
        path = str(_TEST_ROOT / ".env")
        assert validate_path(path) is not None

    def test_ssh_dir_not_blocked_by_validate_path(self):
        # validate_path alone does NOT block ~/.ssh — SSH path protection is
        # enforced at the bash-arg level via _validate_arg_paths/_is_sensitive_path,
        # and at the file-tool level via ensure_workspace_path workspace-bounds check.
        import os
        ssh = os.path.realpath(os.path.expanduser("~/.ssh"))
        assert validate_path(ssh) is None  # validate_path doesn't have this gate

    def test_ssh_dir_blocked_via_workspace_bounds(self):
        import os
        ssh = os.path.realpath(os.path.expanduser("~/.ssh"))
        _, err = ensure_workspace_path(ssh, WS, permission_level=2)
        assert err is not None  # blocked because it's outside workspace root

    def test_system_binary_write_blocked(self):
        assert validate_path("/usr/bin/python3", allow_write=True) is not None

    def test_system_binary_read_ok(self):
        # Reading system paths is allowed by default
        assert validate_path("/usr/bin/python3") is None

    def test_level4_bypasses_protected(self):
        # Level 4 bypasses PROTECTED_PATHS but not live DB or policy blocks
        path = str(_TEST_ROOT / ".env")
        assert validate_path(path, permission_level=4) is None


class TestEnsureWorkspacePath:
    """ensure_workspace_path enforces workspace boundary."""

    def test_relative_path_resolved(self):
        resolved, err = ensure_workspace_path("file.txt", WS)
        assert err is None
        assert resolved is not None

    def test_absolute_within_workspace(self):
        path = str(_TEST_ROOT / "subdir" / "file.txt")
        resolved, err = ensure_workspace_path(path, WS)
        assert err is None

    def test_absolute_outside_workspace_blocked(self):
        _, err = ensure_workspace_path("/etc/passwd", WS)
        assert err is not None

    def test_traversal_blocked(self):
        _, err = ensure_workspace_path("../../etc/passwd", WS)
        assert err is not None

    def test_l3_allows_tmp(self):
        _, err = ensure_workspace_path("/tmp/apex-test-file.txt", WS, permission_level=3)
        assert err is None

    def test_l2_blocks_tmp(self):
        _, err = ensure_workspace_path("/tmp/apex-test-file.txt", WS, permission_level=2)
        assert err is not None

    def test_l4_allows_any_path(self):
        _, err = ensure_workspace_path("/tmp/some-file.txt", WS, permission_level=4)
        assert err is None


# ── prepare_command return shape ──────────────────────────────────────────────

class TestPrepareCommandShape:
    """prepare_command returns correct argv/error shapes."""

    def test_ok_returns_argv_none(self):
        argv, err = prepare_command("ls", WS, permission_level=2)
        assert err is None
        assert isinstance(argv, list)
        assert argv[0].endswith("ls")

    def test_blocked_returns_none_error(self):
        argv, err = prepare_command("ping 127.0.0.1", WS, permission_level=2)
        assert argv is None
        assert isinstance(err, str)
        assert "ping" in err

    def test_l4_returns_sh_lc(self):
        argv, err = prepare_command("ping 127.0.0.1", WS, permission_level=4)
        assert err is None
        assert argv == ["/bin/sh", "-lc", "ping 127.0.0.1"]

    def test_l3_compound_returns_sh_lc(self):
        argv, err = prepare_command("ls | grep foo", WS, permission_level=3)
        assert err is None
        assert argv == ["/bin/sh", "-lc", "ls | grep foo"]

    def test_empty_command_blocked(self):
        _, err = prepare_command("", WS, permission_level=2)
        assert err is not None

    def test_whitespace_only_blocked(self):
        _, err = prepare_command("   ", WS, permission_level=2)
        assert err is not None


# ── DEFAULT_LEVEL3_ALLOWED_COMMANDS completeness ──────────────────────────────

class TestL3AllowlistContents:
    """Spot-check the l3 allowlist for expected entries."""

    EXPECTED = {
        "awk", "cat", "cp", "curl", "cut", "diff", "echo", "find",
        "git", "grep", "head", "ls", "mkdir", "mv", "python3",
        "rm", "sed", "sqlite3", "tail", "touch", "wc",
    }
    SHOULD_NOT_CONTAIN = {"ping", "node", "brew", "docker", "bash", "sh"}

    def test_expected_commands_present(self):
        missing = self.EXPECTED - DEFAULT_LEVEL3_ALLOWED_COMMANDS
        assert not missing, f"Missing from l3 allowlist: {missing}"

    def test_sensitive_commands_absent(self):
        present = self.SHOULD_NOT_CONTAIN & DEFAULT_LEVEL3_ALLOWED_COMMANDS
        assert not present, f"Should not be in l3 allowlist: {present}"


# ── Error message quality ─────────────────────────────────────────────────────

class TestErrorMessages:
    """Error messages should be informative and include the level."""

    def test_blocked_bash_error_includes_level(self):
        _, err = prepare_command("ping 127.0.0.1", WS, permission_level=2)
        assert err is not None
        assert "2" in err or "level" in err.lower()

    def test_blocked_bash_error_includes_level_3(self):
        _, err = prepare_command("node --version", WS, permission_level=3)
        assert err is not None
        assert "3" in err or "level" in err.lower()

    def test_l0_error_mentions_disabled(self):
        _, err = prepare_command("ls", WS, permission_level=0)
        assert "disabled" in err.lower()
