import argparse
import os
import sys
import shlex
import getpass
import socket
import zipfile
import base64
from datetime import datetime


class VFSNode:
    def __init__(self, name, parent=None, is_dir=False, mode=0o755, content=b''):
        self.name = name
        self.parent = parent
        self.is_dir = is_dir
        self.children = {} if is_dir else None
        self.content = content
        self.mode = mode
        self.mtime = datetime.now()

    def path(self):
        parts = []
        node = self
        while node and node.parent is not None:
            parts.append(node.name)
            node = node.parent
        return '/' + '/'.join(reversed(parts))


class VFS:
    def __init__(self):
        self.root = VFSNode('', parent=None, is_dir=True)
        self.root.parent = None

    def _ensure_dir(self, path_parts):
        node = self.root
        for p in path_parts:
            if p not in node.children:
                node.children[p] = VFSNode(p, parent=node, is_dir=True)
            node = node.children[p]
        return node

    def load_zip(self, zip_path):
        with zipfile.ZipFile(zip_path, 'r') as zf:
            for info in zf.infolist():
                name = info.filename
                if name.endswith('/'):
                    # директория
                    parts = [p for p in name.split('/') if p]
                    self._ensure_dir(parts)
                else:
                    parts = name.split('/')
                    filename = parts[-1]
                    dir_parts = parts[:-1]
                    parent = self._ensure_dir(dir_parts)
                    raw = zf.read(info)
                    if filename.endswith('.b64'):
                        try:
                            decoded = base64.b64decode(raw)
                        except Exception:
                            decoded = raw
                        content = decoded
                        filename = filename[:-4]  
                    else:
                        content = raw
                    parent.children[filename] = VFSNode(filename, parent=parent, is_dir=False, content=content)

    def resolve(self, cwd_node, path):
        if path == '':
            return cwd_node
        if path.startswith('/'):
            node = self.root
            parts = [p for p in path.split('/') if p]
        else:
            node = cwd_node
            parts = [p for p in path.split('/') if p]
        for p in parts:
            if p == '.':
                continue
            if p == '..':
                if node.parent is not None:
                    node = node.parent
                continue
            if not node.is_dir or p not in node.children:
                return None
            node = node.children[p]
        return node

    def mkdir(self, cwd_node, path, mode=0o755):
        if path.startswith('/'):
            base = self.root
            parts = [p for p in path.split('/') if p]
        else:
            base = cwd_node
            parts = [p for p in path.split('/') if p]
        node = base
        for p in parts:
            if p not in node.children:
                node.children[p] = VFSNode(p, parent=node, is_dir=True, mode=mode)
            else:
                if not node.children[p].is_dir:
                    raise FileExistsError(f"File exists and is not a directory: {p}")
            node = node.children[p]
        return node


class ShellEmulator:
    def __init__(self, vfs=None, prompt_template='{user}@{host}:{cwd}$ ', startup_script=None):
        self.vfs = vfs or VFS()
        self.prompt_template = prompt_template
        self.user = getpass.getuser()
        self.host = socket.gethostname()
        self.cwd = self.vfs.root
        self.home = self.vfs.root  
        self.startup_script = startup_script

    def format_cwd(self):
        p = self.cwd.path()
        if p == '/':
            return '~'
        return p

    def build_prompt(self):
        return self.prompt_template.format(user=self.user, host=self.host, cwd=self.format_cwd())

    def parse_input(self, line: str):
        tokens = line.strip().split()
        if not tokens:
            return None, []
        return tokens[0], tokens[1:]

    def cmd_ls(self, args):
        path = args[0] if args else ''
        target = self.vfs.resolve(self.cwd, path) if path else self.cwd
        if not target:
            print(f"ls: cannot access '{path}': No such file or directory")
            return
        if not target.is_dir:
            print(path)
            return
        names = sorted(target.children.keys())
        for name in names:
            node = target.children[name]
            t = 'd' if node.is_dir else '-'
            print(f"{t} {name}")

    def cmd_cd(self, args):
        path = args[0] if args else ''
        if not path or path == '~':
            self.cwd = self.home
            return
        node = self.vfs.resolve(self.cwd, path)
        if not node:
            print(f"cd: {path}: No such file or directory")
            return
        if not node.is_dir:
            print(f"cd: {path}: Not a directory")
            return
        self.cwd = node

    def cmd_exit(self, args):
        print('Goodbye!')
        sys.exit(0)

    def cmd_tree(self, args):
        start = args[0] if args else ''
        node = self.vfs.resolve(self.cwd, start) if start else self.cwd
        if not node:
            print(f"tree: {start}: No such directory")
            return
        def _walk(n, prefix=''):
            print(prefix + (n.name if n.name else '/'))
            if n.is_dir:
                for k in sorted(n.children.keys()):
                    _walk(n.children[k], prefix + '  ')
        _walk(node)

    def cmd_cal(self, args):
        now = datetime.now()
        year = now.year
        month = now.month
        if len(args) == 1:
            try:
                m = int(args[0])
                if 1 <= m <= 12:
                    month = m
            except Exception:
                pass
        import calendar
        print(calendar.month(year, month))

    def cmd_chmod(self, args):
        if len(args) < 2:
            print('chmod: missing operand')
            return
        mode_str, path = args[0], args[1]
        try:
            mode = int(mode_str, 8)
        except Exception:
            print('chmod: invalid mode')
            return
        node = self.vfs.resolve(self.cwd, path)
        if not node:
            print(f"chmod: cannot access '{path}': No such file or directory")
            return
        node.mode = mode

    def cmd_mkdir(self, args):
        if not args:
            print('mkdir: missing operand')
            return
        path = args[0]
        try:
            self.vfs.mkdir(self.cwd, path)
        except FileExistsError as e:
            print(f'mkdir: {e}')

    def cmd_help(self, args):
        print('Supported commands:')
        print('  ls [path]       - list directory contents (stub -> real)')
        print('  cd [path]       - change directory')
        print('  tree [path]     - print tree of directories')
        print('  cal [month]     - print calendar of current month or specified month (1-12)')
        print('  chmod MODE PATH - change mode (memory only)')
        print('  mkdir PATH      - create directory (memory only)')
        print('  help            - this help')
        print('  exit            - exit emulator')

    def unknown(self, cmd):
        print(f"Error: unknown command '{cmd}'")

    COMMAND_MAP = {
        'ls': cmd_ls,
        'cd': cmd_cd,
        'exit': cmd_exit,
        'tree': cmd_tree,
        'cal': cmd_cal,
        'chmod': cmd_chmod,
        'mkdir': cmd_mkdir,
        'help': cmd_help,
    }

    def run_line(self, line, echo_input=False):
        if echo_input:
            print(self.build_prompt() + line)
        cmd, args = self.parse_input(line)
        if cmd is None:
            return
        func = self.COMMAND_MAP.get(cmd)
        if func:
            try:
                func(self, args)
            except SystemExit:
                raise
            except Exception as e:
                print(f"Error while executing {cmd}: {e}")
        else:
            self.unknown(cmd)

    def run_startup(self):
        if not self.startup_script:
            return
        if not os.path.exists(self.startup_script):
            print(f"Startup script not found: {self.startup_script}")
            return
        with open(self.startup_script, 'r', encoding='utf-8') as f:
            for raw in f:
                line = raw.rstrip('\n')
                stripped = line.strip()
                if not stripped or stripped.startswith('#'):
                    print(f"# {line}")
                    continue
                self.run_line(line, echo_input=True)

    def repl(self):
        try:
            self.run_startup()
            while True:
                try:
                    prompt = self.build_prompt()
                    raw = input(prompt)
                except EOFError:
                    print()
                    break
                except KeyboardInterrupt:
                    print()
                    continue
                self.run_line(raw)
        except SystemExit:
            raise
        except Exception as e:
            print(f"Fatal error in REPL: {e}")


def create_sample_zip(path):
    import io
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with zipfile.ZipFile(path, 'w') as zf:
        zf.writestr('README.txt', 'This is a sample VFS.\n')
        zf.writestr('bin/run.sh', '#!/bin/sh\necho hello')
        zf.writestr('dir1/file1.txt', 'Content of file1')
        zf.writestr('dir1/dir2/file2.txt', 'Content of file2')
        bdata = b"\x00\x01\x02\x03binarydata"
        b64 = base64.b64encode(bdata).decode('ascii')
        zf.writestr('dir1/dir2/data.bin.b64', b64)


def main():
    parser = argparse.ArgumentParser(description='Shell Emulator')
    parser.add_argument('--vfs', help='Path to ZIP archive for VFS', default='samples/minimal.zip')
    parser.add_argument('--prompt', help='Prompt template (use {user},{host},{cwd})', default='{user}@{host}:{cwd}$ ')
    parser.add_argument('--startup', help='Path to startup script', default=None)
    args = parser.parse_args()

    if args.vfs == 'samples/minimal.zip' and not os.path.exists('samples/minimal.zip'):
        print('Creating sample VFS at samples/minimal.zip')
        create_sample_zip('samples/minimal.zip')

    vfs = VFS()
    if args.vfs and os.path.exists(args.vfs):
        try:
            vfs.load_zip(args.vfs)
        except Exception as e:
            print(f"Error loading VFS from {args.vfs}: {e}")
            sys.exit(2)
    else:
        print(f"VFS not found at {args.vfs}, starting with empty VFS")

    shell = ShellEmulator(vfs=vfs, prompt_template=args.prompt, startup_script=args.startup)

    print('--- Debug: startup parameters ---')
    print(f'VFS: {args.vfs}')
    print(f'Prompt template: {args.prompt}')
    print(f'Startup script: {args.startup}')
    print('---------------------------------')

    shell.repl()


if __name__ == '__main__':
    main()

