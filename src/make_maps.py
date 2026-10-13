"""Step 4 - render the maps and the change chart.

Produces, for a light and a dark surface each:

* ``forest-cover-2000``   canopy cover in the baseline year,
* ``forest-loss-by-year`` where and when tree cover was lost, 2001-2024,
* ``loss-and-gain``       loss against 2000-2012 regrowth,
* ``annual-loss``         the same numbers as a chart, for the summary panel.

    python src/make_maps.py
"""

from __future__ import annotations

import csv
import json
import math

import matplotlib
import numpy as np
import rasterio

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402
from matplotlib.patches import Patch, Polygon as MplPolygon, Rectangle  # noqa: E402

import config  # noqa: E402
import geo  # noqa: E402
import viz_theme as vt  # noqa: E402

SOURCE_NOTE = (
    f"Data: Hansen/UMD/Google/USGS/NASA Global Forest Change {config.GFC_VERSION} "
    f"(30 m)  ·  Boundary: geoBoundaries NPL {config.ADM_LEVEL}"
)


def flat(colour: str) -> LinearSegmentedColormap:
    """A one-colour colormap, for painting a boolean mask."""
    return LinearSegmentedColormap.from_list("flat", [colour, colour])


def paint(ax, mask, colour, extent, zorder):
    ax.imshow(
        np.where(mask, 1.0, np.nan),
        extent=extent,
        cmap=flat(colour),
        interpolation="nearest",
        zorder=zorder,
    )


# --------------------------------------------------------------------------
# shared map furniture


def rings(geometry: dict):
    """Every linear ring of a (Multi)Polygon as an (n, 2) array."""
    polygons = (
        geometry["coordinates"]
        if geometry["type"] == "MultiPolygon"
        else [geometry["coordinates"]]
    )
    for polygon in polygons:
        for ring in polygon:
            yield np.asarray(ring)


def draw_boundary(ax, geometry, theme, lw=1.4):
    for ring in rings(geometry):
        ax.add_patch(
            MplPolygon(
                ring,
                closed=True,
                facecolor="none",
                edgecolor=theme.ink,
                linewidth=lw,
                zorder=6,
            )
        )


def frame(ax, extent, theme):
    west, east, south, north = extent
    ax.set_xlim(west, east)
    ax.set_ylim(south, north)
    # Plate Carree: stretch latitude so local distances stay honest.
    ax.set_aspect(1 / math.cos(math.radians((south + north) / 2)))
    ax.set_xticks(np.round(np.linspace(west + 0.02, east - 0.02, 4), 2))
    ax.set_yticks(np.round(np.linspace(south + 0.02, north - 0.02, 4), 2))
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:.2f}°E")
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.2f}°N")
    ax.tick_params(length=3, width=0.8, labelsize=7.5)
    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_edgecolor(theme.axis)
        spine.set_linewidth(0.8)


def scale_bar(ax, extent, theme, km=2.0):
    """A plain bar, bottom-left, sized from the local metres-per-degree."""
    west, east, south, north = extent
    deg = km / (111.320 * math.cos(math.radians((south + north) / 2)))
    x0 = west + (east - west) * 0.05
    y0 = south + (north - south) * 0.06
    height = (north - south) * 0.011
    for i in range(2):
        ax.add_patch(
            Rectangle(
                (x0 + i * deg / 2, y0),
                deg / 2,
                height,
                facecolor=theme.ink if i == 0 else theme.surface,
                edgecolor=theme.ink,
                linewidth=0.7,
                zorder=7,
            )
        )
    ax.text(
        x0 + deg / 2,
        y0 + height * 2.0,
        f"{km:g} km",
        ha="center",
        va="bottom",
        fontsize=7,
        color=theme.ink_secondary,
        zorder=7,
    )


def north_arrow(ax, extent, theme):
    west, east, south, north = extent
    x = east - (east - west) * 0.05
    y = south + (north - south) * 0.06
    span = (north - south) * 0.075
    ax.annotate(
        "",
        xy=(x, y + span),
        xytext=(x, y),
        arrowprops=dict(arrowstyle="-|>", color=theme.ink, linewidth=1.1, mutation_scale=11),
        zorder=7,
    )
    ax.text(
        x,
        y + span * 1.1,
        "N",
        ha="center",
        va="bottom",
        fontsize=8,
        color=theme.ink,
        fontweight="bold",
        zorder=7,
    )


def legend(ax, handles, theme, loc="upper left"):
    box = ax.legend(
        handles=handles,
        loc=loc,
        frameon=True,
        facecolor=theme.surface,
        edgecolor=theme.axis,
        fontsize=7.5,
        labelcolor=theme.ink_secondary,
        borderpad=0.6,
        labelspacing=0.5,
    )
    box.get_frame().set_linewidth(0.8)
    return box


def colourbar(fig, im, theme, label, ticks=None, ticklabels=None):
    cax = fig.add_axes([0.895, 0.17, 0.017, 0.54])
    cb = fig.colorbar(im, cax=cax, ticks=ticks)
    cb.outline.set_edgecolor(theme.axis)
    cb.outline.set_linewidth(0.8)
    cb.set_label(label, color=theme.ink_secondary, fontsize=8)
    cb.ax.tick_params(colors=theme.ink_muted, labelsize=7.5, length=3, width=0.8)
    if ticklabels:
        cb.ax.set_yticklabels(ticklabels)
    plt.setp(cb.ax.get_yticklabels(), color=theme.ink_secondary)
    return cb


def titles(fig, theme, title, subtitle):
    fig.text(0.015, 0.978, title, fontsize=13, fontweight="bold", color=theme.ink, va="top")
    fig.text(0.015, 0.930, subtitle, fontsize=8.5, color=theme.ink_secondary, va="top",
             wrap=True)
    fig.text(0.015, 0.016, SOURCE_NOTE, fontsize=6.8, color=theme.ink_muted, va="bottom")


def save(fig, stem, theme):
    path = config.MAPS / f"{stem}{vt.suffix(theme)}.png"
    fig.savefig(path)
    plt.close(fig)
    print(f"[ok  ] {path.relative_to(config.ROOT)}")


# --------------------------------------------------------------------------
# layers


def load():
    layers = {}
    transform = shape = bounds = None
    for layer in config.GFC_LAYERS:
        with rasterio.open(config.raster_path(layer)) as src:
            layers[layer] = src.read(1)
            transform, shape, bounds = src.transform, src.shape, src.bounds
    geometry = geo.load_boundary()
    inside = geo.boundary_mask(geometry, shape, transform)
    extent = (bounds.left, bounds.right, bounds.bottom, bounds.top)
    return layers, geometry, inside, extent


# --------------------------------------------------------------------------
# figures


def map_canopy(layers, geometry, inside, extent, theme, summary):
    fig, ax = plt.subplots(figsize=(8.0, 6.0))
    fig.subplots_adjust(left=0.075, right=0.875, top=0.855, bottom=0.095)

    canopy = np.where(inside, layers["treecover2000"], np.nan).astype(float)
    im = ax.imshow(
        canopy,
        extent=extent,
        cmap=theme.cmap(theme.canopy, "canopy"),
        vmin=0,
        vmax=100,
        interpolation="nearest",
        zorder=2,
    )
    draw_boundary(ax, geometry, theme)
    frame(ax, extent, theme)
    scale_bar(ax, extent, theme)
    north_arrow(ax, extent, theme)
    colourbar(fig, im, theme, "Tree canopy cover, 2000 (%)")
    # Permanent water covers 6 pixels here - painted for correctness, but far
    # too small to earn a legend entry.
    paint(ax, inside & (layers["datamask"] == 2), theme.water, extent, 3)

    titles(
        fig,
        theme,
        f"Panauti held {summary['forest_2000_ha']:,.0f} ha of forest in 2000",
        f"Tree canopy cover at 30 m resolution, Panauti Municipality, Kavrepalanchok  ·  "
        f"{summary['forest_2000_pct_of_area']}% of the municipality met the "
        f"{config.CANOPY_THRESHOLD}% canopy threshold",
    )
    save(fig, "forest-cover-2000", theme)


def map_loss_year(layers, geometry, inside, extent, theme, summary):
    fig, ax = plt.subplots(figsize=(8.0, 6.0))
    fig.subplots_adjust(left=0.075, right=0.875, top=0.855, bottom=0.095)

    forest = inside & (layers["treecover2000"] >= config.CANOPY_THRESHOLD)
    paint(ax, inside, theme.backdrop, extent, 1)
    paint(ax, forest, theme.canopy[2], extent, 2)

    year_of_loss = layers["lossyear"].astype(float) + 2000
    loss = np.where(forest & (layers["lossyear"] > 0), year_of_loss, np.nan)
    im = ax.imshow(
        loss,
        extent=extent,
        cmap=theme.cmap(theme.lossyear, "lossyear"),
        vmin=config.LOSS_YEAR_START,
        vmax=config.LOSS_YEAR_END,
        interpolation="nearest",
        zorder=4,
    )

    draw_boundary(ax, geometry, theme)
    frame(ax, extent, theme)
    scale_bar(ax, extent, theme)
    north_arrow(ax, extent, theme)
    ticks = [2001, 2006, 2012, 2018, 2024]
    colourbar(fig, im, theme, "Year of tree cover loss", ticks, [str(t) for t in ticks])
    legend(
        ax,
        [
            Patch(facecolor=theme.canopy[2], edgecolor="none", label="Forest standing in 2000"),
            Patch(facecolor=theme.backdrop, edgecolor="none", label="Non-forest"),
        ],
        theme,
    )

    titles(
        fig,
        theme,
        f"{summary['total_loss_ha']:,.0f} ha of that forest was cleared by 2024",
        f"Stand-replacement tree cover loss, {config.LOSS_YEAR_START}–"
        f"{config.LOSS_YEAR_END}  ·  {summary['total_loss_pct_of_2000_forest']}% of the "
        f"2000 forest, with the heaviest single year in {summary['peak_loss_year']}",
    )
    save(fig, "forest-loss-by-year", theme)


def map_loss_gain(layers, geometry, inside, extent, theme, summary):
    fig, ax = plt.subplots(figsize=(8.0, 6.0))
    fig.subplots_adjust(left=0.075, right=0.965, top=0.855, bottom=0.095)

    forest = inside & (layers["treecover2000"] >= config.CANOPY_THRESHOLD)
    paint(ax, inside, theme.backdrop, extent, 1)
    paint(ax, forest, theme.canopy[1], extent, 2)
    paint(ax, inside & (layers["gain"] == 1), theme.gain, extent, 3)
    paint(ax, forest & (layers["lossyear"] > 0), theme.loss, extent, 4)

    draw_boundary(ax, geometry, theme)
    frame(ax, extent, theme)
    scale_bar(ax, extent, theme)
    north_arrow(ax, extent, theme)
    legend(
        ax,
        [
            Patch(facecolor=theme.loss, edgecolor="none",
                  label=f"Loss 2001–2024   −{summary['total_loss_ha']:,.0f} ha"),
            Patch(facecolor=theme.gain, edgecolor="none",
                  label=f"Gain 2000–2012   +{summary['gain_2000_2012_ha']:,.0f} ha"),
            Patch(facecolor=theme.canopy[1], edgecolor="none", label="Forest standing in 2000"),
            Patch(facecolor=theme.backdrop, edgecolor="none", label="Non-forest"),
        ],
        theme,
    )

    titles(
        fig,
        theme,
        "Mapped regrowth offsets about a third of the loss",
        f"Tree cover loss against mapped gain  ·  net change "
        f"{summary['net_change_ha']:,.0f} ha  ·  gain is only mapped for 2000–2012, "
        f"so replanting after 2012 is not yet visible in this layer",
    )
    save(fig, "loss-and-gain", theme)


def chart_annual_loss(theme, summary):
    path = config.TABLES / "panauti_forest_change_2001_2024.csv"
    with path.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    years = [int(r["year"]) for r in rows]
    loss = [float(r["loss_ha"]) for r in rows]
    cumulative = [float(r["cumulative_loss_ha"]) for r in rows]

    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(8.0, 6.2), sharex=True, gridspec_kw={"height_ratios": [1.35, 1]}
    )
    fig.subplots_adjust(left=0.085, right=0.97, top=0.835, bottom=0.11, hspace=0.18)

    # Panel 1 - annual loss. One series, so no legend: the title names it.
    ax1.bar(years, loss, width=0.68, color=theme.loss, zorder=3)
    ax1.set_ylabel("Tree cover loss (ha per year)")
    ax1.set_ylim(0, max(loss) * 1.24)

    peak = max(range(len(loss)), key=lambda i: loss[i])
    runner = max((i for i in range(len(loss)) if i != peak), key=lambda i: loss[i])
    for i in (peak, runner):
        ax1.text(
            years[i],
            loss[i] + max(loss) * 0.03,
            f"{loss[i]:.0f} ha",
            ha="center",
            va="bottom",
            fontsize=8,
            fontweight="bold" if i == peak else "normal",
            color=theme.ink if i == peak else theme.ink_secondary,
            zorder=4,
        )

    mean = summary["mean_annual_loss_ha"]
    ax1.axhline(mean, color=theme.ink_muted, linewidth=1.0, linestyle=(0, (4, 3)), zorder=2)
    ax1.text(
        years[0] - 0.4,
        mean + max(loss) * 0.045,
        f"24-year mean  {mean:.1f} ha/yr",
        fontsize=7.5,
        color=theme.ink_muted,
        va="bottom",
        bbox=dict(facecolor=theme.surface, edgecolor="none", pad=1.5),
        zorder=4,
    )

    # Panel 2 - cumulative loss. A separate panel, never a second y-axis.
    ax2.fill_between(years, cumulative, color=theme.loss, alpha=0.12, zorder=2)
    ax2.plot(years, cumulative, color=theme.loss, linewidth=2.0, zorder=3)
    ax2.plot(
        [years[-1]], [cumulative[-1]], marker="o", markersize=5.5, color=theme.loss,
        markeredgecolor=theme.surface, markeredgewidth=2.0, zorder=4,
    )
    ax2.text(
        years[-1] - 0.5,
        cumulative[-1],
        f"{cumulative[-1]:,.0f} ha cumulative",
        ha="right",
        va="center",
        fontsize=8,
        fontweight="bold",
        color=theme.ink,
    )
    ax2.set_ylabel("Cumulative loss (ha)")
    ax2.set_ylim(0, cumulative[-1] * 1.2)
    ax2.set_xlim(years[0] - 0.9, years[-1] + 0.9)
    ax2.set_xticks(years[::2])

    for ax in (ax1, ax2):
        ax.yaxis.grid(True, color=theme.grid, linewidth=0.8, zorder=0)
        ax.set_axisbelow(True)
        ax.tick_params(length=3, width=0.8, labelsize=8)

    titles(
        fig,
        theme,
        "Forest loss in Panauti is accelerating",
        f"Annual and cumulative tree cover loss inside the 2000 forest extent, "
        f"{config.LOSS_YEAR_START}–{config.LOSS_YEAR_END}  ·  "
        f"{config.CANOPY_THRESHOLD}% canopy threshold  ·  values in "
        f"outputs/tables/panauti_forest_change_2001_2024.csv",
    )
    save(fig, "annual-loss", theme)


def main() -> None:
    summary = json.loads((config.TABLES / "summary.json").read_text(encoding="utf-8"))
    layers, geometry, inside, extent = load()

    for theme in vt.THEMES:
        with plt.rc_context(vt.rc(theme)):
            map_canopy(layers, geometry, inside, extent, theme, summary)
            map_loss_year(layers, geometry, inside, extent, theme, summary)
            map_loss_gain(layers, geometry, inside, extent, theme, summary)
            chart_annual_loss(theme, summary)


if __name__ == "__main__":
    main()
