import configparser
import os
import sys
import json
import urllib.request
from urllib.error import URLError, HTTPError
from urllib.parse import urljoin

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
        'ascii_tree': bool
    }
    CONFIG_FILE = 'config.ini'
    CONFIG_SECTION = 'settings'
    VALID_REPO_MODES = {'online', 'offline'}
    NPM_REGISTRY_URL = 'https://registry.npmjs.org/'

    def __init__(self):
        self.config = configparser.ConfigParser()
        self.params = {}

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
        
        for param, param_type in self.REQUIRED_PARAMS.items():
            if not self.config.has_option(self.CONFIG_SECTION, param):
                raise ConfigError(f"Отсутствует обязательный параметр: {param}")
            
            raw_value = self.config.get(self.CONFIG_SECTION, param).strip()
            try:
                self.params[param] = self._convert_value(raw_value, param_type)
            except ValueError as e:
                raise ConfigError(f"Некорректное значение для '{param}': {str(e)}")
        
        # Валидация режима репозитория
        if self.params['repository_mode'].lower() not in self.VALID_REPO_MODES:
            raise ConfigError(
                f"Некорректный режим репозитория: {self.params['repository_mode']}. "
                f"Допустимые значения: {', '.join(self.VALID_REPO_MODES)}"
            )

    def _convert_value(self, value: str, target_type):
        """Преобразует строковое значение к целевому типу"""
        if target_type is bool:
            if value.lower() in ('true', '1', 'yes', 'on'):
                return True
            if value.lower() in ('false', '0', 'no', 'off'):
                return False
            raise ValueError("ожидалось булево значение (true/false)")
        return target_type(value)

    def print_config(self):
        """Выводит параметры конфигурации"""
        print("Текущие параметры конфигурации:")
        print("-" * 40)
        for param, value in self.params.items():
            print(f"{param.replace('_', ' ').title()}: {value}")
        print("-" * 40)

    def fetch_package_data(self, package_name: str) -> dict:
        """
        Получает метаданные пакета в зависимости от режима репозитория
        
        :param package_name: Имя пакета
        :return: Словарь с данными пакета
        :raises PackageFetchError: При ошибках получения данных
        """
        mode = self.params['repository_mode'].lower()
        repo_path = self.params['repository_path']
        
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
        
        :param package_name: Имя анализируемого пакета
        :return: Словарь {имя_зависимости: версия}
        :raises PackageFetchError: При ошибках получения или обработки данных
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

    def run(self):
        """Основной метод запуска приложения"""
        try:
            self.load_config()
            self.print_config()
            
            # Этап 2: Сбор данных о зависимостях
            package_name = self.params['package_name']
            dependencies = self.get_direct_dependencies(package_name)
            
            print(f"\nПрямые зависимости пакета '{package_name}':")
            if dependencies:
                for dep_name, dep_version in dependencies.items():
                    print(f"  ├─ {dep_name}@{dep_version}")
                print("  └─ (конец списка)")
            else:
                print("  (Нет прямых зависимостей)")
            
            return 0
            
        except ConfigError as e:
            print(f"ОШИБКА КОНФИГУРАЦИИ: {e}", file=sys.stderr)
            print("\nПример корректного config.ini:", file=sys.stderr)
            print(self._get_config_example(), file=sys.stderr)
            return 1
        
        except PackageFetchError as e:
            print(f"ОШИБКА ЗАГРУЗКИ ДАННЫХ: {e}", file=sys.stderr)
            if self.params.get('repository_mode', '').lower() == 'offline':
                print("\nПодсказка для offline-режима:", file=sys.stderr)
                print("Убедитесь, что в директории репозитория есть файлы вида '<пакет>.json'", file=sys.stderr)
                print("Пример содержимого файла: ", file=sys.stderr)
                print("{", file=sys.stderr)
                print('  "dist-tags": {"latest": "1.0.0"},', file=sys.stderr)
                print('  "versions": {', file=sys.stderr)
                print('    "1.0.0": {', file=sys.stderr)
                print('      "dependencies": {', file=sys.stderr)
                print('        "lodash": "^4.17.21"', file=sys.stderr)
                print('      }', file=sys.stderr)
                print('    }', file=sys.stderr)
                print('  }', file=sys.stderr)
                print("}", file=sys.stderr)
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
package_name = lodash
repository_path = {self.NPM_REGISTRY_URL}
repository_mode = online
output_image = graph.png
ascii_tree = true
        """.strip()
        
        offline_example = f"""
[{self.CONFIG_SECTION}]
package_name = my-package
repository_path = ./local-repo
repository_mode = offline
output_image = deps.png
ascii_tree = false
        """.strip()
        
        return f"Режим ONLINE:\n{online_example}\n\nРежим OFFLINE:\n{offline_example}"

if __name__ == "__main__":
    app = DependencyVisualizer()
    sys.exit(app.run())