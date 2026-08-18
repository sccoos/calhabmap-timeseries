from __future__ import annotations

import io
import json
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import pyarrow as pa
import pyarrow.parquet as pq


ERDDAP_BASE_URL = "https://erddap.sccoos.org/erddap"
REGION_ORDER = {"north": 0, "central": 1, "south": 2}

META_COLUMNS = ["Location_Code", "time", "latitude", "longitude"]
HAB_SPECIES_COLUMNS = [
    "Pseudo_nitzschia_delicatissima_group",
    "Pseudo_nitzschia_seriata_group",
    "Alexandrium_spp",
]
DOMOIC_ACID_COLUMNS = ["pDA"]

HAB_UNIT = "cells/L"
DOMOIC_ACID_UNIT = "ng/mL"

UNIT_MAP = {
    **{column: HAB_UNIT for column in HAB_SPECIES_COLUMNS},
    **{column: DOMOIC_ACID_UNIT for column in DOMOIC_ACID_COLUMNS},
}

OUTPUT_COLUMNS = [
    "Location",
    "latitude",
    "longitude",
    "datetime_utc",
    "Year",
    "Month",
    "Day",
    "Date",
    "Alexandrium_spp",
    "Pn_delicatissima",
    "Pn_seriata",
    "Domoic_Acid",
]

CALHABMAP_SITES = {
    "CPP": {
        "site_name": "Cal Poly Pier",
        "dataset_name": "HABs-CalPolyPier",
        "has_spatt": False,
        "region": "central",
    },
    "BML": {
        "site_name": "Bodega Marine Lab",
        "dataset_name": "HABs-BodegaMarineLab",
        "has_spatt": False,
        "region": "north",
    },
    "BBB": {
        "site_name": "Bodega Marine Lab Buoy",
        "dataset_name": "HABs-BodegaMarineLabBuoy",
        "has_spatt": False,
        "region": "north",
    },
    "HUM": {
        "site_name": "Humboldt Bay",
        "dataset_name": "HABs-Humboldt",
        "has_spatt": True,
        "region": "north",
    },
    "HSB": {
        "site_name": "Humboldt South Bay",
        "dataset_name": "HABs-HumboldtSouthBay",
        "has_spatt": True,
        "region": "north",
    },
    "MBB": {
        "site_name": "Morro Bay Back",
        "dataset_name": "HABs-MorroBayFrontBay",
        "has_spatt": False,
        "region": "central",
    },
    "MBF": {
        "site_name": "Morro Bay Front",
        "dataset_name": "HABs-MorroBayBackBay",
        "has_spatt": False,
        "region": "central",
    },
    "HAB_MWII": {
        "site_name": "Monterey Wharf",
        "dataset_name": "HABs-MontereyWharf",
        "has_spatt": False,
        "region": "central",
    },
    "NP": {
        "site_name": "Newport Beach Pier",
        "dataset_name": "HABs-NewportBeachPier",
        "has_spatt": False,
        "region": "south",
    },
    "NBP": {
        "site_name": "Newport Beach Pier",
        "dataset_name": "HABs-NewportBeachPier",
        "has_spatt": False,
        "region": "south",
    },
    "HAB_SCW": {
        "site_name": "Santa Cruz Wharf",
        "dataset_name": "HABs-SantaCruzWharf",
        "has_spatt": True,
        "region": "central",
    },
    "SCW": {
        "site_name": "Santa Cruz Wharf",
        "dataset_name": "HABs-SantaCruzWharf",
        "has_spatt": True,
        "region": "south",
    },
    "SIO": {
        "site_name": "Scripps Pier",
        "dataset_name": "HABs-ScrippsPier",
        "has_spatt": True,
        "region": "south",
    },
    "SMP": {
        "site_name": "Santa Monica Pier",
        "dataset_name": "HABs-SantaMonicaPier",
        "has_spatt": False,
        "region": "south",
    },
    "SW": {
        "site_name": "Stearns Wharf",
        "dataset_name": "HABs-StearnsWharf",
        "has_spatt": True,
        "region": "south",
    },
    "T00": {
        "site_name": "Tomales Bay Mouth",
        "dataset_name": "HABs-TomalesBayMouth",
        "has_spatt": False,
        "region": "north",
    },
    "TBB": {
        "site_name": "Tomales Bay Mid-Channel Buoy",
        "dataset_name": "HABs-TomalesBayMid-ChannelBuoy",
        "has_spatt": False,
        "region": "north",
    },
    "T16": {
        "site_name": "Inner Tomales Bay",
        "dataset_name": "HABs-InnerTomalesBay",
        "has_spatt": False,
        "region": "north",
    },
    "TP": {
        "site_name": "Trinidad Pier",
        "dataset_name": "HABs-TrinidadPier",
        "has_spatt": True,
        "region": "north",
    },
}


def parse_datetime(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    if value.endswith("Z"):
        value = value[:-1] + "+00:00"

    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def format_erddap_datetime(value: str | datetime) -> str:
    return parse_datetime(value).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_json(url: str) -> dict[str, Any]:
    response = subprocess.run(
        ["curl", "-L", "--silent", url],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(response.stdout)


def get_dataset_info(dataset_name: str) -> dict[str, dict[str, str]]:
    info_url = f"{ERDDAP_BASE_URL}/info/{quote(dataset_name)}/index.json"
    payload = fetch_json(info_url)
    rows = payload["table"]["rows"]
    attributes: dict[str, dict[str, str]] = {}

    for row_type, variable_name, attribute_name, _data_type, value in rows:
        if row_type != "attribute":
            continue
        attributes.setdefault(variable_name, {})[attribute_name] = value

    return attributes


def get_dataset_name(site_code: str) -> str:
    try:
        return CALHABMAP_SITES[site_code]["dataset_name"]
    except KeyError as exc:
        raise ValueError(f"Unknown CALHABMAP site code: {site_code}") from exc


def get_most_recent_date(dataset_info: dict[str, dict[str, str]], dataset_name: str) -> datetime:
    try:
        _start_seconds, end_seconds = dataset_info["time"]["actual_range"].split(", ")
    except KeyError as exc:
        raise ValueError(f"Unable to locate time actual_range for dataset {dataset_name}") from exc

    return datetime.fromtimestamp(float(end_seconds), tz=timezone.utc)


def get_station_coordinates(dataset_info: dict[str, dict[str, str]]) -> tuple[float | None, float | None]:
    global_attrs = dataset_info.get("NC_GLOBAL", {})
    latitude = global_attrs.get("geospatial_lat_max") or global_attrs.get("geospatial_lat_min")
    longitude = global_attrs.get("geospatial_lon_max") or global_attrs.get("geospatial_lon_min")
    return parse_float(latitude), parse_float(longitude)


def get_dataset_query_range(
    dataset_info: dict[str, dict[str, str]],
    date_start: str | datetime | None,
    date_end: str | datetime | None,
) -> tuple[datetime, datetime]:
    global_attrs = dataset_info.get("NC_GLOBAL", {})
    start_value = date_start or global_attrs.get("time_coverage_start")
    end_value = date_end or global_attrs.get("time_coverage_end")

    if start_value is None or end_value is None:
        raise ValueError("Dataset is missing time_coverage_start or time_coverage_end metadata")

    return parse_datetime(start_value), parse_datetime(end_value)


def build_site_manifest_entry(
    site_code: str,
    site_info: dict[str, Any],
    dataset_info: dict[str, dict[str, str]],
    site_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    latitude, longitude = get_station_coordinates(dataset_info)
    global_attrs = dataset_info.get("NC_GLOBAL", {})

    return {
        "site_name": site_info["site_name"],
        "dataset_name": site_info["dataset_name"],
        "region": site_info.get("region"),
        "start_date": global_attrs.get("time_coverage_start"),
        "end_date": global_attrs.get("time_coverage_end"),
        "row_count": len(site_rows),
        "spatt_data": site_info["has_spatt"],
        "latitude": latitude,
        "longitude": longitude,
    }


def build_tabledap_url(dataset_name: str, date_start: str | datetime, date_end: str | datetime) -> str:
    variables = META_COLUMNS + HAB_SPECIES_COLUMNS + DOMOIC_ACID_COLUMNS
    query_parts = [
        ",".join(variables),
        f"time>={format_erddap_datetime(date_start)}",
        f"time<={format_erddap_datetime(date_end)}",
    ]
    query = "&".join(quote(part, safe=",:>=<()/-") for part in query_parts)
    return f"{ERDDAP_BASE_URL}/tabledap/{quote(dataset_name)}.json?{query}"


def parse_int(value: Any) -> int | None:
    if value is None or value == "NaN":
        return None
    return int(float(value))


def parse_float(value: Any) -> float | None:
    if value is None or value == "NaN":
        return None
    return float(value)


def transform_site_row(row: dict[str, Any]) -> dict[str, Any]:
    dt = parse_datetime(row["time"])
    return {
        "Location": row["Location_Code"],
        "latitude": parse_float(row["latitude"]),
        "longitude": parse_float(row["longitude"]),
        "datetime_utc": dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "Year": dt.year,
        "Month": dt.month,
        "Day": dt.day,
        "Date": dt.date().isoformat(),
        "Alexandrium_spp": parse_float(row["Alexandrium_spp"]),
        "Pn_delicatissima": parse_int(row["Pseudo_nitzschia_delicatissima_group"]),
        "Pn_seriata": parse_int(row["Pseudo_nitzschia_seriata_group"]),
        "Domoic_Acid": parse_float(row["pDA"]),
    }


def query_site_data(
    site_code: str,
    date_start: str | datetime | None = None,
    date_end: str | datetime | None = None,
    dataset_info: dict[str, dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    dataset_name = get_dataset_name(site_code)
    dataset_info = dataset_info or get_dataset_info(dataset_name)
    start_dt, end_dt = get_dataset_query_range(dataset_info, date_start, date_end)

    most_recent_date = get_most_recent_date(dataset_info, dataset_name)
    print(f"{site_code} : {most_recent_date.isoformat()}", file=sys.stderr)

    if start_dt > most_recent_date:
        return []

    payload = fetch_json(build_tabledap_url(dataset_name, start_dt, end_dt))
    table = payload["table"]
    column_names = table["columnNames"]

    transformed_rows = []
    for raw_row in table["rows"]:
        row = dict(zip(column_names, raw_row))
        transformed_rows.append(transform_site_row(row))

    return transformed_rows


def build_combined_rows_and_manifest(
    date_start: str | datetime | None = None,
    date_end: str | datetime | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    sites_manifest: dict[str, Any] = {}
    dataset_info_cache: dict[str, dict[str, dict[str, str]]] = {}
    dataset_rows_cache: dict[str, list[dict[str, Any]]] = {}

    ordered_sites = sorted(
        CALHABMAP_SITES.items(),
        key=lambda item: (
            REGION_ORDER.get(item[1].get("region"), 999),
            item[1]["site_name"],
            item[0],
        ),
    )

    for site_code, site_info in ordered_sites:
        dataset_name = site_info["dataset_name"]
        dataset_info = dataset_info_cache.get(dataset_name)
        if dataset_info is None:
            dataset_info = get_dataset_info(dataset_name)
            dataset_info_cache[dataset_name] = dataset_info

        site_rows = dataset_rows_cache.get(dataset_name)
        if site_rows is None:
            site_rows = query_site_data(site_code, date_start, date_end, dataset_info=dataset_info)
            dataset_rows_cache[dataset_name] = site_rows
            rows.extend(site_rows)

        sites_manifest[site_code] = build_site_manifest_entry(site_code, site_info, dataset_info, site_rows)

    rows.sort(key=lambda row: (row["Location"], row["datetime_utc"]))
    manifest = {
        "generated_at": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "site_count": len(sites_manifest),
        "sites": sites_manifest,
        "units": {
            "Alexandrium_spp": UNIT_MAP["Alexandrium_spp"],
            "Pn_delicatissima": UNIT_MAP["Pseudo_nitzschia_delicatissima_group"],
            "Pn_seriata": UNIT_MAP["Pseudo_nitzschia_seriata_group"],
            "Domoic_Acid": UNIT_MAP["pDA"],
        },
    }
    return rows, manifest


def rows_to_parquet(rows: list[dict[str, Any]]) -> bytes:
    column_data = {column: [row.get(column) for row in rows] for column in OUTPUT_COLUMNS}
    table = pa.table(column_data)
    buffer = io.BytesIO()
    pq.write_table(table, buffer)
    return buffer.getvalue()


def build_archive(
    date_start: str | datetime | None = None,
    date_end: str | datetime | None = None,
) -> bytes:
    rows, manifest = build_combined_rows_and_manifest(date_start, date_end)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("habmap_timeseries.parquet", rows_to_parquet(rows))
        archive.writestr("manifest.json", json.dumps(manifest, indent=2))

    return buffer.getvalue()


def main() -> None:
    sys.stdout.buffer.write(build_archive())


if __name__ == "__main__":
    main()
