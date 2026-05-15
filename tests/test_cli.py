"""Tests for CLI commands."""

from unittest.mock import patch

from click.testing import CliRunner

from gitlab_repo_audit.cli import cli


def test_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "index" in result.output
    assert "report" in result.output


def test_index_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["index", "--help"])
    assert result.exit_code == 0
    assert "GROUP_PATH" in result.output


def test_report_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["report", "--help"])
    assert result.exit_code == 0
    assert "--output" in result.output or "-o" in result.output


def test_report_no_db(tmp_path):
    runner = CliRunner()
    result = runner.invoke(cli, ["report", "--db", str(tmp_path / "nonexistent.db")])
    assert result.exit_code != 0
    assert "not found" in result.output.lower() or "Database" in result.output


def test_index_no_token():
    runner = CliRunner()
    with patch.dict("os.environ", {}, clear=True):
        result = runner.invoke(cli, ["index", "some/group", "--token", ""])
    assert result.exit_code != 0
