from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def _read_results(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as results_file:
        return list(csv.DictReader(results_file))


def create_plots(results_path: str | Path, output_dir: str | Path) -> tuple[Path, Path]:
    results_path = Path(results_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = _read_results(results_path)
    if not rows:
        raise ValueError("The results file does not contain any measurements")

    tokens = [int(row["token_count"]) for row in rows]
    durations = [float(row["total_seconds"]) for row in rows]
    cumulative_tokens = [int(row["cumulative_token_count"]) for row in rows]
    cumulative = [float(row["cumulative_seconds"]) for row in rows]
    labels = [row["file_name"] for row in rows]

    points = sorted(zip(tokens, durations, labels))
    sorted_tokens, sorted_durations, sorted_labels = zip(*points)
    token_plot = output_dir / "time_vs_tokens.png"
    plt.figure(figsize=(11, 7))
    plt.scatter(sorted_tokens, sorted_durations, color="steelblue", s=70)
    plt.plot(sorted_tokens, sorted_durations, color="steelblue", alpha=0.45)
    for token_count, duration, label in points:
        plt.annotate(
            f"{label}\n{duration:.2f} с",
            (token_count, duration),
            textcoords="offset points",
            xytext=(0, 9),
            ha="center",
            fontsize=8,
        )
    plt.title("Зависимость времени обработки от количества токенов")
    plt.xlabel("Количество токенов")
    plt.ylabel("Время обработки одного файла (с)")
    plt.grid(True, alpha=0.3, linestyle="--")
    plt.tight_layout()
    plt.savefig(token_plot, dpi=160)
    plt.close()

    cumulative_plot = output_dir / "cumulative_processing_time.png"
    plt.figure(figsize=(11, 7))
    plt.plot(cumulative_tokens, cumulative, marker="o", color="darkorange", linewidth=2)
    for token_count, total, label in zip(cumulative_tokens, cumulative, labels):
        plt.annotate(
            f"{label}\n{total:.2f} с",
            (token_count, total),
            textcoords="offset points",
            xytext=(0, 9),
            ha="center",
            fontsize=8,
        )
    plt.title("Зависимость накопленного времени от общего количества токенов")
    plt.xlabel("Общее количество токенов обработанных файлов")
    plt.ylabel("Накопленное время (с)")
    plt.ticklabel_format(style="plain", axis="x")
    plt.grid(True, alpha=0.3, linestyle="--")
    plt.tight_layout()
    plt.savefig(cumulative_plot, dpi=160)
    plt.close()

    return token_plot, cumulative_plot


def main() -> None:
    parser = argparse.ArgumentParser(description="Build performance charts from benchmark CSV")
    parser.add_argument("results", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("tests/results"))
    args = parser.parse_args()
    create_plots(args.results, args.output_dir)


if __name__ == "__main__":
    main()
