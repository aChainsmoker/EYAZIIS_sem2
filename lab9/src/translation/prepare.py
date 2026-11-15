"""Подготовка двух моделей выполняется при явном запуске модуля."""

from src.translation.service import SUPPORTED_DIRECTIONS


def main():
    import argostranslate.package
    installed = {
        (package.from_code, package.to_code)
        for package in argostranslate.package.get_installed_packages()
    }
    missing = [pair for pair in SUPPORTED_DIRECTIONS if pair not in installed]
    if not missing:
        print("Модели Argos EN→RU и RU→EN уже установлены.")
        return
    argostranslate.package.update_package_index()
    available = argostranslate.package.get_available_packages()
    for source, target in missing:
        package = next((item for item in available
                        if item.from_code == source and item.to_code == target), None)
        if package is None:
            raise RuntimeError(f"В индексе Argos отсутствует модель {source}→{target}.")
        argostranslate.package.install_from_path(package.download())
        print(f"Модель Argos {source.upper()}→{target.upper()} установлена.")


if __name__ == "__main__":
    main()
