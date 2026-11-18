"""Four still images for the README and for sharing, one per step of the argument.

Each title states the finding, so the image still makes sense when it is seen on its own.
The interactive versions, with sources, are on the site.
"""
from __future__ import annotations

import textwrap

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

import edgar
import make_front

OUT = edgar.ROOT / "charts"
TICKERS = ["MSFT", "GOOGL", "AMZN", "META", "ORCL", "CRWV"]
COLORS = dict(zip(TICKERS, ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"]))
INK, INK2, MUTED, GRID, BG, ACCENT, REST = "#15181e", "#454953", "#767983", "#d8d1c0", "#f6f2e9", "#a8321f", "#d5cebd"
SERIF = ["Newsreader", "Georgia", "Iowan Old Style", "DejaVu Serif"]
SANS = ["IBM Plex Sans", "Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"]
SOURCE = "Source: company filings with the SEC. Abhay Kumar, The AI Promise Ledger."

plt.rcParams.update({
    "font.family": SANS, "font.size": 11, "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "figure.facecolor": BG, "axes.facecolor": BG, "savefig.facecolor": BG,
})


def _frame(title: str, subtitle: str, height: float = 5.6, left: float = 0.07):
    """A chart with a headline that states the finding (wrapped to at most two lines), a subtitle and a source line."""
    title, subtitle = textwrap.fill(title, 62), textwrap.fill(subtitle, 112)
    head = 0.42 + 0.36 * (title.count("\n") + 1) + 0.24 * (subtitle.count("\n") + 1) + 0.3  # inches used above the plot
    height += head - 1.32
    fig, ax = plt.subplots(figsize=(10, height), dpi=200)
    fig.subplots_adjust(left=left, right=0.95, top=1 - head / height, bottom=0.95 / height)
    fig.text(0.05, 1 - 0.36 / height, title, ha="left", va="top", fontfamily=SERIF, fontsize=17, color=INK, linespacing=1.15)
    fig.text(0.05, 1 - (0.42 + 0.36 * (title.count("\n") + 1)) / height, subtitle, ha="left", va="top", fontsize=10.5, color=INK2, linespacing=1.3)
    fig.text(0.05, 0.22 / height, SOURCE, ha="left", va="bottom", fontsize=8.5, color=MUTED)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.tick_params(length=0)
    ax.set_axisbelow(True)
    return fig, ax


def cash_gap(a: dict) -> None:
    labels = ["FY2019", "FY2020", "FY2021", "FY2022", "FY2023", "FY2024", "FY2025", "Latest 12m"]
    su = a["sources_uses"]
    share = sum(r["capex"] for r in su) / sum(r["cfo"] for r in su)
    fig, ax = _frame(f"Six AI spenders now put {share * 100:.0f} cents of every dollar of cash they generate into buildings and equipment",
                     "Capital spending as a share of cash from operations. Above the dashed line a company spends more than it generates.")
    for t in TICKERS:
        if t == "CRWV":
            continue  # off the scale
        h = {p["period"]: p["share"] for p in a["funding"]["history"][t]}
        ys = [h.get(l) for l in labels[:-1]] + [h.get("TTM")]
        pts = [(i, y * 100) for i, y in enumerate(ys) if y is not None]
        ax.plot([p[0] for p in pts], [p[1] for p in pts], color=COLORS[t], linewidth=2)
        ax.scatter([pts[-1][0]], [pts[-1][1]], color=COLORS[t], s=34, zorder=3, edgecolor=BG, linewidth=1.5)
        ax.text(pts[-1][0] + 0.12, pts[-1][1], f"{a['names'][t]} {pts[-1][1]:.0f}%", va="center", fontsize=9.5, color=INK)
    ax.axhline(100, color=MUTED, linewidth=1, linestyle=(0, (4, 3)))
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels([l.replace("FY20", "FY") for l in labels])
    ax.set_xlim(-0.2, len(labels) + 0.35)
    ax.set_ylim(0, 180)
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    fig.savefig(OUT / "1_cash_gap.png")
    plt.close(fig)


def leverage(a: dict) -> None:
    rows = sorted(a["leverage"], key=lambda r: r["pro_forma"])
    hot = sorted((r for r in rows if r["pro_forma"] >= 4), key=lambda r: -r["ebitda"])
    fig, ax = _frame(f"Count the signed leases as debt and {' and '.join(a['names'][r['ticker']] for r in hot)} stand apart",
                     "Borrowings plus leases, in years of cash earnings. Hollow: today. Solid: with leases signed but not yet started. Earnings held at today's level.", 5.0, 0.15)
    for i, r in enumerate(rows):
        c = ACCENT if r["pro_forma"] >= 4 else INK2
        ax.plot([r["today"], r["pro_forma"]], [i, i], color=c, linewidth=3, alpha=0.35, solid_capstyle="round")
        ax.scatter([r["today"]], [i], s=70, facecolor=BG, edgecolor=c, linewidth=2, zorder=3)
        ax.scatter([r["pro_forma"]], [i], s=90, color=c, zorder=3)
        ax.text(r["pro_forma"] + 0.45, i, f"{r['today']:.1f}× → {r['pro_forma']:.1f}×", va="center", fontsize=10.5, color=INK, weight="bold" if r["pro_forma"] >= 4 else "normal")
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([a["names"][r["ticker"]] for r in rows], fontsize=11, color=INK)
    ax.set_xlim(0, max(r["pro_forma"] for r in rows) + 4)
    ax.set_ylim(-0.6, len(rows) - 0.4)
    ax.set_xticks(range(0, int(max(r["pro_forma"] for r in rows)) + 5, 5))
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0f}×")
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    fig.savefig(OUT / "2_who_can_carry_it.png")
    plt.close(fig)


def then_and_now(a: dict) -> None:
    n = a["nvidia"]
    last = n["financing"][-1]
    rev = last["revenue_annualized"]
    rows = [("NVIDIA, 2026", last["narrow"] / rev, last["guarantees_other"] / rev, True, False)]
    rows += [(c["company"].split(" ")[0], c["high_promised"], c["peak_in_force_ratio"], False, not c["high_promised_complete"]) for c in n["history"]]
    rows.sort(key=lambda r: r[1])
    fig, ax = _frame("NVIDIA has promised its customers about as much as the telecom makers once did. Far less is in force.",
                     "Share of annual sales. Pale: financing promised to customers. Solid: actually lent, or guarantees in force. "
                     "Telecom makers: the highest each reached, 1997 to 2003.", 5.2, 0.16)
    for i, (name, promised, force, now, minimum) in enumerate(rows):
        c = ACCENT if now else INK2
        ax.barh(i + 0.19, promised * 100, height=0.34, color=c, alpha=0.32)
        ax.barh(i - 0.19, force * 100, height=0.34, color=c)
        ax.text(promised * 100 + 0.5, i + 0.19, ("at least " if minimum else "") + f"{promised * 100:.0f}% promised", va="center", fontsize=10, color=INK)
        ax.text(force * 100 + 0.5, i - 0.19, f"{force * 100:.0f}% in force", va="center", fontsize=10, color=INK, weight="bold" if now else "normal")
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([r[0] for r in rows], fontsize=11, color=INK)
    ax.set_xlim(0, 40)
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    fig.savefig(OUT / "3_then_and_now.png")
    plt.close(fig)


def your_fund(funds: list) -> None:
    f = next(x for x in funds if x["key"] == "sp500")
    parts = [("NVIDIA", f["nvidia"], COLORS["MSFT"]), ("Other AI hardware makers", f["other_ai"], COLORS["AMZN"]), ("The six paying for it", f["customers"], COLORS["GOOGL"])]
    total = sum(p[1] for p in parts)
    counts = [int(p[1]) for p in parts]
    for i in sorted(range(3), key=lambda i: -(parts[i][1] - counts[i]))[: round(total) - sum(counts)]:
        counts[i] += 1
    cells = [c for (_, _, c), k in zip(parts, counts) for _ in range(k)]
    fig = plt.figure(figsize=(10, 5.6), dpi=200)
    fig.text(0.05, 0.94, textwrap.fill(f"{round(total)} cents of every dollar in an S&P 500 index fund sit on one side or the other of AI spending", 62), fontfamily=SERIF, fontsize=17, color=INK, va="top", linespacing=1.15)
    fig.text(0.05, 0.79, f"Each square is one cent. Holdings as reported for {f['as_of']}.", fontsize=10.5, color=INK2, va="top")
    ax = fig.add_axes([0.05, 0.1, 0.38, 0.62])
    ax.set_aspect("equal")
    ax.axis("off")
    for i in range(100):
        ax.add_patch(plt.Rectangle((i % 10, 9 - i // 10), 0.9, 0.9, color=cells[i] if i < len(cells) else REST))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    y = 0.62
    for (name, pct, color), k in zip(parts, counts):
        fig.patches.append(plt.Rectangle((0.52, y - 0.012), 0.02, 0.035, transform=fig.transFigure, color=color))
        fig.text(0.555, y + 0.005, f"{name}", fontsize=12.5, color=INK, va="center")
        fig.text(0.93, y + 0.005, f"{pct:.1f}¢", fontsize=12.5, color=INK, va="center", ha="right", weight="bold")
        y -= 0.1
    fig.patches.append(plt.Rectangle((0.52, y - 0.012), 0.02, 0.035, transform=fig.transFigure, color=REST))
    fig.text(0.555, y + 0.005, "Everything else", fontsize=12.5, color=INK2, va="center")
    fig.text(0.93, y + 0.005, f"{100 - total:.1f}¢", fontsize=12.5, color=INK2, va="center", ha="right")
    fig.text(0.05, 0.04, SOURCE, fontsize=8.5, color=MUTED)
    fig.savefig(OUT / "0_your_fund.png")
    plt.close(fig)


def social_card(a: dict) -> None:
    """The picture drawn when the site's address is pasted into LinkedIn or a chat: 1200 x 627 pixels."""
    import site_shell

    su, lev = a["sources_uses"], {r["ticker"]: r for r in a["leverage"]}
    share = sum(r["capex"] for r in su) / sum(r["cfo"] for r in su)
    leases = sum(r["value"] for r in a["leases"]["latest"])
    hot = sorted((r for r in a["leverage"] if r["pro_forma"] >= 4), key=lambda r: -r["ebitda"])
    w, h = site_shell.CARD_SIZE
    fig = plt.figure(figsize=(w / 100, h / 100), dpi=100)
    fig.patches.append(plt.Rectangle((0, 0.965), 1, 0.035, transform=fig.transFigure, color=INK))
    fig.text(0.06, 0.865, "A RESEARCH NOTE BUILT FROM SEC FILINGS", fontsize=13, color=ACCENT, family="monospace")
    fig.text(0.06, 0.80, "AI spending now takes all the cash\nits biggest builders generate.", fontfamily=SERIF, fontsize=40, color=INK, va="top", linespacing=1.12)
    facts = [
        (f"{share * 100:.0f}¢", "of every dollar of operating\ncash goes on buildings\nand equipment"),
        (f"${leases / 1e12:.2f}tn", "of leases signed but not\nyet on the books"),
        (" · ".join(f"{r['pro_forma']:.1f}×" for r in hot), " and ".join(a["names"][r["ticker"]] for r in hot) + ":\ndebt against earnings with\nthose leases counted"),
    ]
    fig.patches.append(plt.Rectangle((0.06, 0.435), 0.88, 0.003, transform=fig.transFigure, color=INK))
    for i, (num, cap) in enumerate(facts):
        x = 0.06 + i * 0.30
        fig.text(x, 0.375, num, fontsize=30, color=ACCENT if i == 2 else INK, weight="bold", family="monospace", va="top")
        fig.text(x, 0.255, cap, fontsize=14.5, color=INK2, va="top", linespacing=1.3)
    fig.text(0.06, 0.055, f"{site_shell.SITE_NAME}  ·  {site_shell.AUTHOR}", fontsize=14, color=INK, family="monospace")
    fig.savefig(site_shell.DOCS / site_shell.CARD, dpi=100)
    plt.close(fig)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    for old in OUT.glob("*.png"):
        old.unlink()
    payload = make_front.build_payload()
    a = payload["argument"]
    your_fund(payload["funds"])
    cash_gap(a)
    leverage(a)
    then_and_now(a)
    social_card(a)
    print("charts written:", ", ".join(sorted(p.name for p in OUT.glob("*.png"))))


if __name__ == "__main__":
    main()
