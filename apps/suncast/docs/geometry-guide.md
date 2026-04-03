# Geometry Guide

suncast renders shadow visualizations from a geometry configuration that defines your
building footprints on a virtual compass canvas. This guide explains the YAML format,
coordinate system, and SVG import workflow.

---

## Canvas Coordinate System

The canvas is a square grid measured in arbitrary units:

- **Origin** `(0, 0)` is the **top-left** corner
- `canvas.size` sets the side length (default: 100)
- All building and highlight vertices must fall within `0..canvas.size`
- suncast automatically scales everything to fit inside a circular viewport via
  `fit_to_circle()` — you can use any coordinate scale

---

## YAML Format

Create a file (e.g. `geometry.yaml`) with the following structure:

```yaml
canvas:
  size: 100            # square canvas side length
  north_rotation: 0    # degrees clockwise from canvas-up to true north

buildings:
  - name: home
    vertices:          # polygon as (x, y) coordinate pairs
      - [50.75, 33.75]
      - [80.00, 52.25]
      - [67.25, 72.50]
      - [70.75, 75.00]
      - [62.00, 89.00]
      - [54.75, 90.50]
      - [26.50, 72.75]
    casts_shadow: true
    style: home        # "home" | "neighbor" | "default"

  - name: neighbour_north
    vertices:
      - [4.75, 59.00]
      - [10.50, 49.75]
      - [6.75, 47.50]
      - [18.25, 29.25]
      - [22.00, 31.50]
      - [32.00, 15.25]
      - [54.00, 28.75]
      - [26.75, 72.75]
    casts_shadow: true
    style: neighbor

highlighted_regions:
  - name: dining_room
    vertices:
      - [70.75, 75.00]
      - [62.00, 89.00]
      - [58.75, 86.25]
      - [66.00, 72.00]
      - [80.00, 52.25]
      - [67.25, 72.50]
    color: '#b38c3a'   # any CSS color
```

Point `SUNCAST_GEOMETRY_FILE` to your file. See `geometry.example.yaml` in the
repository as a starting point.

---

## Building Properties

| Property       | Type              | Default     | Description                                       |
| -------------- | ----------------- | ----------- | ------------------------------------------------- |
| `name`         | string            | *required*  | Unique identifier for the building                |
| `vertices`     | list of `[x, y]`  | *required*  | Polygon vertices (minimum 3 points)               |
| `casts_shadow` | bool              | `true`      | Whether this building projects a shadow           |
| `style`        | string            | `"default"` | Rendering style: `home`, `neighbor`, or `default` |

### Building Styles

| Style      | Fill Color                   | Description                        |
| ---------- | ---------------------------- | ---------------------------------- |
| `home`     | `secondary_color` (`#b38c3a`) | Your home — stands out with accent |
| `neighbor` | `primary_color` (`#614c1f`)   | Adjacent buildings                 |
| `default`  | `primary_color` (`#614c1f`)   | Same as `neighbor`                 |

---

## North Rotation

The `north_rotation` field aligns the compass dial with your real-world orientation:

- **Value:** degrees clockwise from canvas-up to true north
- **0** = up is north (default)
- **90** = left is north
- **180** = down is north

!!! tip "Finding your north rotation"
    Open a satellite map, identify the angle between your buildings' vertical axis and
    true north, and set `north_rotation` to that value. Compare rendered shadows with
    reality at a known time to fine-tune.

---

## Highlighted Regions

Highlighted regions mark areas of interest (garden, terrace, patio) with custom colors
rendered at 50% opacity. They use the same vertex format as buildings:

```yaml
highlighted_regions:
  - name: terrace
    vertices:
      - [60.0, 70.0]
      - [75.0, 70.0]
      - [75.0, 85.0]
      - [60.0, 85.0]
    color: '#4a90d9'
```

---

## Auto-Scaling

suncast calls `fit_to_circle()` at startup to normalize all vertex coordinates so that
every building and highlight fits within the compass circle with 5% padding. This means:

- You can use **any coordinate scale** — millimeters, pixels, arbitrary units
- All shapes are uniformly scaled relative to the canvas center
- The compass ring always surrounds your buildings cleanly

No manual scaling is needed.

---

## SVG Import

As an alternative to writing YAML by hand, you can draw building footprints in an SVG
editor and import them directly.

### Workflow

1. Draw building footprints in **Inkscape** (or any SVG editor) using `<polygon>` or
   straight-line `<path>` elements
2. Name shapes via `id` attributes or Inkscape labels
3. Create a **sidecar YAML file** mapping shape IDs to roles:

    ```yaml title="geometry.sidecar.yaml"
    canvas:
      north_rotation: 0

    shape_roles:
      home:
        casts_shadow: true
        style: home
      neighbour_north:
        style: neighbor
      dining_room:
        highlighted: true
        color: '#b38c3a'
    ```

4. Point `SUNCAST_GEOMETRY_FILE` to the `.svg` file — suncast auto-detects the SVG
   format and looks for a sidecar file at `<filename>.sidecar.yaml`

Shapes not listed in `shape_roles` get default properties (`casts_shadow: true`,
`style: default`).

!!! info "SVG limitations"
    Only `<polygon>` elements and `<path>` elements with straight-line commands
    (M, L, H, V, Z) are supported. Curves (C, S, Q, A) are silently skipped.

---

## Convex Footprint Limitation

!!! warning "Convex footprints only"
    suncast uses silhouette-edge detection (min/max angle from the sun reference point)
    to determine which building edges cast shadows. This algorithm works correctly only
    for **convex polygons** — shapes where every interior angle is less than 180°.
    Simple rectangles, triangles, and regular polygons are fine.

    **Concave shapes** (L-shaped, U-shaped, courtyards) will produce distorted shadows
    because the silhouette detection identifies the wrong boundary edges.

<div class="geometry-comparison">
  <figure>
    <img src="../images/generated/convex-ok.svg" alt="Convex building - correct shadow" width="250">
    <figcaption>
      <strong>Convex footprint</strong>
      Convex rectangle - shadow projects correctly.
    </figcaption>
  </figure>
  <figure>
    <img src="../images/generated/concave-distorted.svg" alt="Concave building - distorted shadow" width="250">
    <figcaption>
      <strong>Concave footprint</strong>
      L-shaped building - shadow distortion from incorrect silhouette detection.
    </figcaption>
  </figure>
</div>

**Workaround:** Split concave buildings into multiple convex shapes. For example, model
an L-shaped building as two overlapping rectangles.

---

## Tips

- **Start simple** — a single rectangle is enough to see shadows
- Use `geometry.example.yaml` from the repository as a starting point
- Adjust `north_rotation` by comparing rendered shadows with reality at a known time
- Keep buildings convex — split complex shapes into overlapping rectangles
- See [ADR-003](adr/ADR-003-house-geometry-configuration.md) for the design rationale
  behind the geometry format
