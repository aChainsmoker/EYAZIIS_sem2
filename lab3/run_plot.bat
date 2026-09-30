@echo off
cd /d "%~dp0"
python -m tests.plot tests/results/benchmark_results.csv --output-dir tests/results