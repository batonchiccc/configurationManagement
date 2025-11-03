import os
import sys
import re
from pathlib import Path

def find_dist_info_dirs():
    site_packages = [p for p in sys.path if 'site-packages' in p]
    dist_info_dirs = []
    for sp in site_packages:
        if os.path.isdir(sp):
            for item in os.listdir(sp):
                if item.endswith('.dist-info'):
                    dist_info_dirs.append(os.path.join(sp, item))
    return dist_info_dirs

def parse_metadata(metadata_path):
    with open(metadata_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    name = None
    deps = []
    for line in content.splitlines():
        if line.startswith('Name: '):
            name = line.split(':', 1)[1].strip()
        elif line.startswith('Requires-Dist: '):
            dep = line.split(':', 1)[1].strip()
            pkg_name = re.split(r'\s*\(', dep)[0].strip()
            deps.append(pkg_name)
    return name, deps

def build_dependency_graph():
    graph = {}
    for dist_dir in find_dist_info_dirs():
        metadata_file = os.path.join(dist_dir, 'METADATA')
        if os.path.isfile(metadata_file):
            name, deps = parse_metadata(metadata_file)
            if name:
                graph[name] = deps
    return graph

def print_dot(graph):
    print("digraph G {")
    for pkg, deps in graph.items():
        for dep in deps:
            print(f'  "{pkg}" -> "{dep}";')
    print("}")

if __name__ == "__main__":
    graph = build_dependency_graph()
    print_dot(graph)