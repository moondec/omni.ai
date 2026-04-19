"""
CheckpointManager — workspace snapshot system for agent task rollback.

Strategy (automatic, no user configuration required):
  1. If the workspace is inside a git repository → git commit checkpoint.
     Full history, lossless, supports diff.
  2. Otherwise → lightweight file-copy snapshot in .agent_checkpoints/.
     Works for any directory, no git dependency.
"""

import os
import re
import json
import shutil
import datetime
import subprocess
from typing import List, Dict, Optional


class CheckpointManager:
    SNAPSHOT_DIR = ".agent_checkpoints"
    MAX_FILE_SNAPSHOTS = 15          # auto-prune oldest beyond this limit
    MAX_FILE_SIZE_BYTES = 2 * 1024 * 1024  # skip files > 2 MB in file mode
    SKIP_DIRS = {
        '.git', '__pycache__', 'node_modules', '.venv', 'venv',
        '.agent_checkpoints', '.mypy_cache', '.pytest_cache',
    }
    SKIP_EXTENSIONS = {
        '.exe', '.dll', '.so', '.dylib', '.bin',
        '.pkl', '.h5', '.pt', '.pth', '.onnx', '.npy', '.npz',
        '.mp4', '.mp3', '.wav', '.avi', '.mov',
        '.zip', '.tar', '.gz', '.7z', '.rar',
        '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.webp',
        '.pdf', '.docx', '.xlsx', '.pptx',
    }

    def __init__(self, workspace_path: str):
        self.workspace_path = workspace_path

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    def create(self, label: str) -> Optional[str]:
        """Create a checkpoint before an agent task. Returns id or None."""
        try:
            if self._is_git_repo():
                return self._git_create(label)
            return self._file_create(label)
        except Exception:
            return None

    def list(self) -> List[Dict]:
        """Return checkpoints newest-first."""
        try:
            if self._is_git_repo():
                return self._git_list()
            return self._file_list()
        except Exception:
            return []

    def restore(self, checkpoint_id: str) -> bool:
        """Restore workspace to checkpoint. Returns True on success."""
        try:
            if self._is_git_repo():
                return self._git_restore(checkpoint_id)
            return self._file_restore(checkpoint_id)
        except Exception:
            return False

    def diff_summary(self, checkpoint_id: str) -> str:
        """Human-readable summary of changes since the checkpoint."""
        try:
            if self._is_git_repo():
                r = self._git('diff', '--stat', checkpoint_id, 'HEAD')
                if r.returncode == 0:
                    return r.stdout.strip() or "(no file changes since checkpoint)"
            return "(diff available only for git-based checkpoints)"
        except Exception:
            return "(could not compute diff)"

    def mode(self) -> str:
        return "git" if self._is_git_repo() else "file"

    # ------------------------------------------------------------------ #
    #  Git helpers                                                         #
    # ------------------------------------------------------------------ #

    def _is_git_repo(self) -> bool:
        try:
            r = subprocess.run(
                ['git', 'rev-parse', '--git-dir'],
                cwd=self.workspace_path,
                capture_output=True, text=True, timeout=5
            )
            return r.returncode == 0
        except Exception:
            return False

    def _git(self, *args) -> subprocess.CompletedProcess:
        return subprocess.run(
            ['git'] + list(args),
            cwd=self.workspace_path,
            capture_output=True, text=True, timeout=30
        )

    def _git_create(self, label: str) -> Optional[str]:
        self._git('add', '-A')
        status = self._git('status', '--porcelain')
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if not status.stdout.strip():
            # Nothing to commit — record current HEAD as the checkpoint reference
            head = self._git('rev-parse', 'HEAD')
            return head.stdout.strip() if head.returncode == 0 else None

        msg = f"[agent-checkpoint] {ts} | {label[:80]}"
        r = self._git(
            '-c', 'user.name=Bielik Agent',
            '-c', 'user.email=agent@bielik.local',
            'commit', '-m', msg,
        )
        if r.returncode == 0:
            head = self._git('rev-parse', 'HEAD')
            return head.stdout.strip() if head.returncode == 0 else None
        return None

    def _git_list(self) -> List[Dict]:
        r = self._git(
            'log', '--all',
            '--grep=agent-checkpoint',
            '--format=%H|%ai|%s',
        )
        if r.returncode != 0:
            return []
        checkpoints = []
        for line in r.stdout.strip().splitlines():
            if not line:
                continue
            parts = line.split('|', 2)
            if len(parts) != 3:
                continue
            commit_hash, timestamp, subject = parts
            # Extract the human label from the commit message
            label = re.sub(r'^\[agent-checkpoint\]\s*[\d\-: ]+\s*\|\s*', '', subject)
            checkpoints.append({
                'id': commit_hash[:10],
                'full_id': commit_hash,
                'timestamp': timestamp[:19],
                'label': label,
                'type': 'git',
            })
        return checkpoints

    def _git_restore(self, commit_hash: str) -> bool:
        # Stage any uncommitted changes first so reset is clean
        self._git('add', '-A')
        r = self._git('reset', '--hard', commit_hash)
        return r.returncode == 0

    # ------------------------------------------------------------------ #
    #  File-snapshot helpers                                               #
    # ------------------------------------------------------------------ #

    def _file_create(self, label: str) -> Optional[str]:
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        slug = re.sub(r'[^\w]', '_', label[:40]).strip('_')
        checkpoint_id = f"{ts}__{slug}"
        checkpoint_dir = os.path.join(
            self.workspace_path, self.SNAPSHOT_DIR, checkpoint_id
        )
        os.makedirs(checkpoint_dir, exist_ok=True)
        self._copy_workspace(self.workspace_path, checkpoint_dir)

        meta = {
            'id': checkpoint_id,
            'timestamp': ts[:4] + '-' + ts[4:6] + '-' + ts[6:8]
                         + ' ' + ts[9:11] + ':' + ts[11:13] + ':' + ts[13:15],
            'label': label,
            'type': 'file',
        }
        with open(os.path.join(checkpoint_dir, '.meta.json'), 'w') as f:
            json.dump(meta, f, indent=2)

        self._prune_file_snapshots()
        return checkpoint_id

    def _copy_workspace(self, src_root: str, dst_root: str):
        for item in os.listdir(src_root):
            if item in self.SKIP_DIRS or item.startswith('.'):
                continue
            src = os.path.join(src_root, item)
            dst = os.path.join(dst_root, item)
            if os.path.isfile(src):
                _, ext = os.path.splitext(item)
                if ext.lower() in self.SKIP_EXTENSIONS:
                    continue
                if os.path.getsize(src) > self.MAX_FILE_SIZE_BYTES:
                    continue
                shutil.copy2(src, dst)
            elif os.path.isdir(src):
                self._copy_dir(src, dst)

    def _copy_dir(self, src: str, dst: str):
        os.makedirs(dst, exist_ok=True)
        for item in os.listdir(src):
            if item in self.SKIP_DIRS:
                continue
            s = os.path.join(src, item)
            d = os.path.join(dst, item)
            if os.path.isfile(s):
                _, ext = os.path.splitext(item)
                if ext.lower() in self.SKIP_EXTENSIONS:
                    continue
                if os.path.getsize(s) > self.MAX_FILE_SIZE_BYTES:
                    continue
                shutil.copy2(s, d)
            elif os.path.isdir(s):
                self._copy_dir(s, d)

    def _file_list(self) -> List[Dict]:
        snap_dir = os.path.join(self.workspace_path, self.SNAPSHOT_DIR)
        if not os.path.isdir(snap_dir):
            return []
        checkpoints = []
        for entry in sorted(os.listdir(snap_dir), reverse=True):
            meta_path = os.path.join(snap_dir, entry, '.meta.json')
            if os.path.isfile(meta_path):
                try:
                    with open(meta_path) as f:
                        checkpoints.append(json.load(f))
                except Exception:
                    pass
        return checkpoints

    def _file_restore(self, checkpoint_id: str) -> bool:
        snap_dir = os.path.join(
            self.workspace_path, self.SNAPSHOT_DIR, checkpoint_id
        )
        if not os.path.isdir(snap_dir):
            return False
        for item in os.listdir(snap_dir):
            if item == '.meta.json':
                continue
            src = os.path.join(snap_dir, item)
            dst = os.path.join(self.workspace_path, item)
            if os.path.isfile(src):
                shutil.copy2(src, dst)
            elif os.path.isdir(src):
                if os.path.exists(dst):
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
        return True

    def _prune_file_snapshots(self):
        """Delete oldest file snapshots beyond MAX_FILE_SNAPSHOTS."""
        snap_dir = os.path.join(self.workspace_path, self.SNAPSHOT_DIR)
        if not os.path.isdir(snap_dir):
            return
        entries = sorted(
            [e for e in os.listdir(snap_dir)
             if os.path.isfile(os.path.join(snap_dir, e, '.meta.json'))],
        )
        while len(entries) > self.MAX_FILE_SNAPSHOTS:
            oldest = entries.pop(0)
            shutil.rmtree(os.path.join(snap_dir, oldest), ignore_errors=True)
