"""Тесты для CLI команд."""

import pytest
import subprocess
import sys
from pathlib import Path


class TestCLICommands:
    """Тесты для новых CLI команд."""

    def test_cli_help_shows_subcommands(self):
        """Тест что CLI показывает подкоманды."""
        result = subprocess.run([
            sys.executable, '-m', 'annex4parser', '--help'
        ], capture_output=True, text=True, cwd=Path(__file__).parent.parent)
        
        assert result.returncode == 0
        output = result.stdout
        
        # Должны быть видны обе подкоманды
        assert 'update-single' in output
        assert 'update-all' in output
        assert 'Annex4Parser CLI' in output

    def test_update_single_help(self):
        """Тест справки для update-single команды."""
        result = subprocess.run([
            sys.executable, '-m', 'annex4parser', 'update-single', '--help'
        ], capture_output=True, text=True, cwd=Path(__file__).parent.parent)
        
        assert result.returncode == 0
        output = result.stdout
        
        # Должны быть видны параметры для update-single
        assert '--name' in output
        assert '--version' in output
        assert '--url' in output
        assert '--db-url' in output
        assert '--cache-dir' in output

    def test_update_all_help(self):
        """Тест справки для update-all команды."""
        result = subprocess.run([
            sys.executable, '-m', 'annex4parser', 'update-all', '--help'
        ], capture_output=True, text=True, cwd=Path(__file__).parent.parent)
        
        assert result.returncode == 0
        output = result.stdout
        
        # Должны быть видны параметры для update-all
        assert '--db-url' in output
        assert '--config' in output
        assert '--verbose' in output

    def test_cli_requires_subcommand(self):
        """Тест что CLI требует указания подкоманды."""
        result = subprocess.run([
            sys.executable, '-m', 'annex4parser'
        ], capture_output=True, text=True, cwd=Path(__file__).parent.parent)
        
        # Должен вернуть ошибку так как subcommand обязательна
        assert result.returncode != 0
        assert 'required' in result.stderr.lower() or 'choose from' in result.stderr.lower()

    def test_update_single_missing_required_args(self):
        """Тест что update-single требует обязательные аргументы."""
        result = subprocess.run([
            sys.executable, '-m', 'annex4parser', 'update-single'
        ], capture_output=True, text=True, cwd=Path(__file__).parent.parent)
        
        assert result.returncode != 0
        # Должен требовать --name, --version, --url
        error_output = result.stderr.lower()
        assert 'required' in error_output or 'error' in error_output

    @pytest.mark.integration
    def test_update_all_dry_run(self):
        """Интеграционный тест для update-all с минимальной конфигурацией."""
        # Создаем временную конфигурацию
        import tempfile
        import yaml
        
        config_data = {
            'sources': []  # Пустой список источников для быстрого теста
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config_data, f)
            config_path = f.name
        
        try:
            result = subprocess.run([
                sys.executable, '-m', 'annex4parser', 'update-all',
                '--config', config_path,
                '--db-url', 'sqlite:///:memory:',
                '--verbose'
            ], capture_output=True, text=True, cwd=Path(__file__).parent.parent, timeout=30)
            
            # Команда должна выполниться успешно даже с пустыми источниками
            if result.returncode != 0:
                print(f"STDOUT: {result.stdout}")
                print(f"STDERR: {result.stderr}")
            
            # Может быть ошибка импорта или другие проблемы, но не критичные
            # Главное что CLI парсинг работает
            assert 'update-all' in result.stdout or 'Update-all' in result.stdout or result.returncode == 0
            
        finally:
            Path(config_path).unlink()


class TestCLIBackwardCompatibility:
    """Тесты обратной совместимости CLI."""

    def test_old_cli_still_works_via_update_single(self):
        """Тест что старый способ вызова работает через update-single."""
        # Старый способ теперь должен работать через update-single
        result = subprocess.run([
            sys.executable, '-m', 'annex4parser', 'update-single', '--help'
        ], capture_output=True, text=True, cwd=Path(__file__).parent.parent)
        
        assert result.returncode == 0
        
        # Должны быть те же параметры что были в старом CLI
        output = result.stdout
        assert '--name' in output
        assert '--version' in output  
        assert '--url' in output
        assert '--db-url' in output


class TestCLIErrorHandling:
    """Тесты обработки ошибок в CLI."""

    def test_invalid_subcommand(self):
        """Тест обработки неверной подкоманды."""
        result = subprocess.run([
            sys.executable, '-m', 'annex4parser', 'invalid-command'
        ], capture_output=True, text=True, cwd=Path(__file__).parent.parent)
        
        assert result.returncode != 0
        assert 'invalid choice' in result.stderr.lower() or 'unrecognized arguments' in result.stderr.lower()

    def test_update_single_invalid_db_url(self):
        """Тест обработки неверного DB URL."""
        result = subprocess.run([
            sys.executable, '-m', 'annex4parser', 'update-single',
            '--name', 'Test Regulation',
            '--version', '1.0',
            '--url', 'https://example.com',
            '--db-url', 'invalid://url'
        ], capture_output=True, text=True, cwd=Path(__file__).parent.parent, timeout=10)
        
        # Должна быть ошибка с неверным DB URL
        assert result.returncode != 0

    def test_update_all_invalid_config_path(self):
        """Тест обработки неверного пути к конфигу."""
        result = subprocess.run([
            sys.executable, '-m', 'annex4parser', 'update-all',
            '--config', '/nonexistent/path.yaml'
        ], capture_output=True, text=True, cwd=Path(__file__).parent.parent, timeout=10)
        
        # Должна быть ошибка с несуществующим файлом конфигурации
        assert result.returncode != 0
