# ADR-003: House Geometry Configuration

## Status

Accepted **Date:** 2026-03-29

## Context

An existing proof of concept encodes building footprint polygons in `house.py` as Python
dictionaries. This makes the app specific to a single house and requires code changes
for any other user.

The app needs a configurable way to define building footprints (house, neighbors,
highlighted regions) on a 2D canvas. Two input methods are desired: structured data
(YAML/JSON) for explicit control, and SVG file import for users who prefer drawing their
layout in a graphical editor.

## Decision

Support **two input formats** for house geometry, configured via settings:

### Format A: YAML/JSON Polygon Definitions (Primary)

```yaml
canvas:
  size: 100 # square canvas in arbitrary units
  north_rotation: 0 # degrees clockwise from canvas-up to true north

buildings:
  - name: home
    vertices: [[50.75, 33.75], [80.00, 52.25], [67.25, 72.50], ...]
    casts_shadow: true
    style: home # rendering style: "home", "neighbor", "default"

  - name: neighbour_north
    vertices: [[4.75, 59.00], [10.50, 49.75], ...]
    casts_shadow: true
    style: neighbor

highlighted_regions:
  - name: dining_room
    vertices: [[70.75, 75.00], [62.00, 89.00], ...]
    color: '#b38c3a'

  - name: terrace
    vertices: [[30.0, 80.0], [45.0, 80.0], ...]
    color: '#88aa55'
```

The geometry file path is configured via `SUNCAST_GEOMETRY_FILE` (default:
`geometry.yaml`).

### Format B: SVG File Import

Users can provide an SVG file drawn in any editor (e.g., Inkscape). The parser extracts
`<polygon>` and `<path>` elements with **straight-line segments only** (M, L, H, V, Z
commands; curves are rejected with a warning).

Shape identification priority:

1. `id` attribute (e.g., `id="home"`)
2. `inkscape:label` attribute (e.g., `inkscape:label="neighbour"`)
3. `data-name` attribute
4. Auto-generated: `shape_1`, `shape_2`, ...

A companion YAML sidecar file maps shape names to roles and properties:

```yaml
canvas:
  north_rotation: 15

shape_roles:
  home:
    casts_shadow: true
    style: home
  neighbour:
    casts_shadow: true
    style: neighbor
  dining_room:
    highlighted: true
    color: '#b38c3a'
```

This keeps the SVG purely geometric and the role mapping in structured data.

### North Orientation

The `north_rotation` setting (degrees clockwise) rotates the compass reference relative
to the canvas. A value of 0 means canvas-up is true north. A value of 90 means canvas-up
is true east (i.e., north is to the right).

This rotation is applied to the solar azimuth before computing shadow projections, NOT
to the geometry itself — so the SVG output matches the input layout.

## Decision Drivers

- Ease of use for non-technical users (draw in Inkscape)
- Precision for technical users (explicit coordinates)
- Support for multiple buildings and highlighted regions
- Configurable north orientation for arbitrary house orientations

## Considered Options

1. **YAML/JSON only** — explicit, easy to validate, but tedious to author
2. **SVG import only** — visual authoring, but hard to assign roles without sidecar
3. **Both YAML and SVG** — maximum flexibility, moderate implementation effort
4. **GeoJSON** — real-world coordinates, but overkill for a 2D canvas visualization

## Decision Matrix

| Criterion           | YAML only | SVG only | Both | GeoJSON |
| ------------------- | --------- | -------- | ---- | ------- |
| Ease of authoring   | 2         | 5        | 5    | 3       |
| Validation ease     | 5         | 3        | 4    | 4       |
| Role assignment     | 5         | 2        | 4    | 4       |
| Implementation cost | 5         | 3        | 3    | 2       |
| User flexibility    | 3         | 3        | 5    | 4       |

_Scale: 1 (poor) to 5 (excellent)_

## Consequences

### Positive

- Users can choose the method that fits their skill set
- SVG import enables visual editing workflow (draw → export → configure roles)
- YAML gives full control for precise or automated geometry
- North rotation decouples house orientation from canvas layout

### Negative

- SVG parser adds implementation complexity (mitigated by limiting to straight-line
  segments and using Python's `xml.etree` stdlib)
- Two input formats require two code paths and documentation for each

_2026-03-29_
