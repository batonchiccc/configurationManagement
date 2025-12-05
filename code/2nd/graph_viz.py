import os
import tempfile
import subprocess
import json
from graphviz import Digraph

def load_test_repo(file_path):
    """Загружает зависимости из локального JSON-файла."""
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def fetch_and_parse_package_json(repo_url):
    """Клонирует репозиторий и извлекает прямые зависимости из package.json."""
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            subprocess.run(['git', 'clone', repo_url, tmpdir], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            raise Exception("Failed to clone repository.")
        
        package_json_path = os.path.join(tmpdir, 'package.json')
        if not os.path.exists(package_json_path):
            raise Exception("package.json not found in repository.")

        with open(package_json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        dependencies = data.get('dependencies', {})
        package_name = data.get('name', 'unknown-package')
        return {package_name: list(dependencies.keys())}

def build_full_dependency_graph(initial_package, get_direct_deps_func):
    """
    Рекурсивный BFS для построения полного графа зависимостей.
    get_direct_deps_func: функция, возвращающая словарь {pkg: [deps]}
    """
    visited = set()
    graph = {}
    recursion_stack = set()

    def dfs_recursive(pkg):
        if pkg in recursion_stack:
            print(f"Warning: Cycle detected involving {pkg}")
            return
        if pkg in visited:
            return

        recursion_stack.add(pkg)
        direct_deps = get_direct_deps_func(pkg)
        graph.update(direct_deps)

        for dep in direct_deps.get(pkg, []):
            dfs_recursive(dep)

        recursion_stack.remove(pkg)
        visited.add(pkg)

    dfs_recursive(initial_package)
    return graph

def get_direct_deps_from_dict(deps_dict):
    """Возвращает функцию, которая возвращает зависимости из словаря."""
    def get_deps(pkg):
        return {pkg: deps_dict.get(pkg, [])}
    return get_deps

def visualize_dependencies(deps_dict, output_file, output_ascii, root_package, output_dot_file=None):
    """
    Визуализирует граф зависимостей в PNG и, при необходимости, выводит ASCII-дерево и DOT-код.
    """
    dot = Digraph(comment='Dependency Graph')

    def add_nodes_edges(pkg):
        dot.node(pkg, pkg)
        for dep in deps_dict.get(pkg, []):
            dot.edge(pkg, dep)

    for pkg in deps_dict:
        add_nodes_edges(pkg)

    # 2. Сохранить изображение графа в файле формата PNG.
    dot.render(output_file.replace('.png', ''), format='png', cleanup=True)
    print(f"Graph image saved to {output_file}")

    # 1. Сформировать текстовое представление графа (в формате DOT, используемого graphviz).
    dot_code = dot.source
    if output_dot_file:
        with open(output_dot_file, 'w', encoding='utf-8') as f:
            f.write(dot_code)
        print(f"DOT representation saved to {output_dot_file}")
    else:
        print("\n--- DOT Representation (Text) ---")
        print(dot_code)

    # 3. Если задан соответствующий параметр, вывести на экран зависимости в виде ASCII-дерева.
    if output_ascii:
        print("\n--- ASCII Dependency Tree ---")
        def print_tree(pkg, prefix=""):
            print(prefix + pkg)
            children = deps_dict.get(pkg, [])
            for i, child in enumerate(children):
                extension = "├── " if i < len(children) - 1 else "└── "
                print_tree(child, prefix + ("│   " if prefix and not prefix.endswith("└── ") else "    ") + extension)

        print_tree(root_package)
