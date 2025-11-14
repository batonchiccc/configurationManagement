#!/usr/bin/env python3
"""
depvis.py — единый файл, объединяющий весь функционал Этапов 1–3:
 - чтение INI
 - загрузка зависимостей npm (локально или по URL)
 - BFS+рекурсия построения полного графа зависимостей
 - режим тест-графов A: B C ...
"""

import argparse
import configparser
import json
import os
import sys
import urllib.request
from collections import deque
from urllib.parse import urlparse


# =============================================================================
# ЭТАП 1. ЧТЕНИЕ И ВАЛИДАЦИЯ КОНФИГА
# =============================================================================

class ConfigError(Exception):
    pass


EXPECTED_KEYS = {
    "package_name": {"required": True, "type": "str"},
    "repo": {"required": True, "type": "url_or_path"},
    "test_repo_mode": {"required": True, "type": "enum", "choices": ["none", "local-file", "remote-url", "test-graph"]},
    "image_filename": {"required": True, "type": "filename"},
    "ascii_tree": {"required": True, "type": "bool"},
}


def is_probably_url(value):
    try:
        p = urlparse(value)
        return p.scheme in ("http", "https", "git", "ssh")
    except:
        return False


def is_valid_filename(name):
    if not name:
        return False
    if os.path.isabs(name):
        return False
    base = os.path.basename(name)
    if not base:
        return False
    ext = os.path.splitext(base)[1].lower()
    return ext in {".png", ".svg", ".jpg", ".jpeg", ".pdf"}


def validate_value(key, raw):
    raw = raw.strip()
    meta = EXPECTED_KEYS[key]
    t = meta["type"]

    if t == "str":
        if not raw:
            raise ConfigError(f"{key} не может быть пустым")
        return raw

    if t == "bool":
        if raw.lower() in ("1", "true", "yes", "on"):
            return True
        if raw.lower() in ("0", "false", "no", "off"):
            return False
        raise ConfigError(f"{key}: ожидается bool")

    if t == "enum":
        if raw not in meta["choices"]:
            raise ConfigError(f"{key}: допустимо {meta['choices']}")
        return raw

    if t == "filename":
        if not is_valid_filename(raw):
            raise ConfigError(f"{key}: неверное имя файла")
        return raw

    if t == "url_or_path":
        if is_probably_url(raw):
            return raw
        if os.path.exists(raw):
            return os.path.abspath(raw)
        raise ConfigError(f"{key}: путь не существует и не является URL")

    raise ConfigError("Неизвестный тип")


def load_config(path):
    if not os.path.exists(path):
        raise ConfigError("INI-файл не найден")

    config = configparser.ConfigParser()
    config.read(path, encoding="utf-8")

    if "settings" not in config:
        raise ConfigError("нет секции [settings]")

    raw = config["settings"]
    result = {}

    for key in EXPECTED_KEYS:
        if key not in raw:
            raise ConfigError(f"Пропущен параметр {key}")
        result[key] = validate_value(key, raw[key])

    # кросс-проверки для mode
    if result["test_repo_mode"] == "local-file" and not os.path.exists(result["repo"]):
        raise ConfigError("local-file: repo путь не найден")

    return result


# =============================================================================
# ЭТАП 2. ПОЛУЧЕНИЕ ПРЯМЫХ ЗАВИСИМОСТЕЙ NPM
# =============================================================================

class DependencyFetchError(Exception):
    pass


def load_package_json_from_url(url):
    try:
        with urllib.request.urlopen(url) as resp:
            data = resp.read().decode("utf-8")
        return json.loads(data)
    except Exception as e:
        raise DependencyFetchError(f"Ошибка загрузки package.json: {e}")


def load_package_json_from_local(path):
    pkg = os.path.join(path, "package.json")
    if not os.path.exists(pkg):
        raise DependencyFetchError(f"Нет файла {pkg}")
    try:
        with open(pkg, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as e:
        raise DependencyFetchError(f"Ошибка чтения {pkg}: {e}")


def extract_direct_dependencies(pkg_json):
    out = {}
    for section in ("dependencies", "peerDependencies"):
        if section in pkg_json and isinstance(pkg_json[section], dict):
            out.update(pkg_json[section])
    return out


def fetch_package_dependencies(repo, mode):
    if mode == "none":
        return {}

    if mode == "local-file":
        pkg = load_package_json_from_local(repo)
        return extract_direct_dependencies(pkg)

    if mode == "remote-url":
        parsed = urlparse(repo)
        if "github.com" in parsed.netloc:
            parts = parsed.path.strip("/").split("/")
            if len(parts) < 2:
                raise DependencyFetchError("Неверный GitHub URL")

            user, repo_name = parts[0], parts[1]
            # определим ветку
            branch = "main"
            if "tree" in parts:
                idx = parts.index("tree")
                if idx + 1 < len(parts):
                    branch = parts[idx + 1]

            raw_url = f"https://raw.githubusercontent.com/{user}/{repo_name}/{branch}/package.json"
            pkg = load_package_json_from_url(raw_url)
            return extract_direct_dependencies(pkg)

        # допускаем, что пользователь дал прямой raw-url
        pkg = load_package_json_from_url(repo)
        return extract_direct_dependencies(pkg)

    raise DependencyFetchError("Неизвестный режим")


# =============================================================================
# ЭТАП 3. BFS + РЕКУРСИЯ + ТЕСТОВЫЕ ГРАФЫ
# =============================================================================

class DependencyGraphError(Exception):
    pass


def load_test_graph(path):
    graph = {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if ":" not in line:
                    raise DependencyGraphError(f"Неверная строка: {line}")
                pkg, deps = line.split(":", 1)
                pkg = pkg.strip()
                deps_list = deps.strip().split()

                if not pkg.isupper():
                    raise DependencyGraphError(f"Имя пакета должно быть A-Z: {pkg}")

                for d in deps_list:
                    if not d.isupper():
                        raise DependencyGraphError(f"Имя пакета должно быть A-Z: {d}")

                graph[pkg] = deps_list

        # Добавляем узлы без зависимостей
        for pkg in list(graph.keys()):
            for d in graph[pkg]:
                if d not in graph:
                    graph[d] = []

        return graph

    except Exception as e:
        raise DependencyGraphError(f"Ошибка чтения графа: {e}")


def bfs_recursive(start, fetcher, visited=None, out=None):
    if visited is None:
        visited = set()
    if out is None:
        out = {}

    queue = deque([start])

    def step():
        if not queue:
            return
        node = queue.popleft()

        if node in visited:
            return step()

        visited.add(node)
        deps = fetcher(node)
        out[node] = deps

        for d in deps:
            if d not in visited:
                queue.append(d)

        return step()

    step()
    return out


def build_full_graph(package_name, repo, mode, test_graph_path=None):
    if mode == "test-graph":
        graph = load_test_graph(test_graph_path)

        def fetcher(x):
            return graph.get(x, [])

        return bfs_recursive(package_name, fetcher)

    def fetcher_real(x):
        if x != package_name:
            return []
        try:
            deps = fetch_package_dependencies(repo, mode)
        except DependencyFetchError:
            return []
        return list(deps.keys())

    return bfs_recursive(package_name, fetcher_real)


# =============================================================================
# ASCII вывод дерева
# =============================================================================

def print_ascii_tree(graph, root):
    """Красивое дерево зависимостей."""
    def rec(node, prefix="", is_last=True, visited=None):
        if visited is None:
            visited = set()
        connector = "└── " if is_last else "├── "
        print(prefix + connector + node)

        if node in visited:
            return
        visited.add(node)

        deps = graph.get(node, [])
        for i, d in enumerate(deps):
            last = (i == len(deps) - 1)
            new_prefix = prefix + ("    " if is_last else "│   ")
            rec(d, new_prefix, last, visited)

    rec(root)


# =============================================================================
# CLI
# =============================================================================

def main(argv=None):
    parser = argparse.ArgumentParser(description="Dependency Visualizer (Этапы 1–3)")
    parser.add_argument("-c", "--config", default="depvis.ini", help="INI-файл")
    args = parser.parse_args(argv)

    try:
        conf = load_config(args.config)
    except ConfigError as e:
        print("Ошибка конфигурации:", e, file=sys.stderr)
        return 2

    print("Параметры:")
    for k, v in conf.items():
        print(f"  {k} = {v}")

    # Этап 2 — прямые зависимости
    print("\nПрямые зависимости:")

    if conf["test_repo_mode"] == "test-graph":
        print("  (в тестовом режиме прямые зависимости читаются из файла графа)")
    else:
        try:
            deps = fetch_package_dependencies(conf["repo"], conf["test_repo_mode"])
            for k, v in deps.items():
                print(f"  {k}: {v}")
        except DependencyFetchError as e:
            print("Ошибка:", e)

    # Этап 3 — полный граф
    print("\nПостроение полного графа...")

    try:
        graph = build_full_graph(
            conf["package_name"],
            conf["repo"],
            conf["test_repo_mode"],
            test_graph_path=conf["repo"],
        )
    except DependencyGraphError as e:
        print("Ошибка графа:", e)
        return 4

    for k, deps in graph.items():
        print(f"  {k}: {deps}")

    # ASCII вывод при необходимости
    if conf["ascii_tree"]:
        print("\nASCII дерево:")
        print_ascii_tree(graph, conf["package_name"])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
