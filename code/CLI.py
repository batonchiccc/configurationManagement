import configparser
import os
import sys

class ConfigError(Exception):
    """Базовый класс для ошибок конфигурации"""
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

    def run(self):
        """Основной метод запуска приложения"""
        try:
            self.load_config()
            self.print_config()
            return 0
        except ConfigError as e:
            print(f"ОШИБКА КОНФИГУРАЦИИ: {e}", file=sys.stderr)
            print("\nПример корректного config.ini:", file=sys.stderr)
            print(self._get_config_example(), file=sys.stderr)
            return 1

    def _get_config_example(self):
        """Возвращает пример корректного конфига"""
        return f"""
[{self.CONFIG_SECTION}]
package_name = example-package
repository_path = https://repo.example.com
repository_mode = online
output_image = dependency_graph.png
ascii_tree = true
        """.strip()

if __name__ == "__main__":
    app = DependencyVisualizer()
    sys.exit(app.run())