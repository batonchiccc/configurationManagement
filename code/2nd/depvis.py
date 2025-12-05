import configparser
import argparse
from graph_viz import (
    visualize_dependencies,
    fetch_and_parse_package_json,
    load_test_repo,
    build_full_dependency_graph,
    get_direct_deps_from_dict
)

def main():
    parser = argparse.ArgumentParser(description='Tool for visualizing package dependencies.')
    parser.add_argument('--config', type=str, default='config.ini', help='Path to the INI config file')
    args = parser.parse_args()

    config = configparser.ConfigParser()
    config.read(args.config)

    package_name = config['DEFAULT']['package_name']
    repo_url = config['DEFAULT']['repo_url']
    repo_mode = config['DEFAULT']['repo_mode']
    output_image = config['DEFAULT']['output_image']
    output_ascii = config['DEFAULT'].getboolean('output_ascii')
    output_dot_file = config['DEFAULT'].get('output_dot_file', None) # Новый параметр

    print(f"Config loaded:")
    print(f" - Package: {package_name}")
    print(f" - Repo URL: {repo_url}")
    print(f" - Mode: {repo_mode}")
    print(f" - Output Image: {output_image}")
    print(f" - Output ASCII: {output_ascii}")
    print(f" - Output DOT File: {output_dot_file}")

    if repo_mode == 'test':
        print("Running in test mode...")
        test_deps = load_test_repo(repo_url)
        get_deps_func = get_direct_deps_from_dict(test_deps)
        full_graph = build_full_dependency_graph(package_name, get_deps_func)
    elif repo_mode == 'git':
        print("Running in git mode...")
        initial_deps = fetch_and_parse_package_json(repo_url)
        get_deps_func = lambda pkg: initial_deps if pkg == package_name else {}
        full_graph = build_full_dependency_graph(package_name, get_deps_func)
    else:
        print(f"Unknown repo_mode: {repo_mode}")
        return

    print(f"Full dependency graph built: {full_graph}")

    # Передаем output_dot_file в visualize_dependencies
    visualize_dependencies(full_graph, output_image, output_ascii, package_name, output_dot_file)

if __name__ == '__main__':
    main()
