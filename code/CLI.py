import configparser
import os
import sys
import json
import urllib.request
from urllib.error import URLError, HTTPError
from urllib.parse import urljoin
from collections import deque, defaultdict
import subprocess
import platform

class ConfigError(Exception):
    """Базовый класс для ошибок конфигурации"""
    pass

class PackageFetchError(Exception):
    """Класс для ошибок получения данных пакета"""
    pass

class DependencyVisualizer:
    REQUIRED_PARAMS = {
        'package_name': str,
        'repository_path': str,
        'repository_mode': str,
        'output_image': str,
        'ascii_tree': bool,
        'load_order': bool,  # Для этапа 4
        'plantuml_jar': str  # Для этапа 5
    }
    CONFIG_FILE = 'config.ini'
    CONFIG_SECTION = 'settings'
    VALID_REPO_MODES = {'online', 'offline', 'test'}
    NPM_REGISTRY_URL = 'https://registry.npmjs.org/'
    PLANTUML_URL = "https://sourceforge.net/projects/plantuml/files/plantuml.jar/download"

    def __init__(self):
        self.config = configparser.ConfigParser()
        self.params = {}
        self.test_graph = None
        self.dependency_graph = {}
        self.cycles = []

    def load_config(self):
        """Загружает и валидирует конфигурацию"""
        if not os.path.exists(self.CONFIG_FILE):
            raise ConfigError(f"Конфигурационный файл '{self.CONFIG_FILE}' не найден")
        
        try:
            self.config.read(self.CONFIG_FILE)
        except configparser.Error as e:
            raise ConfigError(f"Ошибка чтения конфигурации: {str(e)}")
        
        if not self.config.has_section(self.CONFIG_SECTION):
            raise ConfigError(f"Отсутствует секция [{self.CONFIG_SECTION}] в конфигурации")
        
        # Загружаем параметры с валидацией
        for param, param_type in self.REQUIRED_PARAMS.items():
            if not self.config.has_option(self.CONFIG_SECTION, param):
                # Для совместимости с предыдущими этапами
                if param in ('load_order', 'plantuml_jar'):
                    default_value = "false" if param == 'load_order' else ""
                    self.params[param] = self._convert_value(default_value, param_type)
                    continue
                raise ConfigError(f"Отсутствует обязательный параметр: {param}")
            
            raw_value = self.config.get(self.CONFIG_SECTION, param).strip()
            try:
                self.params[param] = self._convert_value(raw_value, param_type)
            except ValueError as e:
                raise ConfigError(f"Некорректное значение для '{param}': {str(e)}")
        
        # Валидация режима репозитория
        mode = self.params['repository_mode'].lower()
        if mode not in self.VALID_REPO_MODES:
            raise ConfigError(
                f"Некорректный режим репозитория: {mode}. "
                f"Допустимые значения: {', '.join(self.VALID_REPO_MODES)}"
            )
        
        # Загрузка тестового графа для режима 'test'
        if mode == 'test':
            self._load_test_graph()
        
        # Валидация для этапа 5
        if self.params['output_image'].lower().endswith('.png'):
            jar_path = self.params['plantuml_jar']
            if not jar_path:
                raise ConfigError("Для генерации PNG требуется указать путь к plantuml.jar")
            if not os.path.exists(jar_path):
                raise ConfigError(f"Файл plantuml.jar не найден по пути: {jar_path}\n"
                                 f"Скачайте его с: {self.PLANTUML_URL}")

    def _load_test_graph(self):
        """Загружает тестовый граф из файла"""
        test_file = self.params['repository_path']
        if not os.path.exists(test_file):
            raise ConfigError(f"Тестовый файл '{test_file}' не найден")
        
        try:
            with open(test_file, 'r', encoding='utf-8') as f:
                self.test_graph = json.load(f)
        except json.JSONDecodeError as e:
            raise ConfigError(f"Ошибка разбора JSON в тестовом файле: {str(e)}")
        except Exception as e:
            raise ConfigError(f"Ошибка загрузки тестового файла: {str(e)}")
        
        # Валидация структуры тестового графа
        if not isinstance(self.test_graph, dict):
            raise ConfigError("Тестовый файл должен содержать JSON-объект")
        
        for package, deps in self.test_graph.items():
            if not package.isupper() or not package.isalpha():
                raise ConfigError(f"Некорректное имя пакета в тестовом режиме: '{package}'. "
                                  "Должны быть большие латинские буквы")
            if not isinstance(deps, list):
                raise ConfigError(f"Зависимости для '{package}' должны быть списком")
            for dep in deps:
                if not dep.isupper() or not dep.isalpha():
                    raise ConfigError(f"Некорректная зависимость '{dep}' для пакета '{package}'. "
                                      "Должны быть большие латинские буквы")

    def _convert_value(self, value: str, target_type):
        """Преобразует строковое значение к целевому типу"""
        if target_type is bool:
            if value.lower() in ('true', '1', 'yes', 'on'):
                return True
            if value.lower() in ('false', '0', 'no', 'off'):
                return False
            raise ValueError("ожидалось булево значение (true/false)")
        return target_type(value) if value else target_type()

    def print_config(self):
        """Выводит параметры конфигурации"""
        print("Текущие параметры конфигурации:")
        print("-" * 40)
        for param, value in self.params.items():
            if param == 'plantuml_jar' and value:
                value = os.path.basename(value)
            print(f"{param.replace('_', ' ').title()}: {value}")
        if self.params['repository_mode'].lower() == 'test' and self.test_graph:
            print("\nТестовый граф:")
            for pkg, deps in self.test_graph.items():
                print(f"  {pkg} -> {', '.join(deps) if deps else '(нет зависимостей)'}")
        print("-" * 40)

    def fetch_package_data(self, package_name: str) -> dict:
        """
        Получает метаданные пакета в зависимости от режима репозитория
        """
        mode = self.params['repository_mode'].lower()
        repo_path = self.params['repository_path']
        
        # Для тестового режима генерируем искусственные данные
        if mode == 'test':
            if package_name not in self.test_graph:
                raise PackageFetchError(f"Пакет '{package_name}' отсутствует в тестовом графе")
            dependencies = {dep: "1.0.0" for dep in self.test_graph[package_name]}
            return {
                "dist-tags": {"latest": "1.0.0"},
                "versions": {
                    "1.0.0": {
                        "dependencies": dependencies
                    }
                }
            }
        
        try:
            if mode == 'online':
                base_url = repo_path if repo_path else self.NPM_REGISTRY_URL
                url = urljoin(base_url.rstrip('/') + '/', package_name)
                print(f"Запрос данных для пакета '{package_name}' из {url}...")
                with urllib.request.urlopen(url, timeout=10) as response:
                    if response.status != 200:
                        raise PackageFetchError(f"Пакет не найден (HTTP {response.status})")
                    return json.loads(response.read().decode('utf-8'))
            
            elif mode == 'offline':
                file_path = os.path.join(repo_path, f"{package_name}.json")
                print(f"Чтение данных для пакета '{package_name}' из {file_path}...")
                if not os.path.exists(file_path):
                    raise PackageFetchError(f"Файл метаданных не найден: {file_path}")
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        
        except (URLError, HTTPError) as e:
            raise PackageFetchError(f"Ошибка сети: {str(e)}")
        except json.JSONDecodeError as e:
            raise PackageFetchError(f"Ошибка разбора JSON: {str(e)}")
        except Exception as e:
            raise PackageFetchError(f"Неизвестная ошибка: {str(e)}")

    def get_direct_dependencies(self, package_name: str) -> dict:
        """
        Извлекает прямые зависимости для последней версии пакета
        """
        package_data = self.fetch_package_data(package_name)
        
        # Получаем последнюю версию из dist-tags
        dist_tags = package_data.get('dist-tags', {})
        if not dist_tags or 'latest' not in dist_tags:
            raise PackageFetchError(f"Не найдена информация о последней версии для '{package_name}'")
        
        latest_version = dist_tags['latest']
        versions = package_data.get('versions', {})
        
        if latest_version not in versions:
            raise PackageFetchError(
                f"Версия '{latest_version}' не найдена в данных пакета '{package_name}'"
            )
        
        version_data = versions[latest_version]
        return version_data.get('dependencies', {})

    def build_dependency_graph(self, start_package: str):
        """
        Строит граф зависимостей с использованием рекурсивного BFS
        Возвращает: (граф, циклы)
        Граф: {пакет: [зависимости]}
        Циклы: список кортежей (начальный_пакет, зависимость) для циклических связей
        """
        visited = set()
        graph = {}
        cycles = []
        level_queue = deque([start_package])

        def bfs_recursive(current_level):
            """Рекурсивная реализация BFS по уровням"""
            if not current_level:
                return
            
            next_level = deque()
            
            for package in current_level:
                if package in visited:
                    continue
                
                visited.add(package)
                try:
                    deps_dict = self.get_direct_dependencies(package)
                    dependencies = list(deps_dict.keys())
                except PackageFetchError as e:
                    print(f"Предупреждение: не удалось загрузить зависимости для {package}: {e}", file=sys.stderr)
                    dependencies = []
                
                graph[package] = dependencies
                
                # Обработка зависимостей и обнаружение циклов
                for dep in dependencies:
                    if dep in visited:
                        cycles.append((package, dep))
                    elif dep not in next_level and dep not in current_level:
                        next_level.append(dep)
            
            bfs_recursive(next_level)
        
        bfs_recursive(level_queue)
        self.dependency_graph = graph
        self.cycles = cycles
        return graph, cycles

    def topological_sort(self):
        """
        Выполняет топологическую сортировку графа (алгоритм Кана)
        Возвращает порядок загрузки зависимостей
        """
        graph = self.dependency_graph.copy()
        in_degree = defaultdict(int)
        
        # Инициализация степеней захода
        for node in graph:
            in_degree[node] = 0
        
        for deps in graph.values():
            for dep in deps:
                in_degree[dep] += 1
        
        # Очередь узлов со степенью захода 0
        queue = deque([node for node, degree in in_degree.items() if degree == 0])
        order = []
        visited = set()
        
        while queue:
            node = queue.popleft()
            order.append(node)
            visited.add(node)
            
            for neighbor in graph.get(node, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
        
        # Проверка на циклы
        if len(order) != len(in_degree):
            remaining = set(in_degree.keys()) - visited
            print("\nПредупреждение: обнаружены циклы, топологическая сортировка неполная", file=sys.stderr)
            print(f"Узлы в циклах: {', '.join(remaining)}", file=sys.stderr)
        
        return order

    def generate_plantuml_code(self):
        """
        Генерирует PlantUML-код для визуализации графа зависимостей
        """
        plantuml = ["@startuml"]
        plantuml.append("skinparam backgroundColor #EEEBDC")
        plantuml.append("skinparam shadowing false")
        plantuml.append("skinparam ArrowColor #333333")
        plantuml.append("skinparam NodeColor #F0F0F0")
        plantuml.append("skinparam NodeBorderColor #888888")
        plantuml.append("skinparam NodeFontSize 14")
        
        # Добавление узлов
        for node in self.dependency_graph.keys():
            plantuml.append(f"node \"{node}\" as {node}")
        
        # Добавление ребер с выделением циклов
        cycle_edges = set(self.cycles)
        for node, deps in self.dependency_graph.items():
            for dep in deps:
                edge_style = " [color=red, style=bold]" if (node, dep) in cycle_edges else ""
                plantuml.append(f"{node} --> {dep}{edge_style}")
        
        # Добавление пометки для циклов
        if self.cycles:
            plantuml.append("\nlegend top")
            plantuml.append("  <b>Циклические зависимости:</b>")
            for src, dst in self.cycles:
                plantuml.append(f"  {src} --> {dst}")
            plantuml.append("endlegend")
        
        plantuml.append("@enduml")
        return "\n".join(plantuml)

    def generate_png_from_plantuml(self, puml_content):
        """
        Генерирует PNG-изображение из PlantUML-кода
        """
        output_path = self.params['output_image']
        puml_path = os.path.splitext(output_path)[0] + ".puml"
        
        # Сохраняем PlantUML-код в файл
        with open(puml_path, 'w', encoding='utf-8') as f:
            f.write(puml_content)
        
        jar_path = self.params['plantuml_jar']
        try:
            # Определяем путь к java
            java_cmd = "java"
            if platform.system() == "Windows":
                java_cmd = "java.exe"
            
            # Выполняем команду PlantUML
            result = subprocess.run(
                [java_cmd, "-jar", jar_path, puml_path, "-tpng", "-o", os.path.dirname(os.path.abspath(output_path))],
                capture_output=True,
                text=True,
                check=True
            )
            
            print(f"\nИзображение успешно сохранено: {output_path}")
            print(f"PlantUML-код сохранен: {puml_path}")
            
            # Удаляем .puml файл если не нужен
            if not self.params['ascii_tree']:
                os.remove(puml_path)
                
            return True
        except subprocess.CalledProcessError as e:
            print(f"Ошибка генерации PNG: {e.stderr}", file=sys.stderr)
            return False
        except FileNotFoundError:
            print(f"Java не найдена. Убедитесь, что Java установлена и добавлена в PATH", file=sys.stderr)
            return False
        except Exception as e:
            print(f"Неизвестная ошибка при генерации PNG: {str(e)}", file=sys.stderr)
            return False

    def print_dependency_tree(self, graph: dict, start_package: str):
        """Выводит дерево зависимостей в формате ASCII"""
        print(f"\nДерево зависимостей для '{start_package}':")
        
        def print_node(package, prefix="", is_last=True, visited=None):
            if visited is None:
                visited = set()
            
            if package in visited:
                connector = "└── " if is_last else "├── "
                print(f"{prefix}{connector}{package} [цикл]")
                return
            
            visited.add(package)
            connector = "└── " if is_last else "├── "
            print(f"{prefix}{connector}{package}")
            
            new_prefix = prefix + ("    " if is_last else "│   ")
            deps = graph.get(package, [])
            
            for i, dep in enumerate(deps):
                is_last_dep = (i == len(deps) - 1)
                print_node(dep, new_prefix, is_last_dep, visited.copy())
        
        print_node(start_package)

    def print_load_order(self):
        """Выводит порядок загрузки зависимостей (этап 4)"""
        order = self.topological_sort()
        print("\nПорядок загрузки зависимостей (топологическая сортировка):")
        print("-" * 40)
        for i, package in enumerate(order, 1):
            print(f"{i}. {package}")
        print("-" * 40)
        
        # Сравнение с npm
        print("\nСравнение с npm:")
        print("npm использует алгоритм, учитывающий версионные конфликты и оптимизацию node_modules")
        print("Возможные расхождения:")
        print("1. npm может устанавливать пакеты параллельно, тогда как наш алгоритм последователен")
        print("2. npm разрешает версионные конфликты через 'deduping' и 'hoisting'")
        print("3. npm учитывает peerDependencies, которые не включены в наш анализ")
        print("4. npm может пропускать установку зависимостей, уже существующих в вышестоящих уровнях")

    def run(self):
        """Основной метод запуска приложения"""
        try:
            self.load_config()
            self.print_config()
            
            # Этап 3: Построение графа зависимостей
            start_package = self.params['package_name']
            self.build_dependency_graph(start_package)
            
            # Вывод результатов построения графа
            print("\nПостроенный граф зависимостей:")
            print("-" * 40)
            for package, deps in self.dependency_graph.items():
                print(f"{package} -> {', '.join(deps) if deps else '(нет зависимостей)'}")
            print("-" * 40)
            
            if self.cycles:
                print("\nОбнаружены циклические зависимости:")
                for src, dst in self.cycles:
                    print(f"  {src} -> {dst} (цикл)")
            else:
                print("\nЦиклические зависимости не обнаружены.")
            
            # Этап 4: Порядок загрузки (если включен)
            if self.params['load_order']:
                self.print_load_order()
            
            # Этап 5: Визуализация
            if self.params['output_image']:
                puml_code = self.generate_plantuml_code()
                self.generate_png_from_plantuml(puml_code)
            
            # Вывод ASCII-дерева, если требуется
            if self.params['ascii_tree']:
                self.print_dependency_tree(self.dependency_graph, start_package)
            
            return 0
            
        except ConfigError as e:
            print(f"ОШИБКА КОНФИГУРАЦИИ: {e}", file=sys.stderr)
            print("\nПример корректного config.ini:", file=sys.stderr)
            print(self._get_config_example(), file=sys.stderr)
            return 1
        
        except PackageFetchError as e:
            print(f"ОШИБКА ЗАГРУЗКИ ДАННЫХ: {e}", file=sys.stderr)
            return 1
        
        except Exception as e:
            print(f"НЕОБРАБОТАННАЯ ОШИБКА: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc(file=sys.stderr)
            return 1

    def _get_config_example(self):
        """Возвращает пример корректного конфига"""
        online_example = f"""
[{self.CONFIG_SECTION}]
package_name = express
repository_path = {self.NPM_REGISTRY_URL}
repository_mode = online
output_image = graph.png
ascii_tree = true
load_order = true
plantuml_jar = ./plantuml.jar
        """.strip()
        
        test_example = f"""
[{self.CONFIG_SECTION}]
package_name = A
repository_path = ./test_graph.json
repository_mode = test
output_image = test_graph.png
ascii_tree = true
load_order = true
plantuml_jar = ./plantuml.jar
        """.strip()
        
        return (
            f"Режим ONLINE:\n{online_example}\n\n"
            f"Режим TEST (пример файла ./test_graph.json):\n"
            "{\n"
            '  "A": ["B", "C"],\n'
            '  "B": ["D"],\n'
            '  "C": ["D"],\n'
            '  "D": []\n'
            "}\n\n"
            f"Конфигурация для режима TEST:\n{test_example}\n\n"
            "Для генерации PNG требуется plantuml.jar:\n"
            "Скачайте его с https://sourceforge.net/projects/plantuml/files/plantuml.jar/download"
        )

if __name__ == "__main__":
    app = DependencyVisualizer()
    sys.exit(app.run())