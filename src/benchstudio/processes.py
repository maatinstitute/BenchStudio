"""Trusted external commands and managed services, independent of any benchmark."""
from contextlib import contextmanager
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time
from types import MappingProxyType
from typing import Callable, Mapping


class ProcessFailure(RuntimeError):
    pass


def _stop(process):
    if process.poll() is None:
        if os.name == 'posix':
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        else:
            process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            if os.name == 'posix':
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            else:
                process.kill()
            process.wait()


@dataclass(frozen=True)
class ProcessCommand:
    """A trusted argv command. No shell, automatic retry or framework import."""
    name: str
    argv: tuple[str, ...]
    cwd: str | Path
    env: Mapping[str, str] = field(default_factory=dict)
    timeout: float | None = None

    def __post_init__(self):
        if not re.fullmatch(r'[A-Za-z0-9_-]+', self.name):
            raise ValueError('command name must be a safe file stem')
        if not isinstance(self.argv, (tuple, list)) or not self.argv or any(type(a) is not str or not a for a in self.argv):
            raise ValueError('argv must contain nonempty strings')
        if self.timeout is not None and self.timeout <= 0:
            raise ValueError('timeout must be positive')
        object.__setattr__(self, 'argv', tuple(self.argv))
        object.__setattr__(self, 'cwd', Path(self.cwd).resolve())
        object.__setattr__(self, 'env', MappingProxyType(dict(self.env)))

    @contextmanager
    def started(self, log_dir):
        """Own the process and logs; terminate its group on every exit path."""
        root = Path(log_dir)
        root.mkdir(parents=True, exist_ok=True)
        receipt = root / (self.name + '.receipt.json')
        # Each stage's logs are retained rather than overwritten on a rerun.
        with (root / (self.name + '.stdout.log')).open('x') as out:
            with (root / (self.name + '.stderr.log')).open('x') as err:
                start = time.time()
                process = None
                reason = 'interrupted'
                try:
                    process = subprocess.Popen(self.argv, cwd=self.cwd,
                        env={**os.environ, **self.env}, stdin=subprocess.DEVNULL,
                        stdout=out, stderr=err, start_new_session=(os.name == 'posix'))
                    yield process
                    reason = 'returned'
                except BaseException as error:
                    reason = type(error).__name__
                    raise
                finally:
                    if process is not None:
                        _stop(process)
                    with receipt.open('x') as stream:
                        json.dump({'name': self.name, 'argv': self.argv,
                            'cwd': str(self.cwd), 'started_unix': start,
                            'finished_unix': time.time(), 'exit_code': None if process is None else process.returncode,
                            'reason': reason}, stream, indent=2)

    def run(self, log_dir):
        with self.started(log_dir) as process:
            try:
                code = process.wait(timeout=self.timeout)
            except subprocess.TimeoutExpired as error:
                raise ProcessFailure(f'{self.name} timed out; see {log_dir}') from error
            if code:
                raise ProcessFailure(f'{self.name} exited {code}; see {log_dir}')
        return Path(log_dir) / (self.name + '.receipt.json')

    @contextmanager
    def service(self, log_dir, *, ready: Callable[[], bool], startup_timeout=300):
        """Wait for task-specific readiness; always clean up the owned service."""
        if startup_timeout <= 0:
            raise ValueError('startup_timeout must be positive')
        with self.started(log_dir) as process:
            deadline = time.monotonic() + startup_timeout
            while True:
                if process.poll() is not None:
                    raise ProcessFailure(f'{self.name} exited before readiness; see {log_dir}')
                if ready():
                    break
                if time.monotonic() >= deadline:
                    raise ProcessFailure(f'{self.name} readiness timed out; see {log_dir}')
                time.sleep(0.1)
            yield process
