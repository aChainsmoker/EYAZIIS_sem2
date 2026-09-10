import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import io
import base64


def plot_11point_pr(pr_curves: dict[int, list[tuple[float, float]]]) -> str:
    fig, ax = plt.subplots(figsize=(8, 6))
    for k, curve in sorted(pr_curves.items()):
        recalls = [p[0] for p in curve]
        precisions = [p[1] for p in curve]
        ax.plot(recalls, precisions, marker="o", label=f"Top-{k}")
    ax.set_xlabel("Recall")
    ax.set_ylabel("Precision")
    ax.set_title("Precision-Recall Curve")
    ax.set_xticks([i / 10.0 for i in range(11)])
    ax.set_yticks([i / 10.0 for i in range(11)])
    ax.grid(True, alpha=0.3)
    ax.legend()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")


def plot_precision_recall_at_k(avg_metrics: dict) -> str:
    k_values = sorted(avg_metrics["precision"].keys())
    precisions = [avg_metrics["precision"][k] for k in k_values]
    recalls = [avg_metrics["recall"][k] for k in k_values]

    fig, ax = plt.subplots(figsize=(8, 5))
    x = range(len(k_values))
    width = 0.35
    bars1 = ax.bar([i - width / 2 for i in x], precisions, width, label="Precision@k", color="#4C72B0")
    bars2 = ax.bar([i + width / 2 for i in x], recalls, width, label="Recall@k", color="#DD8452")
    ax.set_xlabel("k")
    ax.set_ylabel("Score")
    ax.set_title("Precision@k and Recall@k")
    ax.set_xticks(list(x))
    ax.set_xticklabels([str(k) for k in k_values])
    ax.legend()
    ax.set_ylim(0, 1.1)
    ax.grid(True, alpha=0.3, axis="y")
    for bar in bars1:
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.02, f"{bar.get_height():.2f}", ha="center", va="bottom", fontsize=8)
    for bar in bars2:
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.02, f"{bar.get_height():.2f}", ha="center", va="bottom", fontsize=8)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")
