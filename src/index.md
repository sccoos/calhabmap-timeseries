---
sql:
  habmap_timeseries: ./data/habmap_timeseries/habmap_timeseries.parquet
---

```js
import {renderHABMAPTimeseries} from "./components/HABMAP-Timeseries.js";

const habmapManifest = await FileAttachment("data/habmap_timeseries/manifest.json").json();
const habmapRows = (await sql`SELECT * FROM habmap_timeseries`).toArray();
const params = new URLSearchParams(window.location.search);
const rangeStart = params.get("range_start");
const rangeEnd = params.get("range_end");

const initialDateRange =
  rangeStart && rangeEnd && !Number.isNaN(Date.parse(rangeStart)) && !Number.isNaN(Date.parse(rangeEnd))
    ? {start: rangeStart, end: rangeEnd}
    : null;

document.title = "CalHABMAP Timeseries";

const habmapTimeseries = renderHABMAPTimeseries({
  title: "CalHABMAP Timeseries",
  manifest: habmapManifest,
  rows: habmapRows,
  initialDateRange
});

const page = document.createElement("div");
page.className = "dashboard-page";

const plotPane = document.createElement("div");
plotPane.className = "dashboard-plot-pane";
plotPane.append(habmapTimeseries);

page.append(plotPane);
display(page);
```
