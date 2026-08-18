import {createElement, useEffect, useId, useMemo, useRef, useState} from "npm:react";
import {createRoot} from "npm:react-dom/client";
import Plotly from "npm:plotly.js-dist-min";
import * as d3 from "npm:d3";

const VARIABLE_OPTIONS = [
  {value: "Pn_delicatissima", label: "Pseudo-nitzschia (delicatissima group)", unit: "cells/L"},
  {value: "Pn_seriata", label: "Pseudo-nitzschia (seriata group)", unit: "cells/L"},
  {value: "Alexandrium_spp", label: "Alexandrium spp", unit: "cells/L"},
  {value: "Domoic_Acid", label: "Particulate Domoic Acid", unit: "ng/mL"}
];

const REGION_LABELS = {
  north: "Northern California",
  central: "Central California",
  south: "Southern California",
};

const COLOR_PALETTE = ["#d9251d", "#f5b45a", "#9cc9e5", "#5a8f76", "#5166b4", "#d781c5", "#7d7d7d"];

function formatRegionLabel(region) {
  return REGION_LABELS[region] ?? region;
}

function getDefaultRegion(siteEntries) {
  if (siteEntries.some(([, site]) => site.region === "central")) return "central";
  return siteEntries.find(([, site]) => site.region)?.[1].region ?? "all";
}

function clampDate(value, minDate, maxDate) {
  return new Date(Math.min(maxDate.getTime(), Math.max(minDate.getTime(), value.getTime())));
}

function getInitialVisibleRange(minDate, maxDate, initialDateRange) {
  if (!minDate || !maxDate) return [new Date("2025-08-18T00:00:00Z"), new Date("2026-08-18T00:00:00Z")];

  if (initialDateRange?.start && initialDateRange?.end) {
    const start = clampDate(new Date(initialDateRange.start), minDate, maxDate);
    const end = clampDate(new Date(initialDateRange.end), minDate, maxDate);
    return start <= end ? [start, end] : [end, start];
  }

  const trailingStart = clampDate(d3.utcMonth.offset(maxDate, -12), minDate, maxDate);
  return trailingStart < maxDate ? [trailingStart, maxDate] : [minDate, maxDate];
}

function getYAxisRange(points, start, end) {
  const visibleValues = points
    .filter((point) => point.datetime.getTime() >= start.getTime() && point.datetime.getTime() <= end.getTime())
    .map((point) => point.value)
    .filter((value) => Number.isFinite(value));

  const ymax = visibleValues.length ? d3.max(visibleValues) : 1;
  const paddedMax = ymax > 0 ? ymax * 1.08 : 1;
  return [0, paddedMax];
}

function DropdownSelector({id, label, value, options, variant, isOpen, onToggle, onSelect}) {
  const selectedOption = options.find((option) => option.value === value) ?? options[0];

  return createElement(
    "div",
    {
      className: `hab-dropdown hab-dropdown--${variant}${isOpen ? " hab-dropdown--open" : ""}`
    },
    createElement(
      "button",
      {
        id,
        type: "button",
        className: `hab-dropdown__trigger hab-dropdown__trigger--${variant}`,
        "aria-label": label,
        "aria-haspopup": "listbox",
        "aria-expanded": isOpen ? "true" : "false",
        onClick: onToggle
      },
      createElement("span", {className: "hab-dropdown__label"}, selectedOption?.label ?? "")
    ),
    isOpen
      ? createElement(
          "div",
          {className: "hab-dropdown__menu", role: "listbox", "aria-labelledby": id},
          options.map((option) =>
            createElement(
              "button",
              {
                key: option.value,
                type: "button",
                className: `hab-dropdown__option${option.value === value ? " hab-dropdown__option--selected" : ""}`,
                role: "option",
                "aria-selected": option.value === value ? "true" : "false",
                onClick: () => onSelect(option.value)
              },
              option.label
            )
          )
        )
      : null
  );
}

function HABMAPTimeseries({manifest, rows, initialDateRange = null}) {
  const variableSelectId = useId();
  const regionSelectId = useId();
  const plotRef = useRef(null);
  const headerRef = useRef(null);
  const suppressRelayoutRef = useRef(false);

  const siteEntries = useMemo(() => Object.entries(manifest?.sites ?? {}), [manifest]);
  const [selectedVariable, setSelectedVariable] = useState("Pn_delicatissima");
  const [selectedRegion, setSelectedRegion] = useState(() => getDefaultRegion(siteEntries));
  const [openDropdown, setOpenDropdown] = useState(null);

  const variableOption = VARIABLE_OPTIONS.find((option) => option.value === selectedVariable) ?? VARIABLE_OPTIONS[0];

  const regionOptions = useMemo(() => {
    const regions = Array.from(new Set(siteEntries.map(([, site]) => site.region).filter(Boolean)));
    return [...regions.map((region) => ({value: region, label: formatRegionLabel(region)})), {value: "all", label: "All California"}];
  }, [siteEntries]);

  useEffect(() => {
    if (!openDropdown) return undefined;

    const handlePointerDown = (event) => {
      if (!headerRef.current?.contains(event.target)) {
        setOpenDropdown(null);
      }
    };

    const handleKeyDown = (event) => {
      if (event.key === "Escape") {
        setOpenDropdown(null);
      }
    };

    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("touchstart", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);

    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("touchstart", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [openDropdown]);

  const enrichedRows = useMemo(() => {
    const sites = manifest?.sites ?? {};
    return rows
      .map((row) => {
        const site = sites[row.Location];
        if (!site) return null;

        const rawValue = row[selectedVariable];
        const value = rawValue == null ? null : Number(rawValue);
        const datetime = row.Date ? new Date(`${row.Date}T00:00:00Z`) : null;
        if (!datetime || Number.isNaN(datetime.getTime()) || value == null) return null;

        return {
          datetime,
          value,
          location: row.Location,
          siteName: site.site_name ?? row.Location,
          region: site.region ?? null
        };
      })
      .filter((row) => row && (selectedRegion === "all" || row.region === selectedRegion));
  }, [manifest, rows, selectedRegion, selectedVariable]);

  const series = useMemo(() => {
    const grouped = d3.group(enrichedRows, (row) => row.location);
    return Array.from(grouped, ([location, values], index) => ({
      location,
      siteName: values[0]?.siteName ?? location,
      color: COLOR_PALETTE[index % COLOR_PALETTE.length],
      values: values.slice().sort((a, b) => a.datetime - b.datetime)
    })).sort((a, b) => d3.ascending(a.siteName, b.siteName));
  }, [enrichedRows]);

  const domain = useMemo(() => {
    if (!enrichedRows.length) {
      const fallbackStart = new Date("2025-08-18T00:00:00Z");
      const fallbackEnd = new Date("2026-08-18T00:00:00Z");
      return {minDate: fallbackStart, maxDate: fallbackEnd, visibleRange: [fallbackStart, fallbackEnd]};
    }

    const minDate = d3.min(enrichedRows, (row) => row.datetime);
    const maxDate = d3.max(enrichedRows, (row) => row.datetime);
    return {
      minDate,
      maxDate,
      visibleRange: getInitialVisibleRange(minDate, maxDate, initialDateRange)
    };
  }, [enrichedRows, initialDateRange]);

  const plotData = useMemo(
    () =>
      series.flatMap((site) => [
        {
          type: "scatter",
          mode: "lines",
          name: site.siteName,
          legendgroup: site.location,
          x: site.values.map((point) => point.datetime.toISOString()),
          y: site.values.map((point) => point.value),
          line: {
            color: site.color,
            width: 4
          },
          hoverinfo: "skip"
        },
        {
          type: "scatter",
          mode: "markers",
          name: site.siteName,
          legendgroup: site.location,
          showlegend: false,
          x: site.values.map((point) => point.datetime.toISOString()),
          y: site.values.map((point) => point.value),
          marker: {
            color: site.color,
            size: 9
          },
          hovertemplate: "%{fullData.name}<br>%{y:,.3~f}<extra></extra>"
        }
      ]),
    [series]
  );

  useEffect(() => {
    if (!plotRef.current) return undefined;

    const {visibleRange} = domain;
    const initialYRange = getYAxisRange(enrichedRows, visibleRange[0], visibleRange[1]);
    const showPseudoNitzschiaThreshold =
      selectedVariable === "Pn_delicatissima" || selectedVariable === "Pn_seriata";
    const layout = {
      autosize: true,
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "#ffffff",
      margin: {t: 24, r: 32, b: 72, l: 84},
      hovermode: "x unified",
      hoverdistance: 8,
      spikedistance: -1,
      showlegend: true,
      legend: {
        orientation: "h",
        x: 0.5,
        xanchor: "center",
        font: {size: 12, color: "#111111"}
      },
      font: {
        family: '"Avenir Next", "Segoe UI", sans-serif',
        color: "#313131"
      },
      xaxis: {
        type: "date",
        range: visibleRange.map((date) => date.toISOString()),
        automargin: true,
        showgrid: true,
        gridcolor: "#dddddd",
        tickfont: {size: 15, color: "#4b4b4b"}
      },
      shapes: showPseudoNitzschiaThreshold
        ? [
            {
              type: "line",
              xref: "paper",
              x0: 0,
              x1: 1,
              yref: "y",
              y0: 10000,
              y1: 10000,
              line: {
                color: "#8c8c8c",
                width: 2,
                dash: "dash"
              }
            }
          ]
        : [],
      yaxis: {
        title: {
          text: manifest?.units?.[selectedVariable] ?? variableOption.unit,
          standoff: 10,
          font: {size: 18, color: "#111111"}
        },
        range: initialYRange,
        showgrid: true,
        gridcolor: "#dddddd",
        zeroline: true,
        zerolinecolor: "#b6b6b6",
        zerolinewidth: 2,
        tickfont: {size: 14, color: "#4b4b4b"}
      }
    };

    const config = {
      responsive: true,
      displaylogo: false,
      modeBarButtonsToRemove: ["select2d", "lasso2d", "autoScale2d", "toggleSpikelines"],
      toImageButtonOptions: {
        format: "png",
        filename: "habmap-timeseries"
      }
    };

    Plotly.react(plotRef.current, plotData, layout, config);

    const handleRelayout = (eventData) => {
      if (!eventData || suppressRelayoutRef.current) {
        suppressRelayoutRef.current = false;
        return;
      }

      const nextStartValue =
        eventData["xaxis.range[0]"] ??
        eventData.xaxis?.range?.[0] ??
        (eventData["xaxis.autorange"] ? domain.minDate.toISOString() : null);
      const nextEndValue =
        eventData["xaxis.range[1]"] ??
        eventData.xaxis?.range?.[1] ??
        (eventData["xaxis.autorange"] ? domain.maxDate.toISOString() : null);

      if (!nextStartValue || !nextEndValue) return;

      const nextStart = new Date(nextStartValue);
      const nextEnd = new Date(nextEndValue);
      if (Number.isNaN(nextStart.getTime()) || Number.isNaN(nextEnd.getTime())) return;

      suppressRelayoutRef.current = true;
      Plotly.relayout(plotRef.current, {
        "yaxis.range": getYAxisRange(enrichedRows, nextStart, nextEnd)
      });
    };

    plotRef.current.on("plotly_relayout", handleRelayout);

    return () => {
      plotRef.current?.removeAllListeners?.("plotly_relayout");
      Plotly.purge(plotRef.current);
    };
  }, [domain, enrichedRows, manifest, plotData, selectedVariable, variableOption.unit]);

  return createElement(
    "article",
    {className: "hab-card"},
    createElement(
      "div",
      {className: "hab-card__header", ref: headerRef},
      createElement(DropdownSelector, {
        id: variableSelectId,
        label: "Select variable",
        value: selectedVariable,
        options: VARIABLE_OPTIONS.map(({value, label}) => ({value, label})),
        variant: "title",
        isOpen: openDropdown === "variable",
        onToggle: () => setOpenDropdown((current) => (current === "variable" ? null : "variable")),
        onSelect: (value) => {
          setSelectedVariable(value);
          setOpenDropdown(null);
        }
      }),
      createElement(DropdownSelector, {
        id: regionSelectId,
        label: "Select region",
        value: selectedRegion,
        options: regionOptions,
        variant: "subtitle",
        isOpen: openDropdown === "region",
        onToggle: () => setOpenDropdown((current) => (current === "region" ? null : "region")),
        onSelect: (value) => {
          setSelectedRegion(value);
          setOpenDropdown(null);
        }
      })
    ),
    createElement(
      "div",
      {className: "hab-card__viewport"},
      createElement("div", {
        ref: plotRef,
        className: "hab-plotly",
        "aria-label": `${variableOption.label} timeseries plot`
      })
    )
  );
}

export function renderHABMAPTimeseries(props) {
  const container = document.createElement("div");
  const root = createRoot(container);
  root.render(createElement(HABMAPTimeseries, props));
  return container;
}
