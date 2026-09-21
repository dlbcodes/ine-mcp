"""
main.py — the MCP server itself.

Exposes two tools:
- search_indicators: find INE indicator codes by keyword
- get_indicator: fetch data for a known indicator code

Both hit INE's public API (Instituto Nacional de Estatistica, Portugal).
"""

import requests
import xml.etree.ElementTree as ET
from mcp.server.mcpserver import MCPServer

mcp = MCPServer("ine-pt")


@mcp.tool()
def search_indicators(query: str, lang: str = "PT") -> list[dict]:
    """Search INE's indicator catalogue by keyword.

    Args:
        query: Keyword to search for, e.g. "desemprego" or "unemployment".
        lang: "PT" or "EN".

    Returns a list of matching indicators, each with varcd (the code
    you pass to get_indicator), title, theme, and subtheme.
    """
    url = f"https://www.ine.pt/ine/xml_indic.jsp?opc=3&lang={lang}"
    resp = requests.get(url, timeout=60)  # the full catalogue is a big file
    resp.raise_for_status()

    root = ET.fromstring(resp.content)
    query_lower = query.lower()
    matches = []

    for indicator in root.findall("indicator"):
        title = indicator.findtext("title", "")
        keywords = indicator.findtext("keywords", "")
        description = indicator.findtext("description", "")
        searchable_text = f"{title} {keywords} {description}".lower()

        if query_lower in searchable_text:
            matches.append({
                "varcd": indicator.findtext("varcd", ""),
                "title": title,
                "theme": indicator.findtext("theme", ""),
                "subtheme": indicator.findtext("subtheme", ""),
            })

    return matches


@mcp.tool()
def get_metadata(varcd: str, lang: str = "PT") -> dict:
    """Fetch an indicator's metadata: its dimensions and valid codes.

    Use this before get_indicator to discover what dim1/dim2/etc.
    values are actually valid for a given indicator, instead of
    guessing.

    Args:
        varcd: INE indicator code, e.g. "0008074".
        lang: "PT" or "EN".
    """
    return _fetch_metadata(varcd, lang)


def _fetch_metadata(varcd: str, lang: str = "PT") -> dict:
    """Internal: does the actual metadata request (shared by get_metadata,
    resolve_dimensions, and get_indicator, so we only fetch once per call).

    INE's response shape is inconsistent ACROSS DIFFERENT INDICATORS —
    some return a plain dict, others wrap it in a list — normalize here,
    once, so every caller gets a dict regardless.
    """
    url = (
        "https://www.ine.pt/ine/json_indicador/pindicaMeta.jsp"
        f"?varcd={varcd}&lang={lang}"
    )
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    meta = resp.json()
    if isinstance(meta, list):
        meta = meta[0] if meta else {}
    return meta


def _parse_dimensions(meta) -> dict[str, list[dict]]:
    """Internal: pull every "Dim_NumX_code" key out of the raw metadata
    into a clean {dim_num: [{code, label}, ...]} shape.

    The real path, confirmed against a live response: meta["Dimensoes"]
    ["Categoria_Dim"] is a list containing one dict with all the
    Dim_Num keys.
    """
    dims: dict[str, list[dict]] = {}

    try:
        entries = meta["Dimensoes"]["Categoria_Dim"][0]
    except (KeyError, IndexError, TypeError):
        return dims  # unexpected shape — return empty rather than crash

    for key, value in entries.items():
        if not key.startswith("Dim_Num") or not isinstance(value, list) or not value:
            continue
        entry = value[0]
        dim_num = entry.get("dim_num")
        if dim_num is None:
            continue
        dims.setdefault(dim_num, []).append({
            "code": entry.get("categ_cod"),
            "label": entry.get("categ_dsg"),
        })
    return dims


@mcp.tool()
def resolve_dimensions(varcd: str, filters: dict[str, str], lang: str = "PT") -> dict:
    """Turn human-readable keywords into the real dimension codes
    get_indicator needs — instead of guessing codes like "20" or
    "S7A2015" by hand.

    Args:
        varcd: INE indicator code.
        filters: mapping of dimension number (as a string, e.g. "2")
            to a keyword to search for in that dimension's labels,
            e.g. {"2": "Açores", "3": "Total"}.
        lang: "PT" or "EN".

    Returns the resolved code for each dimension that matched exactly
    one option, plus a list of problems for anything that matched zero
    or more than one — never a silent guess.
    """
    meta = _fetch_metadata(varcd, lang)
    dims = _parse_dimensions(meta)

    resolved = {}
    problems = []

    for dim_num, keyword in filters.items():
        candidates = dims.get(dim_num, [])
        matches = [c for c in candidates if keyword.lower() in (c["label"] or "").lower()]

        if len(matches) == 0:
            problems.append(f"Dimension {dim_num}: no match for '{keyword}'")
        elif len(matches) > 1:
            options = ", ".join(f"{m['label']} ({m['code']})" for m in matches[:5])
            problems.append(f"Dimension {dim_num}: '{keyword}' is ambiguous — {options}")
        else:
            resolved[dim_num] = matches[0]

    return {
        "resolved": resolved,
        "problems": problems,
        "_debug": {
            "dims_found": {k: len(v) for k, v in dims.items()},
        },
    }


@mcp.tool()
def get_indicator(varcd: str, dim1: str, dim2: str, lang: str = "PT") -> dict:
    """Fetch data for an INE indicator by its code (varcd).

    Args:
        varcd: INE indicator code, e.g. "0008074" (use search_indicators
            to find one if you don't already know it).
        dim1: Time dimension code, e.g. "S7A2015".
        dim2: Geographic dimension code, e.g. "11A1312" for Porto, or
            "PT" for the whole country. Required — pass "PT" explicitly
            if you want the national total, rather than leaving it out.
        lang: "PT" or "EN".

    Every result carries a "source" link to verify the number and a
    "measurement" block with its unit — never quote a value from this
    without checking both, since a bare number has no meaning on its own.
    """
    url = (
        "https://www.ine.pt/ine/json_indicador/pindica.jsp"
        f"?op=2&varcd={varcd}&Dim1={dim1}&Dim2={dim2}&lang={lang}"
    )
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    # Enrich with unit/scale from metadata and a human-clickable
    # verification link — a number is not safely quotable without these.
    # Catch any request failure here (not just HTTPError) — the metadata
    # payload is large and can time out under load, and that must never
    # break the primary data fetch, which already succeeded.
    try:
        meta = _fetch_metadata(varcd, lang)
    except requests.exceptions.RequestException:
        meta = {}

    measurement = {
        "unit": meta.get("UnidadeMedida"),
        "scale": meta.get("Potencia10"),
        "decimal_places": meta.get("PrecisaoDecimal"),
    }

    return {
        "source": {
            "api": url,
            "verify_url": data.get("MetaInfUrl"),
        },
        "measurement": measurement,
        "data": data,
    }


if __name__ == "__main__":
    mcp.run()