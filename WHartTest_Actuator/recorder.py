"""
UI 自动化执行器 - Playwright 录制管理
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from playwright.async_api import async_playwright

logger = logging.getLogger('actuator')


@dataclass
class ActiveRecording:
    recording_id: int
    process: asyncio.subprocess.Process
    script_path: Path
    output_dir: Path
    start_url: str
    started_at: float
    name: str


class CodegenRecordingManager:
    """基于 playwright codegen 的录制管理器"""

    def __init__(self, config: Any = None):
        self.config = config
        self.browser_type = getattr(config, 'browser_type', 'chromium') if config else 'chromium'
        self.headless = bool(getattr(config, 'headless', False)) if config else False
        self.user_data_dir = getattr(config, 'user_data_dir', './data/browser') if config else './data/browser'
        self.base_dir = Path(getattr(config, 'screenshot_dir', './data/screenshots') if config else './data/screenshots').parent / 'recordings'
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._active: Optional[ActiveRecording] = None
        self._lock = asyncio.Lock()

    @property
    def active_recording(self) -> Optional[ActiveRecording]:
        return self._active

    async def start(self, *, recording_id: int, start_url: str = '', name: str = '') -> dict:
        async with self._lock:
            if self.headless:
                raise RuntimeError('当前执行器为无头模式，无法开始录制')
            if self._active and self._active.process.returncode is None:
                raise RuntimeError(f'执行器当前已有活动录制会话 #{self._active.recording_id}')

            start_url = (start_url or '').strip() or 'about:blank'
            timestamp = int(time.time())
            output_dir = self.base_dir / f"recording_{recording_id}_{timestamp}"
            output_dir.mkdir(parents=True, exist_ok=True)
            script_path = output_dir / 'recording.js'
            cmd = [
                sys.executable,
                '-m',
                'playwright',
                'codegen',
                '--target',
                'javascript',
                '--browser',
                self.browser_type,
                '--output',
                str(script_path),
                start_url,
            ]
            logger.info("启动录制命令: %s", " ".join(cmd))
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.sleep(1)
            if process.returncode is not None:
                stdout, stderr = await process.communicate()
                raise RuntimeError(
                    f"录制进程启动失败: {stderr.decode('utf-8', errors='ignore') or stdout.decode('utf-8', errors='ignore')}"
                )

            self._active = ActiveRecording(
                recording_id=recording_id,
                process=process,
                script_path=script_path,
                output_dir=output_dir,
                start_url=start_url,
                started_at=time.time(),
                name=name or f"录制-{recording_id}",
            )
            return {
                'recording_id': recording_id,
                'status': 'recording',
                'output_dir': str(output_dir),
                'script_path': str(script_path),
                'start_url': start_url,
            }

    async def stop(self, *, recording_id: int, cancelled: bool = False) -> dict:
        async with self._lock:
            if not self._active or self._active.recording_id != recording_id:
                raise RuntimeError(f'录制会话 #{recording_id} 不存在或已结束')

            active = self._active
            process = active.process
            if process.returncode is None:
                try:
                    if os.name != 'nt':
                        process.send_signal(signal.SIGINT)
                    else:
                        process.terminate()
                    await asyncio.wait_for(process.wait(), timeout=15)
                except asyncio.TimeoutError:
                    logger.warning("录制进程停止超时，尝试强制结束")
                    process.kill()
                    await process.wait()

            stdout, stderr = await process.communicate()
            raw_script = ''
            if active.script_path.exists():
                raw_script = active.script_path.read_text(encoding='utf-8', errors='ignore')

            final_url = self._infer_final_url(raw_script) or active.start_url
            screenshot_path = None if cancelled else await self._capture_final_screenshot(
                output_dir=active.output_dir,
                final_url=final_url,
            )

            duration = max(time.time() - active.started_at, 0.0)
            self._active = None
            return {
                'recording_id': recording_id,
                'status': 'cancelled' if cancelled else 'draft',
                'raw_script': raw_script,
                'artifacts': {
                    'output_dir': str(active.output_dir),
                    'script_path': str(active.script_path),
                    'stdout': stdout.decode('utf-8', errors='ignore'),
                    'stderr': stderr.decode('utf-8', errors='ignore'),
                    'final_screenshot': str(screenshot_path) if screenshot_path else '',
                    'duration': duration,
                    'final_url': final_url,
                },
                'final_url': final_url,
                'error_message': '',
                'cancelled': cancelled,
            }

    async def cancel_if_matches(self, recording_id: int) -> None:
        async with self._lock:
            if self._active and self._active.recording_id == recording_id and self._active.process.returncode is None:
                self._active.process.kill()
                await self._active.process.wait()
                self._active = None

    def _infer_final_url(self, raw_script: str) -> str:
        url = ''
        for line in raw_script.splitlines():
            line = line.strip()
            if "page.goto(" in line or "page.waitForURL(" in line or "expect(page).toHaveURL(" in line:
                matches = []
                quote = None
                buf = []
                for char in line:
                    if quote:
                        if char == quote and (not buf or buf[-1] != '\\'):
                            matches.append("".join(buf))
                            buf = []
                            quote = None
                        else:
                            buf.append(char)
                    elif char in {"'", '"'}:
                        quote = char
                if matches:
                    url = matches[-1]
        return url

    async def _capture_final_screenshot(self, *, output_dir: Path, final_url: str) -> Optional[Path]:
        final_url = (final_url or '').strip()
        if not final_url or not final_url.startswith(('http://', 'https://')):
            return None
        screenshot_path = output_dir / 'final.png'
        try:
            async with async_playwright() as playwright:
                browser_launcher = getattr(playwright, self.browser_type)
                context = await browser_launcher.launch_persistent_context(
                    self.user_data_dir,
                    headless=True,
                    timeout=30000,
                )
                try:
                    page = context.pages[0] if context.pages else await context.new_page()
                    await page.goto(final_url, wait_until='domcontentloaded')
                    await page.screenshot(path=str(screenshot_path), full_page=True)
                finally:
                    await context.close()
            return screenshot_path
        except Exception as exc:
            logger.warning("录制结束截图保存失败: %s", exc)
            return None
