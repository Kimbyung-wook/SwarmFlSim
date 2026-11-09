"""TC-GW-016~018: 진입점의 버스 백엔드 선택과 콘솔 인코딩"""
import os
import subprocess
import sys

import pytest
import swarm_gateway.__main__ as cli
from swarm_api import InMemoryBus
from swarm_api.bus import zenoh_available

ARGS = ["--gcs", "gcs-01", "--lacal", "ws://127.0.0.1:9"]


def _run_cli(*args: str, encoding: str = "cp949") -> subprocess.CompletedProcess:
    """콘솔 인코딩을 고정해 실제 프로세스로 띄운다. PYTHONUTF8은 끈다"""
    env = {**os.environ, "PYTHONUTF8": "0", "PYTHONIOENCODING": encoding}
    return subprocess.run([sys.executable, "-m", "swarm_gateway", *args], env=env, capture_output=True, timeout=60)


class _Reached(Exception):
    pass


def _forbid_start(monkeypatch):
    def no_open(cfg):
        raise AssertionError("open_bus must not be called")

    monkeypatch.setattr(cli, "open_bus", no_open)


def test_default_without_zenoh_exits_with_install_hint(monkeypatch, capsys):
    """TC-GW-016: 기본 실행에서 Zenoh가 없으면 버스를 열지 않고 설치 방법을 알리며 0이 아닌 코드로 끝난다"""
    monkeypatch.setattr(cli, "zenoh_available", lambda: False)
    _forbid_start(monkeypatch)
    with pytest.raises(SystemExit) as exc:
        cli.main(ARGS)
    assert exc.value.code == cli.EXIT_NO_BACKEND != 0
    err = capsys.readouterr().err
    assert "uv sync --extra zenoh" in err and "--bus memory" in err


def test_explicit_zenoh_without_zenoh_exits(monkeypatch, capsys):
    monkeypatch.setattr(cli, "zenoh_available", lambda: False)
    _forbid_start(monkeypatch)
    with pytest.raises(SystemExit) as exc:
        cli.main([*ARGS, "--bus", "zenoh"])
    assert exc.value.code == cli.EXIT_NO_BACKEND
    assert "uv sync --extra zenoh" in capsys.readouterr().err


@pytest.mark.skipif(zenoh_available(), reason="eclipse-zenoh가 설치된 환경")
def test_process_without_zenoh_fails():
    """TC-GW-016: 실제 프로세스. LA-CAL에 접속하기 전에 끝나고 ready가 나오지 않는다"""
    r = _run_cli(*ARGS)
    assert r.returncode == cli.EXIT_NO_BACKEND
    err = r.stderr.decode("cp949")
    assert "uv sync --extra zenoh" in err and "Traceback" not in err
    assert b"ready" not in r.stdout + r.stderr


def test_default_backend_is_zenoh():
    assert cli.build_parser().parse_args(["--gcs", "gcs-01"]).bus == "zenoh"


def test_explicit_memory_uses_memory_bus_without_zenoh(monkeypatch, caplog):
    """TC-GW-017: --bus memory는 Zenoh가 없어도 인메모리 버스로 뜨고 경고를 남긴다"""
    seen = {}

    def fake_open(cfg):
        seen["cfg"] = cfg
        return InMemoryBus()

    async def fake_start(bus, config, url, **kw):
        seen["bus"] = bus
        raise _Reached

    monkeypatch.setattr(cli, "zenoh_available", lambda: False)
    monkeypatch.setattr(cli, "open_bus", fake_open)
    monkeypatch.setattr(cli, "start_gateway", fake_start)
    with pytest.raises(_Reached):
        cli.main([*ARGS, "--bus", "memory", "--log", "WARNING"])
    assert seen["cfg"].backend == "memory" and isinstance(seen["bus"], InMemoryBus)
    assert any("no simulator traffic" in r.getMessage() for r in caplog.records)


def test_unknown_backend_is_usage_error(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main([*ARGS, "--bus", "nats"])
    assert exc.value.code == 2


def test_help_on_cp949_stdout():
    """TC-GW-018: cp949 콘솔에서 환경 변수 없이 --help가 정상 종료하고 한글이 그대로 나온다"""
    r = _run_cli("--help")
    assert r.returncode == 0, r.stderr.decode("cp949", "replace")
    out = r.stdout.decode("cp949")
    assert "--no-multicast" in out and "GCS 엔티티 ID" in out


def test_unencodable_text_does_not_crash_console_on_cp949():
    """표현할 수 없는 문자가 앞으로 도움말·로그에 들어와도 인코딩 오류로 끝나지 않는다"""
    code = ("import sys; from swarm_gateway.__main__ import _tolerate_console_encoding as t; t(); "
            "print(chr(0x21c4) + ' ok'); sys.stderr.write(chr(0x21c4))")
    env = {**os.environ, "PYTHONUTF8": "0", "PYTHONIOENCODING": "cp949:strict"}
    r = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == b"? ok"
