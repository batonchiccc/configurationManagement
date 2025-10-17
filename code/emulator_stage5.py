
#!/usr/bin/env python3
"""Bash-like emulator - Stage 5 (final): adds chmod, mkdir, help, and full documentation."""
import os, sys, shlex, getpass, socket, argparse, io, zipfile, base64, calendar
from datetime import datetime
from pathlib import PurePosixPath

class InMemoryVFS:
    def __init__(self, zip_bytes: bytes):
        self._buf = io.BytesIO(zip_bytes)
        self._zip = zipfile.ZipFile(self._buf, mode='r')
        self._names = set(self._zip.namelist())
        self._dirs = set(n for n in self._names if n.endswith('/'))
        for n in list(self._names):
            if not n.endswith('/'):
                parts = PurePosixPath(n).parts
                for i in range(1, len(parts)):
                    d = '/'.join(parts[:i]) + '/'
                    self._dirs.add(d)
        self._dirs.add('')
        self._files = set(n for n in self._names if not n.endswith('/'))
        self.perms = {name: 0o755 if name.endswith('/') else 0o644 for name in self._names}

    def listdir(self, cwd: str):
        prefix = cwd.rstrip('/') + ('/' if cwd and not cwd.endswith('/') else '')
        seen, results = set(), []
        for name in sorted(self._names):
            if not name.startswith(prefix): continue
            rest = name[len(prefix):]
            if rest == '': continue
            first = rest.split('/', 1)[0]
            if first in seen: continue
            seen.add(first)
            results.append(first + ('/' if prefix + first + '/' in self._dirs else ''))
        return results

    def is_dir(self, path: str):
        p = path.strip('/')
        if p == '': return True
        return (p + '/' in self._dirs)

    def is_file(self, path: str):
        p = path.strip('/')
        return p in self._files

    def read_file(self, path: str):
        p = path.strip('/')
        if p not in self._files: return None
        with self._zip.open(p, 'r') as f: return f.read()

    def mkdir(self, path: str):
        p = path.strip('/') + '/'
        if p in self._dirs or p in self._files:
            raise FileExistsError(f"mkdir: cannot create directory '{path}': File exists")
        parent = '/'.join(p.strip('/').split('/')[:-1])
        if parent and parent + '/' not in self._dirs:
            raise FileNotFoundError(f"mkdir: cannot create directory '{path}': No such file or directory")
        self._dirs.add(p); self._names.add(p); self.perms[p] = 0o755

    def chmod(self, path: str, mode: int):
        p = path.strip('/')
        key = p + '/' if (p + '/') in self._dirs else p
        if key not in self.perms:
            raise FileNotFoundError(f"chmod: cannot access '{path}': No such file or directory")
        self.perms[key] = mode

class BashEmulator:
    def __init__(self, vfs_path=None, prompt=None, startup=None, debug=True):
        self.vfs_path, self.custom_prompt, self.startup_script = vfs_path, prompt, startup
        self.debug, self.cwd, self.running, self.vfs = debug, '', True, None
        if self.vfs_path: self._load_vfs(self.vfs_path)
        self.commands = {
            'ls': 'List directory contents',
            'cd': 'Change current directory',
            'tree': 'Display directory tree',
            'cal': 'Show calendar (cal [month] [year])',
            'mkdir': 'Create directory (in-memory only)',
            'chmod': 'Change file/directory permissions (in-memory only)',
            'help': 'Show list of commands',
            'exit': 'Exit emulator'
        }

    def _load_vfs(self, path):
        with open(path, 'rb') as f: b = f.read()
        self.vfs = InMemoryVFS(b)

    def debug_print_params(self):
        print(f"[DEBUG] VFS: {self.vfs_path}\nPrompt: {self.custom_prompt}\nStartup: {self.startup_script}\n")

    def get_prompt(self):
        if self.custom_prompt: return self.custom_prompt
        return f"{getpass.getuser()}@{socket.gethostname()}:{'/' + self.cwd if self.cwd else '/'}$ "

    def parse_input(self, line):
        if not line.strip(): return None, []
        parts = shlex.split(line); return parts[0], parts[1:] if parts else (None, [])

    def _resolve(self, path):
        p = PurePosixPath(path)
        if p.is_absolute(): return str(p).lstrip('/')
        if self.cwd == '': base = PurePosixPath('.')
        else: base = PurePosixPath(self.cwd)
        return str((base / p)).strip('/')

    def cmd_ls(self, args):
        target = args[0] if args else '.'
        resolved = self._resolve(target)
        if not self.vfs.is_dir(resolved) and not self.vfs.is_file(resolved):
            print(f"ls: cannot access '{target}': No such file or directory")
            return
        if self.vfs.is_file(resolved):
            perms = oct(self.vfs.perms.get(resolved, 0o644))
            print(f"{perms} {target}"); return
        entries = self.vfs.listdir(resolved)
        for e in entries:
            name = (resolved + '/' + e).strip('/')
            key = name if name in self.vfs.perms else name + '/'
            perms = oct(self.vfs.perms.get(key, 0o755))
            print(f"{perms} {e}")

    def cmd_cd(self, args):
        target = args[0] if args else '/'
        if target == '/': self.cwd=''; return
        newp = self._resolve(target)
        if not self.vfs.is_dir(newp):
            print(f"cd: {target}: No such directory"); return
        self.cwd = newp.strip('/')

    def cmd_tree(self, args):
        def walk(path, prefix=''):
            entries = self.vfs.listdir(path)
            for i, e in enumerate(entries):
                is_last = i == len(entries)-1
                connector = '└── ' if is_last else '├── '
                print(prefix + connector + e)
                subpath = (path + '/' + e).strip('/')
                if e.endswith('/') and self.vfs.is_dir(subpath):
                    walk(subpath, prefix + ('    ' if is_last else '│   '))
        start = self.cwd
        print(f"./")
        walk(start)

    def cmd_cal(self, args):
        now = datetime.now()
        y, m = now.year, now.month
        if len(args) == 1: m = int(args[0])
        elif len(args) == 2: m, y = int(args[0]), int(args[1])
        print(calendar.month(y, m))

    def cmd_mkdir(self, args):
        if not args:
            print("mkdir: missing operand"); return
        for d in args:
            try: self.vfs.mkdir(self._resolve(d)); print(f"Directory '{d}' created")
            except Exception as e: print(e)

    def cmd_chmod(self, args):
        if len(args) < 2:
            print("chmod: usage: chmod <mode> <path>"); return
        try: mode = int(args[0], 8)
        except: print("chmod: invalid mode"); return
        path = args[1]
        try: self.vfs.chmod(self._resolve(path), mode); print(f"Permissions of '{path}' changed to {oct(mode)}")
        except Exception as e: print(e)

    def cmd_help(self, args):
        print("Available commands:")
        for cmd, desc in self.commands.items():
            print(f"  {cmd:<8} - {desc}")

    def cmd_exit(self, args):
        code = 0
        if args:
            try: code = int(args[0])
            except: code = 1
        self.running = False
        return ("exit", code)

    def handle(self, cmd, args):
        if cmd == None: return
        if cmd == 'ls': self.cmd_ls(args)
        elif cmd == 'cd': self.cmd_cd(args)
        elif cmd == 'tree': self.cmd_tree(args)
        elif cmd == 'cal': self.cmd_cal(args)
        elif cmd == 'mkdir': self.cmd_mkdir(args)
        elif cmd == 'chmod': self.cmd_chmod(args)
        elif cmd == 'help': self.cmd_help(args)
        elif cmd == 'exit': return self.cmd_exit(args)
        else: print(f"[stub] {cmd} {' '.join(args)}")

    def run(self):
        if self.debug: self.debug_print_params()
        if self.startup_script and os.path.isfile(self.startup_script):
            with open(self.startup_script, 'r', encoding='utf-8') as f:
                for line in f:
                    line=line.strip()
                    if not line or line.startswith('#'): continue
                    print(self.get_prompt()+line)
                    cmd, args=self.parse_input(line)
                    res=self.handle(cmd,args)
                    if isinstance(res,tuple) and res[0]=='exit':
                        print("[startup] exit encountered."); sys.exit(res[1])
        while self.running:
            try: line = input(self.get_prompt())
            except EOFError: print(); break
            cmd, args = self.parse_input(line)
            res = self.handle(cmd, args)
            if isinstance(res, tuple) and res[0]=='exit': sys.exit(res[1])

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--vfs'); ap.add_argument('--prompt'); ap.add_argument('--startup')
    args = ap.parse_args(argv)
    e = BashEmulator(vfs_path=args.vfs, prompt=args.prompt, startup=args.startup)
    e.run()

if __name__ == '__main__': main()
